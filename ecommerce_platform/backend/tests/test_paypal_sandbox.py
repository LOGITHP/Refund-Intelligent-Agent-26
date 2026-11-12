from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hmac
import hashlib
import json
import os
import base64
import re
import zlib
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from app.core.config import Settings, settings
from app.core.crypto import decrypt_secret, encrypt_secret, redact_sensitive_data
from app.core.security import compute_bridge_hmac
from app.db.database import Base, ensure_schema_columns, get_db
from app.db.models import (
    InventoryReservation,
    MerchantOrderAllocation,
    MerchantPaymentPreference,
    Order,
    OrderStatus,
    PaymentLedgerEvent,
    ProcessedWebhookEvent,
    Product,
    utcnow,
)
from app.main import app
from app.services.inventory_service import release_expired_reservations
from app.services.paypal_service import (
    PayPalService,
    _merchant_service_cache,
    get_paypal_service,
    merchant_paypal_aad,
)


class MockPayPalBackend:
    """Controllable httpx.MockTransport simulating PayPal Sandbox REST v2 endpoints."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail_create_order = False
        self.capture_amount_override: str | None = None
        self.capture_status_override: str = "COMPLETED"
        self.webhook_verification_status = "SUCCESS"
        self.rejected_client_ids: set[str] = set()
        self.order_counter = 0
        self.capture_counter = 0
        self.refund_counter = 0
        self.orders: dict[str, dict] = {}
        self.captures: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}

    @staticmethod
    def _extract_basic_client_id(auth_header: str) -> str:
        if auth_header.lower().startswith("basic "):
            encoded = auth_header.split(" ", 1)[1].strip()
            decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            return decoded.split(":", 1)[0]
        return ""

    def handler(self, request: httpx.Request) -> httpx.Response:
        raw_body = request.content.decode("utf-8") if request.content else ""
        try:
            body_json = json.loads(raw_body) if raw_body else {}
        except Exception:
            body_json = {"raw": raw_body}

        headers_lower = {k.lower(): v for k, v in request.headers.items()}
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "host": request.url.host,
                "headers": headers_lower,
                "json": body_json,
            }
        )

        path = request.url.path
        if request.method == "POST" and path == "/v1/oauth2/token":
            client_id = self._extract_basic_client_id(headers_lower.get("authorization", ""))
            if client_id in self.rejected_client_ids or not client_id:
                return httpx.Response(
                    401,
                    json={"error": "invalid_client", "error_description": "Client Authentication failed"},
                )
            return httpx.Response(
                200,
                json={"access_token": f"mock_token_{client_id}", "token_type": "Bearer", "expires_in": 3600},
            )

        if request.method == "POST" and path == "/v2/checkout/orders":
            if self.fail_create_order:
                return httpx.Response(500, json={"name": "INTERNAL_SERVER_ERROR", "message": "Mock PayPal outage"})
            self.order_counter += 1
            pp_order_id = f"PP-ORD-{self.order_counter:04d}"
            pu = (body_json.get("purchase_units") or [{}])[0]
            order_obj = {
                "id": pp_order_id,
                "status": "CREATED",
                "purchase_units": [pu],
            }
            self.orders[pp_order_id] = order_obj
            return httpx.Response(201, json=order_obj)

        if request.method == "POST" and path.startswith("/v2/checkout/orders/") and path.endswith("/capture"):
            pp_order_id = path.split("/")[4]
            stored = self.orders.get(pp_order_id, {})
            pu = (stored.get("purchase_units") or [{}])[0]
            amt = dict(pu.get("amount") or {"currency_code": "USD", "value": "10.00"})
            if self.capture_amount_override is not None:
                amt["value"] = self.capture_amount_override

            self.capture_counter += 1
            cap_id = f"CAP-{self.capture_counter:04d}"
            cap_obj = {
                "id": cap_id,
                "status": self.capture_status_override,
                "amount": amt,
                "supplementary_data": {"related_ids": {"order_id": pp_order_id}},
            }
            self.captures[cap_id] = cap_obj
            return httpx.Response(
                201,
                json={
                    "id": pp_order_id,
                    "status": self.capture_status_override,
                    "purchase_units": [
                        {
                            "payments": {
                                "captures": [cap_obj],
                            }
                        }
                    ],
                },
            )

        if request.method == "GET" and path.startswith("/v2/checkout/orders/"):
            pp_order_id = path.split("/")[4]
            return httpx.Response(200, json=self.orders.get(pp_order_id, {"id": pp_order_id, "status": "APPROVED"}))

        if request.method == "GET" and path.startswith("/v2/payments/captures/"):
            cap_id = path.split("/")[4]
            return httpx.Response(
                200,
                json=self.captures.get(
                    cap_id,
                    {"id": cap_id, "status": "COMPLETED", "amount": {"value": "10.00", "currency_code": "USD"}},
                ),
            )

        if request.method == "POST" and path.startswith("/v2/payments/captures/") and path.endswith("/refund"):
            cap_id = path.split("/")[4]
            self.refund_counter += 1
            ref_id = f"REF-{self.refund_counter:04d}"
            amt = body_json.get("amount") or {"value": "10.00", "currency_code": "USD"}
            ref_obj = {
                "id": ref_id,
                "status": "COMPLETED",
                "amount": amt,
                "links": [
                    {"rel": "up", "href": f"https://api-m.sandbox.paypal.com/v2/payments/captures/{cap_id}"}
                ],
                "supplementary_data": {"related_ids": {"capture_id": cap_id}},
            }
            self.refunds[ref_id] = ref_obj
            return httpx.Response(201, json=ref_obj)

        if request.method == "GET" and path.startswith("/v2/payments/refunds/"):
            ref_id = path.split("/")[4]
            if ref_id in self.refunds:
                return httpx.Response(200, json=self.refunds[ref_id])
            return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

        if request.method == "POST" and path == "/v1/notifications/verify-webhook-signature":
            return httpx.Response(
                200,
                json={"verification_status": self.webhook_verification_status},
            )

        return httpx.Response(404, json={"message": f"Unhandled mock route {request.method} {path}"})


@pytest.fixture()
def sandbox_env(tmp_path, monkeypatch):
    db_file = tmp_path / "paypal_sandbox_test.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    # Seed one starter catalog product (merchant_id=None) inside isolated DB
    with TestingSessionLocal() as s:
        s.add(
            Product(
                merchant_id=None,
                title="Starter Catalog Item",
                brand="Shipkart",
                category="Electronics",
                description="Starter item",
                price=Decimal("100.00"),
                mrp=Decimal("150.00"),
                sandbox_usd_price=Decimal("5.00"),
                stock=10,
                image_url="/api/v1/media/files/product-images/sony_xm5.svg",
            )
        )
        s.commit()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    mock_backend = MockPayPalBackend()
    mock_transport = httpx.MockTransport(mock_backend.handler)
    mock_paypal_svc = PayPalService(
        client_id="sb-test-client-id",
        client_secret="sb-test-client-secret",
        webhook_id="WH-TEST-ID-123",
        base_url="https://api-m.sandbox.paypal.com",
        transport=mock_transport,
    )

    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "sb-test-client-id")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "sb-test-client-secret")
    monkeypatch.setattr(settings, "PAYPAL_WEBHOOK_ID", "WH-TEST-ID-123")
    monkeypatch.setattr(settings, "PAYPAL_ENV", "SANDBOX")
    monkeypatch.setattr(settings, "APP_DATA_ENCRYPTION_KEY", "sb-test-aes256-gcm-encryption-key-32b")
    monkeypatch.setattr(settings, "SEED_SAMPLE_CATALOG", False)
    monkeypatch.setattr(settings, "SERVICE_JWT_SECRET", "sb-test-service-jwt-secret")
    monkeypatch.setattr(settings, "SERVICE_JWT_ISSUER", "refund-intelligence-platform")
    monkeypatch.setattr(settings, "BRIDGE_SHARED_SECRET", "sb-test-bridge-hmac-secret")

    _merchant_service_cache.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_paypal_service] = lambda: mock_paypal_svc

    try:
        with TestClient(app) as client:
            yield {
                "client": client,
                "session_factory": TestingSessionLocal,
                "mock_paypal": mock_backend,
                "paypal_service": mock_paypal_svc,
            }
    finally:
        _merchant_service_cache.clear()
        app.dependency_overrides.clear()
        test_engine.dispose()


def _configure_merchant_paypal(
    client: TestClient,
    merchant_headers: dict,
    *,
    client_id: str = "merch-sb-client-default",
    client_secret: str = "merch-sb-secret-default-9999",
    webhook_id: str = "WH-MERCH-DEFAULT",
    environment: str = "SANDBOX",
    verify_before_save: bool = False,
) -> dict:
    resp = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merchant_headers,
        json={
            "payout_paypal_email": "merchant-sb@business.example.com",
            "payout_currency": "USD",
            "auto_refund_limit_usd": "200.00",
            "return_window_days": 14,
            "is_active": True,
            "paypal_environment": environment,
            "paypal_client_id": client_id,
            "paypal_client_secret": client_secret,
            "paypal_webhook_id": webhook_id,
            "verify_before_save": verify_before_save,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _register(client: TestClient, role: str, suffix: str, name: str = "Test User") -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{role}_{suffix}@example.com",
            "password": "password123",
            "full_name": name,
            "phone": "9876543210",
            "role": role,
            "business_name": f"Biz {suffix}" if role == "merchant" else None,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "user": data["user"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def _create_product(
    client: TestClient,
    merchant_headers: dict,
    *,
    title: str,
    price: str,
    mrp: str,
    sandbox_usd_price: str,
    stock: int = 5,
) -> dict:
    resp = client.post(
        "/api/v1/products/",
        headers=merchant_headers,
        json={
            "title": title,
            "brand": "TestBrand",
            "category": "Electronics",
            "description": "High precision product",
            "price": price,
            "mrp": mrp,
            "sandbox_usd_price": sandbox_usd_price,
            "stock": stock,
            "image_url": "/api/v1/media/files/product-images/sony_xm5.svg",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


SAMPLE_ADDRESS = {
    "full_name": "Test Buyer",
    "phone": "9876543210",
    "pincode": "560001",
    "locality": "MG Road",
    "street_address": "123 Market St",
    "city": "Bengaluru",
    "state": "Karnataka",
}


def test_aes256_gcm_roundtrip_and_redaction():
    key_bytes = os.urandom(32)
    key_b64 = base64.urlsafe_b64encode(key_bytes).decode("ascii")
    key_hex = key_bytes.hex()

    secret = "paypal_live_secret_value_12345"
    ct1 = encrypt_secret(secret, key=key_b64)
    ct2 = encrypt_secret(secret, key=key_b64)

    # Unique 96-bit random nonce per encryption
    assert ct1 != ct2
    assert decrypt_secret(ct1, key=key_b64) == secret
    assert decrypt_secret(ct2, key=key_hex) == secret

    # Tampered ciphertext must fail authentication tag check
    tampered = ct1[:-4] + ("AAAA" if not ct1.endswith("AAAA") else "BBBB")
    with pytest.raises((InvalidTag, ValueError)):
        decrypt_secret(tampered, key=key_b64)

    # Wrong key fails
    wrong_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    with pytest.raises(InvalidTag):
        decrypt_secret(ct1, key=wrong_key)

    # Missing key raises ValueError
    with pytest.raises(ValueError):
        encrypt_secret(secret, key="")

    # Secret scrubbing & Decimal normalization
    scrubbed = redact_sensitive_data(
        {
            "authorization": "Bearer super_secret_jwt",
            "nested": {
                "client_secret": "shh_secret",
                "access_token": "tok_123",
                "amount": Decimal("19.99"),
                "header": "Basic YWRtaW46c2VjcmV0",
            },
            "paypal_order_id": "PP-ORD-0001",
        }
    )
    assert scrubbed["authorization"] == "[REDACTED]"
    assert scrubbed["nested"]["client_secret"] == "[REDACTED]"
    assert scrubbed["nested"]["access_token"] == "[REDACTED]"
    assert scrubbed["nested"]["amount"] == "19.99"
    assert scrubbed["nested"]["header"] == "Basic [REDACTED]"
    assert scrubbed["paypal_order_id"] == "PP-ORD-0001"


def test_multi_merchant_mixed_cart_allocations_and_cross_merchant_guards(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]

    merch_a = _register(client, "merchant", "a1", "Merchant A")
    merch_b = _register(client, "merchant", "b1", "Merchant B")
    buyer = _register(client, "customer", "c1", "Customer One")

    # Merchant payment settings endpoints (configure direct PayPal keys for A and B)
    put_pref = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merch_a["headers"],
        json={
            "payout_paypal_email": "merchant-a-sb@business.example.com",
            "payout_currency": "USD",
            "auto_refund_limit_usd": "200.00",
            "return_window_days": 14,
            "is_active": True,
            "paypal_client_id": "client-a-sb",
            "paypal_client_secret": "secret-a-sb-1234",
            "paypal_webhook_id": "WH-A-1",
        },
    )
    assert put_pref.status_code == 200
    assert put_pref.json()["payout_paypal_email"] == "merchant-a-sb@business.example.com"
    assert put_pref.json()["auto_refund_limit_usd"] == 200.0
    assert put_pref.json()["paypal_configured"] is True

    _configure_merchant_paypal(
        client, merch_b["headers"], client_id="client-b-sb", client_secret="secret-b-sb-5678", webhook_id="WH-B-1"
    )

    # Customer forbidden from merchant payment settings
    assert client.get("/api/v1/merchant/payment-settings", headers=buyer["headers"]).status_code == 403

    prod_a = _create_product(
        client, merch_a["headers"], title="Merchant A Phone", price="1000.00", mrp="1200.00", sandbox_usd_price="12.50"
    )
    prod_b = _create_product(
        client, merch_b["headers"], title="Merchant B Watch", price="500.00", mrp="700.00", sandbox_usd_price="7.50"
    )

    # Starter catalog item (merchant_id=None)
    starter_products = client.get("/api/v1/products/").json()
    starter_item = next(p for p in starter_products if p["merchant_id"] is None)

    # Customer adds Merchant A item (x2), Merchant B item (x1), and starter item (x1)
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_a["id"], "quantity": 2}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_b["id"], "quantity": 1}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": starter_item["id"], "quantity": 1}).status_code == 201

    cfg = client.get("/api/v1/payments/paypal/client-config", headers=buyer["headers"])
    assert cfg.status_code == 200
    cfg_data = cfg.json()
    assert cfg_data["configured"] is True
    assert cfg_data["eligible"] is True
    assert cfg_data["requires_split_checkout"] is True
    assert len(cfg_data["groups"]) == 3
    assert cfg_data["paypal_currency"] == "USD"
    # 12.50*2 + 7.50 + 5.00 = 37.50
    assert cfg_data["paypal_amount"] == 37.5
    assert cfg_data["original_amount"] == 2600.0
    assert cfg_data["items_count"] == 4

    # Unsplit create-order on mixed cart must return 400
    unsplit_resp = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS},
    )
    assert unsplit_resp.status_code == 400

    # Checkout each group sequentially via direct merchant checkout
    c_a = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "merchant_id": merch_a["user"]["id"]},
    )
    assert c_a.status_code == 201, c_a.text
    d_a = c_a.json()
    assert d_a["paypal_amount"] == 25.0
    cap_a = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": d_a["local_order_id"], "paypal_order_id": d_a["paypal_order_id"]},
    )
    assert cap_a.status_code == 200
    assert cap_a.json()["payment_status"] == "PAID"
    assert cap_a.json()["merchant_id"] == merch_a["user"]["id"]

    c_b = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "merchant_id": merch_b["user"]["id"]},
    )
    assert c_b.status_code == 201, c_b.text
    d_b = c_b.json()
    assert d_b["paypal_amount"] == 7.5
    cap_b = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": d_b["local_order_id"], "paypal_order_id": d_b["paypal_order_id"]},
    )
    assert cap_b.status_code == 200

    c_plat = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "is_platform_catalog": True},
    )
    assert c_plat.status_code == 201, c_plat.text
    d_plat = c_plat.json()
    assert d_plat["paypal_amount"] == 5.0
    cap_plat = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": d_plat["local_order_id"], "paypal_order_id": d_plat["paypal_order_id"]},
    )
    assert cap_plat.status_code == 200
    assert cap_plat.json()["merchant_id"] is None

    # Verify exact MerchantOrderAllocation splits in DB
    with SessionLocal() as db:
        alloc_a_row = (
            db.query(MerchantOrderAllocation)
            .filter(MerchantOrderAllocation.order_id == d_a["local_order_id"])
            .one()
        )
        alloc_b_row = (
            db.query(MerchantOrderAllocation)
            .filter(MerchantOrderAllocation.order_id == d_b["local_order_id"])
            .one()
        )
        alloc_p_row = (
            db.query(MerchantOrderAllocation)
            .filter(MerchantOrderAllocation.order_id == d_plat["local_order_id"])
            .one()
        )
        assert alloc_a_row.gross_inr == Decimal("2000.00")
        assert alloc_a_row.gross_usd == Decimal("25.00")
        assert alloc_b_row.gross_inr == Decimal("500.00")
        assert alloc_b_row.gross_usd == Decimal("7.50")
        assert alloc_p_row.gross_inr == Decimal("100.00")
        assert alloc_p_row.gross_usd == Decimal("5.00")
        assert all(a.settlement_status == "CAPTURED" for a in (alloc_a_row, alloc_b_row, alloc_p_row))

    # Verify /merchant/allocations scopes strictly to caller merchant
    alloc_a = client.get("/api/v1/merchant/allocations", headers=merch_a["headers"]).json()
    assert len(alloc_a) == 1
    assert alloc_a[0]["gross_usd"] == 25.0

    alloc_b = client.get("/api/v1/merchant/allocations", headers=merch_b["headers"]).json()
    assert len(alloc_b) == 1
    assert alloc_b[0]["gross_usd"] == 7.5

    # Exclusive Merchant B order -> Merchant A MUST get 403 on status/read/invoice/returns
    excl_order = client.post(
        "/api/v1/orders/",
        headers=buyer["headers"],
        json={
            "shipping_address": SAMPLE_ADDRESS,
            "buy_now_product_id": prod_b["id"],
            "buy_now_quantity": 1,
        },
    )
    assert excl_order.status_code == 201
    excl_id = excl_order.json()["id"]
    excl_item_id = excl_order.json()["items"][0]["id"]

    assert client.get(f"/api/v1/orders/{excl_id}", headers=merch_a["headers"]).status_code == 403
    assert client.patch(f"/api/v1/orders/{excl_id}/status?new_status=PACKED", headers=merch_a["headers"]).status_code == 403
    assert client.get(f"/api/v1/invoices/{excl_id}", headers=merch_a["headers"]).status_code == 403

    # Merchant B delivers it, buyer requests return, Merchant A cannot view or decide Merchant B's return
    assert client.patch(f"/api/v1/orders/{excl_id}/status?new_status=DELIVERED", headers=merch_b["headers"]).status_code == 200
    ret_resp = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": excl_id, "order_item_id": excl_item_id, "reason": "Defective"},
    )
    assert ret_resp.status_code == 201
    ret_id = ret_resp.json()["id"]
    assert client.get(f"/api/v1/returns/{ret_id}", headers=merch_a["headers"]).status_code == 403
    assert client.patch(
        f"/api/v1/returns/{ret_id}/decision",
        headers=merch_a["headers"],
        json={"status": "APPROVED"},
    ).status_code == 403


def test_inventory_reservation_concurrency_expiry_and_capture_exception(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch = _register(client, "merchant", "inv1", "Inv Merchant")
    _configure_merchant_paypal(client, merch["headers"], client_id="inv-client", client_secret="inv-secret-1111")
    buyer1 = _register(client, "customer", "invb1", "Buyer 1")
    buyer2 = _register(client, "customer", "invb2", "Buyer 2")

    prod = _create_product(
        client, merch["headers"], title="Last Rare GPU", price="49999.00", mrp="59999.00", sandbox_usd_price="599.00", stock=1
    )

    # PayPal failure on create-order cleanly releases reservation
    mock_paypal.fail_create_order = True
    fail_resp = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer1["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert fail_resp.status_code == 502
    mock_paypal.fail_create_order = False
    assert client.get(f"/api/v1/products/{prod['id']}").json()["available_stock"] == 1

    # Buyer 1 creates PayPal order -> reserves the 1 available unit
    b1_create = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer1["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert b1_create.status_code == 201
    b1_data = b1_create.json()
    assert client.get(f"/api/v1/products/{prod['id']}").json()["available_stock"] == 0

    # Buyer 2 cannot reserve or buy while Buyer 1 holds an ACTIVE reservation
    b2_blocked = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer2["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert b2_blocked.status_code == 400
    assert "Insufficient stock" in b2_blocked.json()["detail"]

    b2_std_blocked = client.post(
        "/api/v1/orders/",
        headers=buyer2["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert b2_std_blocked.status_code == 400

    # Force Buyer 1's reservation past TTL and run expiry release
    with SessionLocal() as db:
        res = (
            db.query(InventoryReservation)
            .filter(InventoryReservation.order_id == b1_data["local_order_id"])
            .first()
        )
        assert res.status == "ACTIVE"
        res.expires_at = utcnow() - timedelta(minutes=5)
        db.commit()
        expired_count = release_expired_reservations(db)
        assert expired_count == 1

        b1_order = db.query(Order).filter(Order.id == b1_data["local_order_id"]).first()
        assert b1_order.status == OrderStatus.CANCELLED
        assert b1_order.payment_status == "EXPIRED"

    # Now Buyer 2 reserves & captures the last unit -> stock goes to 0
    b2_create = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer2["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert b2_create.status_code == 201
    b2_data = b2_create.json()
    b2_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer2["headers"],
        json={"local_order_id": b2_data["local_order_id"], "paypal_order_id": b2_data["paypal_order_id"]},
    )
    assert b2_cap.status_code == 200
    assert b2_cap.json()["status"] == "ORDERED"
    assert client.get(f"/api/v1/products/{prod['id']}").json()["stock"] == 0

    # Buyer 1 finally captures late -> must enter CAPTURE_EXCEPTION instead of overselling!
    late_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer1["headers"],
        json={"local_order_id": b1_data["local_order_id"], "paypal_order_id": b1_data["paypal_order_id"]},
    )
    assert late_cap.status_code == 200
    assert late_cap.json()["status"] == "CAPTURE_EXCEPTION"
    assert late_cap.json()["payment_status"] == "CAPTURE_EXCEPTION_OUT_OF_STOCK"

    with SessionLocal() as db:
        db_prod = db.query(Product).filter(Product.id == prod["id"]).first()
        assert db_prod.stock == 0  # Never oversold
        exc_event = (
            db.query(PaymentLedgerEvent)
            .filter(
                PaymentLedgerEvent.order_id == b1_data["local_order_id"],
                PaymentLedgerEvent.event_type == "CAPTURE_EXCEPTION_OUT_OF_STOCK",
            )
            .first()
        )
        assert exc_event is not None


def test_capture_ownership_decimal_exactness_idempotency_and_immutable_ledger(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch = _register(client, "merchant", "dec1", "Decimal Merch")
    _configure_merchant_paypal(client, merch["headers"], client_id="dec-client", client_secret="dec-secret-2222")
    buyer1 = _register(client, "customer", "decb1", "Buyer One")
    buyer2 = _register(client, "customer", "decb2", "Buyer Two")

    # Classic IEEE-754 float trap: 0.10 + 0.20 == 0.30 exact in Decimal
    p1 = _create_product(
        client, merch["headers"], title="Item 10c", price="10.00", mrp="12.00", sandbox_usd_price="0.10", stock=5
    )
    p2 = _create_product(
        client, merch["headers"], title="Item 20c", price="20.00", mrp="25.00", sandbox_usd_price="0.20", stock=5
    )

    assert client.post("/api/v1/cart/items", headers=buyer1["headers"], json={"product_id": p1["id"], "quantity": 1}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer1["headers"], json={"product_id": p2["id"], "quantity": 1}).status_code == 201

    create_resp = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer1["headers"],
        json={"shipping_address": SAMPLE_ADDRESS},
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["paypal_amount"] == 0.3

    # Verify PayPal-Request-Id header sent on create-order
    create_call = next(c for c in mock_paypal.calls if c["path"] == "/v2/checkout/orders")
    assert "paypal-request-id" in create_call["headers"]
    assert create_call["json"]["purchase_units"][0]["amount"]["value"] == "0.30"

    # Ownership guard: Buyer 2 cannot capture Buyer 1's order
    wrong_user_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer2["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    )
    assert wrong_user_cap.status_code == 403

    # Binding guard: wrong paypal_order_id rejected
    wrong_id_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer1["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": "SPOOFED-PP-ORDER"},
    )
    assert wrong_id_cap.status_code == 400

    # Amount mismatch detection (0.29 != 0.30)
    mock_paypal.capture_amount_override = "0.29"
    mismatch_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer1["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    )
    assert mismatch_cap.status_code == 400
    mock_paypal.capture_amount_override = None

    # Reset order status from mismatch test to test clean capture on a fresh order
    with SessionLocal() as db:
        ord_row = db.query(Order).filter(Order.id == created["local_order_id"]).first()
        ord_row.status = OrderStatus.PENDING_PAYMENT
        ord_row.payment_status = "PENDING_PAYMENT"
        db.commit()

    cap_calls_before = len([c for c in mock_paypal.calls if c["path"].endswith("/capture")])
    ok_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer1["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    )
    assert ok_cap.status_code == 200
    ok_data = ok_cap.json()
    assert ok_data["status"] == "ORDERED"
    assert ok_data["payment_status"] == "PAID"
    assert ok_data["paypal_capture_id"] is not None

    # Cart cleared after capture
    assert client.get("/api/v1/cart/", headers=buyer1["headers"]).json()["total_items"] == 0

    # Invoice PDF generated and includes PayPal settlement details
    inv_resp = client.get(f"/api/v1/invoices/{created['local_order_id']}", headers=buyer1["headers"])
    assert inv_resp.status_code == 200
    assert inv_resp.headers["content-type"] == "application/pdf"
    assert inv_resp.content.startswith(b"%PDF-")
    decoded_streams = []
    for match in re.finditer(rb"stream[\r\n]+(.*?)[\r\n]*endstream", inv_resp.content, re.S):
        raw_stream = match.group(1).strip()
        try:
            decoded_streams.append(zlib.decompress(base64.a85decode(raw_stream, adobe=True)).decode("latin1"))
        except Exception:
            decoded_streams.append(raw_stream.decode("latin1", errors="ignore"))
    pdf_text = "\n".join(decoded_streams)
    assert created["paypal_order_id"] in pdf_text
    assert ok_data["paypal_capture_id"] in pdf_text
    assert "USD 0.30" in pdf_text

    # Idempotent repeat capture returns 200 without re-calling PayPal /capture
    repeat_cap = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer1["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    )
    assert repeat_cap.status_code == 200
    cap_calls_after = len([c for c in mock_paypal.calls if c["path"].endswith("/capture")])
    assert cap_calls_after == cap_calls_before + 1

    # Ledger sequence & immutability check
    with SessionLocal() as db:
        events = (
            db.query(PaymentLedgerEvent)
            .filter(PaymentLedgerEvent.order_id == created["local_order_id"])
            .order_by(PaymentLedgerEvent.id.asc())
            .all()
        )
        event_types = [e.event_type for e in events]
        assert "ORDER_CREATED" in event_types
        assert "CAPTURE_COMPLETED" in event_types
        capture_ev = next(e for e in events if e.event_type == "CAPTURE_COMPLETED")
        assert capture_ev.amount == Decimal("0.30")

        # Verify append-only constraint
        capture_ev.status_snapshot = "TAMPERED"
        with pytest.raises(ValueError, match="append-only"):
            db.flush()
        db.rollback()


def test_webhook_six_step_verification_dedup_and_reconciliation(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch = _register(client, "merchant", "wh1", "Webhook Merch")
    _configure_merchant_paypal(
        client, merch["headers"], client_id="wh-client", client_secret="wh-secret-3333", webhook_id="WH-TEST-ID-123"
    )
    buyer = _register(client, "customer", "whb1", "Webhook Buyer")
    prod = _create_product(
        client, merch["headers"], title="Webhook Product", price="1500.00", mrp="2000.00", sandbox_usd_price="20.00"
    )

    c_resp = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    ).json()
    cap_resp = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": c_resp["local_order_id"], "paypal_order_id": c_resp["paypal_order_id"]},
    ).json()
    capture_id = cap_resp["paypal_capture_id"]

    valid_headers = {
        "PAYPAL-TRANSMISSION-ID": "tx-1",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-12T10:00:00Z",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-TRANSMISSION-SIG": "sig-valid",
    }

    # 1. Spoofed cert URL (not *.paypal.com over https) -> 401 without calling PayPal verify API
    verify_calls_before = len([c for c in mock_paypal.calls if c["path"].endswith("verify-webhook-signature")])
    spoofed_headers = {**valid_headers, "PAYPAL-CERT-URL": "https://evil-paypal.com/cert.pem"}
    r_spoof = client.post(
        "/api/v1/webhooks/paypal",
        headers=spoofed_headers,
        json={"id": "EVT-SPOOF", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": capture_id}},
    )
    assert r_spoof.status_code == 401
    assert len([c for c in mock_paypal.calls if c["path"].endswith("verify-webhook-signature")]) == verify_calls_before

    # 2. HTTP (non-HTTPS) cert URL -> 401
    http_headers = {**valid_headers, "PAYPAL-CERT-URL": "http://api.sandbox.paypal.com/cert.pem"}
    assert client.post(
        "/api/v1/webhooks/paypal",
        headers=http_headers,
        json={"id": "EVT-HTTP", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": capture_id}},
    ).status_code == 401

    # 3. Invalid PayPal verification signature -> 401
    mock_paypal.webhook_verification_status = "FAILURE"
    assert client.post(
        "/api/v1/webhooks/paypal",
        headers=valid_headers,
        json={"id": "EVT-BAD-SIG", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": capture_id}},
    ).status_code == 401
    mock_paypal.webhook_verification_status = "SUCCESS"

    # 4. Non-allowlisted event ignored cleanly with 200
    r_ignored = client.post(
        "/api/v1/webhooks/paypal",
        headers=valid_headers,
        json={"id": "EVT-UNKNOWN", "event_type": "BILLING.SUBSCRIPTION.CREATED", "resource": {}},
    )
    assert r_ignored.status_code == 200
    assert r_ignored.json()["status"] == "ignored"

    # 5. CUSTOMER.DISPUTE.CREATED -> DISPUTED + deduplication on replay
    dispute_event = {
        "id": "EVT-DISPUTE-1",
        "event_type": "CUSTOMER.DISPUTE.CREATED",
        "resource": {
            "dispute_id": "PP-D-100",
            "dispute_amount": {"currency_code": "USD", "value": "20.00"},
            "disputed_transactions": [{"seller_transaction_id": capture_id}],
            "access_token": "should_be_redacted_in_audit",
        },
    }
    r_disp = client.post("/api/v1/webhooks/paypal", headers=valid_headers, json=dispute_event)
    assert r_disp.status_code == 200
    assert r_disp.json()["status"] == "processed"

    # Replay same event_id -> duplicate 200 without double ledger mutation
    r_disp_dup = client.post("/api/v1/webhooks/paypal", headers=valid_headers, json=dispute_event)
    assert r_disp_dup.status_code == 200
    assert r_disp_dup.json()["status"] == "duplicate"

    with SessionLocal() as db:
        ord_row = db.query(Order).filter(Order.id == c_resp["local_order_id"]).first()
        assert ord_row.payment_status == "DISPUTED"
        wh_row = db.query(ProcessedWebhookEvent).filter(ProcessedWebhookEvent.event_id == "EVT-DISPUTE-1").first()
        assert wh_row is not None
        assert wh_row.raw_redacted_payload["resource"]["access_token"] == "[REDACTED]"
        disp_ledgers = (
            db.query(PaymentLedgerEvent)
            .filter(
                PaymentLedgerEvent.order_id == ord_row.id,
                PaymentLedgerEvent.event_type == "CUSTOMER.DISPUTE.CREATED",
            )
            .all()
        )
        assert len(disp_ledgers) == 1

    # 6. PAYMENT.CAPTURE.REFUNDED webhook -> reconciles via /v2/payments/refunds/{id}
    mock_paypal.refunds["REF-WH-99"] = {
        "id": "REF-WH-99",
        "status": "COMPLETED",
        "amount": {"value": "20.00", "currency_code": "USD"},
        "supplementary_data": {"related_ids": {"capture_id": capture_id, "order_id": c_resp["paypal_order_id"]}},
    }
    r_ref = client.post(
        "/api/v1/webhooks/paypal",
        headers=valid_headers,
        json={
            "id": "EVT-REFUND-1",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource": {
                "id": "REF-WH-99",
                "status": "COMPLETED",
                "amount": {"value": "20.00", "currency_code": "USD"},
                "supplementary_data": {"related_ids": {"capture_id": capture_id}},
            },
        },
    )
    assert r_ref.status_code == 200
    with SessionLocal() as db:
        ord_row = db.query(Order).filter(Order.id == c_resp["local_order_id"]).first()
        assert ord_row.payment_status == "REFUNDED"


def test_paypal_proportional_refunds_by_agent_and_merchant(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch_a = _register(client, "merchant", "refa", "Refund Merch A")
    merch_b = _register(client, "merchant", "refb", "Refund Merch B")
    _configure_merchant_paypal(client, merch_a["headers"], client_id="ref-client-a", client_secret="ref-secret-a-4444")
    _configure_merchant_paypal(client, merch_b["headers"], client_id="ref-client-b", client_secret="ref-secret-b-5555")
    buyer = _register(client, "customer", "refc", "Refund Buyer")

    prod_a1 = _create_product(
        client, merch_a["headers"], title="Prod A1", price="1000.00", mrp="1200.00", sandbox_usd_price="12.50"
    )
    prod_a2 = _create_product(
        client, merch_a["headers"], title="Prod A2", price="500.00", mrp="600.00", sandbox_usd_price="7.50"
    )

    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_a1["id"], "quantity": 1}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_a2["id"], "quantity": 1}).status_code == 201

    created = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS},
    ).json()
    captured = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    ).json()

    order_id = captured["id"]
    item_a = next(i for i in captured["items"] if i["product_id"] == prod_a1["id"])
    item_b = next(i for i in captured["items"] if i["product_id"] == prod_a2["id"])

    # Deliver order
    assert client.patch(f"/api/v1/orders/{order_id}/status?new_status=DELIVERED", headers=merch_a["headers"]).status_code == 200

    # Return 1: Prod A1 (1000/1500 * 20.00 = 13.33 USD) -> executed after REF-001 merchant approval
    ret_a = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": order_id, "order_item_id": item_a["id"], "reason": "Damaged"},
    )
    assert ret_a.status_code == 201
    ret_a_data = ret_a.json()
    assert ret_a_data["refund_currency"] == "USD"
    assert ret_a_data["refund_paypal_amount"] == 13.33

    # Unauthenticated agent decision must fail 401
    unauth_dec = client.post(
        f"/api/v1/returns/{ret_a_data['id']}/agent-decision",
        json={
            "action": "APPROVE",
            "confidence_score": 0.95,
            "reasoning": "Verified defect",
            "execute_paypal_refund": True,
        },
    )
    assert unauth_dec.status_code == 401

    # Service-authenticated agent recommendation queues UNDER_REVIEW (REF-001: zero direct PayPal refund!)
    now = datetime.now(timezone.utc)
    service_jwt = jwt.encode(
        {
            "sub": "refund-agent-core",
            "iss": settings.SERVICE_JWT_ISSUER,
            "scope": "bridge:read_write",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.SERVICE_JWT_SECRET,
        algorithm="HS256",
    )
    service_headers = {"Authorization": f"Bearer {service_jwt}"}
    agent_dec = client.post(
        f"/api/v1/returns/{ret_a_data['id']}/agent-decision",
        headers=service_headers,
        json={
            "action": "APPROVE",
            "confidence_score": 0.95,
            "reasoning": "Verified defect",
            "execute_paypal_refund": True,
        },
    )
    assert agent_dec.status_code == 200
    assert agent_dec.json()["status"] == "UNDER_REVIEW"
    assert agent_dec.json()["refund_transaction_id"] is None
    assert len([c for c in mock_paypal.calls if c["path"].endswith("/refund")]) == 0

    # Merchant B cannot approve/execute Merchant A's return (403)
    cross_exec = client.post(
        f"/api/v1/returns/{ret_a_data['id']}/execute-approved-refund",
        headers=merch_b["headers"],
        json={"approval_reference": "CROSS-TENANT-BLOCK"},
    )
    assert cross_exec.status_code == 403

    # Merchant A explicitly approves and executes the proportional PayPal refund (13.33 USD)
    merch_a_exec = client.post(
        f"/api/v1/returns/{ret_a_data['id']}/execute-approved-refund",
        headers=merch_a["headers"],
        json={
            "approval_reference": "MERCH-A-APP-001",
            "merchant_notes": "Merchant A verified defect and approved PayPal refund",
        },
    )
    assert merch_a_exec.status_code == 200
    assert merch_a_exec.json()["status"] == "REFUNDED"
    assert merch_a_exec.json()["refund_transaction_id"].startswith("REF-")

    # Return 2: Prod A2 (500/1500 * 20.00 = 6.67 USD) -> executed by Merchant A decision
    ret_b = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": order_id, "order_item_id": item_b["id"], "reason": "Wrong color"},
    )
    assert ret_b.status_code == 201
    ret_b_data = ret_b.json()
    assert ret_b_data["refund_paypal_amount"] == 6.67

    merch_dec = client.patch(
        f"/api/v1/returns/{ret_b_data['id']}/decision",
        headers=merch_a["headers"],
        json={"status": "REFUNDED", "merchant_notes": "Approved by Merchant A"},
    )
    assert merch_dec.status_code == 200
    assert merch_dec.json()["refund_transaction_id"].startswith("REF-")

    with SessionLocal() as db:
        ord_row = db.query(Order).filter(Order.id == order_id).first()
        assert ord_row.payment_status == "REFUNDED"

        alloc_a = (
            db.query(MerchantOrderAllocation)
            .filter(MerchantOrderAllocation.order_id == order_id, MerchantOrderAllocation.merchant_id == merch_a["user"]["id"])
            .first()
        )
        assert alloc_a.refunded_usd == Decimal("20.00")

        refund_events = (
            db.query(PaymentLedgerEvent)
            .filter(PaymentLedgerEvent.order_id == order_id, PaymentLedgerEvent.event_type == "REFUND_COMPLETED")
            .all()
        )
        assert len(refund_events) == 2
        assert sum(e.amount for e in refund_events) == Decimal("20.00")

    refund_calls = [c for c in mock_paypal.calls if c["path"].endswith("/refund")]
    assert len(refund_calls) == 2
    assert refund_calls[0]["json"]["amount"]["value"] == "13.33"
    assert refund_calls[1]["json"]["amount"]["value"] == "6.67"
    assert refund_calls[0]["headers"]["authorization"] == "Bearer mock_token_ref-client-a"
    assert refund_calls[1]["headers"]["authorization"] == "Bearer mock_token_ref-client-a"



def test_paypal_config_token_caching_and_postgresql_ddl(sandbox_env, monkeypatch):
    client = sandbox_env["client"]
    mock_paypal = sandbox_env["mock_paypal"]
    paypal_svc = sandbox_env["paypal_service"]

    # 1. Settings SANDBOX vs LIVE base URL
    assert Settings(PAYPAL_ENV="SANDBOX").PAYPAL_BASE_URL == "https://api-m.sandbox.paypal.com"
    assert Settings(PAYPAL_ENV="LIVE").PAYPAL_BASE_URL == "https://api-m.paypal.com"

    # 2. PostgreSQL dialect DDL compilation verification across all tables & Numeric columns
    pg_dialect = postgresql.dialect()
    compiled_ddl = [
        str(CreateTable(table).compile(dialect=pg_dialect))
        for table in Base.metadata.sorted_tables
    ]
    joined_ddl = "\n".join(compiled_ddl)
    assert "NUMERIC(12, 2)" in joined_ddl
    assert "inventory_reservations" in joined_ddl
    assert "payment_ledger_events" in joined_ddl
    assert "processed_webhook_events" in joined_ddl
    assert "merchant_order_allocations" in joined_ddl
    assert "merchant_payment_preferences" in joined_ddl

    # 3. OAuth2 token caching across multiple order creates
    paypal_svc.clear_token_cache()
    calls_before = len([c for c in mock_paypal.calls if c["path"] == "/v1/oauth2/token"])
    paypal_svc.create_order(request_id="req-cache-1", amount_usd=Decimal("10.00"), reference_id="ORD-C1")
    paypal_svc.create_order(request_id="req-cache-2", amount_usd=Decimal("15.00"), reference_id="ORD-C2")
    calls_after = len([c for c in mock_paypal.calls if c["path"] == "/v1/oauth2/token"])
    assert calls_after == calls_before + 1

    # 4. Unconfigured PayPal credentials behavior
    buyer = _register(client, "customer", "unconf1", "Unconfigured Buyer")
    starter = client.get("/api/v1/products/").json()[0]
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": starter["id"], "quantity": 1}).status_code == 201

    unconfigured_svc = PayPalService(
        client_id="",
        client_secret="",
        webhook_id="",
        base_url="https://api-m.sandbox.paypal.com",
        transport=httpx.MockTransport(mock_paypal.handler),
    )
    app.dependency_overrides[get_paypal_service] = lambda: unconfigured_svc
    cfg = client.get("/api/v1/payments/paypal/client-config", headers=buyer["headers"])
    assert cfg.status_code == 200
    assert cfg.json()["configured"] is False
    assert cfg.json()["eligible"] is False
    assert cfg.json()["client_id"] == ""

    create_503 = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS},
    )
    assert create_503.status_code == 503


def test_bridge_context_service_auth_and_hmac_relay(sandbox_env, monkeypatch):
    client = sandbox_env["client"]
    merch = _register(client, "merchant", "brg1", "Bridge Merchant")
    _configure_merchant_paypal(client, merch["headers"], client_id="brg-client", client_secret="brg-secret-6666")
    buyer = _register(client, "customer", "brgb1", "Bridge Buyer")

    prod = _create_product(
        client, merch["headers"], title="Bridge Headphones", price="2999.00", mrp="3999.00", sandbox_usd_price="36.00"
    )
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod["id"], "quantity": 1}).status_code == 201

    created = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS},
    ).json()
    captured = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": created["local_order_id"], "paypal_order_id": created["paypal_order_id"]},
    ).json()
    order_id = captured["id"]
    item_id = captured["items"][0]["id"]

    # Unauthenticated and customer-authenticated bridge-context requests must fail 401
    assert client.get(f"/api/v1/orders/{order_id}/bridge-context").status_code == 401
    assert client.get(f"/api/v1/orders/{order_id}/bridge-context", headers=buyer["headers"]).status_code == 401

    # Capture HMAC relay emitted during return submission
    relayed: list[dict] = []

    def fake_httpx_post(url, content=None, headers=None, timeout=None):
        relayed.append({"url": url, "content": content, "headers": headers or {}})
        return httpx.Response(202, json={"accepted": True})

    monkeypatch.setattr("app.api.v1.endpoints.returns.httpx.post", fake_httpx_post)

    ret_resp = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": order_id, "order_item_id": item_id, "reason": "Bridge defect test"},
    )
    assert ret_resp.status_code == 201
    assert len(relayed) == 1
    assert relayed[0]["url"].endswith("/api/v1/bridge/shipkart/return-event")
    expected_sig = compute_bridge_hmac(relayed[0]["content"], settings.BRIDGE_SHARED_SECRET)
    assert hmac.compare_digest(relayed[0]["headers"]["X-Bridge-Signature"], expected_sig)

    # Valid Service JWT retrieves full bridge-context + pending returns
    now = datetime.now(timezone.utc)
    service_jwt = jwt.encode(
        {
            "sub": "refund-agent-core",
            "iss": settings.SERVICE_JWT_ISSUER,
            "scope": "bridge:read_write",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.SERVICE_JWT_SECRET,
        algorithm="HS256",
    )
    service_headers = {"Authorization": f"Bearer {service_jwt}"}
    ctx_resp = client.get(f"/api/v1/orders/{order_id}/bridge-context", headers=service_headers)
    assert ctx_resp.status_code == 200
    ctx = ctx_resp.json()
    assert ctx["paypal_capture_id"] == captured["paypal_capture_id"]
    assert len(ctx["items"]) == 1
    assert len(ctx["allocations"]) == 1
    assert len(ctx["returns"]) == 1

    pending_resp = client.get("/api/v1/returns/bridge/pending", headers=service_headers)
    assert pending_resp.status_code == 200
    assert any(r["id"] == ret_resp.json()["id"] for r in pending_resp.json())


def test_merchant_paypal_credentials_encryption_masking_verify_and_clear(sandbox_env, monkeypatch):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch = _register(client, "merchant", "cred1", "Credential Merchant")
    merch_id = merch["user"]["id"]
    buyer = _register(client, "customer", "credb1", "Credential Buyer")
    prod = _create_product(
        client, merch["headers"], title="Creds Camera", price="5000.00", mrp="6000.00", sandbox_usd_price="60.00"
    )

    # 1. Default unconfigured state
    get_init = client.get("/api/v1/merchant/payment-settings", headers=merch["headers"])
    assert get_init.status_code == 200
    init_data = get_init.json()
    assert init_data["paypal_configured"] is False
    assert init_data["has_client_secret"] is False
    assert init_data["client_secret_last4"] is None
    assert init_data["payment_provider_mode"] == "MERCHANT_DIRECT"
    assert init_data["webhook_callback_path"] == f"/api/v1/webhooks/paypal/{merch_id}"
    assert init_data["credential_verified_at"] is None

    # 2. Missing APP_DATA_ENCRYPTION_KEY blocks saving secret with 503
    monkeypatch.setattr(settings, "APP_DATA_ENCRYPTION_KEY", "")
    missing_key_resp = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merch["headers"],
        json={
            "paypal_client_id": "merch-live-id",
            "paypal_client_secret": "merch-super-secret-8899",
        },
    )
    assert missing_key_resp.status_code == 503
    monkeypatch.setattr(settings, "APP_DATA_ENCRYPTION_KEY", "sb-test-aes256-gcm-encryption-key-32b")

    # 3. verify_before_save=True with invalid credentials fails 400 and rolls back (does NOT persist)
    mock_paypal.rejected_client_ids.add("bad-client-id")
    bad_verify = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merch["headers"],
        json={
            "paypal_environment": "SANDBOX",
            "paypal_client_id": "bad-client-id",
            "paypal_client_secret": "bad-secret-0000",
            "verify_before_save": True,
        },
    )
    assert bad_verify.status_code == 400
    assert "bad-secret-0000" not in bad_verify.text
    assert client.get("/api/v1/merchant/payment-settings", headers=merch["headers"]).json()["paypal_configured"] is False

    # 4. verify_before_save=True with valid LIVE credentials encrypts with AES-256-GCM + masks last4 + sets verified_at
    save_ok = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merch["headers"],
        json={
            "payout_paypal_email": "direct-merchant@business.example.com",
            "payout_currency": "USD",
            "auto_refund_limit_usd": "300.00",
            "return_window_days": 10,
            "is_active": True,
            "paypal_environment": "live",
            "paypal_client_id": "merch-direct-client-id-1",
            "paypal_client_secret": "merch-direct-secret-WXYZ",
            "paypal_webhook_id": "WH-DIRECT-1",
            "verify_before_save": True,
        },
    )
    assert save_ok.status_code == 200, save_ok.text
    saved = save_ok.json()
    assert saved["paypal_configured"] is True
    assert saved["paypal_environment"] == "LIVE"
    assert saved["paypal_client_id"] == "merch-direct-client-id-1"
    assert saved["has_client_secret"] is True
    assert saved["client_secret_last4"] == "WXYZ"
    assert saved["paypal_webhook_id"] == "WH-DIRECT-1"
    assert saved["credential_verified_at"] is not None
    assert "merch-direct-secret-WXYZ" not in save_ok.text

    # Verify live host was hit during OAuth verification
    oauth_call = [c for c in mock_paypal.calls if c["path"] == "/v1/oauth2/token"][-1]
    assert oauth_call["host"] == "api-m.paypal.com"

    # Verify ciphertext in DB is AES-256-GCM encrypted with merchant AAD
    with SessionLocal() as db:
        pref = (
            db.query(MerchantPaymentPreference)
            .filter(MerchantPaymentPreference.merchant_id == merch_id)
            .one()
        )
        assert pref.encrypted_paypal_client_secret != "merch-direct-secret-WXYZ"
        assert (
            decrypt_secret(
                pref.encrypted_paypal_client_secret,
                associated_data=merchant_paypal_aad(merch_id),
            )
            == "merch-direct-secret-WXYZ"
        )

    # 5. Updating policy fields without resending secret preserves encrypted secret & verification
    policy_upd = client.put(
        "/api/v1/merchant/payment-settings",
        headers=merch["headers"],
        json={
            "payout_currency": "USD",
            "auto_refund_limit_usd": "250.00",
            "return_window_days": 21,
            "is_active": True,
            "paypal_environment": "LIVE",
        },
    )
    assert policy_upd.status_code == 200
    assert policy_upd.json()["has_client_secret"] is True
    assert policy_upd.json()["client_secret_last4"] == "WXYZ"
    assert policy_upd.json()["return_window_days"] == 21

    # 6. Explicit POST /verify-paypal with stored credentials updates credential_verified_at
    verify_stored = client.post(
        "/api/v1/merchant/payment-settings/verify-paypal",
        headers=merch["headers"],
        json={},
    )
    assert verify_stored.status_code == 200
    assert verify_stored.json()["verified"] is True
    assert verify_stored.json()["credential_verified_at"] is not None

    # 7. DELETE /credentials wipes keys, invalidates cache, and blocks checkout with 503
    cleared = client.delete("/api/v1/merchant/payment-settings/credentials", headers=merch["headers"])
    assert cleared.status_code == 200
    c_data = cleared.json()
    assert c_data["paypal_configured"] is False
    assert c_data["paypal_client_id"] is None
    assert c_data["has_client_secret"] is False
    assert c_data["client_secret_last4"] is None
    assert c_data["paypal_webhook_id"] is None
    assert c_data["credential_verified_at"] is None

    blocked_order = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod["id"], "buy_now_quantity": 1},
    )
    assert blocked_order.status_code == 503


def test_merchant_isolation_split_checkout_and_selective_cart_clearing(sandbox_env):
    client = sandbox_env["client"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch_a = _register(client, "merchant", "isoa", "Isolation Store A")
    merch_b = _register(client, "merchant", "isob", "Isolation Store B")
    merch_c = _register(client, "merchant", "isoc", "Unconfigured Store C")
    buyer = _register(client, "customer", "isobuyer", "Split Buyer")

    _configure_merchant_paypal(
        client, merch_a["headers"], client_id="iso-client-a", client_secret="iso-secret-a-1111", webhook_id="WH-ISO-A"
    )
    _configure_merchant_paypal(
        client, merch_b["headers"], client_id="iso-client-b", client_secret="iso-secret-b-2222", webhook_id="WH-ISO-B"
    )

    prod_a = _create_product(
        client, merch_a["headers"], title="Alpha Laptop", price="2000.00", mrp="2500.00", sandbox_usd_price="25.00"
    )
    prod_b = _create_product(
        client, merch_b["headers"], title="Beta Mouse", price="400.00", mrp="500.00", sandbox_usd_price="5.00"
    )
    prod_c = _create_product(
        client, merch_c["headers"], title="Gamma Cable", price="100.00", mrp="150.00", sandbox_usd_price="2.00"
    )
    starter_item = next(p for p in client.get("/api/v1/products/").json() if p["merchant_id"] is None)

    # Unconfigured merchant C must NEVER fall back to platform credentials
    assert client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod_c["id"], "buy_now_quantity": 1},
    ).status_code == 503

    # Add items from Merch A, Merch B, and starter platform catalog to cart
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_a["id"], "quantity": 1}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": prod_b["id"], "quantity": 2}).status_code == 201
    assert client.post("/api/v1/cart/items", headers=buyer["headers"], json={"product_id": starter_item["id"], "quantity": 1}).status_code == 201

    cfg = client.get("/api/v1/payments/paypal/client-config", headers=buyer["headers"]).json()
    assert cfg["requires_split_checkout"] is True
    assert len(cfg["groups"]) == 3
    by_mid = {g["merchant_id"]: g for g in cfg["groups"]}
    assert by_mid[merch_a["user"]["id"]]["client_id"] == "iso-client-a"
    assert by_mid[merch_a["user"]["id"]]["paypal_amount"] == 25.0
    assert by_mid[merch_b["user"]["id"]]["client_id"] == "iso-client-b"
    assert by_mid[merch_b["user"]["id"]]["paypal_amount"] == 10.0
    assert by_mid[None]["is_platform_catalog"] is True
    assert by_mid[None]["paypal_amount"] == 5.0

    # 1. Capture Merchant A group -> ONLY prod_a removed from cart, uses iso-client-a token
    ord_a = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "merchant_id": merch_a["user"]["id"]},
    ).json()
    cap_a = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": ord_a["local_order_id"], "paypal_order_id": ord_a["paypal_order_id"]},
    )
    assert cap_a.status_code == 200
    assert cap_a.json()["merchant_id"] == merch_a["user"]["id"]
    assert cap_a.json()["payment_provider_mode"] == "MERCHANT_DIRECT"

    cart_after_a = client.get("/api/v1/cart/", headers=buyer["headers"]).json()
    remaining_pids = {i["product_id"] for i in cart_after_a["items"]}
    assert remaining_pids == {prod_b["id"], starter_item["id"]}

    # Verify Merchant A calls used Merchant A's OAuth token
    last_cap_call_a = [c for c in mock_paypal.calls if c["path"].endswith("/capture")][-1]
    assert last_cap_call_a["headers"]["authorization"] == "Bearer mock_token_iso-client-a"

    # 2. Capture Merchant B group -> ONLY prod_b removed from cart, uses iso-client-b token
    ord_b = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "merchant_id": merch_b["user"]["id"]},
    ).json()
    cap_b = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": ord_b["local_order_id"], "paypal_order_id": ord_b["paypal_order_id"]},
    )
    assert cap_b.status_code == 200
    cart_after_b = client.get("/api/v1/cart/", headers=buyer["headers"]).json()
    assert {i["product_id"] for i in cart_after_b["items"]} == {starter_item["id"]}

    last_cap_call_b = [c for c in mock_paypal.calls if c["path"].endswith("/capture")][-1]
    assert last_cap_call_b["headers"]["authorization"] == "Bearer mock_token_iso-client-b"

    # 3. Capture Platform Starter group -> cart becomes empty, uses platform token
    ord_p = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "is_platform_catalog": True},
    ).json()
    cap_p = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": ord_p["local_order_id"], "paypal_order_id": ord_p["paypal_order_id"]},
    )
    assert cap_p.status_code == 200
    assert cap_p.json()["merchant_id"] is None
    assert cap_p.json()["payment_provider_mode"] == "PLATFORM_SANDBOX"
    assert client.get("/api/v1/cart/", headers=buyer["headers"]).json()["total_items"] == 0

    # 4. Deliver & refund Merchant A and Merchant B orders using each merchant's isolated credentials
    order_a_id = cap_a.json()["id"]
    order_b_id = cap_b.json()["id"]
    assert client.patch(f"/api/v1/orders/{order_a_id}/status?new_status=DELIVERED", headers=merch_a["headers"]).status_code == 200
    assert client.patch(f"/api/v1/orders/{order_b_id}/status?new_status=DELIVERED", headers=merch_b["headers"]).status_code == 200

    ret_a = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": order_a_id, "order_item_id": cap_a.json()["items"][0]["id"], "reason": "Defective A"},
    ).json()
    ret_b = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": order_b_id, "order_item_id": cap_b.json()["items"][0]["id"], "reason": "Defective B"},
    ).json()

    # Cross-merchant refund blocked 403
    assert client.post(
        f"/api/v1/returns/{ret_a['id']}/execute-approved-refund",
        headers=merch_b["headers"],
        json={"approval_reference": "CROSS-BLOCK"},
    ).status_code == 403

    assert client.post(
        f"/api/v1/returns/{ret_a['id']}/execute-approved-refund",
        headers=merch_a["headers"],
        json={"approval_reference": "APP-A-1"},
    ).status_code == 200
    ref_call_a = [c for c in mock_paypal.calls if c["path"].endswith("/refund")][-1]
    assert ref_call_a["headers"]["authorization"] == "Bearer mock_token_iso-client-a"

    assert client.post(
        f"/api/v1/returns/{ret_b['id']}/execute-approved-refund",
        headers=merch_b["headers"],
        json={"approval_reference": "APP-B-1"},
    ).status_code == 200
    ref_call_b = [c for c in mock_paypal.calls if c["path"].endswith("/refund")][-1]
    assert ref_call_b["headers"]["authorization"] == "Bearer mock_token_iso-client-b"


def test_per_merchant_webhook_six_step_and_service_jwt_status_endpoints(sandbox_env):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]
    mock_paypal = sandbox_env["mock_paypal"]

    merch_a = _register(client, "merchant", "wha", "WH Merch A")
    merch_b = _register(client, "merchant", "whb", "WH Merch B")
    merch_c = _register(client, "merchant", "whc", "WH Merch C Unconf")
    buyer = _register(client, "customer", "whbuyer", "WH Buyer")

    _configure_merchant_paypal(
        client, merch_a["headers"], client_id="wh-client-a", client_secret="wh-secret-a-1111", webhook_id="WH-MERCH-A"
    )
    _configure_merchant_paypal(
        client, merch_b["headers"], client_id="wh-client-b", client_secret="wh-secret-b-2222", webhook_id="WH-MERCH-B"
    )

    prod_a = _create_product(
        client, merch_a["headers"], title="WH Prod A", price="1000.00", mrp="1200.00", sandbox_usd_price="15.00"
    )
    prod_b = _create_product(
        client, merch_b["headers"], title="WH Prod B", price="800.00", mrp="900.00", sandbox_usd_price="10.00"
    )

    ord_a = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod_a["id"], "buy_now_quantity": 1},
    ).json()
    cap_a = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": ord_a["local_order_id"], "paypal_order_id": ord_a["paypal_order_id"]},
    ).json()

    ord_b = client.post(
        "/api/v1/payments/paypal/create-order",
        headers=buyer["headers"],
        json={"shipping_address": SAMPLE_ADDRESS, "buy_now_product_id": prod_b["id"], "buy_now_quantity": 1},
    ).json()
    cap_b = client.post(
        "/api/v1/payments/paypal/capture-order",
        headers=buyer["headers"],
        json={"local_order_id": ord_b["local_order_id"], "paypal_order_id": ord_b["paypal_order_id"]},
    ).json()

    valid_headers = {
        "PAYPAL-TRANSMISSION-ID": "tx-merch-1",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-12T10:00:00Z",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-M1",
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-TRANSMISSION-SIG": "sig-valid",
    }

    # Unconfigured Merchant C webhook -> 503
    assert client.post(
        f"/api/v1/webhooks/paypal/{merch_c['user']['id']}",
        headers=valid_headers,
        json={"id": "EVT-M-UNCONF", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": cap_a["paypal_capture_id"]}},
    ).status_code == 503

    # Cross-merchant webhook: Merchant B's capture sent to Merchant A's webhook URL -> 403 and order B untouched
    cross_wh = client.post(
        f"/api/v1/webhooks/paypal/{merch_a['user']['id']}",
        headers=valid_headers,
        json={
            "id": "EVT-CROSS-WH",
            "event_type": "CUSTOMER.DISPUTE.CREATED",
            "resource": {
                "dispute_id": "PP-D-CROSS",
                "dispute_amount": {"currency_code": "USD", "value": "10.00"},
                "disputed_transactions": [{"seller_transaction_id": cap_b["paypal_capture_id"]}],
            },
        },
    )
    assert cross_wh.status_code == 403
    with SessionLocal() as db:
        assert db.query(Order).filter(Order.id == cap_b["id"]).one().payment_status == "PAID"

    # Valid Merchant A webhook verifies using WH-MERCH-A and updates Order A
    ok_wh = client.post(
        f"/api/v1/webhooks/paypal/{merch_a['user']['id']}",
        headers=valid_headers,
        json={
            "id": "EVT-MERCH-A-DISP",
            "event_type": "CUSTOMER.DISPUTE.CREATED",
            "resource": {
                "dispute_id": "PP-D-A1",
                "dispute_amount": {"currency_code": "USD", "value": "15.00"},
                "disputed_transactions": [{"seller_transaction_id": cap_a["paypal_capture_id"]}],
            },
        },
    )
    assert ok_wh.status_code == 200
    assert ok_wh.json()["status"] == "processed"
    verify_call = [c for c in mock_paypal.calls if c["path"].endswith("verify-webhook-signature")][-1]
    assert verify_call["json"]["webhook_id"] == "WH-MERCH-A"
    assert verify_call["headers"]["authorization"] == "Bearer mock_token_wh-client-a"

    with SessionLocal() as db:
        assert db.query(Order).filter(Order.id == cap_a["id"]).one().payment_status == "DISPUTED"

    # Service-JWT capture & refund status endpoints
    assert client.patch(f"/api/v1/orders/{cap_b['id']}/status?new_status=DELIVERED", headers=merch_b["headers"]).status_code == 200
    ret_b = client.post(
        "/api/v1/returns/",
        headers=buyer["headers"],
        json={"order_id": cap_b["id"], "order_item_id": cap_b["items"][0]["id"], "reason": "WH Refund check"},
    ).json()
    exec_b = client.post(
        f"/api/v1/returns/{ret_b['id']}/execute-approved-refund",
        headers=merch_b["headers"],
        json={"approval_reference": "APP-WH-B"},
    ).json()

    # Unauthenticated and non-service tokens rejected 401
    assert client.get(f"/api/v1/orders/{cap_b['id']}/paypal-capture-status").status_code == 401
    assert client.get(f"/api/v1/orders/{cap_b['id']}/paypal-capture-status", headers=buyer["headers"]).status_code == 401
    assert client.get(f"/api/v1/returns/{ret_b['id']}/paypal-refund-status").status_code == 401

    now = datetime.now(timezone.utc)
    service_jwt = jwt.encode(
        {
            "sub": "refund-agent-core",
            "iss": settings.SERVICE_JWT_ISSUER,
            "scope": "bridge:read_write",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.SERVICE_JWT_SECRET,
        algorithm="HS256",
    )
    svc_headers = {"Authorization": f"Bearer {service_jwt}"}

    cap_status = client.get(f"/api/v1/orders/{cap_b['id']}/paypal-capture-status", headers=svc_headers)
    assert cap_status.status_code == 200
    cap_json = cap_status.json()
    assert cap_json["is_real_paypal_capture"] is True
    assert cap_json["paypal_capture_status"] == "COMPLETED"
    assert cap_json["merchant_id"] == merch_b["user"]["id"]
    cap_get_call = [c for c in mock_paypal.calls if c["method"] == "GET" and c["path"].startswith("/v2/payments/captures/")][-1]
    assert cap_get_call["headers"]["authorization"] == "Bearer mock_token_wh-client-b"

    ref_status = client.get(f"/api/v1/returns/{ret_b['id']}/paypal-refund-status", headers=svc_headers)
    assert ref_status.status_code == 200
    ref_json = ref_status.json()
    assert ref_json["is_real_paypal_refund"] is True
    assert ref_json["paypal_refund_status"] == "COMPLETED"
    assert ref_json["refund_transaction_id"] == exec_b["refund_transaction_id"]
    ref_get_call = [c for c in mock_paypal.calls if c["method"] == "GET" and c["path"].startswith("/v2/payments/refunds/")][-1]
    assert ref_get_call["headers"]["authorization"] == "Bearer mock_token_wh-client-b"


def test_ensure_schema_columns_upgrades_legacy_sqlite_db(tmp_path):
    legacy_db = tmp_path / "legacy.db"
    eng = create_engine(f"sqlite:///{legacy_db}", connect_args={"check_same_thread": False})
    try:
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER)"))
            conn.execute(
                text(
                    "CREATE TABLE merchant_payment_preferences ("
                    "id INTEGER PRIMARY KEY, merchant_id INTEGER)"
                )
            )
            conn.execute(text("CREATE TABLE return_requests (id INTEGER PRIMARY KEY)"))

        ensure_schema_columns(eng)
        ensure_schema_columns(eng)  # Idempotent second run

        insp = inspect(eng)
        order_cols = {c["name"] for c in insp.get_columns("orders")}
        pref_cols = {c["name"] for c in insp.get_columns("merchant_payment_preferences")}
        assert "merchant_id" in order_cols
        assert {
            "paypal_environment",
            "paypal_client_id",
            "encrypted_paypal_client_secret",
            "paypal_client_secret_last4",
            "paypal_webhook_id",
            "credential_verified_at",
        }.issubset(pref_cols)
    finally:
        eng.dispose()


def test_starter_catalog_claiming_seller_metadata_and_webhook_id_validation(sandbox_env, monkeypatch):
    client = sandbox_env["client"]
    SessionLocal = sandbox_env["session_factory"]

    merch_a = _register(client, "merchant", "claim_a", "Claim Merch A")
    merch_b = _register(client, "merchant", "claim_b", "Claim Merch B")
    buyer = _register(client, "customer", "claim_buyer", "Claim Buyer")

    # Add two more starter catalog items (merchant_id=None)
    with SessionLocal() as db:
        db.add_all(
            [
                Product(
                    merchant_id=None,
                    title="Starter Headphones 2",
                    brand="Sony",
                    category="Electronics",
                    description="Starter item 2",
                    price=Decimal("200.00"),
                    mrp=Decimal("250.00"),
                    sandbox_usd_price=Decimal("10.00"),
                    stock=8,
                    image_url="/api/v1/media/files/product-images/sony_xm5.svg",
                ),
                Product(
                    merchant_id=None,
                    title="Starter Watch 3",
                    brand="Apple",
                    category="Electronics",
                    description="Starter item 3",
                    price=Decimal("300.00"),
                    mrp=Decimal("350.00"),
                    sandbox_usd_price=Decimal("15.00"),
                    stock=4,
                    image_url="/api/v1/media/files/product-images/sony_xm5.svg",
                ),
            ]
        )
        db.commit()

    # 1. Unclaimed starter items show seller_name="Shipkart Platform Catalog" and paypal_ready per settings
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "")
    prods_unready = client.get("/api/v1/products/").json()
    starter_items = [p for p in prods_unready if p["merchant_id"] is None]
    assert len(starter_items) == 3
    assert all(p["seller_name"] == "Shipkart Platform Catalog" and p["paypal_ready"] is False for p in starter_items)

    # Friendly checkout message when starter item is unclaimed and platform PayPal is unconfigured
    unconfigured_svc = PayPalService(client_id="", client_secret="", webhook_id="")
    app.dependency_overrides[get_paypal_service] = lambda: unconfigured_svc
    cfg_starter = client.get(
        f"/api/v1/payments/paypal/client-config?buy_now_product_id={starter_items[0]['id']}",
        headers=buyer["headers"],
    )
    assert cfg_starter.status_code == 200
    assert cfg_starter.json()["eligible"] is False
    assert "Claim starter listings in Seller Hub" in cfg_starter.json()["reason"]

    # 2. Reject URLs pasted into paypal_webhook_id
    for bad_wh in [
        "http://localhost:8000/api/v1/webhooks/paypal/19",
        "HTTPS://api.shipkart.example/webhooks/19",
        "ftp://example.com/hook",
        "/api/v1/webhooks/paypal/19",
    ]:
        bad_resp = client.put(
            "/api/v1/merchant/payment-settings",
            headers=merch_a["headers"],
            json={"paypal_webhook_id": bad_wh},
        )
        assert bad_resp.status_code == 422, bad_resp.text
        assert "not a callback URL" in bad_resp.text

    # Valid PayPal Developer Dashboard Webhook ID is accepted
    _configure_merchant_paypal(
        client,
        merch_a["headers"],
        client_id="claim-client-a",
        client_secret="claim-secret-a-1111",
        webhook_id="8PT597350X239142B",
    )

    # 3. Claim single starter product
    target_1 = starter_items[0]
    target_2 = starter_items[1]
    target_3 = starter_items[2]

    # Customer cannot claim
    assert client.post(f"/api/v1/products/{target_1['id']}/claim", headers=buyer["headers"]).status_code == 403
    # Non-existent product -> 404
    assert client.post("/api/v1/products/999999/claim", headers=merch_a["headers"]).status_code == 404

    # Merchant A claims target_1 -> 200 + paypal_ready=True + seller_name
    claim_1 = client.post(f"/api/v1/products/{target_1['id']}/claim", headers=merch_a["headers"])
    assert claim_1.status_code == 200, claim_1.text
    c1_data = claim_1.json()
    assert c1_data["merchant_id"] == merch_a["user"]["id"]
    assert c1_data["seller_name"] == merch_a["user"]["business_name"]
    assert c1_data["paypal_ready"] is True

    # Idempotent repeat claim by same merchant -> 200
    claim_1_again = client.post(f"/api/v1/products/{target_1['id']}/claim", headers=merch_a["headers"])
    assert claim_1_again.status_code == 200
    assert claim_1_again.json()["merchant_id"] == merch_a["user"]["id"]

    # Another merchant attempting to claim target_1 -> 409 Conflict
    claim_conflict = client.post(f"/api/v1/products/{target_1['id']}/claim", headers=merch_b["headers"])
    assert claim_conflict.status_code == 409

    # 4. PUT /products/{id} on unclaimed starter item assigns merchant_id to editing merchant
    edit_claim = client.put(
        f"/api/v1/products/{target_2['id']}",
        headers=merch_b["headers"],
        json={"title": "Edited & Claimed Starter 2"},
    )
    assert edit_claim.status_code == 200, edit_claim.text
    e2_data = edit_claim.json()
    assert e2_data["merchant_id"] == merch_b["user"]["id"]
    assert e2_data["seller_name"] == merch_b["user"]["business_name"]
    assert e2_data["paypal_ready"] is False  # Merchant B hasn't configured PayPal yet

    # Friendly checkout message for unconfigured merchant
    cfg_merch_b = client.get(
        f"/api/v1/payments/paypal/client-config?buy_now_product_id={target_2['id']}",
        headers=buyer["headers"],
    )
    assert cfg_merch_b.status_code == 200
    assert cfg_merch_b.json()["eligible"] is False
    assert f"{merch_b['user']['business_name']} has not connected their Direct PayPal credentials" in cfg_merch_b.json()["reason"]

    # 5. Bulk claim remaining active starter items via POST /products/claim-starter
    bulk_claim = client.post("/api/v1/products/claim-starter", headers=merch_a["headers"])
    assert bulk_claim.status_code == 200, bulk_claim.text
    bulk_data = bulk_claim.json()
    assert bulk_data["claimed_count"] == 1
    assert len(bulk_data["products"]) == 1
    assert bulk_data["products"][0]["id"] == target_3["id"]
    assert bulk_data["products"][0]["merchant_id"] == merch_a["user"]["id"]
    assert bulk_data["products"][0]["paypal_ready"] is True

    # Repeat bulk claim returns 0
    bulk_empty = client.post("/api/v1/products/claim-starter", headers=merch_a["headers"])
    assert bulk_empty.status_code == 200
    assert bulk_empty.json() == {"claimed_count": 0, "products": []}

    # Verify get_product, create_product, list_merchant_products include seller_name & paypal_ready
    got_t1 = client.get(f"/api/v1/products/{target_1['id']}").json()
    assert got_t1["seller_name"] == merch_a["user"]["business_name"]
    assert got_t1["paypal_ready"] is True

    created_new = _create_product(
        client, merch_a["headers"], title="Direct PayPal Ready Item", price="999.00", mrp="1299.00", sandbox_usd_price="12.00"
    )
    assert created_new["seller_name"] == merch_a["user"]["business_name"]
    assert created_new["paypal_ready"] is True

    merch_a_list = client.get("/api/v1/products/merchant/my", headers=merch_a["headers"]).json()
    assert all(p["paypal_ready"] is True for p in merch_a_list if p["merchant_id"] == merch_a["user"]["id"])
