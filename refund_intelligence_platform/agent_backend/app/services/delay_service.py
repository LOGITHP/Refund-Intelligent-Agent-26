"""Deterministic Blueprint DELAY-001..DELAY-006 delay detection engine."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    IssuerInquiry,
    RefundApproval,
    RefundCase,
    RefundTimelineEvent,
    RefundTransaction,
    ReturnCase,
    ReturnInspection,
    ReturnShipment,
)
from app.services.timeline_service import ensure_utc

_CARRIER_SOURCE_TYPES = frozenset({"CARRIER", "CARRIER_SIMULATOR", "LOGISTICS"})


class DelayService:
    """Evaluates deterministic SLA delay rules DELAY-001 through DELAY-006."""

    def __init__(
        self,
        *,
        pickup_sla_hours: int = 48,
        transit_sla_hours: int = 72,
        inspection_sla_hours: int = 48,
        approval_sla_hours: int = 48,
        paypal_pending_sla_hours: int = 24,
        issuer_posting_sla_hours: int = 72,
    ) -> None:
        self.pickup_sla_hours = pickup_sla_hours
        self.transit_sla_hours = transit_sla_hours
        self.inspection_sla_hours = inspection_sla_hours
        self.approval_sla_hours = approval_sla_hours
        self.paypal_pending_sla_hours = paypal_pending_sla_hours
        self.issuer_posting_sla_hours = issuer_posting_sla_hours

    def evaluate_delays(
        self,
        db: Session,
        refund_case_id: uuid.UUID,
        *,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Evaluate all 6 Blueprint delay rules deterministically for a RefundCase."""
        refund_case = db.get(RefundCase, refund_case_id)
        if refund_case is None:
            raise ValueError(f"RefundCase '{refund_case_id}' not found.")

        now = ensure_utc(as_of) if as_of is not None else utcnow()

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

        tl_filters = [RefundTimelineEvent.refund_case_id == refund_case.id]
        if return_case is not None:
            tl_filters.append(RefundTimelineEvent.return_case_id == return_case.id)
        timeline_events = list(
            db.scalars(select(RefundTimelineEvent).where(or_(*tl_filters))).all()
        )

        latest_shipment = shipments[0] if shipments else None
        latest_inspection = inspections[0] if inspections else None
        latest_approval = approvals[0] if approvals else None
        completed_tx = next((t for t in transactions if (t.status or "").upper() == "COMPLETED"), None)
        pending_tx = next((t for t in transactions if (t.status or "").upper() == "PENDING"), None)
        latest_inquiry = inquiries[0] if inquiries else None

        delays: list[dict[str, Any]] = []
        missing_evidence_for_sla = False

        # ------------------------------------------------------------------
        # DELAY-001: Pickup overdue > 48h since return approval
        # ------------------------------------------------------------------
        if return_case is not None and return_case.approved_at is not None:
            ship_status = (latest_shipment.status or "").upper() if latest_shipment is not None else ""
            not_picked_up = latest_shipment is None or (
                latest_shipment.pickup_at is None
                and ship_status in {"PICKUP_SCHEDULED", "PICKUP_OVERDUE", "LABEL_CREATED"}
            )
            if not_picked_up:
                elapsed_h = (now - ensure_utc(return_case.approved_at)).total_seconds() / 3600.0
                if elapsed_h > self.pickup_sla_hours or ship_status == "PICKUP_OVERDUE":
                    owner = "CARRIER" if latest_shipment is not None else "MERCHANT"
                    action = (
                        "FOLLOW_UP_CARRIER_PICKUP"
                        if latest_shipment is not None
                        else "SCHEDULE_RETURN_PICKUP"
                    )
                    delays.append(
                        {
                            "rule_code": "DELAY-001",
                            "delay_owner": owner,
                            "recommended_action": action,
                            "sla_hours": self.pickup_sla_hours,
                            "hours_elapsed": round(max(elapsed_h, 0.0), 2),
                            "description": (
                                f"Return pickup overdue ({round(max(elapsed_h, 0.0), 1)}h since "
                                f"return approval, SLA {self.pickup_sla_hours}h)."
                            ),
                            "evidence": {
                                "approved_at": ensure_utc(return_case.approved_at).isoformat(),
                                "shipment_status": ship_status or "NO_SHIPMENT",
                            },
                        }
                    )

        # ------------------------------------------------------------------
        # DELAY-002: Carrier transit stalled > 72h since last carrier event
        # ------------------------------------------------------------------
        if latest_shipment is not None:
            ship_status = (latest_shipment.status or "").upper()
            in_transit_phase = (
                ship_status not in {"DELIVERED_TO_MERCHANT", "PICKUP_SCHEDULED", "PICKUP_OVERDUE", "LABEL_CREATED", "CANCELLED"}
                or (latest_shipment.pickup_at is not None and latest_shipment.delivered_at is None)
            )
            if in_transit_phase and ship_status != "DELIVERED_TO_MERCHANT":
                carrier_events = [
                    ev
                    for ev in timeline_events
                    if (ev.source_type or "").upper() in _CARRIER_SOURCE_TYPES
                    or (ev.event_type or "").upper().startswith(("CARRIER_", "SHIPMENT_", "PICKUP_"))
                ]
                last_carrier_ts: datetime | None = None
                if carrier_events:
                    last_carrier_ts = max(ensure_utc(ev.occurred_at) for ev in carrier_events)
                elif latest_shipment.last_synced_at is not None:
                    last_carrier_ts = ensure_utc(latest_shipment.last_synced_at)
                elif latest_shipment.pickup_at is not None:
                    last_carrier_ts = ensure_utc(latest_shipment.pickup_at)

                if last_carrier_ts is not None:
                    elapsed_h = (now - last_carrier_ts).total_seconds() / 3600.0
                    if elapsed_h > self.transit_sla_hours or ship_status in {"CARRIER_STALLED", "LOST_PACKAGE"}:
                        delays.append(
                            {
                                "rule_code": "DELAY-002",
                                "delay_owner": "CARRIER",
                                "recommended_action": "QUERY_CARRIER_TRACKING",
                                "sla_hours": self.transit_sla_hours,
                                "hours_elapsed": round(max(elapsed_h, 0.0), 2),
                                "description": (
                                    f"Carrier transit stalled ({round(max(elapsed_h, 0.0), 1)}h since "
                                    f"last carrier scan, SLA {self.transit_sla_hours}h)."
                                ),
                                "evidence": {
                                    "tracking_number": latest_shipment.tracking_number,
                                    "shipment_status": ship_status,
                                    "last_carrier_event_at": last_carrier_ts.isoformat(),
                                },
                            }
                        )
                elif ship_status in {"CARRIER_STALLED", "LOST_PACKAGE"}:
                    delays.append(
                        {
                            "rule_code": "DELAY-002",
                            "delay_owner": "CARRIER",
                            "recommended_action": "QUERY_CARRIER_TRACKING",
                            "sla_hours": self.transit_sla_hours,
                            "hours_elapsed": None,
                            "description": f"Carrier reported transit exception '{ship_status}'.",
                            "evidence": {
                                "tracking_number": latest_shipment.tracking_number,
                                "shipment_status": ship_status,
                            },
                        }
                    )
                else:
                    missing_evidence_for_sla = True

        # ------------------------------------------------------------------
        # DELAY-003: Warehouse inspection overdue > 48h after DELIVERED_TO_MERCHANT
        # ------------------------------------------------------------------
        if return_case is not None and not approvals and not transactions:
            is_delivered = (
                latest_shipment is not None
                and (
                    (latest_shipment.status or "").upper() == "DELIVERED_TO_MERCHANT"
                    or latest_shipment.delivered_at is not None
                )
            ) or (return_case.status or "").upper() in {"DELIVERED_TO_MERCHANT", "INSPECTION_PENDING"}

            insp_status = (latest_inspection.inspection_status or "").upper() if latest_inspection is not None else ""
            inspection_incomplete = latest_inspection is None or (
                latest_inspection.completed_at is None
                and insp_status in {"INSPECTION_PENDING", "PENDING", ""}
            )

            if is_delivered and inspection_incomplete:
                delivered_at: datetime | None = (
                    ensure_utc(latest_shipment.delivered_at)
                    if latest_shipment is not None and latest_shipment.delivered_at is not None
                    else None
                )
                if delivered_at is None:
                    delivery_events = [
                        ev
                        for ev in timeline_events
                        if (ev.event_type or "").upper() in {"DELIVERED_TO_MERCHANT", "CARRIER_DELIVERED"}
                    ]
                    if delivery_events:
                        delivered_at = max(ensure_utc(ev.occurred_at) for ev in delivery_events)

                if delivered_at is not None:
                    elapsed_h = (now - delivered_at).total_seconds() / 3600.0
                    if elapsed_h > self.inspection_sla_hours:
                        delays.append(
                            {
                                "rule_code": "DELAY-003",
                                "delay_owner": "MERCHANT",
                                "recommended_action": "ESCALATE_WAREHOUSE_INSPECTION",
                                "sla_hours": self.inspection_sla_hours,
                                "hours_elapsed": round(max(elapsed_h, 0.0), 2),
                                "description": (
                                    f"Warehouse inspection overdue ({round(max(elapsed_h, 0.0), 1)}h "
                                    f"since delivery, SLA {self.inspection_sla_hours}h)."
                                ),
                                "evidence": {
                                    "delivered_at": delivered_at.isoformat(),
                                    "inspection_status": insp_status or "NOT_STARTED",
                                },
                            }
                        )
                else:
                    missing_evidence_for_sla = True

        # ------------------------------------------------------------------
        # DELAY-004: Merchant refund approval overdue > 48h after inspection passed
        # ------------------------------------------------------------------
        case_status = (refund_case.status or "").upper()
        inspection_passed = (
            latest_inspection is not None
            and (latest_inspection.inspection_status or "").upper() in {"INSPECTION_PASSED", "PASSED", "APPROVED"}
        )
        approval_pending = (
            latest_approval is None
            and not transactions
            and case_status not in {"APPROVED", "MERCHANT_APPROVED", "REJECTED", "REJECTED_BY_MERCHANT", "CANCELLED"}
        )
        if inspection_passed and approval_pending:
            if latest_inspection is not None and latest_inspection.completed_at is not None:
                insp_completed_at = ensure_utc(latest_inspection.completed_at)
                elapsed_h = (now - insp_completed_at).total_seconds() / 3600.0
                if elapsed_h > self.approval_sla_hours:
                    delays.append(
                        {
                            "rule_code": "DELAY-004",
                            "delay_owner": "MERCHANT",
                            "recommended_action": "NOTIFY_MERCHANT_APPROVAL_SLA",
                            "sla_hours": self.approval_sla_hours,
                            "hours_elapsed": round(max(elapsed_h, 0.0), 2),
                            "description": (
                                f"Merchant refund approval overdue ({round(max(elapsed_h, 0.0), 1)}h "
                                f"after inspection passed, SLA {self.approval_sla_hours}h)."
                            ),
                            "evidence": {
                                "inspection_completed_at": insp_completed_at.isoformat(),
                                "refund_case_status": case_status,
                            },
                        }
                    )
            else:
                missing_evidence_for_sla = True

        # ------------------------------------------------------------------
        # DELAY-005: PayPal refund submission stuck PENDING > 24h
        # ------------------------------------------------------------------
        if completed_tx is None and pending_tx is not None:
            submitted_ts = ensure_utc(pending_tx.submitted_at or pending_tx.created_at)
            elapsed_h = (now - submitted_ts).total_seconds() / 3600.0
            if elapsed_h > self.paypal_pending_sla_hours:
                delays.append(
                    {
                        "rule_code": "DELAY-005",
                        "delay_owner": "PAYPAL",
                        "recommended_action": "RECONCILE_PAYPAL_REFUND",
                        "sla_hours": self.paypal_pending_sla_hours,
                        "hours_elapsed": round(max(elapsed_h, 0.0), 2),
                        "description": (
                            f"PayPal refund '{pending_tx.paypal_refund_id or pending_tx.id}' stuck "
                            f"PENDING ({round(max(elapsed_h, 0.0), 1)}h, SLA {self.paypal_pending_sla_hours}h)."
                        ),
                        "evidence": {
                            "paypal_refund_id": pending_tx.paypal_refund_id,
                            "submitted_at": submitted_ts.isoformat(),
                        },
                    }
                )

        # ------------------------------------------------------------------
        # DELAY-006: PayPal COMPLETED > 72h (or issuer DELAYED_POSTING) while bank credit unconfirmed
        # ------------------------------------------------------------------
        paypal_completed = completed_tx is not None or case_status in {"PAYPAL_COMPLETED", "REFUND_COMPLETED"}
        bank_confirmed = case_status in {"CONFIRMED_POSTED", "ISSUER_POSTED"}
        if latest_inquiry is not None:
            inq_status = (latest_inquiry.status or "").upper()
            resp_data = latest_inquiry.response_data or {}
            posting_status = str(resp_data.get("posting_status") or "").upper()
            if (
                inq_status in {"CREDIT_POSTED", "CONFIRMED_POSTED", "POSTED"}
                or resp_data.get("credit_posted") is True
                or posting_status in {"POSTED", "POSTED_TO_REPLACEMENT_CARD"}
            ):
                bank_confirmed = True

        if paypal_completed and not bank_confirmed:
            issuer_delayed = False
            if latest_inquiry is not None:
                inq_status = (latest_inquiry.status or "").upper()
                inq_scenario = str((latest_inquiry.response_data or {}).get("scenario") or "").upper()
                issuer_delayed = inq_status == "DELAYED_POSTING" or inq_scenario == "DELAYED_POSTING"

            pp_completed_at: datetime | None = None
            if completed_tx is not None:
                pp_completed_at = ensure_utc(completed_tx.completed_at or completed_tx.created_at)

            elapsed_h = (
                (now - pp_completed_at).total_seconds() / 3600.0
                if pp_completed_at is not None
                else None
            )

            if issuer_delayed or (elapsed_h is not None and elapsed_h > self.issuer_posting_sla_hours):
                delays.append(
                    {
                        "rule_code": "DELAY-006",
                        "delay_owner": "ISSUER_OR_BANK",
                        "recommended_action": "INITIATE_ISSUER_INQUIRY",
                        "sla_hours": self.issuer_posting_sla_hours,
                        "hours_elapsed": round(max(elapsed_h, 0.0), 2) if elapsed_h is not None else None,
                        "description": (
                            "PayPal refund is COMPLETED, but confirmed issuer/bank credit posting "
                            "is still unconfirmed beyond SLA. PayPal refund completion is not "
                            "confirmed bank credit posting."
                        ),
                        "evidence": {
                            "paypal_completed_at": pp_completed_at.isoformat() if pp_completed_at else None,
                            "issuer_inquiry_status": latest_inquiry.status if latest_inquiry else "NONE",
                            "issuer_delayed_posting": issuer_delayed,
                        },
                    }
                )
            elif pp_completed_at is None and not issuer_delayed:
                missing_evidence_for_sla = True

        if not delays:
            if return_case is None and not transactions and not approvals:
                missing_evidence_for_sla = True
            return {
                "refund_case_id": str(refund_case.id),
                "as_of": now.isoformat(),
                "delay_detected": False,
                "delay_owner": "UNKNOWN" if missing_evidence_for_sla else "NONE",
                "triggered_rules": [],
                "delays": [],
            }

        return {
            "refund_case_id": str(refund_case.id),
            "as_of": now.isoformat(),
            "delay_detected": True,
            "delay_owner": delays[0]["delay_owner"],
            "triggered_rules": [d["rule_code"] for d in delays],
            "delays": delays,
        }
