"""Hard compliance & authorization guardrails (REF-001..REF-004, AUTH-001..002, CASE-001, QTY-001)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    ComplianceViolation,
    RefundApproval,
    RefundCase,
    RefundTransaction,
    ReturnCase,
)
from app.services.audit_service import AuditService

RESERVED_TRANSACTION_STATUSES = ("PENDING", "SUBMITTED", "COMPLETED")


class ComplianceViolationError(ValueError):
    """Raised when a mandatory financial, authorization, or policy rule fails."""

    def __init__(
        self,
        message: str,
        *,
        rule_code: str,
        status_code: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.rule_code = rule_code
        self.status_code = status_code
        self.details = details or {}


class ComplianceService:
    """Enforces Blueprint Section 11/12 controls and records violations + audit logs."""

    @staticmethod
    def record_violation_and_raise(
        db: Session,
        *,
        rule_code: str,
        message: str,
        status_code: int,
        severity: str = "HIGH",
        refund_case_id: uuid.UUID | None = None,
        resource_type: str = "refund_case",
        resource_id: uuid.UUID | None = None,
        actor_type: str = "SYSTEM",
        shipkart_actor_id: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> ComplianceViolationError:
        violation = ComplianceViolation(
            id=uuid.uuid4(),
            refund_case_id=refund_case_id,
            rule_code=rule_code,
            severity=severity,
            description=message,
            status="OPEN",
            created_at=utcnow(),
        )
        db.add(violation)
        db.flush()

        AuditService.record_audit(
            db,
            actor_type=actor_type,
            shipkart_actor_id=shipkart_actor_id,
            action=f"COMPLIANCE_BLOCKED_{rule_code}",
            resource_type=resource_type,
            resource_id=resource_id or refund_case_id or violation.id,
            after_state={"rule_code": rule_code, "message": message, "details": details or {}},
        )
        return ComplianceViolationError(
            message,
            rule_code=rule_code,
            status_code=status_code,
            details=details,
        )

    @classmethod
    def assert_merchant_access(
        cls,
        db: Session,
        *,
        case: ReturnCase | RefundCase,
        actor_shipkart_merchant_id: int | None = None,
        actor_merchant_id: uuid.UUID | None = None,
    ) -> None:
        """AUTH-001: Verify actor belongs to the owning merchant tenant."""
        resource_type = "return_case" if isinstance(case, ReturnCase) else "refund_case"
        refund_case_id = None if isinstance(case, ReturnCase) else case.id

        if case.shipkart_merchant_id is not None:
            if actor_shipkart_merchant_id is not None and actor_shipkart_merchant_id == case.shipkart_merchant_id:
                return
            if (
                actor_shipkart_merchant_id is None
                and actor_merchant_id is not None
                and case.merchant_id == actor_merchant_id
            ):
                return
            raise cls.record_violation_and_raise(
                db,
                rule_code="AUTH-001",
                message="Merchant is not authorized to access or mutate this case.",
                status_code=403,
                severity="CRITICAL",
                refund_case_id=refund_case_id,
                resource_type=resource_type,
                resource_id=case.id,
                actor_type="MERCHANT",
                shipkart_actor_id=actor_shipkart_merchant_id,
                details={
                    "expected_shipkart_merchant_id": case.shipkart_merchant_id,
                    "actual_shipkart_merchant_id": actor_shipkart_merchant_id,
                },
            )

        if case.merchant_id is not None:
            if actor_merchant_id is not None and case.merchant_id == actor_merchant_id:
                return
            raise cls.record_violation_and_raise(
                db,
                rule_code="AUTH-001",
                message="Merchant is not authorized to access or mutate this case.",
                status_code=403,
                severity="CRITICAL",
                refund_case_id=refund_case_id,
                resource_type=resource_type,
                resource_id=case.id,
                actor_type="MERCHANT",
                shipkart_actor_id=actor_shipkart_merchant_id,
            )

        # Shipkart platform-owned catalog items have no per-merchant owner (None/None).
        if actor_shipkart_merchant_id is not None or actor_merchant_id is not None:
            return

        raise cls.record_violation_and_raise(
            db,
            rule_code="AUTH-001",
            message="Merchant is not authorized to access or mutate this case.",
            status_code=403,
            severity="CRITICAL",
            refund_case_id=refund_case_id,
            resource_type=resource_type,
            resource_id=case.id,
            actor_type="MERCHANT",
            shipkart_actor_id=actor_shipkart_merchant_id,
        )

    @classmethod
    def assert_customer_access(
        cls,
        db: Session,
        *,
        case: ReturnCase | RefundCase,
        actor_shipkart_customer_id: int | None = None,
        actor_customer_id: uuid.UUID | None = None,
    ) -> None:
        """AUTH-002: Verify actor is the owning customer."""
        resource_type = "return_case" if isinstance(case, ReturnCase) else "refund_case"
        refund_case_id = None if isinstance(case, ReturnCase) else case.id

        if case.shipkart_customer_id is not None:
            if actor_shipkart_customer_id is not None and actor_shipkart_customer_id == case.shipkart_customer_id:
                return
            if (
                actor_shipkart_customer_id is None
                and actor_customer_id is not None
                and case.customer_id == actor_customer_id
            ):
                return
            raise cls.record_violation_and_raise(
                db,
                rule_code="AUTH-002",
                message="Customer is not authorized to access this case.",
                status_code=403,
                severity="HIGH",
                refund_case_id=refund_case_id,
                resource_type=resource_type,
                resource_id=case.id,
                actor_type="CUSTOMER",
                shipkart_actor_id=actor_shipkart_customer_id,
            )

        if actor_customer_id is None or case.customer_id != actor_customer_id:
            raise cls.record_violation_and_raise(
                db,
                rule_code="AUTH-002",
                message="Customer is not authorized to access this case.",
                status_code=403,
                severity="HIGH",
                refund_case_id=refund_case_id,
                resource_type=resource_type,
                resource_id=case.id,
                actor_type="CUSTOMER",
                shipkart_actor_id=actor_shipkart_customer_id,
            )

    @classmethod
    def assert_rejection_reason(
        cls,
        db: Session,
        *,
        reason: str | None,
        refund_case_id: uuid.UUID | None = None,
        resource_type: str = "refund_case",
        resource_id: uuid.UUID | None = None,
        actor_type: str = "MERCHANT",
        shipkart_actor_id: int | None = None,
    ) -> str:
        """CASE-001: Rejections require a clear human-provided explanation."""
        clean = (reason or "").strip()
        if len(clean) < 3:
            raise cls.record_violation_and_raise(
                db,
                rule_code="CASE-001",
                message="A rejection reason of at least 3 characters is required.",
                status_code=422,
                severity="MEDIUM",
                refund_case_id=refund_case_id,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
            )
        return clean

    @staticmethod
    def get_remaining_refundable_balance(db: Session, refund_case: RefundCase) -> Decimal:
        """Calculate captured_amount minus all pending/submitted/completed refund transactions."""
        if refund_case.captured_amount is None:
            return Decimal("0.00")

        captured = Decimal(str(refund_case.captured_amount)).quantize(Decimal("0.01"))
        stmt = select(func.coalesce(func.sum(RefundTransaction.amount), 0)).where(
            RefundTransaction.status.in_(RESERVED_TRANSACTION_STATUSES)
        )
        if refund_case.paypal_capture_id:
            stmt = stmt.where(RefundTransaction.paypal_capture_id == refund_case.paypal_capture_id)
        else:
            stmt = stmt.where(RefundTransaction.refund_case_id == refund_case.id)

        reserved = Decimal(str(db.scalar(stmt) or "0.00")).quantize(Decimal("0.01"))
        return (captured - reserved).quantize(Decimal("0.01"))

    @classmethod
    def assert_within_refundable_balance(
        cls,
        db: Session,
        *,
        refund_case: RefundCase,
        requested_amount: Decimal,
        actor_type: str = "SYSTEM",
        shipkart_actor_id: int | None = None,
    ) -> Decimal:
        """REF-002: Prevent over-refunds beyond verified remaining refundable capture balance."""
        amount = Decimal(str(requested_amount)).quantize(Decimal("0.01"))
        if amount <= Decimal("0.00"):
            raise cls.record_violation_and_raise(
                db,
                rule_code="REF-002",
                message="Refund amount must be greater than zero.",
                status_code=422,
                severity="HIGH",
                refund_case_id=refund_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
                details={"requested_amount": str(amount)},
            )

        if refund_case.captured_amount is None:
            raise cls.record_violation_and_raise(
                db,
                rule_code="REF-002",
                message="Verified captured_amount is missing; cannot validate refundable balance.",
                status_code=422,
                severity="CRITICAL",
                refund_case_id=refund_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
            )

        remaining = cls.get_remaining_refundable_balance(db, refund_case)
        if amount > remaining:
            raise cls.record_violation_and_raise(
                db,
                rule_code="REF-002",
                message=(
                    f"Requested refund {amount} exceeds remaining refundable balance {remaining}."
                ),
                status_code=422,
                severity="CRITICAL",
                refund_case_id=refund_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
                details={
                    "requested_amount": str(amount),
                    "remaining_balance": str(remaining),
                    "captured_amount": str(refund_case.captured_amount),
                },
            )
        return remaining

    @classmethod
    def assert_merchant_approval_exists(
        cls,
        db: Session,
        *,
        refund_case: RefundCase,
        actor_type: str = "SYSTEM",
        shipkart_actor_id: int | None = None,
    ) -> RefundApproval:
        """REF-001: Verify explicit latest Merchant approval exists before PayPal execution."""
        latest_approval = db.scalar(
            select(RefundApproval)
            .where(RefundApproval.refund_case_id == refund_case.id)
            .order_by(RefundApproval.created_at.desc())
            .limit(1)
        )
        if latest_approval is None or latest_approval.decision != "APPROVED":
            raise cls.record_violation_and_raise(
                db,
                rule_code="REF-001",
                message="Explicit merchant approval is mandatory before refund execution.",
                status_code=403,
                severity="CRITICAL",
                refund_case_id=refund_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
                details={"latest_decision": latest_approval.decision if latest_approval else None},
            )
        return latest_approval

    @classmethod
    def assert_capture_verified(
        cls,
        db: Session,
        *,
        refund_case: RefundCase,
        paypal_capture_id: str | None,
        actor_type: str = "SYSTEM",
        shipkart_actor_id: int | None = None,
    ) -> str:
        """REF-004: Refund must target the verified original PayPal capture ID."""
        expected = (refund_case.paypal_capture_id or "").strip()
        provided = (paypal_capture_id or "").strip()
        if not expected or not provided or expected != provided:
            raise cls.record_violation_and_raise(
                db,
                rule_code="REF-004",
                message="PayPal capture ID is missing or does not match the original captured order.",
                status_code=422,
                severity="CRITICAL",
                refund_case_id=refund_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
                details={"expected_capture_id": expected or None, "provided_capture_id": provided or None},
            )
        return expected

    @classmethod
    def find_existing_by_idempotency_key(
        cls,
        db: Session,
        *,
        idempotency_key: str,
    ) -> RefundTransaction | None:
        """REF-003: Look up an existing transaction by idempotency_key."""
        clean_key = (idempotency_key or "").strip()
        if not clean_key:
            raise ComplianceViolationError(
                "idempotency_key is required for refund execution.",
                rule_code="REF-003",
                status_code=422,
            )
        return db.scalar(
            select(RefundTransaction).where(RefundTransaction.idempotency_key == clean_key)
        )
