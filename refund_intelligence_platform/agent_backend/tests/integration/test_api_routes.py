"""Integration tests for Task 8: FastAPI route surface, RBAC, ownership, and error contracts."""

from __future__ import annotations

import hashlib
import io
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import compute_hmac_signature
from app.db.base import Base
from app.db.models import (
    AgentDecision,
    AgentExecution,
    Evidence,
    RefundCase,
    ReturnCase,
)
from app.db.session import get_db
from app.integrations.minio_client import AgentMinIOClient, InMemoryObjectStorage
from app.integrations.paypal_client import PayPalClient
from app.integrations.simulators import (
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
)
from app.services.evidence_service import EvidenceService

USER_JWT_SECRET = "test-shipkart-user-jwt-secret-32-bytes"
SERVICE_JWT_SECRET = "test-agent-service-jwt-secret-32-bytes"
BRIDGE_HMAC_SECRET = "test-bridge-hmac-shared-secret-32bytes"


def _make_jwt(user_id: int, role: str) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "user_id": user_id,
            "role": role,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        },
        USER_JWT_SECRET,
        algorithm="HS256",
    )


def _make_valid_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(30, 144, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _make_mock_simulators() -> tuple[
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
    PayPalClient,
]:
    def carrier_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "is_simulated": True})
        if request.url.path == "/carrier/shipments" and request.method == "GET":
            return httpx.Response(200, json={"shipments": [], "is_simulated": True})
        return httpx.Response(
            200,
            json={
                "tracking_number": "TRACK-SK-100",
                "status": "DELIVERED_TO_MERCHANT",
                "carrier_name": "BlueDart",
                "is_simulated": True,
            },
        )

    def issuer_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "is_simulated": True})
        if request.url.path == "/issuer/inquiries" and request.method == "GET":
            return httpx.Response(200, json={"inquiries": [], "is_simulated": True})
        return httpx.Response(
            200,
            json={
                "inquiry_id": "INQ-SIM-1",
                "status": "DELAYED_POSTING",
                "scenario": "DELAYED_POSTING",
                "credit_posted": False,
                "is_simulated": True,
            },
        )

    def reg_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "is_simulated": True})
        if request.url.path == "/regulatory/rules":
            return httpx.Response(200, json={"rules": [{"id": "IN-RBI-01"}], "is_simulated": True})
        return httpx.Response(
            200,
            json={
                "jurisdiction": "IN",
                "evaluation_status": "POTENTIALLY_APPLICABLE",
                "rule_version": "2026.1",
                "matched_rules": [{"rule_id": "IN-CPA-2019"}],
                "unresolved_questions": [],
                "is_simulated": True,
            },
        )

    def paypal_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "pp-tok", "expires_in": 300})
        if request.url.path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(200, json={"verification_status": "SUCCESS"})
        if request.url.path.endswith("/refund"):
            return httpx.Response(201, json={"id": "PP-REF-100", "status": "COMPLETED"})
        if "/v2/payments/captures/" in request.url.path:
            return httpx.Response(200, json={"id": "CAP-100", "status": "COMPLETED"})
        return httpx.Response(200, json={"id": "PP-REF-100", "status": "COMPLETED"})

    return (
        CarrierSimulatorClient(transport=httpx.MockTransport(carrier_handler)),
        IssuerSimulatorClient(transport=httpx.MockTransport(issuer_handler)),
        RegulatorySimulatorClient(transport=httpx.MockTransport(reg_handler)),
        PayPalClient(
            client_id="pp-id",
            client_secret="pp-secret",
            webhook_id="pp-wh-id",
            transport=httpx.MockTransport(paypal_handler),
        ),
    )


@pytest.fixture()
def api_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", USER_JWT_SECRET)
    monkeypatch.setattr(settings, "SERVICE_JWT_SECRET", SERVICE_JWT_SECRET)
    monkeypatch.setattr(settings, "BRIDGE_SHARED_SECRET", BRIDGE_HMAC_SECRET)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

    from app.api.v1 import (
        get_carrier_client,
        get_evidence_service,
        get_issuer_client,
        get_paypal_client,
        get_regulatory_client,
    )
    from app.main import app

    fake_storage = InMemoryObjectStorage()
    fake_minio = AgentMinIOClient(client=fake_storage)
    fake_evidence_svc = EvidenceService(minio_client=fake_minio)
    carrier_cli, issuer_cli, reg_cli, paypal_cli = _make_mock_simulators()

    def _override_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_evidence_service] = lambda: fake_evidence_svc
    app.dependency_overrides[get_carrier_client] = lambda: carrier_cli
    app.dependency_overrides[get_issuer_client] = lambda: issuer_cli
    app.dependency_overrides[get_regulatory_client] = lambda: reg_cli
    app.dependency_overrides[get_paypal_client] = lambda: paypal_cli

    try:
        with TestClient(app) as client:
            yield client, TestingSessionLocal
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _create_sample_case(client: TestClient, *, customer_id: int = 101, merchant_id: int = 201) -> tuple[str, str]:
    token = _make_jwt(customer_id, "customer")
    resp = client.post(
        "/api/v1/returns",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "shipkart_order_id": 5001,
            "shipkart_return_id": 7001,
            "shipkart_customer_id": customer_id,
            "shipkart_merchant_id": merchant_id,
            "reason_code": "DAMAGED_ITEM",
            "customer_description": "Screen arrived cracked in corner",
            "captured_amount": "120.00",
            "paypal_order_id": "PP-ORD-5001",
            "paypal_capture_id": "CAP-5001",
            "items": [
                {
                    "shipkart_order_item_id": 9001,
                    "quantity_requested": 1,
                    "purchased_quantity": 1,
                    "unit_price": "120.00",
                    "condition_reported": "DAMAGED",
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["return_case"]["id"], body["refund_case"]["id"]


def test_health_and_cross_tenant_ownership_enforcement(api_context) -> None:
    client, _ = api_context

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    return_id, refund_id = _create_sample_case(client, customer_id=101, merchant_id=201)

    cust_a = _make_jwt(101, "customer")
    cust_b = _make_jwt(999, "customer")
    merch_a = _make_jwt(201, "merchant")
    merch_b = _make_jwt(888, "merchant")

    # Customer A can access own timeline & ETA; Customer B gets 403 AUTH-002
    assert client.get(f"/api/v1/refunds/{refund_id}/timeline", headers={"Authorization": f"Bearer {cust_a}"}).status_code == 200
    eta_res = client.get(f"/api/v1/refunds/{refund_id}/eta", headers={"Authorization": f"Bearer {cust_a}"})
    assert eta_res.status_code == 200
    assert eta_res.json()["disclaimer"] == "This is an estimate, not a guaranteed credit date."

    b_get = client.get(f"/api/v1/returns/{return_id}", headers={"Authorization": f"Bearer {cust_b}"})
    assert b_get.status_code == 403
    assert b_get.json()["error"]["code"] == "AUTH-002"

    b_chat = client.post(
        f"/api/v1/refunds/{refund_id}/chat",
        headers={"Authorization": f"Bearer {cust_b}"},
        json={"question": "Where is my refund?"},
    )
    assert b_chat.status_code == 403

    b_upload = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers={"Authorization": f"Bearer {cust_b}"},
        files={"file": ("photo.png", _make_valid_png_bytes(), "image/png")},
    )
    assert b_upload.status_code == 403

    # Merchant B cannot approve or inspect Merchant A's case -> 403 AUTH-001
    mb_approve = client.post(
        f"/api/v1/merchant/refunds/{refund_id}/approve",
        headers={"Authorization": f"Bearer {merch_b}"},
        json={"reason": "Attempt cross-tenant approval", "approved_amount": "120.00"},
    )
    assert mb_approve.status_code == 403
    assert mb_approve.json()["error"]["code"] == "AUTH-001"

    mb_inspect = client.post(
        f"/api/v1/merchant/returns/{return_id}/inspect",
        headers={"Authorization": f"Bearer {merch_b}"},
        json={"condition_result": "DAMAGED", "notes": "Wrong merchant"},
    )
    assert mb_inspect.status_code == 403

    # Merchant A can view their case
    assert client.get(f"/api/v1/merchant/refunds/{refund_id}", headers={"Authorization": f"Bearer {merch_a}"}).status_code == 200


def test_evidence_upload_rejects_spoofed_exe_422_and_accepts_valid_png(api_context) -> None:
    client, _ = api_context
    return_id, _ = _create_sample_case(client, customer_id=101, merchant_id=201)
    cust_a = _make_jwt(101, "customer")

    # Spoofed PE/EXE renamed .jpg -> 422 structured error
    spoof_res = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers={"Authorization": f"Bearer {cust_a}"},
        files={"file": ("receipt.jpg", b"MZ\x90\x00\x03\x00\x00\x00", "image/jpeg")},
    )
    assert spoof_res.status_code == 422
    err = spoof_res.json()["error"]
    assert err["code"] == "EXECUTABLE_PAYLOAD_REJECTED"
    assert "request_id" in err

    # Valid PNG accepted & SHA-256 recorded
    png_bytes = _make_valid_png_bytes()
    ok_res = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers={"Authorization": f"Bearer {cust_a}"},
        files={"file": ("damage.png", png_bytes, "image/png")},
    )
    assert ok_res.status_code == 201, ok_res.text
    data = ok_res.json()
    assert data["sha256_hash"] == hashlib.sha256(png_bytes).hexdigest()
    assert data["verification_status"] == "VERIFIED"


def test_paypal_refund_blocked_without_merchant_approval_ref_001_and_succeeds_after_approval(api_context) -> None:
    client, _ = api_context
    _return_id, refund_id = _create_sample_case(client, customer_id=101, merchant_id=201)
    merch_a = _make_jwt(201, "merchant")

    # Calling /payments/paypal/refund without RefundApproval -> 403 REF-001
    blocked = client.post(
        "/api/v1/payments/paypal/refund",
        headers={"Authorization": f"Bearer {merch_a}"},
        json={"refund_case_id": refund_id, "idempotency_key": "idem-no-approval"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "REF-001"

    # Merchant approves first -> 200
    approve_res = client.post(
        f"/api/v1/merchant/refunds/{refund_id}/approve",
        headers={"Authorization": f"Bearer {merch_a}"},
        json={"approved_amount": "120.00", "reason": "Verified damaged return"},
    )
    assert approve_res.status_code == 200, approve_res.text
    assert approve_res.json()["decision"] == "APPROVED"

    # Now PayPal execution succeeds -> 200
    exec_res = client.post(
        "/api/v1/payments/paypal/refund",
        headers={"Authorization": f"Bearer {merch_a}"},
        json={"refund_case_id": refund_id, "idempotency_key": "idem-after-approval"},
    )
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["status"] == "COMPLETED"
    assert exec_res.json()["paypal_refund_id"] == "PP-REF-100"


def test_bridge_hmac_rejects_unsigned_and_creates_case_idempotently(api_context) -> None:
    client, SessionLocal = api_context

    payload = {
        "shipkart_return_id": 8801,
        "shipkart_order_id": 5501,
        "shipkart_customer_id": 301,
        "shipkart_merchant_id": 401,
        "reason_code": "DEFECTIVE",
        "customer_description": "Device does not power on",
        "captured_amount": "89.99",
        "paypal_capture_id": "CAP-8801",
        "items": [
            {
                "shipkart_order_item_id": 9901,
                "quantity_requested": 1,
                "purchased_quantity": 1,
                "unit_price": "89.99",
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Missing signature -> 401
    assert (
        client.post(
            "/api/v1/bridge/shipkart/return-event",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        ).status_code
        == 401
    )

    # Tampered signature -> 401
    assert (
        client.post(
            "/api/v1/bridge/shipkart/return-event",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Bridge-Signature": "sha256=" + ("0" * 64),
            },
        ).status_code
        == 401
    )

    # Valid HMAC signature -> 201 created, second call idempotent 200
    sig = compute_hmac_signature(raw_body, BRIDGE_HMAC_SECRET)
    ok_first = client.post(
        "/api/v1/bridge/shipkart/return-event",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Signature": f"sha256={sig}",
        },
    )
    assert ok_first.status_code == 201, ok_first.text
    assert ok_first.json()["created"] is True

    ok_second = client.post(
        "/api/v1/bridge/shipkart/return-event",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Signature": f"sha256={sig}",
        },
    )
    assert ok_second.status_code == 200
    assert ok_second.json()["created"] is False
    assert ok_second.json()["refund_case_id"] == ok_first.json()["refund_case_id"]

    with SessionLocal() as db:
        assert db.scalar(select(ReturnCase).where(ReturnCase.shipkart_return_id == 8801)) is not None
        assert db.scalar(select(RefundCase).where(RefundCase.shipkart_return_id == 8801)) is not None


def test_agents_investigate_persists_3_executions_and_requires_approval(api_context) -> None:
    client, SessionLocal = api_context
    return_id, refund_id = _create_sample_case(client, customer_id=101, merchant_id=201)
    cust_a = _make_jwt(101, "customer")

    # Upload verified evidence so the 3-node graph flows Intake -> Investigation -> Resolution
    up = client.post(
        f"/api/v1/returns/{return_id}/evidence",
        headers={"Authorization": f"Bearer {cust_a}"},
        files={"file": ("photo.png", _make_valid_png_bytes(), "image/png")},
    )
    assert up.status_code == 201

    inv_res = client.post(
        f"/api/v1/agents/investigate/{refund_id}",
        headers={"Authorization": f"Bearer {cust_a}"},
        json={"customer_query": "Please investigate my damaged return"},
    )
    assert inv_res.status_code == 200, inv_res.text
    body = inv_res.json()
    assert len(body["execution_records"]) == 3
    assert body["resolution_result"]["requires_approval"] is True

    with SessionLocal() as db:
        case_uuid = uuid.UUID(refund_id)
        execs = list(db.scalars(select(AgentExecution).where(AgentExecution.case_id == case_uuid)).all())
        assert len(execs) == 3
        decisions = list(
            db.scalars(
                select(AgentDecision)
                .join(AgentExecution, AgentDecision.execution_id == AgentExecution.id)
                .where(AgentExecution.case_id == case_uuid)
            ).all()
        )
        assert len(decisions) >= 1
        assert all(d.requires_approval is True for d in decisions)

    ops_sess = client.post("/api/v1/operations/auth/demo-session")
    assert ops_sess.status_code == 200
    ops_headers = {"Authorization": f"Bearer {ops_sess.json()['access_token']}"}
    execs_res = client.get(f"/api/v1/operations/agents/executions?case_id={refund_id}", headers=ops_headers)
    assert execs_res.status_code == 200, execs_res.text
    assert execs_res.json()["count"] == 3
    case_res = client.get(f"/api/v1/operations/cases/{refund_id}", headers=ops_headers)
    assert case_res.status_code == 200, case_res.text
    assert len(case_res.json()["agent_executions"]) == 3


def test_operations_routes_and_demo_session_return_valid_structured_json(api_context) -> None:
    client, _ = api_context
    _create_sample_case(client, customer_id=101, merchant_id=201)

    session_res = client.post("/api/v1/operations/auth/demo-session")
    assert session_res.status_code == 200, session_res.text
    ops_token = session_res.json()["access_token"]
    ops_headers = {"Authorization": f"Bearer {ops_token}"}

    for path in (
        "/api/v1/operations/overview",
        "/api/v1/operations/cases",
        "/api/v1/operations/agents/executions",
        "/api/v1/operations/integrations/health",
        "/api/v1/operations/eta",
        "/api/v1/operations/compliance",
        "/api/v1/operations/audit",
    ):
        res = client.get(path, headers=ops_headers)
        assert res.status_code == 200, f"{path} failed: {res.text}"
        assert isinstance(res.json(), dict)

    ov_body = client.get("/api/v1/operations/overview", headers=ops_headers).json()
    assert ov_body["service_status"]["paypal_sandbox"] in {"MERCHANT_DIRECT", "CONFIGURED"}
    assert ov_body["service_status"]["shipkart_bridge"] == "CONFIGURED"

    assert client.get("/api/v1/operations/cases").status_code == 401


def test_overview_paypal_sandbox_reports_merchant_direct_when_bridge_configured(
    api_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overview status matrix reports MERCHANT_DIRECT instead of UNCONFIGURED when Shipkart bridge is active."""
    client, _ = api_context
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "")

    ops_token = client.post("/api/v1/operations/auth/demo-session").json()["access_token"]
    ov = client.get(
        "/api/v1/operations/overview",
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert ov.status_code == 200, ov.text
    assert ov.json()["service_status"]["paypal_sandbox"] == "MERCHANT_DIRECT"
    assert ov.json()["service_status"]["shipkart_bridge"] == "CONFIGURED"

    monkeypatch.setattr(settings, "BRIDGE_SHARED_SECRET", "")
    ov_unconf = client.get(
        "/api/v1/operations/overview",
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert ov_unconf.status_code == 200
    assert ov_unconf.json()["service_status"]["paypal_sandbox"] == "UNCONFIGURED"


def test_bridge_shipkart_flat_payload_status_sync_and_customer_intelligence(api_context) -> None:
    client, SessionLocal = api_context

    # Exact flat payload emitted by Shipkart `_relay_return_event_to_agent` for starter catalog (merchant_id=None)
    flat_payload = {
        "event_type": "RETURN_REQUESTED",
        "shipkart_return_id": 9101,
        "shipkart_order_id": 6101,
        "shipkart_order_item_id": 8101,
        "shipkart_customer_id": 501,
        "shipkart_merchant_id": None,
        "reason": "Product received with physical screen crack exceeding 50 chars description limit check",
        "comments": "Corner of box was crushed on arrival",
        "evidence_urls": ["/api/v1/media/files/return-evidence/crack.png"],
        "refund_amount": "69999.00",
        "refund_currency": "USD",
        "refund_paypal_amount": "799.00",
        "captured_amount": "799.00",
        "original_currency": "INR",
        "paypal_currency": "USD",
        "quantity_requested": 1,
        "purchased_quantity": 1,
        "unit_price": "69999.00",
        "paypal_capture_id": "CAP-FLAT-9101",
        "paypal_order_id": "PP-FLAT-6101",
    }
    raw_body = json.dumps(flat_payload).encode("utf-8")
    sig = compute_hmac_signature(raw_body, BRIDGE_HMAC_SECRET)

    created = client.post(
        "/api/v1/bridge/shipkart/return-event",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Signature": f"sha256={sig}",
        },
    )
    assert created.status_code == 201, created.text
    refund_id = created.json()["refund_case_id"]
    return_id = created.json()["return_case_id"]
    assert created.json()["created"] is True

    cust_owner = _make_jwt(501, "customer")
    cust_other = _make_jwt(999, "customer")
    merch_actor = _make_jwt(201, "merchant")

    # AUTH-002 blocks Customer B; Customer A receives consolidated intelligence without leaks
    assert (
        client.get(
            f"/api/v1/refunds/{refund_id}/intelligence",
            headers={"Authorization": f"Bearer {cust_other}"},
        ).status_code
        == 403
    )

    intel = client.get(
        f"/api/v1/refunds/{refund_id}/intelligence",
        headers={"Authorization": f"Bearer {cust_owner}"},
    )
    assert intel.status_code == 200, intel.text
    intel_body = intel.json()
    assert intel_body["refund_case"]["requested_amount"] == "799.00"
    assert intel_body["refund_case"]["captured_amount"] == "799.00"
    assert intel_body["refund_case"]["currency"] == "USD"
    assert intel_body["refund_case"]["original_currency"] == "INR"
    assert intel_body["eta"]["disclaimer"] == "This is an estimate, not a guaranteed credit date."
    assert intel_body["issuer_status"]["is_simulated"] is True

    # Merchant actor can view & approve platform starter catalog case (merchant_id=None)
    assert (
        client.get(
            f"/api/v1/merchant/refunds/{refund_id}/investigation",
            headers={"Authorization": f"Bearer {merch_actor}"},
        ).status_code
        == 200
    )

    # Status sync webhook updates status & timeline idempotently
    sync_payload = {
        **flat_payload,
        "event_type": "RETURN_STATUS_UPDATED",
        "status": "REFUNDED",
        "refund_transaction_id": "PP-REF-SYNC-9101",
        "merchant_notes": "Approved & refunded via Seller Hub",
    }
    sync_raw = json.dumps(sync_payload).encode("utf-8")
    sync_sig = compute_hmac_signature(sync_raw, BRIDGE_HMAC_SECRET)
    synced = client.post(
        "/api/v1/bridge/shipkart/return-event",
        content=sync_raw,
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Signature": f"sha256={sync_sig}",
        },
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["created"] is False
    assert synced.json()["updated"] is True
    assert synced.json()["status"] == "PAYPAL_COMPLETED"

    with SessionLocal() as db:
        rc = db.get(RefundCase, uuid.UUID(refund_id))
        ret = db.get(ReturnCase, uuid.UUID(return_id))
        assert rc is not None and ret is not None
        assert rc.requested_amount == Decimal("799.00")
        assert rc.status == "PAYPAL_COMPLETED"


def test_standard_checkout_inr_approval_preserves_inr_in_operations_overview(api_context) -> None:
    """INR STANDARD_CHECKOUT returns approved without PayPal USD must stay INR in overview KPIs."""
    client, SessionLocal = api_context

    inr_payload = {
        "event_type": "RETURN_REQUESTED",
        "shipkart_return_id": 9202,
        "shipkart_order_id": 6202,
        "shipkart_order_item_id": 8202,
        "shipkart_customer_id": 502,
        "shipkart_merchant_id": 201,
        "reason": "DEFECTIVE",
        "comments": "Does not power on cleanly",
        "refund_amount": "24990.00",
        "refund_currency": "INR",
        "refund_paypal_amount": None,
        "captured_amount": None,
        "original_currency": "INR",
        "paypal_currency": "USD",
        "quantity_requested": 1,
        "purchased_quantity": 1,
        "unit_price": "24990.00",
        "paypal_capture_id": None,
        "paypal_order_id": None,
    }
    raw_body = json.dumps(inr_payload).encode("utf-8")
    sig = compute_hmac_signature(raw_body, BRIDGE_HMAC_SECRET)

    created = client.post(
        "/api/v1/bridge/shipkart/return-event",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Signature": f"sha256={sig}",
        },
    )
    assert created.status_code == 201, created.text
    refund_id = created.json()["refund_case_id"]

    with SessionLocal() as db:
        rc = db.get(RefundCase, uuid.UUID(refund_id))
        assert rc is not None
        assert rc.currency == "INR"
        assert rc.original_currency == "INR"
        assert rc.paypal_currency == "INR"

    merch_token = _make_jwt(201, "merchant")
    app_res = client.post(
        f"/api/v1/merchant/refunds/{refund_id}/approve",
        headers={"Authorization": f"Bearer {merch_token}"},
        json={"reason": "Approved INR standard checkout return"},
    )
    assert app_res.status_code == 200, app_res.text
    assert app_res.json()["currency"] == "INR"
    assert app_res.json()["approved_amount"] == "24990.00"

    ops_token = client.post("/api/v1/operations/auth/demo-session").json()["access_token"]
    ov = client.get(
        "/api/v1/operations/overview",
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert ov.status_code == 200, ov.text
    ov_body = ov.json()
    assert ov_body["total_requested_by_currency"].get("INR") == "24990.00"
    assert ov_body["total_approved_by_currency"].get("INR") == "24990.00"
    assert "USD" not in ov_body["total_approved_by_currency"]


def test_platform_operator_auth_flow_health_sanitization_and_shipkart_sync(api_context) -> None:
    """Verify dedicated email/password JWT login, zero port/secret leakage, and Shipkart recommendation sync."""
    client, SessionLocal = api_context

    # 1. Public status reports no operators configured yet
    st0 = client.get("/api/v1/operations/auth/status")
    assert st0.status_code == 200
    assert st0.json()["has_operators"] is False

    # 2. Setup first platform operator (non-hardcoded runtime credential)
    generated_secret = f"OpTest!{secrets.token_urlsafe(10)}"
    setup_res = client.post(
        "/api/v1/operations/auth/setup",
        json={
            "email": "ops-lead@refund-intel.example",
            "password": generated_secret,
            "full_name": "Ops Lead",
        },
    )
    assert setup_res.status_code == 201, setup_res.text
    setup_body = setup_res.json()
    assert setup_body["user"]["email"] == "ops-lead@refund-intel.example"
    assert setup_body["user"]["role"] == "operations"
    assert "password" not in json.dumps(setup_body).lower()

    # 3. Duplicate setup must return 409 Conflict
    dup_res = client.post(
        "/api/v1/operations/auth/setup",
        json={
            "email": "second@refund-intel.example",
            "password": generated_secret,
            "full_name": "Second",
        },
    )
    assert dup_res.status_code == 409

    # 4. Login with wrong password -> 401; valid password -> 200 JWT
    bad_login = client.post(
        "/api/v1/operations/auth/login",
        json={"email": "ops-lead@refund-intel.example", "password": "wrong-password-123"},
    )
    assert bad_login.status_code == 401

    good_login = client.post(
        "/api/v1/operations/auth/login",
        json={"email": "ops-lead@refund-intel.example", "password": generated_secret},
    )
    assert good_login.status_code == 200, good_login.text
    ops_jwt = good_login.json()["access_token"]
    ops_headers = {"Authorization": f"Bearer {ops_jwt}"}

    me_res = client.get("/api/v1/operations/auth/me", headers=ops_headers)
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == "ops-lead@refund-intel.example"

    # Shipkart merchant & customer JWTs must NEVER access platform operations endpoints
    assert (
        client.get(
            "/api/v1/operations/overview",
            headers={"Authorization": f"Bearer {_make_jwt(201, 'merchant')}"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/operations/overview",
            headers={"Authorization": f"Bearer {_make_jwt(101, 'customer')}"},
        ).status_code
        == 403
    )

    # 5. Integrations health must expose ZERO raw port numbers or PayPal secrets
    health_res = client.get("/api/v1/operations/integrations/health", headers=ops_headers)
    assert health_res.status_code == 200
    health_dump = json.dumps(health_res.json())
    assert re.search(r":\d{4}", health_dump) is None, f"Exposed port detected: {health_dump}"
    assert "client_secret" not in health_dump.lower()
    assert "minioadmin" not in health_dump.lower()

    # 6. Agent investigation syncs recommendation to Shipkart bridge + populates readable customer summary
    from app.api.v1 import get_shipkart_client
    from app.main import app as fastapi_app

    class _SpyShipkartClient:
        def __init__(self) -> None:
            self.posted: list[tuple[int, dict[str, Any]]] = []

        def post_agent_recommendation(self, return_id: int, payload: dict[str, Any]) -> dict[str, Any]:
            self.posted.append((return_id, payload))
            return {"ok": True, "id": return_id}

    spy = _SpyShipkartClient()
    _, refund_id = _create_sample_case(client, customer_id=101, merchant_id=201)
    with SessionLocal() as db:
        rc = db.get(RefundCase, uuid.UUID(refund_id))
        assert rc is not None
        rc.shipkart_return_id = 7788
        db.commit()

    fastapi_app.dependency_overrides[get_shipkart_client] = lambda: spy
    try:
        inv_res = client.post(
            f"/api/v1/agents/investigate/{refund_id}",
            headers=ops_headers,
            json={"customer_query": "Please check return evidence"},
        )
        assert inv_res.status_code == 200, inv_res.text
        assert inv_res.json()["shipkart_synced"] is True
        assert inv_res.json()["summary"]
    finally:
        fastapi_app.dependency_overrides.pop(get_shipkart_client, None)

    assert len(spy.posted) == 1
    synced_return_id, synced_payload = spy.posted[0]
    assert synced_return_id == 7788
    assert synced_payload["execute_paypal_refund"] is False  # REF-001 enforced
    assert synced_payload["action"] in {"APPROVE", "REJECT", "ESCALATE"}

    intel_res = client.get(
        f"/api/v1/refunds/{refund_id}/intelligence",
        headers={"Authorization": f"Bearer {_make_jwt(101, 'customer')}"},
    )
    assert intel_res.status_code == 200, intel_res.text
    summary = intel_res.json()["latest_agent_summary"]
    assert summary is not None
    assert summary["customer_message"] != summary["recommended_action"]
    assert "evidence_references" in summary


