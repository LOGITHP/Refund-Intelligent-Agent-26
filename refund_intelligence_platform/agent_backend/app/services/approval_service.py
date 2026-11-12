"""Merchant refund approval & rejection service creating immutable RefundApproval records."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import RefundApproval, RefundCase, RefundTimelineEvent
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService, ComplianceViolationError


class ApprovalService:
    """Records immutable merchant decisions on financial refund cases."""

    @staticmethod
    def record_merchant_decision(
        db: Session,
        refund_case_id: uuid.UUID,
        *,
        shipkart_merchant_id: int | None = None,
        merchant_id: uuid.UUID | None = None,
        shipkart_merchant_user_id: int | None = None,
        merchant_user_id: uuid.UUID | None = None,
        decision: str,
        approved_amount: Decimal | None = None,
        currency: str | None = None,
        reason: str = "",
        policy_version: str = "v1.0",
        approval_reference: str | None = None,
    ) -> RefundApproval:
        """Validate AUTH-001, CASE-001, and REF-002 then persist an immutable RefundApproval."""
        refund_case = db.get(RefundCase, refund_case_id)
        if refund_case is None:
            raise ComplianceViolationError(
                "Refund case not found.",
                rule_code="CASE-404",
                status_code=404,
            )

        ComplianceService.assert_merchant_access(
            db,
            case=refund_case,
            actor_shipkart_merchant_id=shipkart_merchant_id,
            actor_merchant_id=merchant_id,
        )

        normalized_decision = (decision or "").strip().upper()
        if normalized_decision not in ("APPROVED", "REJECTED"):
            raise ComplianceViolationError(
                "Decision must be APPROVED or REJECTED.",
                rule_code="CASE-002",
                status_code=422,
            )

        clean_reason = ComplianceService.assert_rejection_reason(
            db,
            reason=reason,
            refund_case_id=refund_case.id,
            resource_type="refund_case",
            resource_id=refund_case.id,
            actor_type="MERCHANT",
            shipkart_actor_id=shipkart_merchant_user_id or shipkart_merchant_id,
        )

        now = utcnow()
        before_state = {
            "status": refund_case.status,
            "approved_amount": str(refund_case.approved_amount) if refund_case.approved_amount is not None else None,
        }

        final_amount: Decimal | None = None
        if normalized_decision == "APPROVED":
            raw_amount = approved_amount if approved_amount is not None else refund_case.requested_amount
            final_amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
            if refund_case.captured_amount is not None:
                ComplianceService.assert_within_refundable_balance(
                    db,
                    refund_case=refund_case,
                    requested_amount=final_amount,
                    actor_type="MERCHANT",
                    shipkart_actor_id=shipkart_merchant_user_id or shipkart_merchant_id,
                )
            elif final_amount <= Decimal("0.00"):
                raise ComplianceViolationError(
                    "Approved amount must be greater than zero.",
                    rule_code="REF-002",
                    status_code=422,
                )
            refund_case.approved_amount = final_amount
            refund_case.status = "APPROVED_BY_MERCHANT"
        else:
            final_amount = Decimal("0.00")
            refund_case.approved_amount = Decimal("0.00")
            refund_case.status = "REJECTED_BY_MERCHANT"
            refund_case.resolved_at = now
            refund_case.resolution_summary = clean_reason

        approval = RefundApproval(
            id=uuid.uuid4(),
            refund_case_id=refund_case.id,
            merchant_user_id=merchant_user_id,
            shipkart_merchant_user_id=shipkart_merchant_user_id,
            decision=normalized_decision,
            approved_amount=final_amount,
            currency=(
                currency
                or refund_case.currency
                or refund_case.original_currency
                or refund_case.paypal_currency
                or "USD"
            ).strip().upper(),
            reason=clean_reason,
            policy_version=policy_version,
            approval_reference=approval_reference,
            created_at=now,
        )
        db.add(approval)
        db.flush()

        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=refund_case.return_case_id,
                refund_case_id=refund_case.id,
                event_type=f"MERCHANT_REFUND_{normalized_decision}",
                source_type="MERCHANT",
                source_reference=str(approval.id),
                description=f"Merchant {normalized_decision.lower()} refund: {clean_reason}",
                event_data={
                    "decision": normalized_decision,
                    "approved_amount": str(final_amount),
                    "policy_version": policy_version,
                },
                occurred_at=now,
                recorded_at=now,
                verified=True,
            )
        )
        AuditService.record_audit(
            db,
            actor_type="MERCHANT",
            actor_id=merchant_user_id,
            shipkart_actor_id=shipkart_merchant_user_id or shipkart_merchant_id,
            action=f"MERCHANT_REFUND_{normalized_decision}",
            resource_type="refund_case",
            resource_id=refund_case.id,
            before_state=before_state,
            after_state={
                "status": refund_case.status,
                "approved_amount": str(final_amount),
                "approval_id": str(approval.id),
            },
        )
        db.commit()
        db.refresh(approval)
        return approval
