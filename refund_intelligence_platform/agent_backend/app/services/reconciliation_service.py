"""PayPal webhook idempotency and pending-refund reconciliation service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import ProcessedWebhookEvent, RefundCase, RefundTransaction, ReturnCase
from app.integrations.shipkart_client import ShipkartBridgeClient, ShipkartBridgeError
from app.services.timeline_service import TimelineService, ensure_utc

_REFUND_EVENT_DEFAULT_STATUS: dict[str, str] = {
    "PAYMENT.CAPTURE.REFUNDED": "COMPLETED",
    "PAYMENT.REFUND.COMPLETED": "COMPLETED",
    "PAYMENT.REFUND.PENDING": "PENDING",
    "PAYMENT.REFUND.FAILED": "FAILED",
    "PAYMENT.REFUND.DENIED": "FAILED",
    "PAYMENT.REFUND.CANCELLED": "CANCELLED",
    "PAYMENT.CAPTURE.REVERSED": "REVERSED",
    "PAYMENT.CAPTURE.DENIED": "FAILED",
}


def _parse_ts(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return ensure_utc(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return ensure_utc(datetime.fromisoformat(raw.strip().replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _extract_capture_id(resource: dict[str, Any]) -> str | None:
    if resource.get("capture_id"):
        return str(resource["capture_id"])
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    if related.get("capture_id"):
        return str(related["capture_id"])
    for link in resource.get("links") or []:
        if isinstance(link, dict) and link.get("rel") == "up":
            href = str(link.get("href") or "")
            if "/captures/" in href:
                return href.rstrip("/").split("/captures/")[-1].split("/")[0]
    return None


def _compute_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ShipkartPayPalRefundAdapter:
    """Lightweight bridge-backed PayPal refund reader (never stores merchant secrets)."""

    def __init__(
        self,
        shipkart_client: ShipkartBridgeClient,
        shipkart_return_id: int,
    ) -> None:
        self._shipkart_client = shipkart_client
        self._shipkart_return_id = shipkart_return_id

    def get_refund(self, refund_id: str | None = None) -> dict[str, Any]:
        """Fetch PayPal refund status via Shipkart's Service-JWT bridge endpoint."""
        try:
            data = self._shipkart_client.fetch_paypal_refund_status(self._shipkart_return_id)
        except ShipkartBridgeError as exc:
            return {
                "degraded": True,
                "status": "UNAVAILABLE",
                "error_status_code": exc.status_code,
            }
        if not isinstance(data, dict):
            return {"degraded": True, "status": "UNAVAILABLE"}
        return data


class ReconciliationService:
    """Handles PAY-002 idempotent PayPal webhook processing and active transaction polling."""

    def __init__(self, timeline_service: TimelineService | None = None) -> None:
        self.timeline_service = timeline_service or TimelineService()

    def _apply_paypal_status(
        self,
        db: Session,
        *,
        refund_tx: RefundTransaction,
        target_status: str,
        raw_payload: dict[str, Any],
        occurred_at: datetime,
        source_type: str,
        source_reference: str,
        description: str,
    ) -> RefundCase | None:
        normalized_status = target_status.strip().upper()
        refund_case = db.get(RefundCase, refund_tx.refund_case_id)

        refund_tx.status = normalized_status
        refund_tx.paypal_response = dict(raw_payload)
        if normalized_status == "COMPLETED":
            if refund_tx.completed_at is None:
                refund_tx.completed_at = occurred_at
            if refund_case is not None and (refund_case.status or "").upper() not in {
                "CONFIRMED_POSTED",
                "ISSUER_POSTED",
            }:
                refund_case.status = "PAYPAL_COMPLETED"
        elif normalized_status in {"FAILED", "CANCELLED", "DENIED"}:
            if refund_case is not None:
                refund_case.status = "REFUND_FAILED"
        elif normalized_status == "REVERSED":
            if refund_case is not None:
                refund_case.status = "REVERSED"
        elif normalized_status == "PENDING":
            if refund_case is not None and (refund_case.status or "").upper() not in {
                "PAYPAL_COMPLETED",
                "CONFIRMED_POSTED",
                "ISSUER_POSTED",
            }:
                refund_case.status = "PAYPAL_PENDING"

        self.timeline_service.record_event(
            db,
            refund_case_id=refund_tx.refund_case_id,
            return_case_id=refund_case.return_case_id if refund_case is not None else None,
            event_type=f"PAYPAL_REFUND_{normalized_status}",
            source_type=source_type,
            source_reference=source_reference,
            description=description,
            occurred_at=occurred_at,
            event_data={
                "paypal_refund_id": refund_tx.paypal_refund_id,
                "paypal_capture_id": refund_tx.paypal_capture_id,
                "status": normalized_status,
                "amount": str(refund_tx.amount),
                "currency": refund_tx.currency,
            },
            verified=True,
        )
        return refund_case

    def process_paypal_webhook(
        self,
        db: Session,
        *,
        provider_event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Idempotently process a PayPal webhook event (PAY-002)."""
        clean_event_id = (provider_event_id or "").strip()
        if not clean_event_id:
            raise ValueError("provider_event_id must not be empty.")

        clean_event_type = (event_type or "").strip().upper()

        existing = db.scalar(
            select(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.provider == "paypal",
                ProcessedWebhookEvent.provider_event_id == clean_event_id,
            )
        )
        if existing is not None:
            return {
                "deduplicated": True,
                "provider": "paypal",
                "provider_event_id": clean_event_id,
                "event_type": existing.event_type,
                "processing_status": existing.processing_status,
            }

        webhook_row = ProcessedWebhookEvent(
            provider="paypal",
            provider_event_id=clean_event_id,
            event_type=clean_event_type,
            payload_hash=_compute_payload_hash(payload),
            processing_status="RECEIVED",
            received_at=utcnow(),
        )
        db.add(webhook_row)
        db.flush()

        resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else payload
        resource_status = str(resource.get("status") or "").strip().upper()
        target_status = resource_status or _REFUND_EVENT_DEFAULT_STATUS.get(clean_event_type, "")

        if clean_event_type not in _REFUND_EVENT_DEFAULT_STATUS:
            webhook_row.processing_status = "IGNORED"
            webhook_row.processed_at = utcnow()
            db.flush()
            return {
                "deduplicated": False,
                "provider": "paypal",
                "provider_event_id": clean_event_id,
                "event_type": clean_event_type,
                "processing_status": webhook_row.processing_status,
                "refund_transaction_id": None,
                "refund_case_id": None,
            }

        paypal_refund_id = resource.get("id") or resource.get("refund_id")
        paypal_capture_id = _extract_capture_id(resource)

        refund_tx: RefundTransaction | None = None
        if paypal_refund_id:
            refund_tx = db.scalar(
                select(RefundTransaction).where(
                    RefundTransaction.paypal_refund_id == str(paypal_refund_id)
                )
            )
        if refund_tx is None and paypal_capture_id:
            refund_tx = db.scalar(
                select(RefundTransaction)
                .where(RefundTransaction.paypal_capture_id == str(paypal_capture_id))
                .order_by(RefundTransaction.created_at.desc())
            )

        occurred_at = (
            _parse_ts(resource.get("update_time"))
            or _parse_ts(payload.get("create_time"))
            or utcnow()
        )

        refund_case: RefundCase | None = None
        if refund_tx is not None and target_status:
            if paypal_refund_id and not refund_tx.paypal_refund_id:
                refund_tx.paypal_refund_id = str(paypal_refund_id)
            refund_case = self._apply_paypal_status(
                db,
                refund_tx=refund_tx,
                target_status=target_status,
                raw_payload=payload,
                occurred_at=occurred_at,
                source_type="PAYPAL_WEBHOOK",
                source_reference=clean_event_id,
                description=(
                    f"PayPal webhook '{clean_event_type}' reported refund status '{target_status}' "
                    "(PayPal completion does not confirm issuer bank posting)."
                ),
            )

        webhook_row.processing_status = "PROCESSED"
        webhook_row.processed_at = utcnow()
        db.flush()

        return {
            "deduplicated": False,
            "provider": "paypal",
            "provider_event_id": clean_event_id,
            "event_type": clean_event_type,
            "processing_status": webhook_row.processing_status,
            "refund_transaction_id": str(refund_tx.id) if refund_tx is not None else None,
            "refund_case_id": str(refund_tx.refund_case_id) if refund_tx is not None else None,
            "transaction_status": refund_tx.status if refund_tx is not None else None,
            "case_status": refund_case.status if refund_case is not None else None,
        }

    def reconcile_pending_refund_transaction(
        self,
        db: Session,
        refund_tx: RefundTransaction,
        paypal_client: Any,
    ) -> RefundTransaction:
        """Query PayPal (or Shipkart merchant bridge) for a pending RefundTransaction and reconcile state transitions."""
        client = paypal_client
        if isinstance(paypal_client, ShipkartBridgeClient):
            refund_case = db.get(RefundCase, refund_tx.refund_case_id)
            shipkart_return_id = refund_case.shipkart_return_id if refund_case is not None else None
            if (
                shipkart_return_id is None
                and refund_case is not None
                and refund_case.return_case_id is not None
            ):
                ret_case = db.get(ReturnCase, refund_case.return_case_id)
                if ret_case is not None:
                    shipkart_return_id = ret_case.shipkart_return_id
            if shipkart_return_id is None:
                return refund_tx
            client = ShipkartPayPalRefundAdapter(paypal_client, shipkart_return_id)

        is_bridge_adapter = isinstance(client, ShipkartPayPalRefundAdapter)
        if not refund_tx.paypal_refund_id and not is_bridge_adapter:
            return refund_tx

        try:
            raw_resp = client.get_refund(refund_tx.paypal_refund_id or "")
        except ShipkartBridgeError:
            return refund_tx

        if hasattr(raw_resp, "model_dump"):
            resp_dict: dict[str, Any] = raw_resp.model_dump()
        elif isinstance(raw_resp, dict):
            resp_dict = dict(raw_resp)
        else:
            return refund_tx

        if resp_dict.get("degraded") is True:
            return refund_tx

        remote_status = str(resp_dict.get("status") or "").strip().upper()
        if not remote_status:
            return refund_tx

        if is_bridge_adapter and not refund_tx.paypal_refund_id and resp_dict.get("id"):
            refund_tx.paypal_refund_id = str(resp_dict["id"])

        current_status = (refund_tx.status or "").strip().upper()
        if remote_status != current_status:
            occurred_at = (
                _parse_ts(resp_dict.get("update_time"))
                or _parse_ts(resp_dict.get("create_time"))
                or utcnow()
            )
            refund_ref = refund_tx.paypal_refund_id or str(resp_dict.get("id") or refund_tx.id)
            self._apply_paypal_status(
                db,
                refund_tx=refund_tx,
                target_status=remote_status,
                raw_payload=resp_dict,
                occurred_at=occurred_at,
                source_type="PAYPAL_API",
                source_reference=f"{refund_ref}:{remote_status}",
                description=(
                    f"PayPal API reconciliation transitioned refund '{refund_ref}' "
                    f"from '{current_status}' to '{remote_status}'."
                ),
            )
            db.flush()

        return refund_tx
