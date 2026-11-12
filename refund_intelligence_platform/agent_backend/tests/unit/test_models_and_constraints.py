import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Float, Numeric, create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db.models import (
    AgentDecision,
    AgentExecution,
    AuditLog,
    ComplianceViolation,
    Evidence,
    IssuerInquiry,
    ProcessedWebhookEvent,
    RefundApproval,
    RefundCase,
    RefundEtaEstimate,
    RefundFollowup,
    RefundTimelineEvent,
    RefundTransaction,
    RegulatoryEvaluation,
    ReturnCase,
    ReturnCaseItem,
    ReturnInspection,
    ReturnShipment,
)


EXPECTED_TABLES = {
    "return_cases",
    "return_case_items",
    "return_shipments",
    "return_inspections",
    "refund_cases",
    "refund_transactions",
    "refund_approvals",
    "evidence",
    "refund_timeline_events",
    "agent_executions",
    "agent_decisions",
    "refund_eta_estimates",
    "refund_followups",
    "issuer_inquiries",
    "regulatory_evaluations",
    "compliance_violations",
    "audit_logs",
    "processed_webhook_events",
    "platform_users",
}


def _make_sqlite_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(bind=engine)


def test_all_18_tables_present_and_zero_float_money_columns() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES

    money_columns = [
        ReturnCaseItem.refund_amount_requested.property.columns[0],
        ReturnCaseItem.refund_amount_approved.property.columns[0],
        RefundCase.requested_amount.property.columns[0],
        RefundCase.approved_amount.property.columns[0],
        RefundCase.captured_amount.property.columns[0],
        RefundTransaction.amount.property.columns[0],
        RefundApproval.approved_amount.property.columns[0],
    ]
    for col in money_columns:
        assert isinstance(col.type, Numeric), f"{col.table.name}.{col.name} must use Numeric"
        assert not isinstance(col.type, Float), f"{col.table.name}.{col.name} must not use Float"
        assert (col.type.precision, col.type.scale) == (18, 2)

    for table in Base.metadata.tables.values():
        for col in table.columns:
            assert not isinstance(col.type, Float), f"{table.name}.{col.name} must not use Float"


def test_postgresql_ddl_compilation_emits_uuid_numeric_jsonb_inet() -> None:
    pg_dialect = postgresql.dialect()
    ddl_map = {
        name: str(CreateTable(table).compile(dialect=pg_dialect))
        for name, table in Base.metadata.tables.items()
    }

    assert "UUID" in ddl_map["return_cases"]
    assert "NUMERIC(18, 2)" in ddl_map["refund_cases"]
    assert "NUMERIC(18, 2)" in ddl_map["refund_transactions"]
    assert "JSONB" in ddl_map["refund_transactions"]
    assert "INET" in ddl_map["audit_logs"]
    assert "UNIQUE (provider, provider_event_id)" in ddl_map["processed_webhook_events"]


def test_refund_approval_is_immutable() -> None:
    session = _make_sqlite_session()
    now = datetime.now(timezone.utc)
    refund_case = RefundCase(
        id=uuid.uuid4(),
        shipkart_order_id=101,
        shipkart_customer_id=11,
        shipkart_merchant_id=22,
        case_type="RETURN_REFUND",
        status="MERCHANT_APPROVAL_PENDING",
        requested_amount=Decimal("49.99"),
        currency="USD",
        original_currency="INR",
        paypal_currency="USD",
        reason="Damaged item",
        opened_at=now,
    )
    session.add(refund_case)
    session.flush()

    approval = RefundApproval(
        id=uuid.uuid4(),
        refund_case_id=refund_case.id,
        shipkart_merchant_user_id=22,
        decision="APPROVED",
        approved_amount=Decimal("49.99"),
        currency="USD",
        reason="Verified inspection pass",
        policy_version="v1.0",
        created_at=now,
    )
    session.add(approval)
    session.commit()

    approval.reason = "Tampered reason"
    with pytest.raises(ValueError, match="immutable"):
        session.commit()
    session.rollback()

    persisted = session.get(RefundApproval, approval.id)
    assert persisted is not None
    session.delete(persisted)
    with pytest.raises(ValueError, match="immutable"):
        session.commit()
    session.rollback()
    session.close()


def test_audit_log_is_immutable() -> None:
    session = _make_sqlite_session()
    now = datetime.now(timezone.utc)
    log_entry = AuditLog(
        id=uuid.uuid4(),
        shipkart_actor_id=22,
        actor_type="MERCHANT",
        action="REFUND_APPROVED",
        resource_type="refund_case",
        resource_id=uuid.uuid4(),
        after_state={"approved_amount": "49.99"},
        ip_address="127.0.0.1",
        created_at=now,
    )
    session.add(log_entry)
    session.commit()

    log_entry.action = "TAMPERED_ACTION"
    with pytest.raises(ValueError, match="immutable"):
        session.commit()
    session.rollback()

    persisted = session.get(AuditLog, log_entry.id)
    assert persisted is not None
    session.delete(persisted)
    with pytest.raises(ValueError, match="immutable"):
        session.commit()
    session.rollback()
    session.close()


def test_unique_constraints_webhook_and_refund_idempotency() -> None:
    session = _make_sqlite_session()
    now = datetime.now(timezone.utc)

    evt1 = ProcessedWebhookEvent(
        id=uuid.uuid4(),
        provider="PAYPAL",
        provider_event_id="WH-EVT-001",
        event_type="PAYMENT.CAPTURE.REFUNDED",
        payload_hash="a" * 64,
        processing_status="PROCESSED",
        received_at=now,
    )
    session.add(evt1)
    session.commit()

    evt_dup = ProcessedWebhookEvent(
        id=uuid.uuid4(),
        provider="PAYPAL",
        provider_event_id="WH-EVT-001",
        event_type="PAYMENT.CAPTURE.REFUNDED",
        payload_hash="a" * 64,
        processing_status="RECEIVED",
        received_at=now,
    )
    session.add(evt_dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    refund_case = RefundCase(
        id=uuid.uuid4(),
        shipkart_order_id=102,
        case_type="RETURN_REFUND",
        status="APPROVED",
        requested_amount=Decimal("25.00"),
        approved_amount=Decimal("25.00"),
        currency="USD",
        original_currency="USD",
        paypal_currency="USD",
        reason="Duplicate test",
        opened_at=now,
    )
    session.add(refund_case)
    session.flush()

    tx1 = RefundTransaction(
        id=uuid.uuid4(),
        refund_case_id=refund_case.id,
        paypal_capture_id="CAP-123",
        paypal_refund_id="REF-123",
        amount=Decimal("25.00"),
        currency="USD",
        status="SUBMITTED",
        idempotency_key="idem-refund-102",
        created_at=now,
    )
    session.add(tx1)
    session.commit()

    tx_dup = RefundTransaction(
        id=uuid.uuid4(),
        refund_case_id=refund_case.id,
        paypal_capture_id="CAP-123",
        paypal_refund_id="REF-456",
        amount=Decimal("25.00"),
        currency="USD",
        status="PENDING",
        idempotency_key="idem-refund-102",
        created_at=now,
    )
    session.add(tx_dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_defaults_on_agent_decision_and_simulators() -> None:
    session = _make_sqlite_session()
    now = datetime.now(timezone.utc)

    rc = RefundCase(
        id=uuid.uuid4(),
        shipkart_order_id=103,
        case_type="RETURN_REFUND_DELAY",
        status="INVESTIGATING",
        requested_amount=Decimal("100.00"),
        currency="USD",
        original_currency="INR",
        paypal_currency="USD",
        reason="Bank credit delayed",
        opened_at=now,
    )
    session.add(rc)
    session.flush()

    exec_row = AgentExecution(
        id=uuid.uuid4(),
        case_id=rc.id,
        case_type="REFUND",
        agent_name="RESOLUTION_COORDINATOR",
        status="COMPLETED",
        input_reference={"refund_case_id": str(rc.id)},
        output_data={"action": "QUEUE_MERCHANT_APPROVAL"},
        model_name="deterministic-fallback",
        prompt_version="v1",
        started_at=now,
    )
    session.add(exec_row)
    session.flush()

    decision = AgentDecision(
        id=uuid.uuid4(),
        execution_id=exec_row.id,
        decision_type="QUEUE_MERCHANT_APPROVAL",
        recommendation={"amount": "100.00"},
        evidence_references=[],
        confidence=Decimal("0.9250"),
        decision_status="PROPOSED",
        created_at=now,
    )
    inquiry = IssuerInquiry(
        id=uuid.uuid4(),
        refund_case_id=rc.id,
        provider_type="SIMULATOR",
        status="DELAYED_POSTING",
        request_data={},
        response_data={},
        created_at=now,
        updated_at=now,
    )
    reg = RegulatoryEvaluation(
        id=uuid.uuid4(),
        refund_case_id=rc.id,
        jurisdiction="IN",
        evaluation_status="POTENTIALLY_APPLICABLE",
        transaction_context={},
        rule_version="IN-2026.1",
        matched_rules=[],
        unresolved_questions=[],
        evaluated_at=now,
    )
    session.add_all([decision, inquiry, reg])
    session.commit()

    assert decision.requires_approval is True
    assert inquiry.is_simulated is True
    assert reg.is_simulated is True
    session.close()


def test_alembic_offline_sql_generation() -> None:
    """Verify Alembic offline upgrade SQL emits all 18 tables and triggers cleanly."""
    import contextlib
    import io
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parents[2]
    buf = io.StringIO()
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    with contextlib.redirect_stdout(buf):
        command.upgrade(alembic_cfg, "head", sql=True)

    sql_output = buf.getvalue()
    for table_name in EXPECTED_TABLES:
        assert f"CREATE TABLE {table_name}" in sql_output, f"Missing CREATE TABLE {table_name}"
    assert "NUMERIC(18, 2)" in sql_output
    assert "trg_refund_approvals_immutable" in sql_output
    assert "trg_audit_logs_immutable" in sql_output

