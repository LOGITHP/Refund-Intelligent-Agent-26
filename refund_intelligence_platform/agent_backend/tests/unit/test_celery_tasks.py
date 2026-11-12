import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    AgentExecution,
    Evidence,
    ProcessedWebhookEvent,
    RefundCase,
    RefundEtaEstimate,
    RefundFollowup,
    RefundTimelineEvent,
    RefundTransaction,
    ReturnCase,
)
from app.worker.celery_app import celery_app
from app.worker.tasks import (
    detect_overdue_cases_task,
    poll_due_followups_task,
    process_webhook_event_task,
    reconcile_pending_paypal_refunds_task,
    run_agent_pipeline_task,
    set_paypal_client_factory,
    set_session_factory,
    set_shipkart_client_factory,
)


@pytest.fixture()
def isolated_worker_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    old_eager = celery_app.conf.task_always_eager
    old_prop = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    set_session_factory(TestSessionLocal)

    try:
        yield TestSessionLocal
    finally:
        set_session_factory(None)
        celery_app.conf.task_always_eager = old_eager
        celery_app.conf.task_eager_propagates = old_prop
        engine.dispose()


def test_celery_app_configuration_and_beat_schedule() -> None:
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.result_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.worker_hijack_root_logger is False

    schedule = celery_app.conf.beat_schedule
    assert "poll-due-followups-every-5m" in schedule
    assert schedule["poll-due-followups-every-5m"]["schedule"] == 300.0
    assert "reconcile-pending-paypal-refunds-every-10m" in schedule
    assert schedule["reconcile-pending-paypal-refunds-every-10m"]["schedule"] == 600.0
    assert "detect-overdue-cases-every-15m" in schedule
    assert schedule["detect-overdue-cases-every-15m"]["schedule"] == 900.0


def test_run_agent_pipeline_task_eager_execution(isolated_worker_db) -> None:
    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        rc = RefundCase(
            id=uuid.uuid4(),
            shipkart_order_id=801,
            shipkart_customer_id=11,
            shipkart_merchant_id=22,
            case_type="RETURN_REFUND",
            status="INVESTIGATING",
            requested_amount=Decimal("45.00"),
            captured_amount=Decimal("45.00"),
            currency="USD",
            original_currency="INR",
            paypal_currency="USD",
            paypal_capture_id="CAP-801",
            reason="Item arrived damaged",
            opened_at=now,
        )
        db.add(rc)
        db.flush()
        db.add(
            Evidence(
                id=uuid.uuid4(),
                refund_case_id=rc.id,
                file_name="damage.png",
                storage_key="evidence/801/damage.png",
                mime_type="image/png",
                file_size=1024,
                sha256_hash="b" * 64,
                source_type="CUSTOMER",
                verification_status="VERIFIED",
                extracted_metadata={"note": "broken hinge"},
                created_at=now,
            )
        )
        db.commit()
        case_id = rc.id

    res = run_agent_pipeline_task.delay(str(case_id), "Please check my refund").get()
    assert res["status"] == "COMPLETED"
    assert res["refund_case_id"] == str(case_id)

    with isolated_worker_db() as db:
        executions = db.query(AgentExecution).filter_by(case_id=case_id).all()
        assert len(executions) >= 1


def test_poll_due_followups_task_processes_due_and_skips_future(isolated_worker_db) -> None:
    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        # Case 1: Terminal completed case with a due followup -> should become EXECUTED
        rc_done = RefundCase(
            id=uuid.uuid4(),
            shipkart_order_id=802,
            case_type="RETURN_REFUND",
            status="CONFIRMED_POSTED",
            requested_amount=Decimal("30.00"),
            captured_amount=Decimal("30.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            reason="Resolved case",
            opened_at=now - timedelta(days=3),
        )
        # Case 2: Delayed PayPal pending case with a due followup -> rescheduled
        rc_delayed = RefundCase(
            id=uuid.uuid4(),
            shipkart_order_id=803,
            case_type="RETURN_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("60.00"),
            captured_amount=Decimal("60.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-803",
            reason="PayPal pending",
            opened_at=now - timedelta(hours=72),
        )
        db.add_all([rc_done, rc_delayed])
        db.flush()

        db.add(
            RefundTransaction(
                id=uuid.uuid4(),
                refund_case_id=rc_delayed.id,
                paypal_capture_id="CAP-803",
                paypal_refund_id="REF-803",
                amount=Decimal("60.00"),
                currency="USD",
                status="PENDING",
                idempotency_key="idem-803",
                submitted_at=now - timedelta(hours=40),
                created_at=now - timedelta(hours=40),
            )
        )

        f_due_done = RefundFollowup(
            id=uuid.uuid4(),
            refund_case_id=rc_done.id,
            target_type="ISSUER",
            scheduled_at=now - timedelta(minutes=10),
            status="SCHEDULED",
            action_type="CHECK_POSTING",
            attempt_count=0,
            created_at=now - timedelta(hours=2),
        )
        f_due_delayed = RefundFollowup(
            id=uuid.uuid4(),
            refund_case_id=rc_delayed.id,
            target_type="PAYPAL",
            scheduled_at=now - timedelta(minutes=5),
            status="SCHEDULED",
            action_type="RECONCILE_PENDING",
            attempt_count=0,
            created_at=now - timedelta(hours=2),
        )
        f_future = RefundFollowup(
            id=uuid.uuid4(),
            refund_case_id=rc_delayed.id,
            target_type="ISSUER",
            scheduled_at=now + timedelta(hours=6),
            status="SCHEDULED",
            action_type="FUTURE_CHECK",
            attempt_count=0,
            created_at=now,
        )
        db.add_all([f_due_done, f_due_delayed, f_future])
        db.commit()
        due_done_id, due_delayed_id, future_id = f_due_done.id, f_due_delayed.id, f_future.id

    summary = poll_due_followups_task.delay().get()
    assert summary["processed"] == 2

    with isolated_worker_db() as db:
        row_done = db.get(RefundFollowup, due_done_id)
        row_delayed = db.get(RefundFollowup, due_delayed_id)
        row_future = db.get(RefundFollowup, future_id)

        assert row_done is not None and row_done.attempt_count == 1
        assert row_done.status == "EXECUTED"
        assert row_done.last_attempt_at is not None

        assert row_delayed is not None and row_delayed.attempt_count == 1
        assert row_delayed.status == "SCHEDULED"
        assert row_delayed.scheduled_at.replace(tzinfo=timezone.utc) > now

        assert row_future is not None and row_future.attempt_count == 0
        assert row_future.status == "SCHEDULED"


def test_process_webhook_event_task_is_idempotent(isolated_worker_db) -> None:
    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        rc = RefundCase(
            id=uuid.uuid4(),
            shipkart_order_id=804,
            case_type="RETURN_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("55.00"),
            captured_amount=Decimal("55.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-804",
            reason="Webhook test",
            opened_at=now,
        )
        db.add(rc)
        db.flush()
        db.add(
            RefundTransaction(
                id=uuid.uuid4(),
                refund_case_id=rc.id,
                paypal_capture_id="CAP-804",
                paypal_refund_id="REF-804",
                amount=Decimal("55.00"),
                currency="USD",
                status="PENDING",
                idempotency_key="idem-804",
                submitted_at=now,
                created_at=now,
            )
        )
        db.commit()
        case_id = rc.id

    payload = {
        "id": "WH-PAYPAL-804",
        "event_type": "PAYMENT.CAPTURE.REFUNDED",
        "resource": {
            "id": "REF-804",
            "status": "COMPLETED",
            "supplementary_data": {"related_ids": {"capture_id": "CAP-804"}},
        },
    }

    first = process_webhook_event_task.delay("WH-PAYPAL-804", "PAYMENT.CAPTURE.REFUNDED", payload).get()
    second = process_webhook_event_task.delay("WH-PAYPAL-804", "PAYMENT.CAPTURE.REFUNDED", payload).get()

    assert first["deduplicated"] is False
    assert first["transaction_status"] == "COMPLETED"
    assert second["deduplicated"] is True

    with isolated_worker_db() as db:
        events = db.query(ProcessedWebhookEvent).filter_by(provider_event_id="WH-PAYPAL-804").all()
        assert len(events) == 1
        refreshed = db.get(RefundCase, case_id)
        assert refreshed is not None and refreshed.status == "PAYPAL_COMPLETED"


def test_detect_overdue_cases_task_flags_delays_and_persists_eta(isolated_worker_db) -> None:
    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        ret = ReturnCase(
            id=uuid.uuid4(),
            shipkart_order_id=805,
            reason_code="DAMAGED_ITEM",
            customer_description="Delayed pickup",
            status="RETURN_APPROVED",
            requested_at=now - timedelta(hours=80),
            approved_at=now - timedelta(hours=72),
            created_at=now - timedelta(hours=80),
            updated_at=now - timedelta(hours=72),
        )
        db.add(ret)
        db.flush()

        rc = RefundCase(
            id=uuid.uuid4(),
            return_case_id=ret.id,
            shipkart_order_id=805,
            case_type="RETURN_REFUND",
            status="INVESTIGATING",
            requested_amount=Decimal("75.00"),
            captured_amount=Decimal("75.00"),
            currency="USD",
            original_currency="INR",
            paypal_currency="USD",
            paypal_capture_id="CAP-805",
            reason="Pickup overdue",
            opened_at=now - timedelta(hours=72),
        )
        db.add(rc)
        db.commit()
        case_id = rc.id

    res1 = detect_overdue_cases_task.delay().get()
    res2 = detect_overdue_cases_task.delay().get()

    assert res1["evaluated"] == 1
    assert res1["overdue_cases"] == 1
    assert res1["breaches_detected"] >= 1
    assert res2["overdue_cases"] == 1

    with isolated_worker_db() as db:
        breach_events = (
            db.query(RefundTimelineEvent)
            .filter_by(refund_case_id=case_id, source_type="DELAY_MONITOR")
            .all()
        )
        # Deduplicated across repeat runs!
        assert len(breach_events) == 1
        assert breach_events[0].event_type == "SLA_BREACH_DELAY-001"

        etas = db.query(RefundEtaEstimate).filter_by(refund_case_id=case_id).all()
        assert len(etas) == 2
        assert sum(1 for e in etas if e.is_current) == 1


def test_reconcile_pending_paypal_refunds_task_skips_unconfigured_and_reconciles_configured(
    isolated_worker_db,
) -> None:
    import httpx
    from app.integrations.paypal_client import PayPalClient

    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        rc = RefundCase(
            id=uuid.uuid4(),
            shipkart_order_id=806,
            case_type="RETURN_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("40.00"),
            captured_amount=Decimal("40.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-806",
            reason="Reconciliation test",
            opened_at=now,
        )
        db.add(rc)
        db.flush()
        tx = RefundTransaction(
            id=uuid.uuid4(),
            refund_case_id=rc.id,
            paypal_capture_id="CAP-806",
            paypal_refund_id="REF-806",
            amount=Decimal("40.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-806",
            submitted_at=now,
            created_at=now,
        )
        db.add(tx)
        db.commit()
        tx_id, case_id = tx.id, rc.id

    # 1. When PayPal is unconfigured, skips cleanly without mutating
    skipped = reconcile_pending_paypal_refunds_task.delay().get()
    assert skipped["skipped"] is True
    assert skipped["checked"] == 0

    # 2. When PayPalClient is configured, reconciles PENDING -> COMPLETED
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if request.url.path == "/v2/payments/refunds/REF-806":
            return httpx.Response(
                200,
                json={"id": "REF-806", "status": "COMPLETED", "update_time": "2026-11-12T06:00:00Z"},
            )
        return httpx.Response(404)

    set_paypal_client_factory(
        lambda: PayPalClient(
            base_url="https://api-m.sandbox.paypal.com",
            client_id="cid",
            client_secret="csec",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        res = reconcile_pending_paypal_refunds_task.delay().get()
    finally:
        set_paypal_client_factory(None)

    assert res["skipped"] is False
    assert res["checked"] == 1
    assert res["reconciled"] == 1

    with isolated_worker_db() as db:
        refreshed_tx = db.get(RefundTransaction, tx_id)
        refreshed_case = db.get(RefundCase, case_id)
        assert refreshed_tx is not None and refreshed_tx.status == "COMPLETED"
        assert refreshed_case is not None and refreshed_case.status == "PAYPAL_COMPLETED"


def test_reconcile_pending_paypal_refunds_task_uses_shipkart_bridge_when_service_jwt_configured(
    isolated_worker_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx
    from app.core.config import settings
    from app.integrations.shipkart_client import ShipkartBridgeClient

    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "")
    monkeypatch.setattr(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes")

    now = datetime.now(timezone.utc)
    with isolated_worker_db() as db:
        # Merchant 1: has shipkart_return_id=901 -> reconciles PENDING -> COMPLETED
        rc1 = RefundCase(
            id=uuid.uuid4(),
            shipkart_return_id=901,
            shipkart_order_id=1901,
            shipkart_merchant_id=101,
            case_type="RETURN_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("40.00"),
            captured_amount=Decimal("40.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-901",
            reason="Merchant 1 pending refund",
            opened_at=now,
        )
        # Merchant 2: has shipkart_return_id=902 -> bridge returns 503 -> stays PENDING cleanly
        rc2 = RefundCase(
            id=uuid.uuid4(),
            shipkart_return_id=902,
            shipkart_order_id=1902,
            shipkart_merchant_id=102,
            case_type="RETURN_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("25.00"),
            captured_amount=Decimal("25.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-902",
            reason="Merchant 2 unconfigured",
            opened_at=now,
        )
        # Case 3: no shipkart_return_id -> skipped without querying bridge
        rc3 = RefundCase(
            id=uuid.uuid4(),
            shipkart_return_id=None,
            shipkart_order_id=1903,
            shipkart_merchant_id=103,
            case_type="CANCELLATION_REFUND",
            status="PAYPAL_PENDING",
            requested_amount=Decimal("15.00"),
            captured_amount=Decimal("15.00"),
            currency="USD",
            original_currency="USD",
            paypal_currency="USD",
            paypal_capture_id="CAP-903",
            reason="No return id",
            opened_at=now,
        )
        db.add_all([rc1, rc2, rc3])
        db.flush()

        tx1 = RefundTransaction(
            id=uuid.uuid4(),
            refund_case_id=rc1.id,
            paypal_capture_id="CAP-901",
            paypal_refund_id="REF-901",
            amount=Decimal("40.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-901",
            submitted_at=now,
            created_at=now,
        )
        tx2 = RefundTransaction(
            id=uuid.uuid4(),
            refund_case_id=rc2.id,
            paypal_capture_id="CAP-902",
            paypal_refund_id="REF-902",
            amount=Decimal("25.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-902",
            submitted_at=now,
            created_at=now,
        )
        tx3 = RefundTransaction(
            id=uuid.uuid4(),
            refund_case_id=rc3.id,
            paypal_capture_id="CAP-903",
            paypal_refund_id="REF-903",
            amount=Decimal("15.00"),
            currency="USD",
            status="PENDING",
            idempotency_key="idem-903",
            submitted_at=now,
            created_at=now,
        )
        db.add_all([tx1, tx2, tx3])
        db.commit()
        tx1_id, tx2_id, tx3_id, rc1_id, rc2_id = tx1.id, tx2.id, tx3.id, rc1.id, rc2.id

    called_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_paths.append(request.url.path)
        if request.url.path == "/api/v1/returns/901/paypal-refund-status":
            return httpx.Response(
                200,
                json={"id": "REF-901", "status": "COMPLETED", "update_time": "2026-11-12T06:00:00Z"},
            )
        if request.url.path == "/api/v1/returns/902/paypal-refund-status":
            return httpx.Response(503, json={"detail": "Merchant PayPal credentials not configured"})
        return httpx.Response(404)

    set_shipkart_client_factory(
        lambda: ShipkartBridgeClient(
            base_url="http://shipkart.test",
            transport=httpx.MockTransport(handler),
        )
    )
    try:
        res = reconcile_pending_paypal_refunds_task.delay().get()
    finally:
        set_shipkart_client_factory(None)

    assert res["skipped"] is False
    assert res["mode"] == "shipkart_bridge"
    assert res["checked"] == 2
    assert res["reconciled"] == 1
    assert called_paths == [
        "/api/v1/returns/901/paypal-refund-status",
        "/api/v1/returns/902/paypal-refund-status",
    ]

    with isolated_worker_db() as db:
        r_tx1 = db.get(RefundTransaction, tx1_id)
        r_tx2 = db.get(RefundTransaction, tx2_id)
        r_tx3 = db.get(RefundTransaction, tx3_id)
        r_rc1 = db.get(RefundCase, rc1_id)
        r_rc2 = db.get(RefundCase, rc2_id)
        assert r_tx1 is not None and r_tx1.status == "COMPLETED"
        assert r_rc1 is not None and r_rc1.status == "PAYPAL_COMPLETED"
        assert r_tx2 is not None and r_tx2.status == "PENDING"
        assert r_rc2 is not None and r_rc2.status == "PAYPAL_PENDING"
        assert r_tx3 is not None and r_tx3.status == "PENDING"
