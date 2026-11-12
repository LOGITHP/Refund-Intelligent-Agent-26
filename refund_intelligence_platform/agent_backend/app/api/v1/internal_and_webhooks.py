"""PayPal refund execution, webhooks, internal schedulers, and Shipkart HMAC bridge routes."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_merchant_case_access,
    extract_int_claim,
    get_actor_shipkart_id,
    get_actor_type_label,
    get_paypal_client,
    resolve_refund_case,
    serialize_eta,
    serialize_transaction,
)
from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data
from app.core.security import require_roles, verify_bridge_hmac
from app.db.base import utcnow
from app.db.models import (
    AuditLog,
    RefundCase,
    RefundFollowup,
    RefundTimelineEvent,
    RefundTransaction,
    ReturnCase,
)
from app.db.session import get_db
from app.integrations.paypal_client import PayPalAPIError, PayPalClient
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService, ComplianceViolationError
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.reconciliation_service import ReconciliationService
from app.services.refund_service import RefundService
from app.services.return_service import ReturnService
from app.services.timeline_service import TimelineService

logger = logging.getLogger(__name__)
router = APIRouter()

_PAY_ROLES = require_roles("merchant", "operations", "admin", "service")
_INTERNAL_ROLES = require_roles("operations", "admin", "service")
_TERMINAL_CASE_STATUSES = frozenset(
    {
        "CONFIRMED_POSTED",
        "ISSUER_POSTED",
        "REJECTED",
        "REJECTED_BY_MERCHANT",
        "RETURN_REJECTED",
        "CANCELLED",
        "CLOSED_REJECTED",
        "REFUND_FAILED",
    }
)


class ExecutePayPalRefundRequest(BaseModel):
    refund_case_id: str
    idempotency_key: str = Field(..., min_length=1, max_length=150)
    paypal_capture_id: str | None = None


class EtaRecalculateRequest(BaseModel):
    refund_case_id: str | None = None


class EtaCalculateRequest(BaseModel):
    refund_case_id: str


class DelayDetectRequest(BaseModel):
    refund_case_id: str | None = None


class ScheduleFollowupRequest(BaseModel):
    refund_case_id: str
    target_type: str = "ISSUER"
    target_reference: str | None = None
    action_type: str = "POLL_REFUND_STATUS"
    delay_hours: int = Field(default=4, ge=0, le=720)


class BridgeReturnItem(BaseModel):
    shipkart_order_item_id: int | None = None
    order_item_id: uuid.UUID | None = None
    quantity_requested: int = Field(..., gt=0)
    purchased_quantity: int = Field(..., gt=0)
    unit_price: Decimal | None = None
    refund_amount_requested: Decimal | None = None
    condition_reported: str = "UNKNOWN"


class BridgeReturnEventPayload(BaseModel):
    event_type: str = "RETURN_REQUESTED"
    shipkart_return_id: int
    shipkart_order_id: int
    shipkart_customer_id: int
    shipkart_merchant_id: int | None = None
    reason_code: str = Field(..., min_length=2, max_length=50)
    customer_description: str = ""
    case_type: str = "RETURN_REFUND"
    requested_amount: Decimal | None = None
    captured_amount: Decimal | None = None
    original_amount: Decimal | None = None
    currency: str = "USD"
    original_currency: str = "INR"
    paypal_currency: str = "USD"
    paypal_order_id: str | None = None
    paypal_capture_id: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    status: str | None = None
    refund_transaction_id: str | None = None
    merchant_notes: str | None = None
    approval_reference: str | None = None
    items: list[BridgeReturnItem] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize_shipkart_flat_payload(cls, raw: Any) -> Any:
        """Accept both nested items payloads and Shipkart's flat HMAC relay payload."""
        if not isinstance(raw, dict):
            return raw
        data = dict(raw)

        # Normalize reason_code (<= 50 chars) & customer_description from Shipkart `reason`/`comments`
        raw_reason = str(data.get("reason_code") or data.get("reason") or "").strip()
        if not data.get("reason_code"):
            slug = re.sub(r"[^A-Z0-9]+", "_", raw_reason.upper()).strip("_")[:50]
            data["reason_code"] = slug if len(slug) >= 2 else "RETURN_REQUEST"
        else:
            clean_rc = str(data["reason_code"]).strip()[:50]
            data["reason_code"] = clean_rc if len(clean_rc) >= 2 else "RETURN_REQUEST"

        if not data.get("customer_description"):
            reason_text = str(data.get("reason") or "").strip()
            comments_text = str(data.get("comments") or "").strip()
            if reason_text and comments_text:
                data["customer_description"] = f"{reason_text}: {comments_text}"
            else:
                data["customer_description"] = reason_text or comments_text or ""

        # Separate INR catalog display vs PayPal USD settlement amounts cleanly
        refund_paypal = data.get("refund_paypal_amount")
        refund_raw = data.get("refund_amount")
        refund_curr = str(data.get("refund_currency") or "").strip().upper()

        if data.get("original_amount") is None and refund_raw is not None:
            data["original_amount"] = refund_raw

        if data.get("requested_amount") is None:
            if refund_paypal is not None and (not refund_curr or refund_curr == "USD"):
                data["requested_amount"] = refund_paypal
                data.setdefault("currency", "USD")
                data.setdefault("paypal_currency", "USD")
            elif refund_raw is not None:
                data["requested_amount"] = refund_raw
                resolved_curr = refund_curr or str(data.get("original_currency") or "INR").upper()
                data["currency"] = resolved_curr
                data["original_currency"] = str(data.get("original_currency") or resolved_curr).upper()
                has_paypal_refs = bool(
                    data.get("paypal_capture_id")
                    or data.get("paypal_order_id")
                    or data.get("captured_amount") is not None
                )
                if not has_paypal_refs:
                    data["paypal_currency"] = resolved_curr
        elif "refund_currency" in data and "currency" not in data:
            data["currency"] = refund_curr or "USD"

        if not data.get("items"):
            qty_req = max(1, int(data.get("quantity_requested") or 1))
            qty_purch = max(qty_req, int(data.get("purchased_quantity") or qty_req))
            req_amt = data.get("requested_amount")
            data["items"] = [
                {
                    "shipkart_order_item_id": data.get("shipkart_order_item_id"),
                    "order_item_id": data.get("order_item_id"),
                    "quantity_requested": qty_req,
                    "purchased_quantity": qty_purch,
                    "unit_price": data.get("unit_price"),
                    "refund_amount_requested": req_amt if req_amt is not None else "0.00",
                    "condition_reported": data.get("condition_reported") or "UNKNOWN",
                }
            ]

        return data


# ---------------------------------------------------------------------------
# PayPal Execution (REF-001..REF-004 + AUTH-001)
# ---------------------------------------------------------------------------
@router.post("/payments/paypal/refund", tags=["Payments"])
def execute_paypal_refund(
    payload: ExecutePayPalRefundRequest,
    actor: dict[str, Any] = Depends(_PAY_ROLES),
    db: Session = Depends(get_db),
    paypal_client: PayPalClient = Depends(get_paypal_client),
) -> dict[str, Any]:
    """Execute an idempotent PayPal refund strictly guarded by Merchant REF-001 approval."""
    refund_case = resolve_refund_case(db, payload.refund_case_id)
    assert_merchant_case_access(db, refund_case, actor)

    actor_type = get_actor_type_label(actor)
    shipkart_actor_id = get_actor_shipkart_id(actor)
    role = str(actor.get("role") or "").strip().lower()
    sk_merchant = extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")

    if payload.paypal_capture_id is not None:
        try:
            ComplianceService.assert_capture_verified(
                db,
                refund_case=refund_case,
                paypal_capture_id=payload.paypal_capture_id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
            )
        except ComplianceViolationError:
            db.commit()
            raise

    try:
        tx = RefundService.execute_approved_refund(
            db,
            refund_case.id,
            idempotency_key=payload.idempotency_key,
            paypal_client=paypal_client,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
            actor_shipkart_merchant_id=(sk_merchant if role == "merchant" else None),
        )
    except ComplianceViolationError:
        db.commit()
        raise

    return serialize_transaction(tx)


# ---------------------------------------------------------------------------
# PayPal Webhooks (Signature Verified + PAY-002 Idempotent Reconciliation)
# ---------------------------------------------------------------------------
@router.post("/webhooks/paypal", tags=["Webhooks"])
async def receive_paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
    paypal_client: PayPalClient = Depends(get_paypal_client),
) -> dict[str, Any]:
    """Verify PayPal webhook cryptographic signature and process event idempotently."""
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook payload must be a JSON object",
        )

    env_name = (settings.ENVIRONMENT or "").strip().lower()
    if paypal_client._webhook_id.strip() or env_name not in {"development", "dev", "local", "test"}:
        try:
            verified = paypal_client.verify_webhook_signature(dict(request.headers), payload)
        except PayPalAPIError:
            raise
        if not verified:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="PayPal webhook signature verification failed",
            )

    provider_event_id = str(payload.get("id") or payload.get("event_id") or "").strip()
    event_type = str(payload.get("event_type") or "").strip()
    if not provider_event_id or not event_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PayPal webhook payload must include 'id' and 'event_type'",
        )

    result = ReconciliationService().process_paypal_webhook(
        db,
        provider_event_id=provider_event_id,
        event_type=event_type,
        payload=redact_sensitive_data(payload),
    )
    db.commit()
    return result


# ---------------------------------------------------------------------------
# Internal Deterministic Operations & Scheduler Trigger Endpoints
# ---------------------------------------------------------------------------
@router.post("/internal/eta/recalculate", tags=["Internal"])
def internal_recalculate_eta(
    payload: EtaRecalculateRequest | None = Body(default=None),
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Recalculate and persist deterministic ETA snapshots for one or all active RefundCases."""
    eta_svc = ETAService()
    if payload and payload.refund_case_id:
        rc = resolve_refund_case(db, payload.refund_case_id)
        snap = eta_svc.compute_and_persist_eta(db, rc.id)
        db.commit()
        return {
            "status": "ok",
            "recalculated_count": 1,
            "estimates": [serialize_eta(snap)],
        }

    cases = list(
        db.scalars(
            select(RefundCase).where(RefundCase.status.notin_(list(_TERMINAL_CASE_STATUSES)))
        ).all()
    )
    estimates: list[dict[str, Any]] = []
    for rc in cases:
        snap = eta_svc.compute_and_persist_eta(db, rc.id)
        estimates.append(serialize_eta(snap))
    db.commit()
    return {
        "status": "ok",
        "recalculated_count": len(estimates),
        "estimates": estimates,
    }


@router.post("/internal/eta/calculate", tags=["Internal"])
def internal_calculate_single_eta(
    payload: EtaCalculateRequest,
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Calculate and persist a deterministic ETA snapshot for a single RefundCase."""
    rc = resolve_refund_case(db, payload.refund_case_id)
    snap = ETAService().compute_and_persist_eta(db, rc.id)
    db.commit()
    return serialize_eta(snap)


@router.post("/internal/delays/detect", tags=["Internal"])
def internal_detect_delays(
    payload: DelayDetectRequest | None = Body(default=None),
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Evaluate DELAY-001..DELAY-006 SLA rules deterministically across target/active cases."""
    now = utcnow()
    delay_svc = DelayService()
    timeline_svc = TimelineService()

    if payload and payload.refund_case_id:
        cases = [resolve_refund_case(db, payload.refund_case_id)]
    else:
        cases = list(
            db.scalars(
                select(RefundCase).where(RefundCase.status.notin_(list(_TERMINAL_CASE_STATUSES)))
            ).all()
        )

    overdue_cases = 0
    alerts: list[dict[str, Any]] = []
    for rc in cases:
        report = delay_svc.evaluate_delays(db, rc.id, as_of=now)
        delays = list(report.get("delays") or [])
        if delays:
            overdue_cases += 1
            for delay in delays:
                rule_code = str(delay.get("rule_code") or "DELAY")
                timeline_svc.record_event(
                    db,
                    refund_case_id=rc.id,
                    return_case_id=rc.return_case_id,
                    event_type=f"SLA_BREACH_{rule_code}",
                    source_type="DELAY_MONITOR",
                    source_reference=f"{rc.id}:{rule_code}",
                    description=str(delay.get("description") or f"Delay detected ({rule_code})."),
                    occurred_at=now,
                    event_data=delay,
                    verified=True,
                )
                alerts.append({"refund_case_id": str(rc.id), **delay})

    db.commit()
    return {
        "status": "ok",
        "evaluated": len(cases),
        "overdue_cases": overdue_cases,
        "alerts": alerts,
    }


@router.post("/internal/reconciliation/run", tags=["Internal"])
def internal_run_reconciliation(
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
    paypal_client: PayPalClient = Depends(get_paypal_client),
) -> dict[str, Any]:
    """Poll PayPal API for pending RefundTransaction records and reconcile state transitions."""
    reconciler = ReconciliationService()
    pending_txs = list(
        db.scalars(
            select(RefundTransaction)
            .where(RefundTransaction.status == "PENDING")
            .order_by(RefundTransaction.created_at.asc())
        ).all()
    )
    reconciled_count = 0
    for tx in pending_txs:
        before_status = tx.status
        reconciler.reconcile_pending_refund_transaction(db, tx, paypal_client)
        if tx.status != before_status:
            reconciled_count += 1
    db.commit()
    return {
        "status": "ok",
        "checked": len(pending_txs),
        "reconciled": reconciled_count,
    }


@router.post("/internal/followups/schedule", tags=["Internal"], status_code=status.HTTP_201_CREATED)
def internal_schedule_followup(
    payload: ScheduleFollowupRequest,
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Schedule a deterministic automated follow-up poll for a RefundCase."""
    rc = resolve_refund_case(db, payload.refund_case_id)
    now = utcnow()
    followup = RefundFollowup(
        id=uuid.uuid4(),
        refund_case_id=rc.id,
        target_type=payload.target_type.strip().upper(),
        target_reference=payload.target_reference,
        scheduled_at=now + timedelta(hours=payload.delay_hours),
        status="SCHEDULED",
        action_type=payload.action_type.strip().upper(),
        attempt_count=0,
        created_at=now,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return {
        "id": str(followup.id),
        "refund_case_id": str(followup.refund_case_id),
        "target_type": followup.target_type,
        "action_type": followup.action_type,
        "status": followup.status,
        "scheduled_at": followup.scheduled_at.isoformat(),
    }


@router.post("/internal/followups/run", tags=["Internal"])
def internal_run_due_followups(
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute scheduled RefundFollowup jobs whose scheduled_at <= now()."""
    now = utcnow()
    due_followups = list(
        db.scalars(
            select(RefundFollowup)
            .where(
                RefundFollowup.status == "SCHEDULED",
                RefundFollowup.scheduled_at <= now,
            )
            .order_by(RefundFollowup.scheduled_at.asc())
        ).all()
    )

    delay_svc = DelayService()
    eta_svc = ETAService()
    executed_count = 0
    rescheduled_count = 0

    for followup in due_followups:
        rc = db.get(RefundCase, followup.refund_case_id)
        followup.attempt_count = int(followup.attempt_count or 0) + 1
        followup.last_attempt_at = now

        if rc is None or (rc.status or "").upper() in _TERMINAL_CASE_STATUSES:
            followup.status = "EXECUTED"
            executed_count += 1
            continue

        report = delay_svc.evaluate_delays(db, rc.id, as_of=now)
        eta_svc.compute_and_persist_eta(db, rc.id, estimated_from=now)

        if not report.get("delays") or followup.attempt_count >= 3:
            followup.status = "EXECUTED"
            executed_count += 1
        else:
            followup.status = "SCHEDULED"
            followup.scheduled_at = now + timedelta(hours=4)
            rescheduled_count += 1

    db.commit()
    return {
        "status": "ok",
        "processed": len(due_followups),
        "executed": executed_count,
        "rescheduled": rescheduled_count,
    }


@router.get("/internal/audit/events", tags=["Internal"])
def internal_audit_events(
    resource_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: dict[str, Any] = Depends(_INTERNAL_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Internal audit events query returning redacted append-only records."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if resource_type and resource_type.strip():
        stmt = stmt.where(AuditLog.resource_type == resource_type.strip())
    if action and action.strip():
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))

    rows = list(db.scalars(stmt).all())
    items = [
        {
            "id": str(row.id),
            "actor_type": row.actor_type,
            "shipkart_actor_id": row.shipkart_actor_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id),
            "before_state": redact_sensitive_data(row.before_state),
            "after_state": redact_sensitive_data(row.after_state),
            "created_at": row.created_at.isoformat() if isinstance(row.created_at, datetime) else str(row.created_at),
        }
        for row in rows
    ]
    return {"events": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Shipkart HMAC Signed Bridge Event Ingestion
# ---------------------------------------------------------------------------
@router.post("/bridge/shipkart/return-event", tags=["Shipkart Bridge"])
def ingest_shipkart_return_event(
    raw_body: bytes = Depends(verify_bridge_hmac),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Ingest HMAC-SHA256 signed Shipkart return event idempotently on shipkart_return_id."""
    try:
        payload = BridgeReturnEventPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(exc.json()),
        ) from exc

    existing_return = db.scalar(
        select(ReturnCase).where(ReturnCase.shipkart_return_id == payload.shipkart_return_id)
    )
    if existing_return is not None:
        existing_refund = db.scalar(
            select(RefundCase)
            .where(RefundCase.return_case_id == existing_return.id)
            .order_by(RefundCase.opened_at.desc())
        )
        updated = False
        event_upper = (payload.event_type or "").strip().upper()
        incoming_status = (payload.status or "").strip().upper()

        if existing_refund is not None and (event_upper == "RETURN_STATUS_UPDATED" or incoming_status):
            now = utcnow()
            return_status_map = {
                "APPROVED": "RETURN_APPROVED",
                "PICKUP_SCHEDULED": "PICKUP_SCHEDULED",
                "REJECTED": "RETURN_REJECTED",
            }
            if incoming_status in return_status_map:
                existing_return.status = return_status_map[incoming_status]
                existing_return.updated_at = now
                if incoming_status == "APPROVED" and existing_return.approved_at is None:
                    existing_return.approved_at = now
                elif incoming_status == "REJECTED" and existing_return.closed_at is None:
                    existing_return.closed_at = now

            if incoming_status == "REJECTED" and existing_refund.status not in _TERMINAL_CASE_STATUSES:
                existing_refund.status = "REJECTED_BY_MERCHANT"
                existing_refund.resolved_at = now
                existing_refund.resolution_summary = (payload.merchant_notes or "").strip() or existing_refund.resolution_summary
            elif incoming_status == "APPROVED" and existing_refund.status == "INVESTIGATING":
                existing_refund.status = "MERCHANT_APPROVAL_PENDING"
            elif incoming_status == "REFUND_INITIATED" and existing_refund.status not in _TERMINAL_CASE_STATUSES:
                existing_refund.status = "REFUND_SUBMITTED"
            elif incoming_status == "REFUNDED" and existing_refund.status not in _TERMINAL_CASE_STATUSES:
                existing_refund.status = "PAYPAL_COMPLETED" if existing_refund.paypal_capture_id else "REFUND_COMPLETED"
                if existing_refund.approved_amount is None:
                    existing_refund.approved_amount = existing_refund.requested_amount
                existing_refund.resolved_at = now

            ref_key = f"shipkart_status:{existing_return.shipkart_return_id}:{incoming_status or event_upper}:{payload.refund_transaction_id or ''}"
            TimelineService().record_event(
                db,
                return_case_id=existing_return.id,
                refund_case_id=existing_refund.id,
                event_type=f"SHIPKART_{incoming_status or 'STATUS_SYNC'}",
                source_type="SHIPKART_BRIDGE",
                source_reference=ref_key,
                description=(
                    f"Shipkart reported status '{incoming_status or event_upper}'"
                    + (f" (TXN: {payload.refund_transaction_id})" if payload.refund_transaction_id else "")
                    + (f" — {payload.merchant_notes}" if payload.merchant_notes else ".")
                ),
                event_data=redact_sensitive_data(
                    {
                        "shipkart_status": incoming_status,
                        "refund_transaction_id": payload.refund_transaction_id,
                        "approval_reference": payload.approval_reference,
                    }
                ),
                occurred_at=now,
                verified=True,
            )
            ETAService().compute_and_persist_eta(db, existing_refund.id)
            db.commit()
            updated = True

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "created": False,
                "updated": updated,
                "shipkart_return_id": existing_return.shipkart_return_id,
                "return_case_id": str(existing_return.id),
                "refund_case_id": str(existing_refund.id) if existing_refund is not None else None,
                "status": existing_refund.status if existing_refund is not None else existing_return.status,
            },
        )

    return_case = ReturnService.create_return_case(
        db,
        shipkart_order_id=payload.shipkart_order_id,
        shipkart_customer_id=payload.shipkart_customer_id,
        shipkart_merchant_id=payload.shipkart_merchant_id,
        shipkart_return_id=payload.shipkart_return_id,
        reason_code=payload.reason_code.strip().upper(),
        customer_description=payload.customer_description.strip(),
        items=[item.model_dump() for item in payload.items],
    )

    items_total = sum(
        (Decimal(str(i.refund_amount_requested)) for i in return_case.items),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    req_amount = (
        Decimal(str(payload.requested_amount)).quantize(Decimal("0.01"))
        if payload.requested_amount is not None
        else items_total
    )
    cap_amount = (
        Decimal(str(payload.captured_amount)).quantize(Decimal("0.01"))
        if payload.captured_amount is not None
        else None
    )

    now = utcnow()
    refund_case = RefundCase(
        id=uuid.uuid4(),
        return_case_id=return_case.id,
        shipkart_return_id=return_case.shipkart_return_id,
        shipkart_order_id=return_case.shipkart_order_id,
        shipkart_customer_id=return_case.shipkart_customer_id,
        shipkart_merchant_id=return_case.shipkart_merchant_id,
        case_type=payload.case_type.strip().upper(),
        status="INVESTIGATING",
        requested_amount=req_amount,
        captured_amount=cap_amount,
        currency=payload.currency.strip().upper(),
        original_currency=payload.original_currency.strip().upper(),
        paypal_currency=payload.paypal_currency.strip().upper(),
        paypal_order_id=payload.paypal_order_id,
        paypal_capture_id=payload.paypal_capture_id,
        reason=payload.customer_description.strip() or payload.reason_code.strip().upper(),
        opened_at=now,
    )
    db.add(refund_case)
    db.flush()

    db.add(
        RefundTimelineEvent(
            id=uuid.uuid4(),
            return_case_id=return_case.id,
            refund_case_id=refund_case.id,
            event_type="BRIDGE_RETURN_EVENT_RECEIVED",
            source_type="SHIPKART_BRIDGE",
            source_reference=str(payload.shipkart_return_id),
            description="Shipkart bridge return event ingested via verified HMAC-SHA256 webhook.",
            event_data={
                "shipkart_return_id": payload.shipkart_return_id,
                "shipkart_order_id": payload.shipkart_order_id,
                "requested_amount": f"{req_amount:.2f}",
                "currency": refund_case.currency,
                "original_amount": str(payload.original_amount) if payload.original_amount is not None else None,
                "original_currency": refund_case.original_currency,
            },
            occurred_at=now,
            recorded_at=now,
            verified=True,
        )
    )
    if payload.evidence_urls:
        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=return_case.id,
                refund_case_id=refund_case.id,
                event_type="SHIPKART_EVIDENCE_LINKS_ATTACHED",
                source_type="SHIPKART_BRIDGE",
                source_reference=f"links:{payload.shipkart_return_id}",
                description=f"Shipkart referenced {len(payload.evidence_urls)} external return evidence link(s) pending verified upload.",
                event_data={"evidence_urls": redact_sensitive_data(list(payload.evidence_urls))},
                occurred_at=now,
                recorded_at=now,
                verified=False,
            )
        )
    AuditService.record_audit(
        db,
        actor_type="BRIDGE",
        shipkart_actor_id=payload.shipkart_customer_id,
        action="BRIDGE_RETURN_EVENT_INGESTED",
        resource_type="refund_case",
        resource_id=refund_case.id,
        after_state={
            "return_case_id": str(return_case.id),
            "shipkart_return_id": payload.shipkart_return_id,
            "requested_amount": f"{req_amount:.2f}",
        },
    )
    ETAService().compute_and_persist_eta(db, refund_case.id)
    db.commit()

    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            from app.worker.tasks import run_agent_pipeline_task

            run_agent_pipeline_task.delay(
                str(refund_case.id),
                payload.customer_description or payload.reason_code,
            )
        except Exception as exc:
            logger.warning(
                "Could not enqueue background agent investigation for return_id=%s: %s",
                payload.shipkart_return_id,
                redact_sensitive_data(str(exc)),
            )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "created": True,
            "updated": False,
            "shipkart_return_id": return_case.shipkart_return_id,
            "return_case_id": str(return_case.id),
            "refund_case_id": str(refund_case.id),
            "status": refund_case.status,
        },
    )

