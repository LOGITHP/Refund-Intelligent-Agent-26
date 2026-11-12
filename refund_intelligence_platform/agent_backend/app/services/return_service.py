"""Physical return lifecycle service with partial-item quantity & inspection controls."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    RefundTimelineEvent,
    ReturnCase,
    ReturnCaseItem,
    ReturnInspection,
)
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService, ComplianceViolationError

ALLOWED_RETURN_TRANSITIONS: dict[str, set[str]] = {
    "RETURN_REQUESTED": {"RETURN_APPROVED", "RETURN_REJECTED"},
    "RETURN_APPROVED": {"PICKUP_SCHEDULED", "RETURN_REJECTED"},
    "PICKUP_SCHEDULED": {"PICKED_UP", "RETURN_REJECTED"},
    "PICKED_UP": {"IN_TRANSIT"},
    "IN_TRANSIT": {"DELIVERED_TO_MERCHANT"},
    "DELIVERED_TO_MERCHANT": {"PRODUCT_RECEIVED", "INSPECTION_PENDING"},
    "PRODUCT_RECEIVED": {"INSPECTION_PENDING"},
    "INSPECTION_PENDING": {"INSPECTION_COMPLETED"},
    "INSPECTION_COMPLETED": {"REFUND_ELIGIBILITY_DECISION"},
}

INSPECTABLE_RETURN_STATES = frozenset(
    {"DELIVERED_TO_MERCHANT", "PRODUCT_RECEIVED", "INSPECTION_PENDING"}
)


class ReturnService:
    """Manages physical return requests, state transitions, and warehouse inspections."""

    @staticmethod
    def _compute_existing_returned_qty(
        db: Session,
        *,
        shipkart_order_id: int | None,
        shipkart_order_item_id: int | None,
        order_item_id: uuid.UUID | None,
    ) -> int:
        stmt = (
            select(func.coalesce(func.sum(ReturnCaseItem.quantity_requested), 0))
            .join(ReturnCase, ReturnCaseItem.return_case_id == ReturnCase.id)
            .where(ReturnCase.status != "RETURN_REJECTED")
        )
        if shipkart_order_item_id is not None:
            stmt = stmt.where(ReturnCaseItem.shipkart_order_item_id == shipkart_order_item_id)
            if shipkart_order_id is not None:
                stmt = stmt.where(ReturnCase.shipkart_order_id == shipkart_order_id)
        elif order_item_id is not None:
            stmt = stmt.where(ReturnCaseItem.order_item_id == order_item_id)
        else:
            return 0
        return int(db.scalar(stmt) or 0)

    @classmethod
    def create_return_case(
        cls,
        db: Session,
        *,
        shipkart_order_id: int | None = None,
        shipkart_customer_id: int | None = None,
        shipkart_merchant_id: int | None = None,
        shipkart_return_id: int | None = None,
        order_id: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        merchant_id: uuid.UUID | None = None,
        reason_code: str,
        customer_description: str = "",
        items: list[dict[str, Any]],
    ) -> ReturnCase:
        """Create a physical return case enforcing cumulative quantity <= purchased quantity."""
        if not items:
            raise ComplianceViolationError(
                "At least one return item is required.",
                rule_code="QTY-001",
                status_code=422,
            )

        now = utcnow()
        return_case = ReturnCase(
            id=uuid.uuid4(),
            order_id=order_id,
            customer_id=customer_id,
            merchant_id=merchant_id,
            shipkart_return_id=shipkart_return_id,
            shipkart_order_id=shipkart_order_id,
            shipkart_customer_id=shipkart_customer_id,
            shipkart_merchant_id=shipkart_merchant_id,
            reason_code=reason_code,
            customer_description=customer_description,
            status="RETURN_REQUESTED",
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(return_case)
        db.flush()

        in_batch_qty: dict[tuple[Any, Any], int] = {}
        for item in items:
            sk_item_id = item.get("shipkart_order_item_id")
            item_uuid = item.get("order_item_id")
            qty_req = int(item.get("quantity_requested", 0))
            purchased_qty = int(item.get("purchased_quantity", 0))

            if qty_req <= 0 or purchased_qty <= 0:
                raise ComplianceService.record_violation_and_raise(
                    db,
                    rule_code="QTY-001",
                    message="Requested and purchased quantities must be positive integers.",
                    status_code=422,
                    resource_type="return_case",
                    resource_id=return_case.id,
                    actor_type="CUSTOMER",
                    shipkart_actor_id=shipkart_customer_id,
                )

            existing_qty = cls._compute_existing_returned_qty(
                db,
                shipkart_order_id=shipkart_order_id,
                shipkart_order_item_id=sk_item_id,
                order_item_id=item_uuid,
            )
            batch_key = (sk_item_id, item_uuid)
            prior_in_batch = in_batch_qty.get(batch_key, 0)
            total_qty = existing_qty + prior_in_batch + qty_req
            if total_qty > purchased_qty:
                raise ComplianceService.record_violation_and_raise(
                    db,
                    rule_code="QTY-001",
                    message=(
                        f"Cumulative returned quantity ({total_qty}) exceeds purchased quantity ({purchased_qty})."
                    ),
                    status_code=422,
                    resource_type="return_case",
                    resource_id=return_case.id,
                    actor_type="CUSTOMER",
                    shipkart_actor_id=shipkart_customer_id,
                    details={
                        "shipkart_order_item_id": sk_item_id,
                        "existing_qty": existing_qty,
                        "requested_qty": qty_req,
                        "purchased_qty": purchased_qty,
                    },
                )
            in_batch_qty[batch_key] = prior_in_batch + qty_req

            if item.get("refund_amount_requested") is not None:
                req_amount = Decimal(str(item["refund_amount_requested"])).quantize(Decimal("0.01"))
            elif item.get("unit_price") is not None:
                unit_price = Decimal(str(item["unit_price"]))
                req_amount = (unit_price * qty_req).quantize(Decimal("0.01"))
            else:
                req_amount = Decimal("0.00")

            case_item = ReturnCaseItem(
                id=uuid.uuid4(),
                return_case_id=return_case.id,
                order_item_id=item_uuid,
                shipkart_order_item_id=sk_item_id,
                quantity_requested=qty_req,
                condition_reported=str(item.get("condition_reported", "UNKNOWN")),
                refund_amount_requested=req_amount,
            )
            db.add(case_item)

        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=return_case.id,
                event_type="RETURN_REQUESTED",
                source_type="CUSTOMER",
                description="Customer submitted return request.",
                event_data={"reason_code": reason_code, "item_count": len(items)},
                occurred_at=now,
                recorded_at=now,
                verified=True,
            )
        )
        AuditService.record_audit(
            db,
            actor_type="CUSTOMER",
            shipkart_actor_id=shipkart_customer_id,
            action="RETURN_CASE_CREATED",
            resource_type="return_case",
            resource_id=return_case.id,
            after_state={"status": return_case.status, "reason_code": reason_code},
        )
        db.commit()
        db.refresh(return_case)
        return return_case

    @classmethod
    def transition_return_status(
        cls,
        db: Session,
        return_case: ReturnCase,
        target_status: str,
        *,
        actor_type: str,
        shipkart_actor_id: int | None = None,
        actor_shipkart_merchant_id: int | None = None,
        reason: str | None = None,
    ) -> ReturnCase:
        """Transition a physical return case through allowed lifecycle states."""
        if actor_type.upper() == "MERCHANT" and actor_shipkart_merchant_id is not None:
            ComplianceService.assert_merchant_access(
                db,
                case=return_case,
                actor_shipkart_merchant_id=actor_shipkart_merchant_id,
            )

        clean_target = target_status.strip().upper()
        if clean_target == "RETURN_REJECTED":
            ComplianceService.assert_rejection_reason(
                db,
                reason=reason,
                resource_type="return_case",
                resource_id=return_case.id,
                actor_type=actor_type,
                shipkart_actor_id=shipkart_actor_id,
            )

        allowed = ALLOWED_RETURN_TRANSITIONS.get(return_case.status, set())
        if clean_target not in allowed:
            raise ComplianceViolationError(
                f"Invalid return state transition from {return_case.status} to {clean_target}.",
                rule_code="STATE-001",
                status_code=422,
                details={"current_status": return_case.status, "target_status": clean_target},
            )

        now = utcnow()
        before = {"status": return_case.status}
        return_case.status = clean_target
        return_case.updated_at = now
        if clean_target == "RETURN_APPROVED":
            return_case.approved_at = now
        elif clean_target == "RETURN_REJECTED":
            return_case.closed_at = now

        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=return_case.id,
                event_type=clean_target,
                source_type=actor_type.upper(),
                description=reason or f"Return transitioned to {clean_target}.",
                event_data={"from_status": before["status"], "to_status": clean_target},
                occurred_at=now,
                recorded_at=now,
                verified=True,
            )
        )
        AuditService.record_audit(
            db,
            actor_type=actor_type.upper(),
            shipkart_actor_id=shipkart_actor_id,
            action=f"RETURN_STATUS_{clean_target}",
            resource_type="return_case",
            resource_id=return_case.id,
            before_state=before,
            after_state={"status": clean_target, "reason": reason},
        )
        db.commit()
        db.refresh(return_case)
        return return_case

    @classmethod
    def record_inspection(
        cls,
        db: Session,
        return_case_id: uuid.UUID,
        *,
        shipkart_merchant_id: int | None = None,
        merchant_id: uuid.UUID | None = None,
        inspector_id: uuid.UUID | None = None,
        shipkart_inspector_id: int | None = None,
        condition_result: str,
        notes: str = "",
        completed: bool = True,
    ) -> ReturnInspection:
        """Record merchant warehouse inspection outcome enforcing AUTH-001."""
        return_case = db.get(ReturnCase, return_case_id)
        if return_case is None:
            raise ComplianceViolationError(
                "Return case not found.",
                rule_code="CASE-404",
                status_code=404,
            )

        ComplianceService.assert_merchant_access(
            db,
            case=return_case,
            actor_shipkart_merchant_id=shipkart_merchant_id,
            actor_merchant_id=merchant_id,
        )

        if return_case.status not in INSPECTABLE_RETURN_STATES:
            raise ComplianceViolationError(
                f"Cannot inspect return case in status {return_case.status}.",
                rule_code="STATE-002",
                status_code=422,
                details={"current_status": return_case.status},
            )

        now = utcnow()
        inspection = ReturnInspection(
            id=uuid.uuid4(),
            return_case_id=return_case.id,
            inspector_id=inspector_id,
            shipkart_inspector_id=shipkart_inspector_id,
            inspection_status="INSPECTION_COMPLETED" if completed else "INSPECTION_PENDING",
            condition_result=condition_result.strip().upper(),
            notes=notes,
            completed_at=now if completed else None,
            created_at=now,
        )
        db.add(inspection)

        before = {"status": return_case.status}
        return_case.status = "INSPECTION_COMPLETED" if completed else "INSPECTION_PENDING"
        return_case.updated_at = now

        db.add(
            RefundTimelineEvent(
                id=uuid.uuid4(),
                return_case_id=return_case.id,
                event_type=return_case.status,
                source_type="MERCHANT",
                source_reference=str(inspection.id),
                description=f"Warehouse inspection recorded: {inspection.condition_result}.",
                event_data={"condition_result": inspection.condition_result, "completed": completed},
                occurred_at=now,
                recorded_at=now,
                verified=True,
            )
        )
        AuditService.record_audit(
            db,
            actor_type="MERCHANT",
            actor_id=inspector_id,
            shipkart_actor_id=shipkart_inspector_id or shipkart_merchant_id,
            action="RETURN_INSPECTION_RECORDED",
            resource_type="return_case",
            resource_id=return_case.id,
            before_state=before,
            after_state={"status": return_case.status, "condition_result": inspection.condition_result},
        )
        db.commit()
        db.refresh(inspection)
        return inspection
