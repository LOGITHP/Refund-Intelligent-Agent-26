"""Unit tests for Task 3: logging redaction, security bridge, Shipkart client, MinIO, and EvidenceService."""

from __future__ import annotations

import hashlib
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.core.logging_redact import RedactingFormatter, redact_sensitive_data
from app.core.security import (
    compute_hmac_signature,
    create_service_jwt,
    get_current_actor,
    require_roles,
    verify_bridge_hmac,
    verify_hmac_signature,
    verify_service_jwt,
    verify_shipkart_user_token,
)
from app.integrations.minio_client import AgentMinIOClient, InMemoryObjectStorage
from app.integrations.shipkart_client import ShipkartBridgeClient, ShipkartBridgeError
from app.services.evidence_service import (
    EvidenceService,
    EvidenceValidationError,
    ValidatedEvidence,
)


def _make_valid_png_bytes(width: int = 8, height: int = 6) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(12, 120, 200))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_valid_jpeg_bytes(width: int = 10, height: int = 4) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(200, 40, 20))
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Logging Redaction Tests
# ---------------------------------------------------------------------------


def test_redact_sensitive_data_strips_secrets_tokens_and_card_fields_recursively() -> None:
    payload = {
        "order_id": 101,
        "status": "PENDING",
        "company": "Shipkart",
        "client_secret": "super-secret-paypal-value",
        "nested": {
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def",
            "api_key": "nvapi-abcdef1234567890",
            "card_pan": "4111111111111111",
            "cvv": "999",
            "card_number": "4111-1111-1111-1111",
            "cookie": "session=xyz123",
            "safe_note": "Customer called about delayed parcel",
        },
        "logs": [
            "Calling upstream with Bearer my-jwt-token-123 and key nvapi-xyz987654321",
            {"password": "hunter2", "token": "tok_live_999", "reason": "damaged"},
        ],
    }

    redacted = redact_sensitive_data(payload)

    assert redacted["order_id"] == 101
    assert redacted["status"] == "PENDING"
    assert redacted["company"] == "Shipkart"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["nested"]["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["card_pan"] == "[REDACTED]"
    assert redacted["nested"]["cvv"] == "[REDACTED]"
    assert redacted["nested"]["card_number"] == "[REDACTED]"
    assert redacted["nested"]["cookie"] == "[REDACTED]"
    assert redacted["nested"]["safe_note"] == "Customer called about delayed parcel"
    assert "my-jwt-token-123" not in redacted["logs"][0]
    assert "nvapi-xyz987654321" not in redacted["logs"][0]
    assert "Bearer [REDACTED]" in redacted["logs"][0]
    assert redacted["logs"][1]["password"] == "[REDACTED]"
    assert redacted["logs"][1]["token"] == "[REDACTED]"
    assert redacted["logs"][1]["reason"] == "damaged"

    # Original input must not be mutated
    assert payload["client_secret"] == "super-secret-paypal-value"


def test_redacting_formatter_sanitizes_log_messages_and_extras() -> None:
    formatter = RedactingFormatter("%(levelname)s %(name)s %(message)s")
    record = logging.LogRecord(
        name="refund.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Auth header Bearer tok_secret_abc and key nvapi-secret-999 for order %s",
        args=("ORD-55",),
        exc_info=None,
    )
    record.client_secret = "dont-leak-me"
    record.order_id = 55

    formatted = formatter.format(record)

    assert "tok_secret_abc" not in formatted
    assert "nvapi-secret-999" not in formatted
    assert "dont-leak-me" not in formatted
    assert "ORD-55" in formatted
    assert "55" in formatted


# ---------------------------------------------------------------------------
# 2. HMAC, Service JWT, Shipkart User JWT & FastAPI RBAC Tests
# ---------------------------------------------------------------------------


def test_hmac_signature_verification_accepts_valid_and_rejects_tampered() -> None:
    secret = "bridge-shared-secret-test"
    body = b'{"event":"RETURN_CREATED","shipkart_return_id":42}'

    sig = compute_hmac_signature(body, secret)
    assert verify_hmac_signature(body, sig, secret) is True
    assert verify_hmac_signature(body, f"sha256={sig}", secret) is True

    tampered_body = b'{"event":"RETURN_CREATED","shipkart_return_id":99}'
    assert verify_hmac_signature(tampered_body, sig, secret) is False
    assert verify_hmac_signature(body, "sha256=" + ("0" * 64), secret) is False
    assert verify_hmac_signature(body, "", secret) is False


def test_service_jwt_requires_secret_and_validates_claims() -> None:
    with patch.object(settings, "SERVICE_JWT_SECRET", ""):
        with pytest.raises(RuntimeError):
            create_service_jwt()

    with patch.object(settings, "SERVICE_JWT_SECRET", "svc-secret-key-at-least-32-bytes-long"):
        token = create_service_jwt(subject="refund-agent-core", scope="bridge:read_write")
        claims = verify_service_jwt(token)
        assert claims["sub"] == "refund-agent-core"
        assert claims["iss"] == settings.SERVICE_JWT_ISSUER
        assert claims["scope"] == "bridge:read_write"

        # Tampered token must fail with 401
        with pytest.raises(Exception) as exc_info:
            verify_service_jwt(token + "tamper")
        assert getattr(exc_info.value, "status_code", None) == 401

        # Expired token must fail with 401
        expired_token = create_service_jwt(ttl_seconds=-10)
        with pytest.raises(Exception) as exp_exc:
            verify_service_jwt(expired_token)
        assert getattr(exp_exc.value, "status_code", None) == 401


def test_shipkart_user_jwt_verification_and_fastapi_rbac_dependencies() -> None:
    user_secret = "shipkart-user-jwt-secret-32-bytes-min"
    service_secret = "service-jwt-secret-32-bytes-minimum!"
    bridge_secret = "bridge-hmac-secret-32-bytes-minimum!"

    customer_token = jwt.encode(
        {
            "sub": "101",
            "user_id": 101,
            "role": "customer",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        user_secret,
        algorithm="HS256",
    )
    merchant_token = jwt.encode(
        {
            "sub": "202",
            "user_id": 202,
            "role": "merchant",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        user_secret,
        algorithm="HS256",
    )

    with (
        patch.object(settings, "JWT_SECRET_KEY", user_secret),
        patch.object(settings, "SERVICE_JWT_SECRET", service_secret),
        patch.object(settings, "BRIDGE_SHARED_SECRET", bridge_secret),
    ):
        decoded = verify_shipkart_user_token(customer_token)
        assert decoded["user_id"] == 101
        assert decoded["sub"] == "101"
        assert decoded["role"] == "customer"

        app = FastAPI()

        @app.get("/merchant-only")
        def merchant_only(actor: dict = Depends(require_roles("merchant", "admin"))):
            return {"actor": actor}

        @app.get("/any-actor")
        def any_actor(actor: dict = Depends(get_current_actor)):
            return {"actor": actor}

        @app.post("/bridge-event")
        def bridge_event(raw_body: bytes = Depends(verify_bridge_hmac)):
            return {"bytes": len(raw_body)}

        client = TestClient(app)

        # Unauthenticated -> 401
        assert client.get("/any-actor").status_code == 401
        assert client.get("/any-actor", headers={"Authorization": "Bearer invalid.jwt.tok"}).status_code == 401

        # Customer calling merchant endpoint -> 403
        res_forbidden = client.get(
            "/merchant-only",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert res_forbidden.status_code == 403

        # Merchant calling merchant endpoint -> 200
        res_ok = client.get(
            "/merchant-only",
            headers={"Authorization": f"Bearer {merchant_token}"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json()["actor"]["role"] == "merchant"

        # Service token accepted by get_current_actor
        svc_token = create_service_jwt()
        res_svc = client.get("/any-actor", headers={"Authorization": f"Bearer {svc_token}"})
        assert res_svc.status_code == 200
        assert res_svc.json()["actor"]["sub"] == "refund-agent-core"

        # Bridge HMAC dependency checks
        payload_bytes = b'{"return_id": 77}'
        sig = compute_hmac_signature(payload_bytes, bridge_secret)
        assert (
            client.post(
                "/bridge-event",
                content=payload_bytes,
                headers={"X-Bridge-Signature": f"sha256={sig}"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/bridge-event",
                content=payload_bytes,
                headers={"X-Bridge-Signature": "sha256=" + ("f" * 64)},
            ).status_code
            == 401
        )
        assert client.post("/bridge-event", content=payload_bytes).status_code == 401


# ---------------------------------------------------------------------------
# 3. ShipkartBridgeClient Tests
# ---------------------------------------------------------------------------


def test_shipkart_bridge_client_attaches_service_jwt_and_decodes_responses() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/api/v1/orders/12/bridge-context":
            return httpx.Response(200, json={"order_id": 12, "paypal_capture_id": "CAP-12"})
        if request.url.path == "/api/v1/returns/bridge/pending":
            return httpx.Response(200, json=[{"return_id": 5, "merchant_id": 9}])
        if request.url.path == "/api/v1/media/files/return-evidence/proof.png":
            return httpx.Response(
                200,
                content=b"\x89PNG\r\n\x1a\nfake",
                headers={"content-type": "image/png"},
            )
        if request.url.path == "/api/v1/returns/5/agent-decision":
            return httpx.Response(200, json={"accepted": True, "return_id": 5})
        if request.url.path == "/api/v1/returns/5/execute-approved-refund":
            return httpx.Response(200, json={"status": "REFUNDED", "paypal_refund_id": "REF-99"})
        if request.url.path == "/api/v1/orders/404/bridge-context":
            return httpx.Response(404, json={"detail": "Order not found"})
        return httpx.Response(500, json={"detail": "Unexpected path"})

    transport = httpx.MockTransport(handler)
    with patch.object(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes"):
        client = ShipkartBridgeClient(base_url="http://shipkart.test", transport=transport)

        order_ctx = client.fetch_order_context(12)
        assert order_ctx["paypal_capture_id"] == "CAP-12"

        pending = client.fetch_pending_returns(merchant_id=9)
        assert pending == [{"return_id": 5, "merchant_id": 9}]

        media_bytes, mime = client.fetch_media_bytes("return-evidence/proof.png")
        assert media_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert mime == "image/png"

        rec = client.post_agent_recommendation(5, {"action": "QUEUE_MERCHANT_APPROVAL"})
        assert rec["accepted"] is True

        exec_res = client.submit_approved_refund_execution(5, {"approval_id": "app-1"})
        assert exec_res["paypal_refund_id"] == "REF-99"

        # Every call carries valid Service JWT
        assert len(captured_requests) == 5
        for req in captured_requests:
            auth = req.headers.get("Authorization", "")
            assert auth.startswith("Bearer ")
            claims = verify_service_jwt(auth.split(" ", 1)[1])
            assert claims["sub"] == "refund-agent-core"

        # Non-2xx raises typed ShipkartBridgeError
        with pytest.raises(ShipkartBridgeError) as err:
            client.fetch_order_context(404)
        assert err.value.status_code == 404

        # Path traversal & absolute URLs rejected
        with pytest.raises(ShipkartBridgeError):
            client.fetch_media_bytes("../../etc/passwd")
        with pytest.raises(ShipkartBridgeError):
            client.fetch_media_bytes("https://evil.example/steal.png")

    # Network error raises ShipkartBridgeError cleanly
    def failing_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with patch.object(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes"):
        failing_client = ShipkartBridgeClient(
            base_url="http://shipkart.test",
            transport=httpx.MockTransport(failing_handler),
        )
        with pytest.raises(ShipkartBridgeError) as net_err:
            failing_client.fetch_order_context(1)
        assert net_err.value.status_code is None


def test_shipkart_bridge_client_fetches_paypal_capture_and_refund_status() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path == "/api/v1/orders/42/paypal-capture-status":
            return httpx.Response(
                200,
                json={
                    "id": "CAP-MERCHANT-42",
                    "status": "COMPLETED",
                    "amount": {"value": "120.00", "currency_code": "USD"},
                },
            )
        if request.url.path == "/api/v1/returns/77/paypal-refund-status":
            return httpx.Response(
                200,
                json={
                    "id": "REF-MERCHANT-77",
                    "status": "PENDING",
                    "amount": {"value": "120.00", "currency_code": "USD"},
                },
            )
        if request.url.path == "/api/v1/orders/999/paypal-capture-status":
            return httpx.Response(503, json={"detail": "Merchant PayPal credentials not configured"})
        return httpx.Response(404, json={"detail": "Not found"})

    with patch.object(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes"):
        client = ShipkartBridgeClient(
            base_url="http://shipkart.test",
            transport=httpx.MockTransport(handler),
        )
        cap = client.fetch_paypal_capture_status(42)
        assert cap["id"] == "CAP-MERCHANT-42"
        assert cap["status"] == "COMPLETED"

        ref = client.fetch_paypal_refund_status(77)
        assert ref["id"] == "REF-MERCHANT-77"
        assert ref["status"] == "PENDING"

        assert len(captured_requests) == 2
        for req in captured_requests:
            auth = req.headers.get("Authorization", "")
            assert auth.startswith("Bearer ")
            claims = verify_service_jwt(auth.split(" ", 1)[1])
            assert claims["sub"] == "refund-agent-core"

        with pytest.raises(ShipkartBridgeError) as unconfigured_err:
            client.fetch_paypal_capture_status(999)
        assert unconfigured_err.value.status_code == 503

        with pytest.raises(ShipkartBridgeError) as missing_err:
            client.fetch_paypal_refund_status(404)
        assert missing_err.value.status_code == 404

    def failing_handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with patch.object(settings, "SERVICE_JWT_SECRET", "shipkart-bridge-jwt-secret-32-bytes"):
        failing_client = ShipkartBridgeClient(
            base_url="http://shipkart.test",
            transport=httpx.MockTransport(failing_handler),
        )
        with pytest.raises(ShipkartBridgeError) as net_err:
            failing_client.fetch_paypal_refund_status(77)
        assert net_err.value.status_code is None


# ---------------------------------------------------------------------------
# 4. Hardened Evidence Pipeline + MinIO Tests
# ---------------------------------------------------------------------------


def test_evidence_rejects_executable_spoofed_as_jpg() -> None:
    service = EvidenceService(minio_client=AgentMinIOClient(client=InMemoryObjectStorage()))
    mz_payload = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"

    with pytest.raises(EvidenceValidationError) as exc_info:
        service.validate_and_prepare(mz_payload, "receipt.jpg", "image/jpeg")
    assert exc_info.value.status_code == 422


def test_evidence_rejects_html_script_disguised_as_png() -> None:
    service = EvidenceService(minio_client=AgentMinIOClient(client=InMemoryObjectStorage()))
    html_payload = b"<html><body><script>alert('xss')</script></body></html>"

    with pytest.raises(EvidenceValidationError) as exc_info:
        service.validate_and_prepare(html_payload, "damage.png", "image/png")
    assert exc_info.value.status_code == 422


def test_evidence_rejects_oversized_and_empty_payloads() -> None:
    storage = InMemoryObjectStorage()
    service = EvidenceService(minio_client=AgentMinIOClient(client=storage), max_bytes=64)

    with pytest.raises(EvidenceValidationError) as empty_exc:
        service.validate_and_prepare(b"", "empty.png", "image/png")
    assert empty_exc.value.status_code == 422

    oversized = _make_valid_png_bytes(16, 16)
    assert len(oversized) > 64
    with pytest.raises(EvidenceValidationError) as size_exc:
        service.validate_and_prepare(oversized, "big.png", "image/png")
    assert size_exc.value.status_code == 422


def test_evidence_accepts_valid_png_jpeg_and_pdf_with_sha256_and_minio_storage() -> None:
    fake_storage = InMemoryObjectStorage()
    minio_client = AgentMinIOClient(client=fake_storage)
    persisted: list[ValidatedEvidence] = []
    service = EvidenceService(
        minio_client=minio_client,
        persist_callback=lambda ev, _data: persisted.append(ev),
    )

    png_bytes = _make_valid_png_bytes(12, 8)
    png_ev = service.store_evidence(png_bytes, "../../evil/photo.png", "image/png")
    assert png_ev.detected_mime == "image/png"
    assert png_ev.file_size == len(png_bytes)
    assert png_ev.sha256_hash == hashlib.sha256(png_bytes).hexdigest()
    assert png_ev.extracted_metadata["width"] == 12
    assert png_ev.extracted_metadata["height"] == 8
    assert ".." not in png_ev.file_name
    assert ".." not in png_ev.storage_key
    assert png_ev.verification_status == "VERIFIED"
    assert minio_client.download_bytes(settings.BUCKET_EVIDENCE, png_ev.storage_key) == png_bytes

    jpeg_bytes = _make_valid_jpeg_bytes(10, 5)
    jpeg_ev = service.store_evidence(jpeg_bytes, "box.jpeg", "image/jpeg")
    assert jpeg_ev.detected_mime == "image/jpeg"
    assert jpeg_ev.sha256_hash == hashlib.sha256(jpeg_bytes).hexdigest()
    assert jpeg_ev.extracted_metadata["width"] == 10
    assert jpeg_ev.extracted_metadata["height"] == 5

    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    pdf_ev = service.store_evidence(pdf_bytes, "invoice.pdf", "application/pdf")
    assert pdf_ev.detected_mime == "application/pdf"
    assert pdf_ev.sha256_hash == hashlib.sha256(pdf_bytes).hexdigest()
    assert pdf_ev.extracted_metadata["pdf_version"] == "1.4"
    assert minio_client.download_bytes(settings.BUCKET_EVIDENCE, pdf_ev.storage_key) == pdf_bytes
    assert "http" in minio_client.presigned_get_url(settings.BUCKET_EVIDENCE, pdf_ev.storage_key)
    assert len(persisted) == 3


def test_evidence_rejects_elf_corrupt_image_and_mime_mismatch_and_flags_truncated_pdf() -> None:
    fake_storage = InMemoryObjectStorage()
    minio_client = AgentMinIOClient(client=fake_storage)
    ensured = minio_client.ensure_buckets()
    assert ensured == [settings.BUCKET_EVIDENCE, settings.BUCKET_REPORTS]

    service = EvidenceService(minio_client=minio_client)

    with pytest.raises(EvidenceValidationError) as elf_exc:
        service.validate_and_prepare(b"\x7fELF\x02\x01\x01\x00", "doc.pdf", "application/pdf")
    assert elf_exc.value.status_code == 422

    with pytest.raises(EvidenceValidationError) as corrupt_exc:
        service.validate_and_prepare(b"\xff\xd8\xff\xe0not-a-valid-jpeg", "bad.jpg", "image/jpeg")
    assert corrupt_exc.value.status_code == 422

    png_bytes = _make_valid_png_bytes(4, 4)
    with pytest.raises(EvidenceValidationError) as mismatch_exc:
        service.validate_and_prepare(png_bytes, "img.png", "application/pdf")
    assert mismatch_exc.value.status_code == 422

    flagged_pdf = service.validate_and_prepare(
        b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n",
        "partial.pdf",
        "application/pdf",
    )
    assert flagged_pdf.verification_status == "FLAGGED"
    assert "missing_eof_marker" in flagged_pdf.extracted_metadata["warnings"]
