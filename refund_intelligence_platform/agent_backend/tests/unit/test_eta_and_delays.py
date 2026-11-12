"""Unit tests for Task 6: TimelineService, ETAService, DelayService, ReconciliationService."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    IssuerInquiry,
    ProcessedWebhookEvent,
    RefundApproval,
    RefundCase,
    RefundEtaEstimate,
    RefundTimelineEvent,
    RefundTransaction,
    ReturnCase,
    ReturnInspection,
    ReturnShipment,
)
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.reconciliation_service import ReconciliationService
from app.services.timeline_service import TimelineService


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(bind=engine)


def _create_case_bundle(
    session: Session,
    *,
    now: datetime,
    return_status: str = "RETURN_APPROVED",
    refund_status: str = "INVESTIGATING",
    approved_at: datetime | None = None,
) -> tuple[ReturnCase, RefundCase]:
    ret = ReturnCase(
        id=uuid.uuid4(),
        shipkart_order_id=1001,
        shipkart_customer_id=2001,
        shipkart_merchant_id=3001,
        reason_code="DAMAGED",
        customer_description="Item arrived damaged",
        status=return_status,
        requested_at=now - timedelta(days=5),
        approved_at=approved_at,
    )
    session.add(ret)
    session.flush()

    ref = RefundCase(
        id=uuid.uuid4(),
        return_case_id=ret.id,
        shipkart_order_id=1001,
        shipkart_customer_id=2001,
        shipkart_merchant_id=3001,
        case_type="RETURN_REFUND",
        status=refund_status,
        requested_amount=Decimal("45.00"),
        currency="USD",
        original_currency="INR",
        paypal_currency="USD",
        paypal_order_id="PP-ORD-1001",
        paypal_capture_id="CAP-1001",
        reason="Damaged item refund",
        opened_at=now - timedelta(days=4),
    )
    session.add(ref)
    session.flush()
    return ret, ref


# ---------------------------------------------------------------------------
# 1. TimelineService Tests
# ---------------------------------------------------------------------------


def test_timeline_preserves_dual_timestamps_separates_tracks_and_deduplicates() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        ret, ref = _create_case_bundle(session, now=now)
        svc = TimelineService()

        carrier_occurred = now - timedelta(hours=36)
        paypal_occurred = now - timedelta(hours=6)

        ev1 = svc.record_event(
            session,
            return_case_id=ret.id,
            event_type="CARRIER_PICKED_UP",
            source_type="CARRIER",
            source_reference="TRK-EVT-001",
            description="Parcel picked up by BlueDart",
            occurred_at=carrier_occurred,
            event_data={"location": "Bengaluru"},
            verified=True,
        )
        # Duplicate (source_type, source_reference) for same return_case_id must return existing row
        ev1_dup = svc.record_event(
            session,
            return_case_id=ret.id,
            event_type="CARRIER_PICKED_UP",
            source_type="CARRIER",
            source_reference="TRK-EVT-001",
            description="Duplicate pickup webhook",
            occurred_at=carrier_occurred + timedelta(minutes=5),
            verified=True,
        )
        assert ev1_dup.id == ev1.id

        # Dual timestamps preserved: occurred_at is source time, recorded_at is system recording time
        ev1_occurred = ev1.occurred_at.replace(tzinfo=timezone.utc) if ev1.occurred_at.tzinfo is None else ev1.occurred_at
        ev1_recorded = ev1.recorded_at.replace(tzinfo=timezone.utc) if ev1.recorded_at.tzinfo is None else ev1.recorded_at
        assert ev1_occurred == carrier_occurred
        assert ev1_recorded != carrier_occurred
        assert ev1_recorded >= carrier_occurred

        # Financial event linked to refund_case_id
        ev2 = svc.record_event(
            session,
            refund_case_id=ref.id,
            event_type="PAYPAL_REFUND_COMPLETED",
            source_type="PAYPAL_WEBHOOK",
            source_reference="WH-PP-001",
            description="PayPal capture refunded",
            occurred_at=paypal_occurred,
            verified=True,
        )
        # Duplicate financial event
        ev2_dup = svc.record_event(
            session,
            refund_case_id=ref.id,
            event_type="PAYPAL_REFUND_COMPLETED",
            source_type="PAYPAL_WEBHOOK",
            source_reference="WH-PP-001",
            description="PayPal capture refunded duplicate",
            occurred_at=paypal_occurred,
            verified=True,
        )
        assert ev2_dup.id == ev2.id

        # Earlier physical event recorded AFTER financial event to prove merged sort is by occurred_at
        delivery_occurred = now - timedelta(hours=18)
        svc.record_event(
            session,
            return_case_id=ret.id,
            event_type="DELIVERED_TO_MERCHANT",
            source_type="CARRIER",
            source_reference="TRK-EVT-002",
            description="Parcel delivered to merchant dock",
            occurred_at=delivery_occurred,
            verified=True,
        )
        session.commit()

        unified = svc.get_unified_timeline(session, refund_case_id=ref.id)
        assert len(unified["physical_return_events"]) == 2
        assert len(unified["financial_refund_events"]) == 1
        assert len(unified["merged_events"]) == 3

        assert [e["event_type"] for e in unified["physical_return_events"]] == [
            "CARRIER_PICKED_UP",
            "DELIVERED_TO_MERCHANT",
        ]
        assert [e["event_type"] for e in unified["financial_refund_events"]] == [
            "PAYPAL_REFUND_COMPLETED",
        ]
        # Merged timeline strictly ordered by occurred_at
        assert [e["event_type"] for e in unified["merged_events"]] == [
            "CARRIER_PICKED_UP",
            "DELIVERED_TO_MERCHANT",
            "PAYPAL_REFUND_COMPLETED",
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2. ETAService Tests
# ---------------------------------------------------------------------------


def test_eta_excludes_completed_stage_time_and_rotates_current_snapshot() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        ret, ref = _create_case_bundle(
            session,
            now=now,
            return_status="INSPECTION_PASSED",
            refund_status="MERCHANT_APPROVAL_PENDING",
            approved_at=now - timedelta(days=10),
        )
        # Transit took 7 days in the past, inspection took 2 days in the past (both completed)
        shipment = ReturnShipment(
            return_case_id=ret.id,
            carrier_name="BlueDart",
            tracking_number="TRK-SK-1001",
            status="DELIVERED_TO_MERCHANT",
            pickup_at=now - timedelta(days=9),
            delivered_at=now - timedelta(days=2),
            last_synced_at=now - timedelta(days=2),
        )
        inspection = ReturnInspection(
            return_case_id=ret.id,
            inspection_status="INSPECTION_PASSED",
            condition_result="DAMAGED_CONFIRMED",
            completed_at=now - timedelta(hours=4),
        )
        session.add_all([shipment, inspection])
        session.commit()

        eta_svc = ETAService()
        snap1 = eta_svc.compute_and_persist_eta(session, ref.id, estimated_from=now)
        session.commit()

        assert snap1.is_current is True
        assert snap1.eta_status == "ESTIMATED"
        # Remaining stages: Approval (+2..+24h) + PayPal (+1..+12h) + Issuer (+24..+120h) = +27h .. +156h
        # Crucially, the 7d transit and 2d inspection elapsed durations are NOT added.
        assert _as_utc(snap1.earliest_at) == now + timedelta(hours=27)
        assert _as_utc(snap1.latest_at) == now + timedelta(hours=156)
        completed_stages = [b["stage"] for b in snap1.basis if b.get("status") == "COMPLETED"]
        remaining_stages = [b["stage"] for b in snap1.basis if b.get("status") == "REMAINING"]
        assert "CARRIER_TRANSIT" in completed_stages
        assert "WAREHOUSE_INSPECTION" in completed_stages
        assert remaining_stages == ["MERCHANT_APPROVAL", "PAYPAL_REFUND", "ISSUER_POSTING"]

        # Advance through approval + PayPal completion -> new snapshot flips snap1.is_current = False
        session.add(
            RefundApproval(
                refund_case_id=ref.id,
                shipkart_merchant_user_id=3001,
                decision="APPROVED",
                approved_amount=Decimal("45.00"),
                currency="USD",
                reason="Inspection passed",
            )
        )
        session.add(
            RefundTransaction(
                refund_case_id=ref.id,
                paypal_capture_id="CAP-1001",
                paypal_refund_id="PP-REF-1001",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-1001",
                submitted_at=now + timedelta(minutes=10),
                completed_at=now + timedelta(minutes=15),
            )
        )
        ref.status = "PAYPAL_COMPLETED"
        session.commit()

        t2 = now + timedelta(hours=1)
        snap2 = eta_svc.compute_and_persist_eta(session, ref.id, estimated_from=t2)
        session.commit()

        session.refresh(snap1)
        assert snap1.is_current is False
        assert snap2.is_current is True
        # Only Issuer posting remaining: +24h .. +120h from t2
        assert _as_utc(snap2.earliest_at) == t2 + timedelta(hours=24)
        assert _as_utc(snap2.latest_at) == t2 + timedelta(hours=120)
        assert snap2.confidence_level == "HIGH"

        # Confirmed posted -> COMPLETED with earliest == latest == posted_at
        posted_at = t2 + timedelta(hours=30)
        session.add(
            IssuerInquiry(
                refund_case_id=ref.id,
                provider_type="SIMULATOR",
                institution_code="HDFC_SIM",
                status="CREDIT_POSTED",
                response_data={"credit_posted": True, "posting_status": "POSTED", "posted_at": posted_at.isoformat()},
                updated_at=posted_at,
            )
        )
        session.commit()

        snap3 = eta_svc.compute_and_persist_eta(session, ref.id, estimated_from=posted_at)
        session.commit()
        session.refresh(snap2)
        assert snap2.is_current is False
        assert snap3.is_current is True
        assert snap3.eta_status == "COMPLETED"
        assert _as_utc(snap3.earliest_at) == posted_at
        assert _as_utc(snap3.latest_at) == posted_at
        assert snap3.confidence_level == "HIGH"
    finally:
        session.close()


def test_eta_returns_not_estimable_for_lost_rejected_and_issuer_unavailable() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        eta_svc = ETAService()

        # Case 1: Lost package
        ret_lost, ref_lost = _create_case_bundle(session, now=now)
        session.add(
            ReturnShipment(
                return_case_id=ret_lost.id,
                carrier_name="Delhivery",
                tracking_number="TRK-SK-LOST",
                status="LOST_PACKAGE",
                pickup_at=now - timedelta(days=3),
            )
        )
        session.commit()
        est_lost = eta_svc.compute_and_persist_eta(session, ref_lost.id, estimated_from=now)
        assert est_lost.eta_status == "NOT_ESTIMABLE"
        assert est_lost.earliest_at is None
        assert est_lost.latest_at is None
        assert est_lost.confidence_level == "LOW"
        assert any("blocking_reasons" in entry for entry in est_lost.basis)

        # Case 2: Rejected inspection
        ret_rej, ref_rej = _create_case_bundle(session, now=now, return_status="RETURN_REJECTED")
        session.add(
            ReturnShipment(
                return_case_id=ret_rej.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-REJ",
                status="DELIVERED_TO_MERCHANT",
                delivered_at=now - timedelta(days=1),
            )
        )
        session.add(
            ReturnInspection(
                return_case_id=ret_rej.id,
                inspection_status="RETURN_REJECTED",
                condition_result="CUSTOMER_DAMAGE",
                completed_at=now - timedelta(hours=2),
            )
        )
        session.commit()
        est_rej = eta_svc.compute_and_persist_eta(session, ref_rej.id, estimated_from=now)
        assert est_rej.eta_status == "NOT_ESTIMABLE"
        assert est_rej.earliest_at is None
        assert est_rej.latest_at is None
        assert est_rej.confidence_level == "LOW"

        # Case 3: Issuer unavailable
        _ret_iss, ref_iss = _create_case_bundle(session, now=now, refund_status="PAYPAL_COMPLETED")
        session.add(
            RefundTransaction(
                refund_case_id=ref_iss.id,
                paypal_capture_id="CAP-ISS",
                paypal_refund_id="PP-REF-ISS",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-iss",
                completed_at=now - timedelta(days=2),
            )
        )
        session.add(
            IssuerInquiry(
                refund_case_id=ref_iss.id,
                status="ISSUER_UNAVAILABLE",
                response_data={"error_code": "ISSUER_UNAVAILABLE"},
            )
        )
        session.commit()
        est_iss = eta_svc.compute_and_persist_eta(session, ref_iss.id, estimated_from=now)
        assert est_iss.eta_status == "NOT_ESTIMABLE"
        assert est_iss.earliest_at is None
        assert est_iss.latest_at is None
        assert est_iss.confidence_level == "LOW"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 3. DelayService Tests (DELAY-001 .. DELAY-006)
# ---------------------------------------------------------------------------


def test_delay_service_detects_all_six_rules() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        svc = DelayService()

        # DELAY-001: Pickup overdue > 48h since return approval
        ret1, ref1 = _create_case_bundle(session, now=now, approved_at=now - timedelta(hours=50))
        session.add(
            ReturnShipment(
                return_case_id=ret1.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-D1",
                status="PICKUP_SCHEDULED",
                pickup_at=None,
            )
        )
        session.commit()
        res1 = svc.evaluate_delays(session, ref1.id, as_of=now)
        assert [d["rule_code"] for d in res1["delays"]] == ["DELAY-001"]
        assert res1["delay_owner"] == "CARRIER"

        # DELAY-002: Carrier transit stalled > 72h since last carrier event
        ret2, ref2 = _create_case_bundle(session, now=now, approved_at=now - timedelta(days=6))
        session.add(
            ReturnShipment(
                return_case_id=ret2.id,
                carrier_name="FedEx",
                tracking_number="TRK-SK-D2",
                status="IN_TRANSIT",
                pickup_at=now - timedelta(hours=90),
                last_synced_at=now - timedelta(hours=75),
            )
        )
        session.commit()
        res2 = svc.evaluate_delays(session, ref2.id, as_of=now)
        assert [d["rule_code"] for d in res2["delays"]] == ["DELAY-002"]
        assert res2["delay_owner"] == "CARRIER"

        # DELAY-003: Warehouse inspection overdue > 48h after DELIVERED_TO_MERCHANT
        ret3, ref3 = _create_case_bundle(session, now=now, approved_at=now - timedelta(days=6))
        session.add(
            ReturnShipment(
                return_case_id=ret3.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-D3",
                status="DELIVERED_TO_MERCHANT",
                pickup_at=now - timedelta(days=5),
                delivered_at=now - timedelta(hours=52),
            )
        )
        session.commit()
        res3 = svc.evaluate_delays(session, ref3.id, as_of=now)
        assert [d["rule_code"] for d in res3["delays"]] == ["DELAY-003"]
        assert res3["delay_owner"] == "MERCHANT"

        # DELAY-004: Merchant refund approval overdue > 48h after inspection passed
        ret4, ref4 = _create_case_bundle(
            session,
            now=now,
            return_status="INSPECTION_PASSED",
            refund_status="MERCHANT_APPROVAL_PENDING",
            approved_at=now - timedelta(days=7),
        )
        session.add(
            ReturnShipment(
                return_case_id=ret4.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-D4",
                status="DELIVERED_TO_MERCHANT",
                pickup_at=now - timedelta(days=6),
                delivered_at=now - timedelta(days=3),
            )
        )
        session.add(
            ReturnInspection(
                return_case_id=ret4.id,
                inspection_status="INSPECTION_PASSED",
                condition_result="DAMAGED_CONFIRMED",
                completed_at=now - timedelta(hours=50),
            )
        )
        session.commit()
        res4 = svc.evaluate_delays(session, ref4.id, as_of=now)
        assert [d["rule_code"] for d in res4["delays"]] == ["DELAY-004"]
        assert res4["delay_owner"] == "MERCHANT"

        # DELAY-005: PayPal refund submission stuck PENDING > 24h without completion
        ret5, ref5 = _create_case_bundle(
            session,
            now=now,
            return_status="INSPECTION_PASSED",
            refund_status="PAYPAL_PENDING",
            approved_at=now - timedelta(days=7),
        )
        session.add(
            ReturnShipment(
                return_case_id=ret5.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-D5",
                status="DELIVERED_TO_MERCHANT",
                pickup_at=now - timedelta(days=6),
                delivered_at=now - timedelta(days=4),
            )
        )
        session.add(
            ReturnInspection(
                return_case_id=ret5.id,
                inspection_status="INSPECTION_PASSED",
                condition_result="DAMAGED_CONFIRMED",
                completed_at=now - timedelta(days=3),
            )
        )
        session.add(
            RefundApproval(
                refund_case_id=ref5.id,
                shipkart_merchant_user_id=3001,
                decision="APPROVED",
                approved_amount=Decimal("45.00"),
                currency="USD",
                reason="Approved",
            )
        )
        session.add(
            RefundTransaction(
                refund_case_id=ref5.id,
                paypal_capture_id="CAP-D5",
                paypal_refund_id="PP-REF-D5",
                amount=Decimal("45.00"),
                currency="USD",
                status="PENDING",
                idempotency_key="idem-d5",
                submitted_at=now - timedelta(hours=30),
            )
        )
        session.commit()
        res5 = svc.evaluate_delays(session, ref5.id, as_of=now)
        assert [d["rule_code"] for d in res5["delays"]] == ["DELAY-005"]
        assert res5["delay_owner"] == "PAYPAL"

        # DELAY-006: PayPal COMPLETED > 72h while bank credit unconfirmed
        ret6, ref6 = _create_case_bundle(
            session,
            now=now,
            return_status="INSPECTION_PASSED",
            refund_status="PAYPAL_COMPLETED",
            approved_at=now - timedelta(days=10),
        )
        session.add(
            ReturnShipment(
                return_case_id=ret6.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-D6",
                status="DELIVERED_TO_MERCHANT",
                pickup_at=now - timedelta(days=9),
                delivered_at=now - timedelta(days=7),
            )
        )
        session.add(
            ReturnInspection(
                return_case_id=ret6.id,
                inspection_status="INSPECTION_PASSED",
                condition_result="DAMAGED_CONFIRMED",
                completed_at=now - timedelta(days=6),
            )
        )
        session.add(
            RefundApproval(
                refund_case_id=ref6.id,
                shipkart_merchant_user_id=3001,
                decision="APPROVED",
                approved_amount=Decimal("45.00"),
                currency="USD",
                reason="Approved",
            )
        )
        session.add(
            RefundTransaction(
                refund_case_id=ref6.id,
                paypal_capture_id="CAP-D6",
                paypal_refund_id="PP-REF-D6",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-d6",
                submitted_at=now - timedelta(hours=80),
                completed_at=now - timedelta(hours=78),
            )
        )
        session.commit()
        res6 = svc.evaluate_delays(session, ref6.id, as_of=now)
        assert [d["rule_code"] for d in res6["delays"]] == ["DELAY-006"]
        assert res6["delay_owner"] == "ISSUER_OR_BANK"
        assert res6["delays"][0]["recommended_action"] == "INITIATE_ISSUER_INQUIRY"
        assert "not confirmed" in res6["delays"][0]["description"].lower() or "unconfirmed" in res6["delays"][0]["description"].lower()
    finally:
        session.close()


def test_delay_service_returns_empty_when_on_track_or_missing_evidence() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        svc = DelayService()

        # On-track case: PayPal completed 12h ago
        _ret, ref_ok = _create_case_bundle(session, now=now, refund_status="PAYPAL_COMPLETED")
        session.add(
            RefundTransaction(
                refund_case_id=ref_ok.id,
                paypal_capture_id="CAP-OK",
                paypal_refund_id="PP-REF-OK",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-ok",
                submitted_at=now - timedelta(hours=13),
                completed_at=now - timedelta(hours=12),
            )
        )
        session.commit()
        res_ok = svc.evaluate_delays(session, ref_ok.id, as_of=now)
        assert res_ok["delays"] == []
        assert res_ok["delay_owner"] in {"NONE", "UNKNOWN"}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 4. ReconciliationService Tests
# ---------------------------------------------------------------------------


class FakePayPalClient:
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get_refund(self, paypal_refund_id: str) -> dict[str, Any]:
        self.calls.append(paypal_refund_id)
        return self.responses[paypal_refund_id]


def test_reconciliation_deduplicates_webhooks_and_reconciles_pending_refund() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        _ret, ref = _create_case_bundle(session, now=now, refund_status="PAYPAL_PENDING")
        tx = RefundTransaction(
            refund_case_id=ref.id,
            paypal_capture_id="CAP-1001",
            paypal_refund_id="PP-REF-9001",
            amount=Decimal("45.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-9001",
            submitted_at=now - timedelta(hours=2),
        )
        session.add(tx)
        session.commit()

        rec = ReconciliationService()
        webhook_payload = {
            "id": "WH-EVT-9001",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "create_time": (now - timedelta(minutes=10)).isoformat(),
            "resource": {
                "id": "PP-REF-9001",
                "status": "COMPLETED",
                "capture_id": "CAP-1001",
                "amount": {"value": "45.00", "currency_code": "USD"},
            },
        }

        first = rec.process_paypal_webhook(
            session,
            provider_event_id="WH-EVT-9001",
            event_type="PAYMENT.CAPTURE.REFUNDED",
            payload=webhook_payload,
        )
        session.commit()
        assert first["deduplicated"] is False
        assert first["processing_status"] == "PROCESSED"

        session.refresh(tx)
        session.refresh(ref)
        assert tx.status == "COMPLETED"
        assert ref.status == "PAYPAL_COMPLETED"  # Never falsely marked confirmed bank posted

        # Replay same provider_event_id -> deduplicated without duplicating timeline event
        second = rec.process_paypal_webhook(
            session,
            provider_event_id="WH-EVT-9001",
            event_type="PAYMENT.CAPTURE.REFUNDED",
            payload=webhook_payload,
        )
        assert second["deduplicated"] is True

        wh_rows = session.scalars(select(ProcessedWebhookEvent)).all()
        assert len(wh_rows) == 1
        tl_rows = session.scalars(
            select(RefundTimelineEvent).where(RefundTimelineEvent.refund_case_id == ref.id)
        ).all()
        assert len(tl_rows) == 1

        # Also test active polling reconciliation on a separate PENDING transaction
        _ret2, ref2 = _create_case_bundle(session, now=now, refund_status="PAYPAL_PENDING")
        tx2 = RefundTransaction(
            refund_case_id=ref2.id,
            paypal_capture_id="CAP-2002",
            paypal_refund_id="PP-REF-9002",
            amount=Decimal("45.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-9002",
            submitted_at=now - timedelta(hours=3),
        )
        session.add(tx2)
        session.commit()

        fake_client = FakePayPalClient(
            {
                "PP-REF-9002": {
                    "id": "PP-REF-9002",
                    "status": "COMPLETED",
                    "update_time": now.isoformat(),
                }
            }
        )
        updated_tx2 = rec.reconcile_pending_refund_transaction(session, tx2, fake_client)
        session.commit()

        assert fake_client.calls == ["PP-REF-9002"]
        assert updated_tx2.status == "COMPLETED"
        session.refresh(ref2)
        assert ref2.status == "PAYPAL_COMPLETED"
        tl_rows2 = session.scalars(
            select(RefundTimelineEvent).where(RefundTimelineEvent.refund_case_id == ref2.id)
        ).all()
        assert len(tl_rows2) == 1
    finally:
        session.close()


def test_delay_006_triggers_on_issuer_delayed_posting_and_clears_on_credit_posted() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        svc = DelayService()
        _ret, ref = _create_case_bundle(session, now=now, refund_status="PAYPAL_COMPLETED")
        session.add(
            RefundTransaction(
                refund_case_id=ref.id,
                paypal_capture_id="CAP-ISS-D6",
                paypal_refund_id="PP-REF-ISS-D6",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-iss-d6",
                submitted_at=now - timedelta(hours=20),
                completed_at=now - timedelta(hours=18),
            )
        )
        inq = IssuerInquiry(
            refund_case_id=ref.id,
            status="DELAYED_POSTING",
            response_data={"scenario": "DELAYED_POSTING", "credit_posted": False},
        )
        session.add(inq)
        session.commit()

        res_delayed = svc.evaluate_delays(session, ref.id, as_of=now)
        assert res_delayed["triggered_rules"] == ["DELAY-006"]
        assert res_delayed["delay_owner"] == "ISSUER_OR_BANK"
        assert res_delayed["delays"][0]["recommended_action"] == "INITIATE_ISSUER_INQUIRY"

        # Once confirmed posted, DELAY-006 clears
        inq.status = "CREDIT_POSTED"
        inq.response_data = {"scenario": "DELAYED_POSTING", "credit_posted": True, "posting_status": "POSTED"}
        session.commit()
        res_posted = svc.evaluate_delays(session, ref.id, as_of=now)
        assert res_posted["delays"] == []
        assert res_posted["delay_owner"] == "NONE"
    finally:
        session.close()


def test_eta_not_estimable_for_pickup_overdue_and_insufficient_evidence() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        eta_svc = ETAService()

        # Pickup overdue > 48h without active pickup/tracking
        ret_p, ref_p = _create_case_bundle(
            session, now=now, return_status="RETURN_APPROVED", approved_at=now - timedelta(hours=60)
        )
        session.add(
            ReturnShipment(
                return_case_id=ret_p.id,
                carrier_name="BlueDart",
                tracking_number="TRK-SK-OVERDUE",
                status="PICKUP_OVERDUE",
                pickup_at=None,
            )
        )
        session.commit()
        est_p = eta_svc.compute_and_persist_eta(session, ref_p.id, estimated_from=now)
        assert est_p.eta_status == "NOT_ESTIMABLE"
        assert est_p.earliest_at is None
        assert est_p.latest_at is None
        assert est_p.confidence_level == "LOW"

        # Issuer INSUFFICIENT_EVIDENCE
        _ret_e, ref_e = _create_case_bundle(session, now=now, refund_status="PAYPAL_COMPLETED")
        session.add(
            RefundTransaction(
                refund_case_id=ref_e.id,
                paypal_capture_id="CAP-IE",
                paypal_refund_id="PP-REF-IE",
                amount=Decimal("45.00"),
                currency="USD",
                status="COMPLETED",
                idempotency_key="idem-ie",
                completed_at=now - timedelta(hours=40),
            )
        )
        session.add(
            IssuerInquiry(
                refund_case_id=ref_e.id,
                status="INSUFFICIENT_EVIDENCE",
            )
        )
        session.commit()
        est_e = eta_svc.compute_and_persist_eta(session, ref_e.id, estimated_from=now)
        assert est_e.eta_status == "NOT_ESTIMABLE"
        assert est_e.earliest_at is None
        assert est_e.latest_at is None
    finally:
        session.close()


def test_reconciliation_does_not_mutate_on_degraded_and_handles_failed_transition() -> None:
    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        _ret, ref = _create_case_bundle(session, now=now, refund_status="PAYPAL_PENDING")
        tx = RefundTransaction(
            refund_case_id=ref.id,
            paypal_capture_id="CAP-FAIL",
            paypal_refund_id="PP-REF-FAIL",
            amount=Decimal("45.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-fail",
            submitted_at=now - timedelta(hours=5),
        )
        session.add(tx)
        session.commit()

        rec = ReconciliationService()
        degraded_client = FakePayPalClient(
            {"PP-REF-FAIL": {"degraded": True, "status": "UNAVAILABLE"}}
        )
        res_deg = rec.reconcile_pending_refund_transaction(session, tx, degraded_client)
        assert res_deg.status == "PENDING"
        session.refresh(ref)
        assert ref.status == "PAYPAL_PENDING"

        failed_client = FakePayPalClient(
            {"PP-REF-FAIL": {"id": "PP-REF-FAIL", "status": "FAILED", "update_time": now.isoformat()}}
        )
        res_fail = rec.reconcile_pending_refund_transaction(session, tx, failed_client)
        session.commit()
        assert res_fail.status == "FAILED"
        session.refresh(ref)
        assert ref.status == "REFUND_FAILED"
    finally:
        session.close()


def test_reconciliation_service_supports_shipkart_bridge_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from app.core.config import settings
    from app.integrations.shipkart_client import ShipkartBridgeClient
    from app.services.reconciliation_service import ShipkartPayPalRefundAdapter

    monkeypatch.setattr(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes")

    session = _make_session()
    try:
        now = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        _ret, ref = _create_case_bundle(session, now=now, refund_status="PAYPAL_PENDING")
        ref.shipkart_return_id = 456
        tx = RefundTransaction(
            refund_case_id=ref.id,
            paypal_capture_id="CAP-BR-456",
            paypal_refund_id="PP-REF-BR-456",
            amount=Decimal("45.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-br-456",
            submitted_at=now - timedelta(hours=2),
        )
        session.add(tx)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v1/returns/456/paypal-refund-status":
                return httpx.Response(
                    200,
                    json={
                        "id": "PP-REF-BR-456",
                        "status": "COMPLETED",
                        "update_time": now.isoformat(),
                    },
                )
            return httpx.Response(404)

        bridge_client = ShipkartBridgeClient(
            base_url="http://shipkart.test",
            transport=httpx.MockTransport(handler),
        )
        adapter = ShipkartPayPalRefundAdapter(bridge_client, 456)
        rec = ReconciliationService()
        updated = rec.reconcile_pending_refund_transaction(session, tx, adapter)
        session.commit()

        assert updated.status == "COMPLETED"
        session.refresh(ref)
        assert ref.status == "PAYPAL_COMPLETED"
    finally:
        session.close()
