import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    AgentDecision,
    AgentExecution,
    AuditLog,
    ComplianceViolation,
    RefundApproval,
    RefundCase,
    RefundTimelineEvent,
    RefundTransaction,
    ReturnCase,
)
from app.integrations.paypal_client import PayPalClient
from app.services.approval_service import ApprovalService
from app.services.compliance_service import ComplianceService, ComplianceViolationError
from app.services.refund_service import RefundService
from app.services.return_service import ReturnService


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return Session(bind=engine)


def _seed_refund_case(
    db: Session,
    *,
    shipkart_order_id: int = 501,
    shipkart_merchant_id: int = 10,
    shipkart_customer_id: int = 20,
    captured_amount: Decimal = Decimal("100.00"),
    requested_amount: Decimal = Decimal("60.00"),
    paypal_capture_id: str | None = "CAP-501-XYZ",
) -> RefundCase:
    now = datetime.now(timezone.utc)
    rc = RefundCase(
        id=uuid.uuid4(),
        shipkart_order_id=shipkart_order_id,
        shipkart_merchant_id=shipkart_merchant_id,
        shipkart_customer_id=shipkart_customer_id,
        case_type="RETURN_REFUND",
        status="MERCHANT_APPROVAL_PENDING",
        requested_amount=requested_amount,
        captured_amount=captured_amount,
        currency="USD",
        original_currency="INR",
        paypal_currency="USD",
        paypal_order_id="PP-ORD-501",
        paypal_capture_id=paypal_capture_id,
        reason="Item arrived damaged",
        opened_at=now,
    )
    db.add(rc)
    db.commit()
    return rc


def _make_mock_paypal_client(*, refund_status: str = "COMPLETED") -> tuple[PayPalClient, dict[str, int]]:
    calls = {"token": 0, "refund": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "secret-oauth-token", "expires_in": 3600})
        if request.url.path.endswith("/refund"):
            calls["refund"] += 1
            body = json.loads(request.content.decode("utf-8"))
            assert isinstance(body["amount"]["value"], str)
            return httpx.Response(
                201,
                json={
                    "id": f"PP-REF-{calls['refund']:03d}",
                    "status": refund_status,
                    "amount": body["amount"],
                },
            )
        return httpx.Response(404, json={"error": "not_found"})

    transport = httpx.MockTransport(handler)
    client = PayPalClient(
        base_url="https://api-m.sandbox.paypal.com",
        client_id="test-client-id",
        client_secret="test-client-secret",
        transport=transport,
    )
    return client, calls


def test_refund_without_merchant_approval_blocked_ref_001() -> None:
    db = _make_session()
    rc = _seed_refund_case(db)

    # Even if an AI agent proposed approval, REF-001 must still block execution!
    exec_row = AgentExecution(
        id=uuid.uuid4(),
        case_id=rc.id,
        case_type="REFUND",
        agent_name="RESOLUTION_COORDINATOR",
        status="COMPLETED",
        input_reference={},
        output_data={},
        model_name="deterministic-fallback",
        prompt_version="v1",
        started_at=datetime.now(timezone.utc),
    )
    db.add(exec_row)
    db.flush()
    db.add(
        AgentDecision(
            id=uuid.uuid4(),
            execution_id=exec_row.id,
            decision_type="QUEUE_MERCHANT_APPROVAL",
            recommendation={"approved_amount": "60.00"},
            evidence_references=[],
            confidence=Decimal("0.9500"),
            requires_approval=True,
            decision_status="PROPOSED",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    pp_client, calls = _make_mock_paypal_client()
    with pytest.raises(ComplianceViolationError) as exc_info:
        RefundService.execute_approved_refund(
            db,
            rc.id,
            idempotency_key="idem-no-approval-1",
            paypal_client=pp_client,
        )

    assert exc_info.value.rule_code == "REF-001"
    assert exc_info.value.status_code == 403
    assert calls["refund"] == 0
    violations = db.query(ComplianceViolation).filter_by(refund_case_id=rc.id, rule_code="REF-001").all()
    assert len(violations) == 1
    db.close()


def test_over_refund_exceeding_captured_balance_blocked_ref_002() -> None:
    db = _make_session()
    rc1 = _seed_refund_case(
        db,
        shipkart_order_id=502,
        captured_amount=Decimal("100.00"),
        requested_amount=Decimal("70.00"),
        paypal_capture_id="CAP-502-SHARED",
    )
    ApprovalService.record_merchant_decision(
        db,
        rc1.id,
        shipkart_merchant_id=10,
        shipkart_merchant_user_id=1001,
        decision="APPROVED",
        approved_amount=Decimal("70.00"),
        reason="First partial return approved",
    )
    pp_client, _ = _make_mock_paypal_client(refund_status="COMPLETED")
    tx1 = RefundService.execute_approved_refund(
        db,
        rc1.id,
        idempotency_key="idem-partial-1",
        paypal_client=pp_client,
    )
    assert tx1.status == "COMPLETED"

    # Second refund against same capture requesting 40.00 (70 + 40 = 110 > 100) must fail REF-002
    rc2 = _seed_refund_case(
        db,
        shipkart_order_id=502,
        captured_amount=Decimal("100.00"),
        requested_amount=Decimal("40.00"),
        paypal_capture_id="CAP-502-SHARED",
    )
    with pytest.raises(ComplianceViolationError) as exc_info:
        ApprovalService.record_merchant_decision(
            db,
            rc2.id,
            shipkart_merchant_id=10,
            shipkart_merchant_user_id=1001,
            decision="APPROVED",
            approved_amount=Decimal("40.00"),
            reason="Attempted over-refund",
        )

    assert exc_info.value.rule_code == "REF-002"
    db.close()


def test_partial_return_quantity_exceeding_purchased_qty_blocked() -> None:
    db = _make_session()
    # First return requests 2 out of 3 purchased units
    rc1 = ReturnService.create_return_case(
        db,
        shipkart_order_id=601,
        shipkart_customer_id=20,
        shipkart_merchant_id=10,
        reason_code="DAMAGED_ITEM",
        customer_description="Two units scratched",
        items=[
            {
                "shipkart_order_item_id": 9001,
                "quantity_requested": 2,
                "purchased_quantity": 3,
                "unit_price": Decimal("15.00"),
                "condition_reported": "DAMAGED",
            }
        ],
    )
    assert len(rc1.items) == 1
    assert rc1.items[0].refund_amount_requested == Decimal("30.00")

    # Second return requests 2 more units for same order_item (2 + 2 = 4 > 3) -> blocked!
    with pytest.raises(ComplianceViolationError) as exc_info:
        ReturnService.create_return_case(
            db,
            shipkart_order_id=601,
            shipkart_customer_id=20,
            shipkart_merchant_id=10,
            reason_code="DEFECTIVE",
            customer_description="Trying to exceed quantity",
            items=[
                {
                    "shipkart_order_item_id": 9001,
                    "quantity_requested": 2,
                    "purchased_quantity": 3,
                    "unit_price": Decimal("15.00"),
                    "condition_reported": "DAMAGED",
                }
            ],
        )

    assert exc_info.value.status_code == 422
    db.close()


def test_cross_tenant_merchant_blocked_auth_001() -> None:
    db = _make_session()
    rc = _seed_refund_case(db, shipkart_merchant_id=10)
    ret = ReturnService.create_return_case(
        db,
        shipkart_order_id=602,
        shipkart_customer_id=20,
        shipkart_merchant_id=10,
        reason_code="WRONG_ITEM",
        customer_description="Wrong size delivered",
        items=[
            {
                "shipkart_order_item_id": 9002,
                "quantity_requested": 1,
                "purchased_quantity": 1,
                "refund_amount_requested": Decimal("25.00"),
            }
        ],
    )
    ret.status = "DELIVERED_TO_MERCHANT"
    db.commit()

    # Merchant B (id=99) attempts to approve Merchant A's (id=10) refund
    with pytest.raises(ComplianceViolationError) as exc_refund:
        ApprovalService.record_merchant_decision(
            db,
            rc.id,
            shipkart_merchant_id=99,
            shipkart_merchant_user_id=9901,
            decision="APPROVED",
            approved_amount=Decimal("25.00"),
            reason="Unauthorized cross-tenant approval",
        )
    assert exc_refund.value.rule_code == "AUTH-001"
    assert exc_refund.value.status_code == 403

    # Merchant B (id=99) attempts to inspect Merchant A's (id=10) return
    with pytest.raises(ComplianceViolationError) as exc_inspect:
        ReturnService.record_inspection(
            db,
            ret.id,
            shipkart_merchant_id=99,
            shipkart_inspector_id=9902,
            condition_result="PASSED",
            notes="Cross-tenant inspection attempt",
        )
    assert exc_inspect.value.rule_code == "AUTH-001"
    assert exc_inspect.value.status_code == 403
    db.close()


def test_idempotent_refund_submission_calls_paypal_once_ref_003() -> None:
    db = _make_session()
    rc = _seed_refund_case(db, shipkart_order_id=503, requested_amount=Decimal("45.50"))
    ApprovalService.record_merchant_decision(
        db,
        rc.id,
        shipkart_merchant_id=10,
        shipkart_merchant_user_id=1001,
        decision="APPROVED",
        approved_amount=Decimal("45.50"),
        reason="Inspection verified damage",
    )

    pp_client, calls = _make_mock_paypal_client(refund_status="COMPLETED")
    tx1 = RefundService.execute_approved_refund(
        db,
        rc.id,
        idempotency_key="idem-once-503",
        paypal_client=pp_client,
    )
    tx2 = RefundService.execute_approved_refund(
        db,
        rc.id,
        idempotency_key="idem-once-503",
        paypal_client=pp_client,
    )

    assert tx1.id == tx2.id
    assert calls["refund"] == 1
    assert tx1.status == "COMPLETED"
    assert rc.status == "REFUND_COMPLETED"
    db.close()


def test_rejection_without_reason_blocked_case_001() -> None:
    db = _make_session()
    rc = _seed_refund_case(db, shipkart_order_id=504)
    with pytest.raises(ComplianceViolationError) as exc_info:
        ApprovalService.record_merchant_decision(
            db,
            rc.id,
            shipkart_merchant_id=10,
            shipkart_merchant_user_id=1001,
            decision="REJECTED",
            reason="  ",
        )
    assert exc_info.value.rule_code == "CASE-001"
    assert exc_info.value.status_code == 422

    ret = ReturnService.create_return_case(
        db,
        shipkart_order_id=603,
        shipkart_customer_id=20,
        shipkart_merchant_id=10,
        reason_code="NOT_AS_DESCRIBED",
        customer_description="Color mismatch",
        items=[
            {
                "shipkart_order_item_id": 9003,
                "quantity_requested": 1,
                "purchased_quantity": 1,
                "refund_amount_requested": Decimal("30.00"),
            }
        ],
    )
    with pytest.raises(ComplianceViolationError) as exc_ret:
        ReturnService.transition_return_status(
            db,
            ret,
            "RETURN_REJECTED",
            actor_type="MERCHANT",
            actor_shipkart_merchant_id=10,
            reason="",
        )
    assert exc_ret.value.rule_code == "CASE-001"
    db.close()


def test_paypal_pending_status_does_not_falsely_mark_completed() -> None:
    db = _make_session()
    rc = _seed_refund_case(db, shipkart_order_id=505, requested_amount=Decimal("33.25"))
    ApprovalService.record_merchant_decision(
        db,
        rc.id,
        shipkart_merchant_id=10,
        shipkart_merchant_user_id=1001,
        decision="APPROVED",
        approved_amount=Decimal("33.25"),
        reason="Approved pending settlement",
    )

    pp_client, calls = _make_mock_paypal_client(refund_status="PENDING")
    tx = RefundService.execute_approved_refund(
        db,
        rc.id,
        idempotency_key="idem-pending-505",
        paypal_client=pp_client,
    )

    assert calls["refund"] == 1
    assert tx.status == "PENDING"
    assert tx.completed_at is None
    assert rc.status == "REFUND_SUBMITTED"
    assert rc.resolved_at is None
    events = db.query(RefundTimelineEvent).filter_by(refund_case_id=rc.id).all()
    assert any(evt.event_type == "PAYPAL_REFUND_SUBMITTED" for evt in events)
    audits = db.query(AuditLog).filter_by(resource_id=tx.id).all()
    assert len(audits) == 1
    db.close()


def test_missing_capture_id_blocked_ref_004_and_customer_scope_auth_002() -> None:
    db = _make_session()
    rc = _seed_refund_case(
        db,
        shipkart_order_id=506,
        shipkart_customer_id=20,
        paypal_capture_id=None,
    )
    ApprovalService.record_merchant_decision(
        db,
        rc.id,
        shipkart_merchant_id=10,
        shipkart_merchant_user_id=1001,
        decision="APPROVED",
        approved_amount=Decimal("20.00"),
        reason="Approved before capture check",
    )

    pp_client, calls = _make_mock_paypal_client()
    with pytest.raises(ComplianceViolationError) as exc_ref4:
        RefundService.execute_approved_refund(
            db,
            rc.id,
            idempotency_key="idem-missing-cap-506",
            paypal_client=pp_client,
        )
    assert exc_ref4.value.rule_code == "REF-004"
    assert calls["refund"] == 0

    with pytest.raises(ComplianceViolationError) as exc_auth2:
        ComplianceService.assert_customer_access(
            db,
            case=rc,
            actor_shipkart_customer_id=999,
        )
    assert exc_auth2.value.rule_code == "AUTH-002"
    assert exc_auth2.value.status_code == 403
    db.close()


def test_paypal_client_capture_refund_webhook_verify_and_redaction() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok-live-secret", "expires_in": 3600})
        if request.url.path == "/v2/payments/captures/CAP-1":
            return httpx.Response(
                200,
                json={"id": "CAP-1", "status": "COMPLETED", "client_secret": "leak-me"},
            )
        if request.url.path == "/v2/payments/refunds/REF-1":
            return httpx.Response(200, json={"id": "REF-1", "status": "COMPLETED"})
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        return httpx.Response(404)

    client = PayPalClient(
        base_url="https://api-m.sandbox.paypal.com",
        client_id="cid",
        client_secret="csec",
        webhook_id="WH-ID-1",
        transport=httpx.MockTransport(handler),
    )

    cap = client.get_capture("CAP-1")
    assert cap["status"] == "COMPLETED"
    assert cap["client_secret"] == "[REDACTED]"

    ref = client.get_refund("REF-1")
    assert ref["status"] == "COMPLETED"

    verified = client.verify_webhook_signature(
        {
            "PayPal-Auth-Algo": "SHA256withRSA",
            "PayPal-Cert-Url": "https://api.sandbox.paypal.com/cert.pem",
            "PayPal-Transmission-Id": "tx-1",
            "PayPal-Transmission-Sig": "sig-1",
            "PayPal-Transmission-Time": "2026-11-12T00:00:00Z",
        },
        {"id": "EVT-1", "event_type": "PAYMENT.CAPTURE.REFUNDED"},
    )
    assert verified is True


def test_return_lifecycle_transitions_and_inspection_happy_path() -> None:
    db = _make_session()
    ret = ReturnService.create_return_case(
        db,
        shipkart_order_id=610,
        shipkart_customer_id=20,
        shipkart_merchant_id=10,
        reason_code="DAMAGED_ITEM",
        customer_description="Box torn and item dented",
        items=[
            {
                "shipkart_order_item_id": 9100,
                "quantity_requested": 1,
                "purchased_quantity": 2,
                "unit_price": Decimal("49.99"),
            }
        ],
    )
    for target in (
        "RETURN_APPROVED",
        "PICKUP_SCHEDULED",
        "PICKED_UP",
        "IN_TRANSIT",
        "DELIVERED_TO_MERCHANT",
    ):
        ReturnService.transition_return_status(
            db,
            ret,
            target,
            actor_type="MERCHANT" if target == "RETURN_APPROVED" else "CARRIER",
            actor_shipkart_merchant_id=10 if target == "RETURN_APPROVED" else None,
        )

    inspection = ReturnService.record_inspection(
        db,
        ret.id,
        shipkart_merchant_id=10,
        shipkart_inspector_id=1005,
        condition_result="DAMAGED_CONFIRMED",
        notes="Confirmed dent on side panel",
    )
    assert inspection.inspection_status == "INSPECTION_COMPLETED"
    assert ret.status == "INSPECTION_COMPLETED"
    db.close()
