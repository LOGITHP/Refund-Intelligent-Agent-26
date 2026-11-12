from datetime import datetime, timedelta, timezone
import uuid
from fastapi.testclient import TestClient
import jwt
from app.core.config import settings
from app.main import app


def test_full_ecommerce_lifecycle():
    with TestClient(app) as client:
        # 1. Health check
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

        suffix = uuid.uuid4().hex[:6]

        # 2. Register a brand-new Customer dynamically
        cust_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"customer_{suffix}@example.com",
                "password": "securepassword123",
                "full_name": "Arun Kumar",
                "phone": "9880123456",
                "role": "customer",
            },
        )
        assert cust_reg.status_code == 201
        cust_token = cust_reg.json()["access_token"]
        cust_headers = {"Authorization": f"Bearer {cust_token}"}

        # 3. Register a brand-new Merchant dynamically
        merch_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"merchant_{suffix}@example.com",
                "password": "securepassword123",
                "full_name": "RetailNet Owner",
                "business_name": "RetailNet Electronics",
                "role": "merchant",
            },
        )
        assert merch_reg.status_code == 201
        merch_token = merch_reg.json()["access_token"]
        merch_headers = {"Authorization": f"Bearer {merch_token}"}

        # 4. Verify Role Isolation (Customer cannot create product)
        forbidden_prod = client.post(
            "/api/v1/products/",
            headers=cust_headers,
            json={
                "title": "Unauthorized Product",
                "brand": "Test",
                "category": "Electronics",
                "description": "Should fail",
                "price": 100,
                "mrp": 200,
                "image_url": "/test.svg",
            },
        )
        assert forbidden_prod.status_code == 403

        # 5. List starter catalog products
        products_resp = client.get("/api/v1/products/")
        assert products_resp.status_code == 200
        products = products_resp.json()
        assert len(products) >= 5
        target_product = products[0]

        # 6. Customer Adds to Cart
        cart_resp = client.post(
            "/api/v1/cart/items",
            headers=cust_headers,
            json={"product_id": target_product["id"], "quantity": 1},
        )
        assert cart_resp.status_code == 201
        assert cart_resp.json()["total_items"] >= 1

        # 7. Customer Places Order (Checkout)
        order_resp = client.post(
            "/api/v1/orders/",
            headers=cust_headers,
            json={
                "shipping_address": {
                    "full_name": "Arun Kumar",
                    "phone": "9880123456",
                    "pincode": "560103",
                    "locality": "Bellandur",
                    "street_address": "Flat 402",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                },
                "payment_method": "STANDARD_CHECKOUT",
            },
        )
        assert order_resp.status_code == 201
        order = order_resp.json()
        order_id = order["id"]
        order_item_id = order["items"][0]["id"]
        assert order["status"] == "ORDERED"

        # 8. Verify Invoice PDF generated & accessible
        inv_resp = client.get(f"/api/v1/invoices/{order_id}", headers=cust_headers)
        assert inv_resp.status_code == 200
        assert inv_resp.headers["content-type"] == "application/pdf"

        # 9. Merchant Transitions Order to DELIVERED & Verify tracking_history persistence in DB
        for stage in ["PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]:
            upd_resp = client.patch(
                f"/api/v1/orders/{order_id}/status?new_status={stage}",
                headers=merch_headers,
            )
            assert upd_resp.status_code == 200
            assert upd_resp.json()["status"] == stage

        fetched_order = client.get(f"/api/v1/orders/{order_id}", headers=cust_headers)
        assert fetched_order.status_code == 200
        history = fetched_order.json()["tracking_history"]
        assert all(step["completed"] is True and step["time"] is not None for step in history)

        # 10. Customer Uploads Return Evidence Photo & Submits Return Request
        upload_resp = client.post(
            "/api/v1/media/upload?bucket=return-evidence",
            headers=cust_headers,
            files={"file": ("defect.jpg", b"fake-jpeg-bytes-for-test", "image/jpeg")},
        )
        assert upload_resp.status_code == 200
        evidence_url = upload_resp.json()["url"]

        ret_resp = client.post(
            "/api/v1/returns/",
            headers=cust_headers,
            json={
                "order_id": order_id,
                "order_item_id": order_item_id,
                "reason": "Item is defective or not working",
                "comments": "Screen flickering on arrival",
                "evidence_urls": [evidence_url],
            },
        )
        assert ret_resp.status_code == 201
        ret_data = ret_resp.json()
        return_id = ret_data["id"]
        assert ret_data["status"] == "REQUESTED"

        # 11. Merchant Approves & Completes Refund
        dec_resp = client.patch(
            f"/api/v1/returns/{return_id}/decision",
            headers=merch_headers,
            json={
                "status": "REFUNDED",
                "merchant_notes": "Evidence verified. Refund processed.",
                "refund_transaction_id": "SK-TEST-TXN-999",
            },
        )
        assert dec_resp.status_code == 200
        assert dec_resp.json()["status"] == "REFUNDED"
        assert dec_resp.json()["refund_transaction_id"] == "SK-TEST-TXN-999"
        fetched_ret = client.get(f"/api/v1/returns/{return_id}", headers=cust_headers)
        assert fetched_ret.status_code == 200
        assert all(step["completed"] is True for step in fetched_ret.json()["tracking_history"])


def test_agent_decision_and_merchant_product_crud(monkeypatch):
    monkeypatch.setattr(settings, "SERVICE_JWT_SECRET", "test-service-jwt-secret-key-e2e")
    monkeypatch.setattr(settings, "SERVICE_JWT_ISSUER", "refund-intelligence-platform")
    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:6]

        # Merchant registers & creates product
        merch_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"agent_merch_{suffix}@example.com",
                "password": "password123",
                "full_name": "Agent Store Owner",
                "business_name": "Agent Electronics",
                "role": "merchant",
            },
        )
        merch_headers = {"Authorization": f"Bearer {merch_reg.json()['access_token']}"}

        create_prod = client.post(
            "/api/v1/products/",
            headers=merch_headers,
            json={
                "title": "Test Agent Smartwatch",
                "brand": "Noise",
                "category": "Electronics",
                "description": "AMOLED Display Smartwatch",
                "price": 2999.0,
                "mrp": 5999.0,
                "stock": 5,
                "image_url": "/api/v1/media/files/product-images/sony_xm5.svg",
            },
        )
        assert create_prod.status_code == 201
        prod_id = create_prod.json()["id"]

        # Customer registers new account, places buy-now order, receives delivery, submits return
        cust_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"agent_tester_{suffix}@example.com",
                "password": "password123",
                "full_name": "Agent Tester",
                "role": "customer",
            },
        )
        assert cust_reg.status_code == 201
        cust_headers = {"Authorization": f"Bearer {cust_reg.json()['access_token']}"}

        order_resp = client.post(
            "/api/v1/orders/",
            headers=cust_headers,
            json={
                "shipping_address": {
                    "full_name": "Agent Tester",
                    "phone": "9999999999",
                    "pincode": "560001",
                    "locality": "MG Road",
                    "street_address": "101 Tech Tower",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                },
                "buy_now_product_id": prod_id,
                "buy_now_quantity": 1,
            },
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]
        order_item_id = order_resp.json()["items"][0]["id"]

        # Deliver order
        client.patch(f"/api/v1/orders/{order_id}/status?new_status=DELIVERED", headers=merch_headers)
        merch_orders_resp = client.get("/api/v1/orders/merchant", headers=merch_headers)
        assert merch_orders_resp.status_code == 200
        assert any(o["id"] == order_id for o in merch_orders_resp.json())

        # Submit return
        ret_resp = client.post(
            "/api/v1/returns/",
            headers=cust_headers,
            json={
                "order_id": order_id,
                "order_item_id": order_item_id,
                "reason": "Item arrived physically damaged",
                "comments": "Cracked glass bezel",
                "evidence_urls": [],
            },
        )
        assert ret_resp.status_code == 201
        ret_id = ret_resp.json()["id"]

        # REF-001 & Bridge Hardening: Unauthenticated /agent-decision MUST fail with 401
        unauth_agent = client.post(
            f"/api/v1/returns/{ret_id}/agent-decision",
            json={
                "action": "APPROVE",
                "confidence_score": 0.96,
                "reasoning": "Low fraud risk and clear bezel crack verified.",
                "execute_paypal_refund": True,
                "paypal_capture_id": "CAP-SIM-123",
            },
        )
        assert unauth_agent.status_code == 401

        # Service-authenticated agent recommendation queues UNDER_REVIEW (never executes refund directly)
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
        agent_resp = client.post(
            f"/api/v1/returns/{ret_id}/agent-decision",
            headers=service_headers,
            json={
                "action": "APPROVE",
                "confidence_score": 0.96,
                "reasoning": "Low fraud risk and clear bezel crack verified.",
                "execute_paypal_refund": True,
                "paypal_capture_id": "CAP-SIM-123",
            },
        )
        assert agent_resp.status_code == 200
        assert agent_resp.json()["status"] == "UNDER_REVIEW"
        assert agent_resp.json()["agent_risk_score"] == 0.96
        assert agent_resp.json()["refund_transaction_id"] is None

        # Customer cannot execute an approved refund (403)
        cust_exec = client.post(
            f"/api/v1/returns/{ret_id}/execute-approved-refund",
            headers=cust_headers,
            json={"approval_reference": "FORGED-APP-1"},
        )
        assert cust_exec.status_code == 403

        # Merchant explicit approval executes refund cleanly
        merch_exec = client.post(
            f"/api/v1/returns/{ret_id}/execute-approved-refund",
            headers=merch_headers,
            json={
                "approval_reference": "MERCH-APP-E2E-001",
                "merchant_notes": "Approved after bezel inspection",
            },
        )
        assert merch_exec.status_code == 200
        assert merch_exec.json()["status"] == "REFUNDED"
        assert "SK-REF-" in merch_exec.json()["refund_transaction_id"]


def test_bridge_relay_emits_hmac_signed_decimal_events(monkeypatch):
    import hashlib
    import hmac
    import json
    from app.api.v1.endpoints import returns as returns_ep

    captured_calls = []

    def fake_post(url, *, content, headers, timeout):
        captured_calls.append(
            {
                "url": url,
                "content": content,
                "headers": headers,
                "timeout": timeout,
                "payload": json.loads(content.decode("utf-8")),
            }
        )
        return None

    monkeypatch.setattr(settings, "AGENT_PLATFORM_URL", "http://agent-core.local:8100")
    monkeypatch.setattr(settings, "BRIDGE_SHARED_SECRET", "bridge-secret-test-123")
    monkeypatch.setattr(returns_ep.httpx, "post", fake_post)

    with TestClient(app) as client:
        suffix = uuid.uuid4().hex[:6]
        merch_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"bridge_merch_{suffix}@example.com",
                "password": "password123",
                "full_name": "Bridge Merchant",
                "business_name": "Bridge Store",
                "role": "merchant",
            },
        )
        merch_headers = {"Authorization": f"Bearer {merch_reg.json()['access_token']}"}
        prod_resp = client.post(
            "/api/v1/products/",
            headers=merch_headers,
            json={
                "title": "Bridge Verified Headset",
                "brand": "Boat",
                "category": "Electronics",
                "description": "Wireless headphones",
                "price": 1999.0,
                "mrp": 3999.0,
                "stock": 5,
                "sandbox_usd_price": 24.0,
                "image_url": "/api/v1/media/files/product-images/sony_xm5.svg",
            },
        )
        assert prod_resp.status_code == 201
        prod_id = prod_resp.json()["id"]

        cust_reg = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"bridge_cust_{suffix}@example.com",
                "password": "password123",
                "full_name": "Bridge Customer",
                "role": "customer",
            },
        )
        cust_headers = {"Authorization": f"Bearer {cust_reg.json()['access_token']}"}

        order_resp = client.post(
            "/api/v1/orders/",
            headers=cust_headers,
            json={
                "shipping_address": {
                    "full_name": "Bridge Customer",
                    "phone": "9999999999",
                    "pincode": "560001",
                    "locality": "Indiranagar",
                    "street_address": "12 Main Rd",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                },
                "buy_now_product_id": prod_id,
                "buy_now_quantity": 2,
            },
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]
        order_item_id = order_resp.json()["items"][0]["id"]

        client.patch(f"/api/v1/orders/{order_id}/status?new_status=DELIVERED", headers=merch_headers)
        merch_orders_resp = client.get("/api/v1/orders/merchant", headers=merch_headers)
        assert merch_orders_resp.status_code == 200
        assert any(o["id"] == order_id for o in merch_orders_resp.json())
        ret_resp = client.post(
            "/api/v1/returns/",
            headers=cust_headers,
            json={
                "order_id": order_id,
                "order_item_id": order_item_id,
                "reason": "Left earcup audio dead",
                "comments": "No sound after first charge",
                "evidence_urls": [],
            },
        )
        assert ret_resp.status_code == 201
        ret_id = ret_resp.json()["id"]

        exec_resp = client.post(
            f"/api/v1/returns/{ret_id}/execute-approved-refund",
            headers=merch_headers,
            json={
                "approval_reference": "APP-BRIDGE-42",
                "merchant_notes": "Approved after test verification",
            },
        )
        assert exec_resp.status_code == 200

    assert len(captured_calls) == 2
    first, second = captured_calls[0], captured_calls[1]
    assert first["url"] == "http://agent-core.local:8100/api/v1/bridge/shipkart/return-event"
    for call in captured_calls:
        expected_sig = (
            "sha256="
            + hmac.new(
                b"bridge-secret-test-123", call["content"], hashlib.sha256
            ).hexdigest()
        )
        assert call["headers"]["X-Bridge-Signature"] == expected_sig

    assert first["payload"]["event_type"] == "RETURN_REQUESTED"
    assert isinstance(first["payload"]["refund_amount"], str)
    assert first["payload"]["refund_amount"] == "3998.00"
    assert first["payload"]["quantity_requested"] == 2
    assert first["payload"]["purchased_quantity"] == 2
    assert first["payload"]["unit_price"] == "1999.00"

    assert second["payload"]["event_type"] == "RETURN_STATUS_UPDATED"
    assert second["payload"]["status"] == "REFUNDED"
    assert second["payload"]["approval_reference"] == "APP-BRIDGE-42"
    assert second["payload"]["refund_transaction_id"].startswith("SK-REF-")
