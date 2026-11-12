"""Deterministic stage-remaining ETA calculator and snapshot persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    IssuerInquiry,
    RefundApproval,
    RefundCase,
    RefundEtaEstimate,
    RefundTransaction,
    ReturnCase,
    ReturnInspection,
    ReturnShipment,
)
from app.services.timeline_service import ensure_utc

_REJECTED_STATUSES = frozenset(
    {
        "RETURN_REJECTED",
        "REJECTED_BY_MERCHANT",
        "INSPECTION_FAILED",
        "FAILED",
        "REJECTED",
        "CANCELLED",
        "CLOSED_REJECTED",
    }
)

_INSPECTION_PASSED_STATUSES = frozenset({"INSPECTION_PASSED", "PASSED", "APPROVED"})

_APPROVED_CASE_STATUSES = frozenset(
    {
        "APPROVED",
        "MERCHANT_APPROVED",
        "REFUND_INITIATED",
        "PAYPAL_PENDING",
        "PAYPAL_COMPLETED",
        "REFUND_COMPLETED",
        "COMPLETED",
        "CONFIRMED_POSTED",
        "ISSUER_POSTED",
    }
)

_PAYPAL_COMPLETED_CASE_STATUSES = frozenset(
    {"PAYPAL_COMPLETED", "REFUND_COMPLETED", "COMPLETED", "CONFIRMED_POSTED", "ISSUER_POSTED"}
)

_ISSUER_POSTED_STATUSES = frozenset({"CREDIT_POSTED", "CONFIRMED_POSTED", "POSTED"})

_ISSUER_BLOCKED_STATUSES = frozenset(
    {
        "UNAVAILABLE",
        "ISSUER_UNAVAILABLE",
        "INSUFFICIENT_EVIDENCE",
        "REFERENCE_MISMATCH",
        "MISSING_TRANSACTION_REFERENCE",
    }
)


def _parse_iso_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str) and value.strip():
        try:
            return ensure_utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


class ETAService:
    """Deterministic stage-remaining refund ETA calculator (zero LLM, zero guessing)."""

    PICKUP_SLA_HOURS = 48

    def compute_eta(
        self,
        db: Session,
        refund_case_id: uuid.UUID,
        *,
        estimated_from: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute deterministic ETA payload for a RefundCase without persisting."""
        refund_case = db.get(RefundCase, refund_case_id)
        if refund_case is None:
            raise ValueError(f"RefundCase '{refund_case_id}' not found.")

        base_time = ensure_utc(estimated_from) if estimated_from is not None else utcnow()

        return_case = (
            db.get(ReturnCase, refund_case.return_case_id)
            if refund_case.return_case_id is not None
            else None
        )
        shipments = (
            list(
                db.scalars(
                    select(ReturnShipment)
                    .where(ReturnShipment.return_case_id == return_case.id)
                    .order_by(ReturnShipment.created_at.desc())
                ).all()
            )
            if return_case is not None
            else []
        )
        inspections = (
            list(
                db.scalars(
                    select(ReturnInspection)
                    .where(ReturnInspection.return_case_id == return_case.id)
                    .order_by(ReturnInspection.created_at.desc())
                ).all()
            )
            if return_case is not None
            else []
        )
        approvals = list(
            db.scalars(
                select(RefundApproval)
                .where(RefundApproval.refund_case_id == refund_case.id)
                .order_by(RefundApproval.created_at.desc())
            ).all()
        )
        transactions = list(
            db.scalars(
                select(RefundTransaction)
                .where(RefundTransaction.refund_case_id == refund_case.id)
                .order_by(RefundTransaction.created_at.desc())
            ).all()
        )
        inquiries = list(
            db.scalars(
                select(IssuerInquiry)
                .where(IssuerInquiry.refund_case_id == refund_case.id)
                .order_by(IssuerInquiry.updated_at.desc(), IssuerInquiry.created_at.desc())
            ).all()
        )

        latest_shipment = shipments[0] if shipments else None
        latest_inspection = inspections[0] if inspections else None
        latest_approval = approvals[0] if approvals else None
        completed_tx = next((t for t in transactions if (t.status or "").upper() == "COMPLETED"), None)
        latest_tx = transactions[0] if transactions else None
        latest_inquiry = inquiries[0] if inquiries else None

        blocking_reasons: list[str] = []
        basis: list[dict[str, Any]] = []

        # ------------------------------------------------------------------
        # Check Confirmed Issuer Bank Credit Posting first (terminal success)
        # ------------------------------------------------------------------
        issuer_posted = (refund_case.status or "").upper() in {"CONFIRMED_POSTED", "ISSUER_POSTED"}
        posted_at: datetime | None = None
        if latest_inquiry is not None:
            inq_status = (latest_inquiry.status or "").upper()
            resp_data = latest_inquiry.response_data or {}
            posting_status = str(resp_data.get("posting_status") or "").upper()
            if (
                inq_status in _ISSUER_POSTED_STATUSES
                or resp_data.get("credit_posted") is True
                or posting_status in {"POSTED", "POSTED_TO_REPLACEMENT_CARD"}
            ):
                issuer_posted = True
                posted_at = (
                    _parse_iso_dt(resp_data.get("posted_at"))
                    or (ensure_utc(latest_inquiry.updated_at) if latest_inquiry.updated_at else None)
                )

        if issuer_posted:
            confirmed_ts = (
                posted_at
                or (ensure_utc(refund_case.resolved_at) if refund_case.resolved_at else None)
                or base_time
            )
            basis.append(
                {
                    "stage": "ISSUER_POSTING",
                    "status": "COMPLETED",
                    "min_hours": 0,
                    "max_hours": 0,
                    "detail": "Issuer confirmed refund credit posted to customer account.",
                }
            )
            return {
                "refund_case_id": refund_case.id,
                "eta_status": "COMPLETED",
                "estimated_from": base_time,
                "earliest_at": confirmed_ts,
                "latest_at": confirmed_ts,
                "confidence_level": "HIGH",
                "basis": basis,
                "explanation": "Refund credit confirmed posted by issuing bank.",
            }

        # ------------------------------------------------------------------
        # Check Terminal / Hard Blockers (NOT_ESTIMABLE)
        # ------------------------------------------------------------------
        case_status = (refund_case.status or "").upper()
        if case_status in _REJECTED_STATUSES or case_status == "INSUFFICIENT_EVIDENCE":
            blocking_reasons.append(f"REFUND_CASE_{case_status}")

        if return_case is not None:
            ret_status = (return_case.status or "").upper()
            if ret_status in _REJECTED_STATUSES or ret_status == "LOST_PACKAGE":
                blocking_reasons.append(f"RETURN_CASE_{ret_status}")

        if latest_shipment is not None:
            ship_status = (latest_shipment.status or "").upper()
            if ship_status == "LOST_PACKAGE":
                blocking_reasons.append("CARRIER_LOST_PACKAGE")
            elif ship_status == "PICKUP_OVERDUE" and latest_shipment.pickup_at is None:
                ref_ts = (
                    ensure_utc(return_case.approved_at)
                    if return_case and return_case.approved_at
                    else ensure_utc(latest_shipment.created_at)
                )
                overdue_hours = (base_time - ref_ts).total_seconds() / 3600.0
                if overdue_hours > self.PICKUP_SLA_HOURS or not (latest_shipment.tracking_number or "").strip():
                    blocking_reasons.append("PICKUP_OVERDUE_WITHOUT_ACTIVE_TRACKING")
        elif return_case is not None:
            ret_status = (return_case.status or "").upper()
            if ret_status == "RETURN_APPROVED" and return_case.approved_at is not None:
                overdue_hours = (base_time - ensure_utc(return_case.approved_at)).total_seconds() / 3600.0
                if overdue_hours > self.PICKUP_SLA_HOURS:
                    blocking_reasons.append("PICKUP_OVERDUE_WITHOUT_ACTIVE_TRACKING")

        if latest_inspection is not None:
            insp_status = (latest_inspection.inspection_status or "").upper()
            if insp_status in _REJECTED_STATUSES or insp_status == "INSUFFICIENT_EVIDENCE":
                blocking_reasons.append(f"INSPECTION_{insp_status}")

        if latest_approval is not None and (latest_approval.decision or "").upper() == "REJECTED":
            blocking_reasons.append("MERCHANT_APPROVAL_REJECTED")

        if completed_tx is None and latest_tx is not None:
            tx_status = (latest_tx.status or "").upper()
            if tx_status in {"FAILED", "DENIED", "CANCELLED", "REVERSED"}:
                blocking_reasons.append(f"PAYPAL_REFUND_{tx_status}")

        if latest_inquiry is not None:
            inq_status = (latest_inquiry.status or "").upper()
            resp_data = latest_inquiry.response_data or {}
            err_code = str(resp_data.get("error_code") or "").upper()
            svc_status = str(resp_data.get("issuer_service_status") or "").upper()
            if (
                inq_status in _ISSUER_BLOCKED_STATUSES
                or err_code in _ISSUER_BLOCKED_STATUSES
                or svc_status == "UNAVAILABLE"
            ):
                reason = err_code if err_code in _ISSUER_BLOCKED_STATUSES else f"ISSUER_{inq_status}"
                blocking_reasons.append(reason)

        if blocking_reasons:
            deduped_reasons = list(dict.fromkeys(blocking_reasons))
            basis.append(
                {
                    "stage": "BLOCKED",
                    "status": "BLOCKED",
                    "blocking_reasons": deduped_reasons,
                    "detail": "ETA cannot be deterministically estimated due to blocking state(s).",
                }
            )
            return {
                "refund_case_id": refund_case.id,
                "eta_status": "NOT_ESTIMABLE",
                "estimated_from": base_time,
                "earliest_at": None,
                "latest_at": None,
                "confidence_level": "LOW",
                "basis": basis,
                "explanation": f"ETA not estimable: {', '.join(deduped_reasons)}.",
            }

        # ------------------------------------------------------------------
        # Stage-Remaining Deterministic Calculation (Completed Stages = 0h)
        # ------------------------------------------------------------------
        min_hours = 0
        max_hours = 0
        has_delay_signal = False
        remaining_count = 0

        has_physical_return = return_case is not None or (refund_case.case_type or "").upper() == "RETURN_REFUND"
        ret_status = (return_case.status or "").upper() if return_case is not None else ""

        # Stage A: Carrier Transit
        stage_a_done = (
            not has_physical_return
            or (latest_shipment is not None and (latest_shipment.status or "").upper() == "DELIVERED_TO_MERCHANT")
            or ret_status in {"DELIVERED_TO_MERCHANT", "INSPECTION_PENDING", "INSPECTION_PASSED", "COMPLETED"}
            or completed_tx is not None
        )
        if not has_physical_return:
            basis.append({"stage": "CARRIER_TRANSIT", "status": "NOT_APPLICABLE", "min_hours": 0, "max_hours": 0})
        elif stage_a_done:
            basis.append({"stage": "CARRIER_TRANSIT", "status": "COMPLETED", "min_hours": 0, "max_hours": 0})
        else:
            ship_status = (latest_shipment.status or "").upper() if latest_shipment is not None else "PENDING"
            if ship_status == "OUT_FOR_DELIVERY":
                a_min, a_max = 4, 24
            elif ship_status in {"CARRIER_STALLED", "PICKUP_OVERDUE"}:
                a_min, a_max = 24, 96
                has_delay_signal = True
            else:
                a_min, a_max = 12, 72
            min_hours += a_min
            max_hours += a_max
            remaining_count += 1
            basis.append(
                {
                    "stage": "CARRIER_TRANSIT",
                    "status": "REMAINING",
                    "min_hours": a_min,
                    "max_hours": a_max,
                    "shipment_status": ship_status,
                }
            )

        # Stage B: Warehouse Inspection
        stage_b_done = (
            not has_physical_return
            or (
                latest_inspection is not None
                and (latest_inspection.inspection_status or "").upper() in _INSPECTION_PASSED_STATUSES
            )
            or ret_status == "INSPECTION_PASSED"
            or (latest_approval is not None and (latest_approval.decision or "").upper() == "APPROVED")
            or completed_tx is not None
        )
        if not has_physical_return:
            basis.append({"stage": "WAREHOUSE_INSPECTION", "status": "NOT_APPLICABLE", "min_hours": 0, "max_hours": 0})
        elif stage_b_done:
            basis.append({"stage": "WAREHOUSE_INSPECTION", "status": "COMPLETED", "min_hours": 0, "max_hours": 0})
        else:
            b_min, b_max = 4, 24
            min_hours += b_min
            max_hours += b_max
            remaining_count += 1
            basis.append({"stage": "WAREHOUSE_INSPECTION", "status": "REMAINING", "min_hours": b_min, "max_hours": b_max})

        # Stage C: Merchant Approval
        stage_c_done = (
            (latest_approval is not None and (latest_approval.decision or "").upper() == "APPROVED")
            or case_status in _APPROVED_CASE_STATUSES
            or completed_tx is not None
            or latest_tx is not None
        )
        if stage_c_done:
            basis.append({"stage": "MERCHANT_APPROVAL", "status": "COMPLETED", "min_hours": 0, "max_hours": 0})
        else:
            c_min, c_max = 2, 24
            min_hours += c_min
            max_hours += c_max
            remaining_count += 1
            basis.append({"stage": "MERCHANT_APPROVAL", "status": "REMAINING", "min_hours": c_min, "max_hours": c_max})

        # Stage D: PayPal Refund Submission / Settlement
        stage_d_done = completed_tx is not None or case_status in _PAYPAL_COMPLETED_CASE_STATUSES
        if stage_d_done:
            basis.append({"stage": "PAYPAL_REFUND", "status": "COMPLETED", "min_hours": 0, "max_hours": 0})
        else:
            d_min, d_max = 1, 12
            min_hours += d_min
            max_hours += d_max
            remaining_count += 1
            basis.append(
                {
                    "stage": "PAYPAL_REFUND",
                    "status": "REMAINING",
                    "min_hours": d_min,
                    "max_hours": d_max,
                    "paypal_status": (latest_tx.status if latest_tx is not None else "NOT_SUBMITTED"),
                }
            )

        # Stage E: Card Issuer Posting (not completed because issuer_posted was False above)
        inq_status = (latest_inquiry.status or "").upper() if latest_inquiry is not None else ""
        inq_scenario = (
            str((latest_inquiry.response_data or {}).get("scenario") or "").upper()
            if latest_inquiry is not None
            else ""
        )
        if inq_status == "DELAYED_POSTING" or inq_scenario == "DELAYED_POSTING":
            e_min, e_max = 48, 168
            has_delay_signal = True
        elif inq_status == "REPLACED_CARD" or inq_scenario == "REPLACED_CARD":
            e_min, e_max = 72, 240
            has_delay_signal = True
        else:
            e_min, e_max = 24, 120

        min_hours += e_min
        max_hours += e_max
        remaining_count += 1
        basis.append(
            {
                "stage": "ISSUER_POSTING",
                "status": "REMAINING",
                "min_hours": e_min,
                "max_hours": e_max,
                "issuer_status": inq_status or "UNCONFIRMED",
            }
        )

        if has_delay_signal:
            confidence = "LOW"
        elif remaining_count == 1 and stage_d_done:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

        earliest_at = base_time + timedelta(hours=min_hours)
        latest_at = base_time + timedelta(hours=max_hours)
        remaining_names = [b["stage"] for b in basis if b.get("status") == "REMAINING"]
        explanation = (
            f"Deterministic stage-remaining ETA ({min_hours}h-{max_hours}h) across remaining stages: "
            f"{', '.join(remaining_names)}."
        )

        return {
            "refund_case_id": refund_case.id,
            "eta_status": "ESTIMATED",
            "estimated_from": base_time,
            "earliest_at": earliest_at,
            "latest_at": latest_at,
            "confidence_level": confidence,
            "basis": basis,
            "explanation": explanation,
        }

    def compute_and_persist_eta(
        self,
        db: Session,
        refund_case_id: uuid.UUID,
        *,
        estimated_from: datetime | None = None,
    ) -> RefundEtaEstimate:
        """Compute deterministic ETA, deactivate prior current estimates, and persist snapshot."""
        computed = self.compute_eta(db, refund_case_id, estimated_from=estimated_from)

        db.execute(
            update(RefundEtaEstimate)
            .where(
                RefundEtaEstimate.refund_case_id == refund_case_id,
                RefundEtaEstimate.is_current.is_(True),
            )
            .values(is_current=False)
        )

        snapshot = RefundEtaEstimate(
            refund_case_id=refund_case_id,
            eta_status=computed["eta_status"],
            estimated_from=computed["estimated_from"],
            earliest_at=computed["earliest_at"],
            latest_at=computed["latest_at"],
            confidence_level=computed["confidence_level"],
            basis=computed["basis"],
            explanation=computed["explanation"],
            is_current=True,
        )
        db.add(snapshot)
        db.flush()
        return snapshot
