from decimal import Decimal
import json
import logging
import re
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.crypto import redact_sensitive_data
from app.core.timeline import ORDER_STEP_SEQUENCE, sync_timeline_status
from app.db.database import get_db
from app.db.models import (
    MerchantOrderAllocation,
    Order,
    OrderStatus,
    PaymentLedgerEvent,
    ProcessedWebhookEvent,
    quantize_money,
)
from app.services.inventory_service import (
    convert_reservations_on_capture,
    release_order_reservations,
)
from app.services.order_service import initial_tracking_timeline
from app.services.paypal_service import (
    PayPalAPIError,
    PayPalService,
    get_paypal_service,
    resolve_paypal_service_for_merchant,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_PAYPAL_WEBHOOK_EVENTS = {
    "CHECKOUT.ORDER.APPROVED",
    "PAYMENT.CAPTURE.COMPLETED",
    "PAYMENT.CAPTURE.DENIED",
    "PAYMENT.CAPTURE.PENDING",
    "PAYMENT.CAPTURE.REFUNDED",
    "PAYMENT.CAPTURE.REVERSED",
    "CUSTOMER.DISPUTE.CREATED",
    "CUSTOMER.DISPUTE.UPDATED",
    "CUSTOMER.DISPUTE.RESOLVED",
}

_CAPTURE_LINK_RE = re.compile(r"/v2/payments/captures/([^/?]+)")


def _extract_capture_id_from_links(links: Any) -> Optional[str]:
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict):
            href = str(link.get("href") or "")
            match = _CAPTURE_LINK_RE.search(href)
            if match:
                return match.group(1)
    return None


def _extract_amount(resource: Dict[str, Any]) -> tuple[Optional[Decimal], Optional[str]]:
    amt = resource.get("amount") or resource.get("dispute_amount")
    if isinstance(amt, dict) and amt.get("value") is not None:
        try:
            return quantize_money(amt["value"]), amt.get("currency_code")
        except Exception:
            return None, amt.get("currency_code")
    return None, None


def _locate_order(
    db: Session,
    *,
    paypal_order_id: Optional[str] = None,
    paypal_capture_id: Optional[str] = None,
) -> Optional[Order]:
    if paypal_capture_id:
        order = db.query(Order).filter(Order.paypal_capture_id == paypal_capture_id).first()
        if order:
            return order
    if paypal_order_id:
        order = db.query(Order).filter(Order.paypal_order_id == paypal_order_id).first()
        if order:
            return order
    return None


async def _process_paypal_webhook(
    request: Request,
    db: Session,
    paypal_svc: PayPalService,
    *,
    expected_merchant_id: Optional[int] = None,
) -> Dict[str, Any]:
    raw_bytes = await request.body()
    try:
        event_body = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON webhook payload") from exc

    if not isinstance(event_body, dict) or not event_body.get("id") or not event_body.get("event_type"):
        raise HTTPException(status_code=400, detail="Webhook payload missing id or event_type")

    # Step 1: Verify PAYPAL-CERT-URL (*.paypal.com over HTTPS) + cryptographic signature API
    verified = paypal_svc.verify_webhook_signature(
        headers=request.headers,
        webhook_event=event_body,
    )
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid PayPal webhook signature")

    event_id = str(event_body["id"])
    event_type = str(event_body["event_type"])

    # Step 2: Allowlist event types (ignore unrecognized events cleanly without mutating orders)
    if event_type not in ALLOWED_PAYPAL_WEBHOOK_EVENTS:
        logger.info("Ignoring non-allowlisted PayPal webhook event %s (%s)", event_id, event_type)
        return {"status": "ignored", "event_id": event_id, "event_type": event_type}

    # Step 3: Deduplicate via ProcessedWebhookEvent primary key
    existing = (
        db.query(ProcessedWebhookEvent)
        .filter(ProcessedWebhookEvent.event_id == event_id)
        .first()
    )
    if existing:
        return {"status": "duplicate", "event_id": event_id, "event_type": event_type}

    # Step 4: Persist raw redacted payload cleanly
    redacted_event = redact_sensitive_data(event_body)
    processed_row = ProcessedWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        transmission_id=request.headers.get("paypal-transmission-id"),
        verification_status="SUCCESS",
        raw_redacted_payload=redacted_event,
    )
    db.add(processed_row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate", "event_id": event_id, "event_type": event_type}

    # Step 5: Authoritative re-fetch from PayPal API before mutating local order state
    resource: Dict[str, Any] = event_body.get("resource") or {}
    resource_id = resource.get("id")
    related_ids = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    paypal_order_id: Optional[str] = related_ids.get("order_id")
    paypal_capture_id: Optional[str] = related_ids.get("capture_id") or resource.get("capture_id")
    paypal_refund_id: Optional[str] = None
    auth_resource: Dict[str, Any] = {}

    try:
        if event_type == "CHECKOUT.ORDER.APPROVED":
            paypal_order_id = resource_id or paypal_order_id
            if paypal_order_id:
                auth_resource = paypal_svc.get_order(paypal_order_id)

        elif event_type in {
            "PAYMENT.CAPTURE.COMPLETED",
            "PAYMENT.CAPTURE.DENIED",
            "PAYMENT.CAPTURE.PENDING",
            "PAYMENT.CAPTURE.REVERSED",
        }:
            paypal_capture_id = resource_id or paypal_capture_id
            if paypal_capture_id:
                auth_resource = paypal_svc.get_capture(paypal_capture_id)
                auth_related = (auth_resource.get("supplementary_data") or {}).get("related_ids") or {}
                paypal_order_id = auth_related.get("order_id") or paypal_order_id

        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            paypal_refund_id = resource_id
            if not paypal_capture_id:
                paypal_capture_id = _extract_capture_id_from_links(resource.get("links"))
            if paypal_refund_id:
                try:
                    auth_resource = paypal_svc.get_refund(paypal_refund_id)
                except PayPalAPIError:
                    if paypal_capture_id:
                        auth_resource = paypal_svc.get_capture(paypal_capture_id)
                    else:
                        raise
            elif paypal_capture_id:
                auth_resource = paypal_svc.get_capture(paypal_capture_id)

            auth_related = (auth_resource.get("supplementary_data") or {}).get("related_ids") or {}
            paypal_capture_id = (
                paypal_capture_id
                or auth_related.get("capture_id")
                or _extract_capture_id_from_links(auth_resource.get("links"))
            )
            paypal_order_id = paypal_order_id or auth_related.get("order_id")

        elif event_type.startswith("CUSTOMER.DISPUTE."):
            disputed_txns = resource.get("disputed_transactions") or []
            if disputed_txns and isinstance(disputed_txns[0], dict):
                paypal_capture_id = (
                    disputed_txns[0].get("seller_transaction_id")
                    or paypal_capture_id
                )
            if paypal_capture_id:
                auth_resource = paypal_svc.get_capture(paypal_capture_id)
                auth_related = (auth_resource.get("supplementary_data") or {}).get("related_ids") or {}
                paypal_order_id = paypal_order_id or auth_related.get("order_id")
    except PayPalAPIError as exc:
        db.rollback()
        logger.error("Authoritative PayPal re-fetch failed for webhook %s: %s", event_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed authoritative PayPal resource re-fetch",
        ) from exc

    # Step 6: Reconcile state safely & append immutable ledger event
    order = _locate_order(
        db,
        paypal_order_id=paypal_order_id,
        paypal_capture_id=paypal_capture_id,
    )

    if expected_merchant_id is not None and order is not None and order.merchant_id != expected_merchant_id:
        db.rollback()
        raise HTTPException(
            status_code=403,
            detail="Webhook order does not belong to this merchant",
        )

    amt_val, amt_cur = _extract_amount(auth_resource or resource)
    if amt_val is None:
        amt_val, amt_cur = _extract_amount(resource)

    status_snapshot = str(auth_resource.get("status") or resource.get("status") or event_type)

    if order:
        if event_type == "CHECKOUT.ORDER.APPROVED":
            if order.status == OrderStatus.PENDING_PAYMENT and auth_resource.get("status") == "APPROVED":
                order.payment_status = "APPROVED"

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            if paypal_capture_id and not order.paypal_capture_id:
                order.paypal_capture_id = paypal_capture_id
            if auth_resource.get("status") == "COMPLETED" and order.payment_status != "PAID":
                if convert_reservations_on_capture(db, order):
                    order.status = OrderStatus.ORDERED
                    order.payment_status = "PAID"
                    order.tracking_history = sync_timeline_status(
                        order.tracking_history or initial_tracking_timeline(ordered_completed=False),
                        OrderStatus.ORDERED.value,
                        ORDER_STEP_SEQUENCE,
                    )
                    flag_modified(order, "tracking_history")
                    db.query(MerchantOrderAllocation).filter(
                        MerchantOrderAllocation.order_id == order.id
                    ).update(
                        {"fulfillment_status": "ORDERED", "settlement_status": "CAPTURED"},
                        synchronize_session=False,
                    )
                else:
                    order.status = OrderStatus.CAPTURE_EXCEPTION
                    order.payment_status = "CAPTURE_EXCEPTION_OUT_OF_STOCK"
                    db.query(MerchantOrderAllocation).filter(
                        MerchantOrderAllocation.order_id == order.id
                    ).update(
                        {"fulfillment_status": "CAPTURE_EXCEPTION", "settlement_status": "EXCEPTION_REVIEW"},
                        synchronize_session=False,
                    )

        elif event_type == "PAYMENT.CAPTURE.PENDING":
            if order.payment_status not in ("PAID", "REFUNDED", "REVERSED"):
                order.payment_status = "CAPTURE_PENDING"

        elif event_type == "PAYMENT.CAPTURE.DENIED":
            if order.payment_status != "PAID":
                order.payment_status = "DENIED"
                if order.status == OrderStatus.PENDING_PAYMENT:
                    order.status = OrderStatus.CANCELLED
                    release_order_reservations(db, order.id, new_status="RELEASED")
                    db.query(MerchantOrderAllocation).filter(
                        MerchantOrderAllocation.order_id == order.id
                    ).update(
                        {"fulfillment_status": "CANCELLED", "settlement_status": "FAILED"},
                        synchronize_session=False,
                    )

        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            auth_status = str(auth_resource.get("status") or "").upper()
            if auth_status == "PARTIALLY_REFUNDED" or (
                amt_val is not None
                and order.paypal_amount is not None
                and amt_val < quantize_money(order.paypal_amount)
            ):
                order.payment_status = "PARTIALLY_REFUNDED"
                alloc_status = "PARTIALLY_REFUNDED"
            else:
                order.payment_status = "REFUNDED"
                alloc_status = "REFUNDED"
            db.query(MerchantOrderAllocation).filter(
                MerchantOrderAllocation.order_id == order.id
            ).update({"settlement_status": alloc_status}, synchronize_session=False)

        elif event_type == "PAYMENT.CAPTURE.REVERSED":
            order.payment_status = "REVERSED"
            db.query(MerchantOrderAllocation).filter(
                MerchantOrderAllocation.order_id == order.id
            ).update({"settlement_status": "REVERSED"}, synchronize_session=False)

        elif event_type == "CUSTOMER.DISPUTE.CREATED":
            order.payment_status = "DISPUTED"
            db.query(MerchantOrderAllocation).filter(
                MerchantOrderAllocation.order_id == order.id
            ).update({"settlement_status": "DISPUTE_HOLD"}, synchronize_session=False)

        elif event_type == "CUSTOMER.DISPUTE.UPDATED":
            order.payment_status = "DISPUTE_UNDER_REVIEW"

        elif event_type == "CUSTOMER.DISPUTE.RESOLVED":
            outcome = ((resource.get("dispute_outcome") or {}).get("outcome_code") or "").upper()
            if outcome == "RESOLVED_SELLER_FAVOUR":
                order.payment_status = "PAID"
                db.query(MerchantOrderAllocation).filter(
                    MerchantOrderAllocation.order_id == order.id
                ).update({"settlement_status": "CAPTURED"}, synchronize_session=False)
            else:
                order.payment_status = "DISPUTE_LOST"
                db.query(MerchantOrderAllocation).filter(
                    MerchantOrderAllocation.order_id == order.id
                ).update({"settlement_status": "REVERSED"}, synchronize_session=False)

        status_snapshot = order.payment_status

    db.add(
        PaymentLedgerEvent(
            order_id=order.id if order else None,
            merchant_id=order.merchant_id if order else expected_merchant_id,
            event_type=event_type,
            paypal_order_id=paypal_order_id,
            paypal_capture_id=paypal_capture_id,
            paypal_refund_id=paypal_refund_id,
            idempotency_key=event_id,
            amount=amt_val,
            currency=amt_cur,
            status_snapshot=status_snapshot,
            redacted_payload=redacted_event,
        )
    )
    db.commit()

    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "order_id": order.id if order else None,
    }


@router.post("/paypal")
async def handle_paypal_webhook(
    request: Request,
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    return await _process_paypal_webhook(request, db, paypal_svc, expected_merchant_id=None)


@router.post("/paypal/{merchant_id}")
async def handle_merchant_paypal_webhook(
    merchant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    paypal_svc: PayPalService = Depends(get_paypal_service),
):
    try:
        merchant_svc = resolve_paypal_service_for_merchant(
            db, merchant_id, fallback_service=paypal_svc
        )
    except PayPalAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if not merchant_svc.client_id or not merchant_svc.client_secret:
        raise HTTPException(status_code=503, detail="Merchant PayPal credentials are not configured")
    if not merchant_svc.webhook_id:
        raise HTTPException(status_code=400, detail="Merchant PayPal webhook ID is not configured")

    return await _process_paypal_webhook(
        request,
        db,
        merchant_svc,
        expected_merchant_id=merchant_id,
    )
