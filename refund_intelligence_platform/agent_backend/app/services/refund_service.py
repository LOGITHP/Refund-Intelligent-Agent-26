"""Idempotent PayPal / Shipkart refund execution service guarded by REF-001..REF-004."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_redact import redact_sensitive_data
from app.db.base import utcnow
from app.db.models import (
    RefundApproval,
    RefundCase,
    RefundTimelineEvent,
    RefundTransaction,
)
from app.integrations.paypal_client import PayPalAPIError, PayPalClient
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService, ComplianceViolationError

BridgeExecutor = Callable[[RefundCase, RefundApproval, RefundTransaction], dict[str, Any]]


class RefundService:
    """Executes merchant-approved refunds via Shipkart Bridge or PayPal REST API."""

    @staticmethod
    def _load_locked_refund_case(db: Session, refund_case_id: uuid.UUID) -> RefundCase | None:
        stmt = select(RefundCase).where(RefundCase.id == refund_case_id)
        bind = db.get_bind()
        if bind is not None and bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return db.scalar(stmt)

    @classmethod
    def execute_approved_refund(
        cls,
        db: Session,
        refund_case_id: uuid.UUID,
        *,
        idempotency_key: str,
        paypal_client: PayPalClient | None = None,
        bridge_executor: BridgeExecutor | None = None,
        actor_type: str = "MERCHANT",
        shipkart_actor_id: int | None = None,
        actor_shipkart_merchant_id: int | None = None,
    ) -> RefundTransaction:
        """Execute an approved refund idempotently while enforcing REF-001..REF-004."""
        existing = ComplianceService.find_existing_by_idempotency_key(
            db,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return existing

        refund_case = cls._load_locked_refund_case(db, refund_case_id)
        if refund_case is None:
            raise ComplianceViolationError(
                "Refund case not found.",
                rule_code="CASE-404",
                status_code=404,
            )

        if actor_shipkart_merchant_id is not None:
            ComplianceService.assert_merchant_access(
                db,
                case=refund_case,
                actor_shipkart_merchant_id=actor_shipkart_merchant_id,
            )

        # REF-001: Mandatory explicit Merchant approval check
        approval = ComplianceService.assert_merchant_approval_exists(
            db,
            refund_case=refund_case,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
        )

        # REF-004: Original PayPal capture verification
        capture_id = ComplianceService.assert_capture_verified(
            db,
            refund_case=refund_case,
            paypal_capture_id=refund_case.paypal_capture_id,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
        )

        raw_amount = (
            approval.approved_amount
            if approval.approved_amount is not None
            else (
                refund_case.approved_amount
                if refund_case.approved_amount is not None
                else refund_case.requested_amount
            )
        )
        refund_amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))

        # REF-002: Remaining refundable capture balance guard
        ComplianceService.assert_within_refundable_balance(
            db,
            refund_case=refund_case,
            requested_amount=refund_amount,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
        )

        now = utcnow()
        currency = (refund_case.paypal_currency or refund_case.currency or "USD").strip().upper()
        tx = RefundTransaction(
            id=uuid.uuid4(),
            refund_case_id=refund_case.id,
            paypal_order_id=refund_case.paypal_order_id,
            paypal_capture_id=capture_id,
            amount=refund_amount,
            currency=currency,
            status="PENDING",
            idempotency_key=idempotency_key.strip(),
            submitted_at=now,
            created_at=now,
        )
        db.add(tx)
        db.flush()

        try:
            if bridge_executor is not None:
                raw_response = bridge_executor(refund_case, approval, tx)
            elif paypal_client is not None:
                raw_response = paypal_client.refund_capture(
                    capture_id=capture_id,
                    amount=refund_amount,
                    currency=currency,
                    idempotency_key=tx.idempotency_key,
                    note=approval.reason,
                )
            else:
                raise ComplianceViolationError(
                    "No PayPal client or Shipkart bridge executor provided for refund dispatch.",
                    rule_code="PAYPAL-CONFIG",
                    status_code=503,
                )
        except PayPalAPIError as exc:
            tx.status = "FAILED"
            tx.paypal_response = json.loads(
                json.dumps(redact_sensitive_data({"error": str(exc), "detail": exc.detail}), default=str)
            )
            AuditService.record_audit(
                db,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
                action="PAYPAL_REFUND_FAILED",
                resource_type="refund_transaction",
                resource_id=tx.id,
                after_state={"status": "FAILED", "status_code": exc.status_code},
            )
            db.commit()
            raise ComplianceViolationError(
                f"PayPal refund execution failed: {exc}",
                rule_code="PAYPAL-EXEC-ERR",
                status_code=exc.status_code or 502,
                details={"paypal_detail": exc.detail},
            ) from exc

        sanitized_response = json.loads(
            json.dumps(redact_sensitive_data(raw_response), default=str)
        )
        provider_status = str(sanitized_response.get("status", "PENDING")).strip().upper()
        paypal_refund_id = (
            sanitized_response.get("id")
            or sanitized_response.get("paypal_refund_id")
            or None
        )

        tx.paypal_refund_id = str(paypal_refund_id) if paypal_refund_id else None
        tx.paypal_response = sanitized_response

        if provider_status == "COMPLETED":
            tx.status = "COMPLETED"
            tx.completed_at = utcnow()
            refund_case.status = "REFUND_COMPLETED"
            refund_case.resolved_at = tx.completed_at
            event_type = "PAYPAL_REFUND_COMPLETED"
            event_desc = (
                f"PayPal reported refund {tx.paypal_refund_id or tx.id} COMPLETED "
                f"for {tx.amount} {tx.currency}. Bank issuer posting may still be pending."
            )
        else:
            # Never mark COMPLETED when provider returns PENDING or CREATED
            tx.status = "PENDING"
            refund_case.status = "REFUND_SUBMITTED"
            event_type = "PAYPAL_REFUND_SUBMITTED"
            event_desc = (
                f"PayPal refund {tx.paypal_refund_id or tx.id} submitted with status {provider_status}."
            )

        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=refund_case.return_case_id,
                refund_case_id=refund_case.id,
                event_type=event_type,
                source_type="PAYPAL",
                source_reference=tx.paypal_refund_id or str(tx.id),
                description=event_desc,
                event_data={
                    "paypal_refund_id": tx.paypal_refund_id,
                    "provider_status": provider_status,
                    "amount": str(tx.amount),
                    "currency": tx.currency,
                },
                occurred_at=utcnow(),
                recorded_at=utcnow(),
                verified=True,
            )
        )
        AuditService.record_audit(
            db,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
            action=event_type,
            resource_type="refund_transaction",
            resource_id=tx.id,
            after_state={
                "refund_case_id": str(refund_case.id),
                "approval_id": str(approval.id),
                "paypal_refund_id": tx.paypal_refund_id,
                "status": tx.status,
                "amount": str(tx.amount),
                "currency": tx.currency,
            },
        )
        db.commit()
        db.refresh(tx)
        return tx
