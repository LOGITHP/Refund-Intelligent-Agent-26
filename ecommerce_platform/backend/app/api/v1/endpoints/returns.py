import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.crypto import redact_sensitive_data
from app.core.security import (
    compute_bridge_hmac,
    get_current_customer,
    get_current_merchant,
    get_current_service_actor,
    get_current_user,
    get_merchant_or_service_actor,
)
from app.core.timeline import RETURN_STEP_SEQUENCE, sync_timeline_status
from app.db.database import get_db
from app.db.models import (
    MerchantOrderAllocation,
    Order,
    OrderItem,
    PaymentLedgerEvent,
    ReturnRequest,
    ReturnStatus,
    User,
    UserRole,
    quantize_money,
)
from app.schemas.money import OptionalMoneyField
from app.schemas.order import ReturnCreate, ReturnDecisionUpdate, ReturnOut
from app.services.paypal_service import (
    PayPalAPIError,
    PayPalService,
    get_paypal_service,
    resolve_paypal_service_for_merchant,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def initial_refund_timeline():
    now_iso = datetime.now(timezone.utc).isoformat()
    return [
        {"step": "REQUESTED", "title": "Return Requested", "detail": "Return request submitted with defect/damage evidence.", "time": now_iso, "completed": True},
        {"step": "UNDER_REVIEW", "title": "Reviewing Evidence", "detail": "Seller support is evaluating the return claim and evidence.", "time": now_iso, "completed": True},
        {"step": "APPROVED", "title": "Return Approved", "detail": "Claim approved. Pickup courier scheduled.", "time": None, "completed": False},
        {"step": "PICKUP_SCHEDULED", "title": "Item Picked Up", "detail": "Courier picked up item from customer location.", "time": None, "completed": False},
        {"step": "REFUND_INITIATED", "title": "Refund Initiated", "detail": "Refund initiated to original payment method.", "time": None, "completed": False},
        {"step": "REFUNDED", "title": "Refund Completed", "detail": "Refund credited successfully to customer account.", "time": None, "completed": False},
    ]


def _relay_return_event_to_agent(
    return_req: ReturnRequest,
    order: Optional[Order],
    order_item: Optional[OrderItem],
    *,
    event_type: str = "RETURN_REQUESTED",
    approval_reference: Optional[str] = None,
) -> None:
    """Best-effort HMAC-signed bridge webhook notifying Refund Intelligence Platform of a return."""
    agent_url = (settings.AGENT_PLATFORM_URL or "").strip().rstrip("/")
    bridge_secret = (settings.BRIDGE_SHARED_SECRET or "").strip()
    if not agent_url or not bridge_secret:
        return

    status_value = (
        return_req.status.value
        if hasattr(return_req.status, "value")
        else str(return_req.status)
    )
    qty = int(order_item.quantity) if order_item is not None and order_item.quantity else 1
    payload = {
        "event_type": event_type,
        "shipkart_return_id": return_req.id,
        "shipkart_order_id": return_req.order_id,
        "shipkart_order_item_id": return_req.order_item_id,
        "shipkart_customer_id": return_req.user_id,
        "shipkart_merchant_id": return_req.merchant_id,
        "reason": return_req.reason,
        "comments": return_req.comments,
        "evidence_urls": list(return_req.evidence_urls or []),
        "quantity_requested": qty,
        "purchased_quantity": qty,
        "unit_price": (
            str(quantize_money(order_item.price))
            if order_item is not None and order_item.price is not None
            else None
        ),
        "refund_amount": str(quantize_money(return_req.refund_amount)),
        "refund_currency": return_req.refund_currency or (order.original_currency if order else "INR"),
        "refund_paypal_amount": (
            str(quantize_money(return_req.refund_paypal_amount))
            if return_req.refund_paypal_amount is not None
            else None
        ),
        "captured_amount": (
            str(quantize_money(order.paypal_amount))
            if order is not None and order.paypal_amount is not None
            else None
        ),
        "original_currency": (order.original_currency if order else None) or "INR",
        "paypal_currency": (order.paypal_currency if order else None) or "USD",
        "paypal_capture_id": order.paypal_capture_id if order else None,
        "paypal_order_id": order.paypal_order_id if order else None,
        "status": status_value,
        "refund_transaction_id": return_req.refund_transaction_id,
        "merchant_notes": return_req.merchant_notes,
        "approval_reference": approval_reference,
    }
    raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = compute_bridge_hmac(raw_body, bridge_secret)
    target = f"{agent_url}/api/v1/bridge/shipkart/return-event"

    try:
        httpx.post(
            target,
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Bridge-Signature": signature,
            },
            timeout=2.0,
        )
    except Exception as exc:
        logger.warning(
            "Best-effort agent bridge relay failed for return %s (%s): %s",
            return_req.return_number,
            target,
            exc,
        )


def _execute_paypal_refund_if_applicable(
    db: Session,
    ret: ReturnRequest,
    paypal_svc: PayPalService,
    note_to_payer: str,
    request_id_override: Optional[str] = None,
) -> bool:
    """Executes real PayPal capture refund when order has a real PayPal capture and creds are configured."""
    order = ret.order
    if not order or not order.paypal_capture_id:
        return False
    if order.paypal_capture_id.startswith("CAP-SIM-"):
        return False
    if ret.status == ReturnStatus.REFUNDED and ret.refund_transaction_id:
        return True

    target_merchant_id = order.merchant_id if order.merchant_id is not None else ret.merchant_id
    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, target_merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(
            status_code=503,
            detail="Merchant PayPal credentials are not configured for refund",
        )

    refund_usd = quantize_money(
        ret.refund_paypal_amount
        if ret.refund_paypal_amount is not None
        else (order.paypal_amount or Decimal("0.00"))
    )
    if refund_usd <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="Refundable PayPal USD amount must be greater than zero")

    currency = ret.refund_currency or order.paypal_currency or "USD"
    req_id = (request_id_override or f"refund-ret-{ret.id}").strip()
    try:
        refund_resp = merchant_svc.refund_capture(
            capture_id=order.paypal_capture_id,
            request_id=req_id,
            amount=refund_usd,
            currency_code=currency,
            note_to_payer=note_to_payer,
        )
    except PayPalAPIError as exc:
        db.add(
            PaymentLedgerEvent(
                order_id=order.id,
                return_request_id=ret.id,
                merchant_id=ret.merchant_id,
                event_type="REFUND_FAILED",
                paypal_order_id=order.paypal_order_id,
                paypal_capture_id=order.paypal_capture_id,
                idempotency_key=req_id,
                amount=refund_usd,
                currency=currency,
                status_snapshot="REFUND_FAILED",
                redacted_payload=redact_sensitive_data({"error": str(exc), "details": exc.details}),
            )
        )
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    paypal_refund_id = refund_resp.get("id") or f"PP-REF-{uuid.uuid4().hex[:8].upper()}"
    ret.refund_transaction_id = paypal_refund_id

    alloc_q = db.query(MerchantOrderAllocation).filter(
        MerchantOrderAllocation.order_id == order.id
    )
    if ret.merchant_id is None:
        alloc_q = alloc_q.filter(MerchantOrderAllocation.merchant_id.is_(None))
    else:
        alloc_q = alloc_q.filter(MerchantOrderAllocation.merchant_id == ret.merchant_id)

    alloc = alloc_q.first()
    if alloc:
        alloc.refunded_usd = quantize_money(Decimal(alloc.refunded_usd or 0) + refund_usd)
        if alloc.refunded_usd >= quantize_money(alloc.gross_usd):
            alloc.settlement_status = "REFUNDED"
        else:
            alloc.settlement_status = "PARTIALLY_REFUNDED"

    all_allocs = db.query(MerchantOrderAllocation).filter(
        MerchantOrderAllocation.order_id == order.id
    ).all()
    total_refunded_usd = sum(
        (quantize_money(a.refunded_usd or 0) for a in all_allocs),
        Decimal("0.00"),
    )
    captured_ceiling = quantize_money(order.paypal_amount or 0)
    if captured_ceiling > Decimal("0.00") and total_refunded_usd >= captured_ceiling:
        order.payment_status = "REFUNDED"
    else:
        order.payment_status = "PARTIALLY_REFUNDED"

    db.add(
        PaymentLedgerEvent(
            order_id=order.id,
            return_request_id=ret.id,
            merchant_id=ret.merchant_id,
            event_type="REFUND_COMPLETED",
            paypal_order_id=order.paypal_order_id,
            paypal_capture_id=order.paypal_capture_id,
            paypal_refund_id=paypal_refund_id,
            idempotency_key=req_id,
            amount=refund_usd,
            currency=currency,
            status_snapshot=refund_resp.get("status", "COMPLETED"),
            redacted_payload=redact_sensitive_data(refund_resp),
        )
    )
    return True


@router.post("/", response_model=ReturnOut, status_code=status.HTTP_201_CREATED)
def submit_return_request(
    return_in: ReturnCreate,
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == return_in.order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_item = db.query(OrderItem).filter(
        OrderItem.id == return_in.order_item_id,
        OrderItem.order_id == order.id,
    ).first()
    if not order_item:
        raise HTTPException(status_code=404, detail="Order item not found")

    existing = db.query(ReturnRequest).filter(
        ReturnRequest.order_item_id == order_item.id,
        ReturnRequest.status.notin_([ReturnStatus.REJECTED]),
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="A return request is already active for this item")

    random_suffix = uuid.uuid4().hex[:6].upper()
    return_number = f"RET-SK-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random_suffix}"
    refund_amount = quantize_money(quantize_money(order_item.price) * int(order_item.quantity))

    refund_currency = order.original_currency or "INR"
    refund_paypal_amount = None
    if order.paypal_amount is not None and (
        order.paypal_capture_id or order.payment_method == "PAYPAL_SANDBOX"
    ):
        refund_currency = order.paypal_currency or "USD"
        order_total_inr = quantize_money(order.total_amount)
        order_total_usd = quantize_money(order.paypal_amount)
        if order_total_inr > Decimal("0.00"):
            proportional_usd = quantize_money((refund_amount / order_total_inr) * order_total_usd)
        else:
            proportional_usd = order_total_usd

        prior_returns = db.query(ReturnRequest).filter(
            ReturnRequest.order_id == order.id,
            ReturnRequest.status.notin_([ReturnStatus.REJECTED]),
        ).all()
        already_allocated_usd = sum(
            (quantize_money(r.refund_paypal_amount or 0) for r in prior_returns),
            Decimal("0.00"),
        )
        remaining_usd = max(Decimal("0.00"), quantize_money(order_total_usd - already_allocated_usd))
        refund_paypal_amount = min(proportional_usd, remaining_usd)

    return_req = ReturnRequest(
        return_number=return_number,
        order_id=order.id,
        order_item_id=order_item.id,
        user_id=current_user.id,
        merchant_id=order_item.merchant_id,
        product_id=order_item.product_id,
        reason=return_in.reason,
        comments=return_in.comments,
        evidence_urls=return_in.evidence_urls,
        refund_amount=refund_amount,
        refund_currency=refund_currency,
        refund_paypal_amount=refund_paypal_amount,
        status=ReturnStatus.REQUESTED,
        tracking_history=initial_refund_timeline(),
    )
    db.add(return_req)
    db.commit()
    db.refresh(return_req)

    _relay_return_event_to_agent(return_req, order, order_item)
    return return_req


def _reconcile_return(ret: ReturnRequest, db: Session) -> ReturnRequest:
    synced = sync_timeline_status(ret.tracking_history, ret.status.value, RETURN_STEP_SEQUENCE)
    if synced != (ret.tracking_history or []):
        ret.tracking_history = synced
        flag_modified(ret, "tracking_history")
        db.commit()
        db.refresh(ret)
    return ret


@router.get("/my", response_model=List[ReturnOut])
def get_my_returns(
    current_user: User = Depends(get_current_customer),
    db: Session = Depends(get_db),
):
    items = (
        db.query(ReturnRequest)
        .filter(ReturnRequest.user_id == current_user.id)
        .order_by(ReturnRequest.id.desc())
        .all()
    )
    return [_reconcile_return(r, db) for r in items]


@router.get("/merchant", response_model=List[ReturnOut])
def get_merchant_returns(
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    items = (
        db.query(ReturnRequest)
        .filter(or_(ReturnRequest.merchant_id == current_merchant.id, ReturnRequest.merchant_id.is_(None)))
        .order_by(ReturnRequest.id.desc())
        .all()
    )
    return [_reconcile_return(r, db) for r in items]


@router.get("/bridge/pending", response_model=List[ReturnOut])
def list_pending_returns_for_bridge(
    merchant_id: Optional[int] = Query(None),
    _service_claims: Dict[str, Any] = Depends(get_current_service_actor),
    db: Session = Depends(get_db),
):
    """Service-authenticated queue of active/pending return claims for Refund Intelligence Platform."""
    query = db.query(ReturnRequest).filter(
        ReturnRequest.status.notin_([ReturnStatus.REFUNDED, ReturnStatus.REJECTED])
    )
    if merchant_id is not None:
        query = query.filter(ReturnRequest.merchant_id == merchant_id)

    items = query.order_by(ReturnRequest.id.desc()).all()
    return [_reconcile_return(r, db) for r in items]


@router.get("/{return_id}/paypal-refund-status")
def get_return_paypal_refund_status(
    return_id: int,
    _service_claims: Dict[str, Any] = Depends(get_current_service_actor),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    """Service-authenticated live PayPal refund status check using the owning merchant's credentials."""
    ret = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found")

    refund_txn_id = (ret.refund_transaction_id or "").strip()
    if not refund_txn_id or refund_txn_id.startswith("SK-REF-"):
        return {
            "return_id": ret.id,
            "return_number": ret.return_number,
            "merchant_id": ret.merchant_id,
            "refund_transaction_id": ret.refund_transaction_id,
            "paypal_refund_status": None,
            "is_real_paypal_refund": False,
            "paypal_payload": {},
        }

    target_merchant_id = (
        ret.order.merchant_id
        if (ret.order and ret.order.merchant_id is not None)
        else ret.merchant_id
    )
    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, target_merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(status_code=503, detail="Merchant PayPal credentials are not configured")

    try:
        pp_refund = merchant_svc.get_refund(refund_txn_id)
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    redacted = redact_sensitive_data(pp_refund)
    return {
        "return_id": ret.id,
        "return_number": ret.return_number,
        "merchant_id": target_merchant_id,
        "refund_transaction_id": refund_txn_id,
        "paypal_refund_status": redacted.get("status"),
        "is_real_paypal_refund": True,
        "amount": redacted.get("amount"),
        "paypal_payload": redacted,
    }


@router.get("/{return_id}", response_model=ReturnOut)
def get_return_by_id(
    return_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ret = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found")

    if current_user.role == UserRole.CUSTOMER and ret.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    if current_user.role == UserRole.MERCHANT and ret.merchant_id is not None and ret.merchant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return _reconcile_return(ret, db)


@router.patch("/{return_id}/decision", response_model=ReturnOut)
def decide_return(
    return_id: int,
    decision_in: ReturnDecisionUpdate,
    current_merchant: User = Depends(get_current_merchant),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    ret = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found")
    if ret.merchant_id is not None and ret.merchant_id != current_merchant.id:
        raise HTTPException(status_code=403, detail="Not authorized to decide return for another merchant")

    executed_paypal = False
    if decision_in.status == ReturnStatus.REFUNDED:
        executed_paypal = _execute_paypal_refund_if_applicable(
            db,
            ret,
            paypal_svc,
            note_to_payer=decision_in.merchant_notes or f"Merchant refund for {ret.return_number}",
        )

    ret.status = decision_in.status
    if decision_in.merchant_notes:
        ret.merchant_notes = decision_in.merchant_notes
    if not executed_paypal and decision_in.refund_transaction_id:
        ret.refund_transaction_id = decision_in.refund_transaction_id

    now_iso = datetime.now(timezone.utc).isoformat()
    if decision_in.status == ReturnStatus.REJECTED:
        timeline = copy.deepcopy(ret.tracking_history or [])
        timeline.append(
            {
                "step": "REJECTED",
                "title": "Return Rejected",
                "detail": f"Merchant Reason: {decision_in.merchant_notes or 'Did not satisfy return policy'}",
                "time": now_iso,
                "completed": True,
            }
        )
        ret.tracking_history = timeline
    else:
        ret.tracking_history = sync_timeline_status(
            ret.tracking_history,
            decision_in.status.value,
            RETURN_STEP_SEQUENCE,
            now_iso=now_iso,
        )

    flag_modified(ret, "tracking_history")
    db.commit()
    db.refresh(ret)
    order_item = db.query(OrderItem).filter(OrderItem.id == ret.order_item_id).first()
    _relay_return_event_to_agent(
        ret,
        ret.order,
        order_item,
        event_type="RETURN_STATUS_UPDATED",
    )
    return ret


class AgentDecisionPayload(BaseModel):
    action: str  # APPROVE, REJECT, ESCALATE
    confidence_score: float
    reasoning: str
    execute_paypal_refund: bool = False
    paypal_capture_id: str = ""


class ExecuteApprovedRefundPayload(BaseModel):
    approval_reference: str
    merchant_notes: Optional[str] = None
    refund_amount_usd: OptionalMoneyField = None
    idempotency_key: Optional[str] = None


@router.post("/{return_id}/agent-decision", response_model=ReturnOut)
def record_agent_decision(
    return_id: int,
    payload: AgentDecisionPayload,
    service_claims: Dict[str, Any] = Depends(get_current_service_actor),
    db: Session = Depends(get_db),
):
    """Service-authenticated agent recommendation endpoint enforcing REF-001 mandatory merchant approval."""
    ret = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found")

    ret.agent_risk_score = payload.confidence_score
    reasoning_note = payload.reasoning
    if payload.execute_paypal_refund:
        reasoning_note = (
            f"{payload.reasoning} [REF-001 Guard: Autonomous refund execution blocked; "
            "explicit merchant approval via /execute-approved-refund is required.]"
        )
    ret.agent_reasoning = reasoning_note

    # REF-001: Agent decisions NEVER mark REFUNDED or execute payouts directly.
    if ret.status == ReturnStatus.REQUESTED:
        ret.status = ReturnStatus.UNDER_REVIEW

    now_iso = datetime.now(timezone.utc).isoformat()
    timeline = sync_timeline_status(
        ret.tracking_history or initial_refund_timeline(),
        ret.status.value,
        RETURN_STEP_SEQUENCE,
        now_iso=now_iso,
    )

    action_upper = (payload.action or "").strip().upper()
    if action_upper == "APPROVE":
        step = "AGENT_RECOMMENDATION"
        title = "Agent Recommended Approval (Awaiting Merchant)"
    elif action_upper == "REJECT":
        step = "AGENT_REJECT_RECOMMENDED"
        title = "Agent Recommended Rejection (Awaiting Merchant)"
    else:
        step = "AGENT_ESCALATED"
        title = "Escalated to Merchant Review"

    detail = (
        f"Confidence: {payload.confidence_score * 100:.1f}%. "
        f"Actor: {service_claims.get('sub')}. Reasoning: {reasoning_note}"
    )
    last_entry = timeline[-1] if timeline else None
    if not (
        last_entry
        and last_entry.get("step") == step
        and last_entry.get("detail") == detail
    ):
        timeline.append(
            {
                "step": step,
                "title": title,
                "detail": detail,
                "time": now_iso,
                "completed": True,
            }
        )

    ret.tracking_history = timeline
    flag_modified(ret, "tracking_history")
    db.commit()
    db.refresh(ret)
    return ret


@router.post("/{return_id}/execute-approved-refund", response_model=ReturnOut)
def execute_approved_refund(
    return_id: int,
    payload: ExecuteApprovedRefundPayload,
    actor: Dict[str, Any] = Depends(get_merchant_or_service_actor),
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    """Executes final refund only after explicit merchant approval reference (Merchant or Service JWT)."""
    approval_ref = (payload.approval_reference or "").strip()
    if not approval_ref:
        raise HTTPException(status_code=400, detail="approval_reference is required")

    ret = db.query(ReturnRequest).filter(ReturnRequest.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Return request not found")

    if actor["actor_type"] == "merchant":
        merchant_user: User = actor["user"]
        if ret.merchant_id is not None and ret.merchant_id != merchant_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to execute refund for another merchant",
            )

    if ret.status == ReturnStatus.REFUNDED and ret.refund_transaction_id:
        return ret

    if payload.refund_amount_usd is not None:
        if payload.refund_amount_usd <= Decimal("0.00"):
            raise HTTPException(status_code=400, detail="refund_amount_usd must be positive")
        order = ret.order
        if order and order.paypal_amount is not None:
            prior_refunded = sum(
                (
                    quantize_money(a.refunded_usd or 0)
                    for a in db.query(MerchantOrderAllocation)
                    .filter(MerchantOrderAllocation.order_id == order.id)
                    .all()
                ),
                Decimal("0.00"),
            )
            remaining_ceiling = max(
                Decimal("0.00"),
                quantize_money(quantize_money(order.paypal_amount) - prior_refunded),
            )
            if payload.refund_amount_usd > remaining_ceiling:
                raise HTTPException(
                    status_code=400,
                    detail="Requested refund_amount_usd exceeds remaining captured PayPal balance",
                )
        ret.refund_paypal_amount = payload.refund_amount_usd

    note_text = payload.merchant_notes or f"Approved refund ({approval_ref})"
    executed_paypal = _execute_paypal_refund_if_applicable(
        db,
        ret,
        paypal_svc,
        note_to_payer=note_text,
        request_id_override=payload.idempotency_key,
    )

    ret.status = ReturnStatus.REFUNDED
    if payload.merchant_notes:
        ret.merchant_notes = payload.merchant_notes
    if not executed_paypal and not ret.refund_transaction_id:
        ret.refund_transaction_id = f"SK-REF-{uuid.uuid4().hex[:8].upper()}"

    now_iso = datetime.now(timezone.utc).isoformat()
    timeline = sync_timeline_status(
        ret.tracking_history or initial_refund_timeline(),
        ReturnStatus.REFUNDED.value,
        RETURN_STEP_SEQUENCE,
        now_iso=now_iso,
    )
    timeline.append(
        {
            "step": "APPROVED_REFUND_EXECUTED",
            "title": "Approved Refund Executed",
            "detail": f"Approval Ref: {approval_ref}. Actor: {actor['actor_type']}. TXN: {ret.refund_transaction_id}",
            "time": now_iso,
            "completed": True,
        }
    )
    ret.tracking_history = timeline
    flag_modified(ret, "tracking_history")
    db.commit()
    db.refresh(ret)
    order_item = db.query(OrderItem).filter(OrderItem.id == ret.order_item_id).first()
    _relay_return_event_to_agent(
        ret,
        ret.order,
        order_item,
        event_type="RETURN_STATUS_UPDATED",
        approval_reference=approval_ref,
    )
    return ret
