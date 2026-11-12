# Constraints, Assumptions, and Limitations — `ecommerce_platform` (Shipkart)

This document separates verified system **Constraints**, underlying **Assumptions**, and current **Limitations** derived strictly from inspecting `ecommerce_platform`.

---

## 1. Constraints

Hard boundaries imposed by architecture, external payment APIs, security controls, and platform boundaries:

1. **System of Record Boundary:** `ecommerce_platform` (`orders`, `order_items`, `return_requests`, `merchant_order_allocations`, `payment_ledger_events`, `inventory_reservations`) is the authoritative store for products, orders, inventory, merchant PayPal credentials, and order-level ledger events.
2. **Strict No-Fallback Merchant PayPal Custody (`MERCHANT_DIRECT`):** In `backend/app/services/paypal_service.py` (`resolve_paypal_service_for_merchant`), any product or order with `merchant_id IS NOT NULL` requires that specific merchant's configured `MerchantPaymentPreference` credentials. The backend deliberately refuses to fall back to platform `.env` PayPal keys (`PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`), returning HTTP `503` if the merchant has not configured credentials.
3. **PayPal Browser SDK Single Client-ID Isolation:** `@paypal/react-paypal-js` and PayPal's `window.paypal` script initialize with one `client-id` at a time. Consequently, mixed-merchant carts cannot be paid in a single unified PayPal order (`create-order` returns HTTP `400` if `requires_split_checkout` applies without `merchant_id` / `is_platform_catalog`), forcing sequential per-merchant checkout cards in `Checkout.jsx`.
4. **Human Approval Gate for Refunds (`REF-001`):** In `backend/app/api/v1/endpoints/returns.py`, `POST /api/v1/returns/{return_id}/agent-decision` blocks autonomous refund execution even when `execute_paypal_refund=True` is passed, never calls PayPal, and never transitions `ReturnStatus` to `REFUNDED`. Refunds require either merchant action (`PATCH /decision`) or explicit `approval_reference` on `POST /execute-approved-refund`.
5. **External Payment Rail & Issuer Settlement Boundary:** Shipkart can initiate a PayPal capture refund (`POST /v2/payments/captures/{capture_id}/refund`) or process webhooks (`PAYMENT.CAPTURE.REFUNDED`), but it cannot force or verify downstream card-network clearing or bank/issuer credit posting.
6. **Domestic INR vs PayPal Sandbox Currency Constraint:** PayPal does not support domestic `INR`-to-`INR` settlement within India, so Shipkart stores catalog prices in `INR` (`Product.price`) and settles PayPal Sandbox orders/refunds strictly in `USD` (`Product.sandbox_usd_price`, `Order.paypal_currency`).
7. **Append-Only Ledger Immutability:** SQLAlchemy `before_update` and `before_delete` hooks on `PaymentLedgerEvent` (`models.py`) raise `ValueError` on any mutation attempt.
8. **Merchant Secret Isolation:** Plaintext `paypal_client_secret` values are decrypted in memory only inside Shipkart backend (`core/crypto.py` with `APP_DATA_ENCRYPTION_KEY`) and are never returned to `customer_frontend`, `merchant_frontend`, or `refund_intelligence_platform`.

---

## 2. Assumptions

Conditions the application expects to hold in operation, classified by verification status:

| Assumption | Verification Status | Evidence / Rationale |
|---|---|---|
| Order, item, allocation, and capture IDs link consistently to a single owning merchant or platform catalog per PayPal order. | **Verified** | Enforced by `create_paypal_order`, `capture_paypal_order`, and `MerchantOrderAllocation` in `payments.py` & `test_merchant_isolation_split_checkout_and_selective_cart_clearing`. |
| Merchants configure valid PayPal REST credentials and matching `webhook_id` in Seller Hub when selling via PayPal. | **Configured** | `PUT /merchant/payment-settings` defaults `verify_before_save=True` (checks OAuth2), while `webhook_id` format is validated locally when provided (`merchant_payments.py`). |
| Customers possess an eligible PayPal Sandbox buyer account funded in `USD` for PayPal checkout flows. | **Unverified** | Cannot be enforced by Shipkart code; depends on external PayPal Sandbox account state. |
| `refund_intelligence_platform` (`:8100`) shares identical `BRIDGE_SHARED_SECRET` and `SERVICE_JWT_SECRET` / `SERVICE_JWT_ISSUER` values when bridged. | **Configured** | Declared in `.env.example`, `docker-compose.yml`, `render.yaml`, and `core/config.py`. |
| Authorized human reviewers (merchants) inspect `UNDER_REVIEW` / `AGENT_ESCALATED` cases and provide an explicit `approval_reference`. | **Unverified** | Workflow control assumes merchant login and UI review in `merchant_frontend/src/pages/Returns.jsx`. |
| Production hosting terminates TLS and configures CSP/DNS for PayPal webhooks. | **Unverified** | Local `nginx.conf.template` serves HTTP on ports `3000`/`3001` with PayPal CSP headers; production TLS depends on external reverse proxy or Render platform. |

---

## 3. Limitations

Concrete gaps and operational limitations verified in the current codebase:

1. **No Live Bank / Card Issuer Settlement Integration:** Shipkart stops at PayPal REST capture refund initiation and webhook ingestion; final bank posting status (`ISSUER_POSTED`, etc.) is not verified in Shipkart.
2. **Simulated Local Payouts on Non-PayPal / Mocked Orders:** `STANDARD_CHECKOUT` orders (`payment_method="STANDARD_CHECKOUT"`) and test orders with `CAP-SIM-*` capture IDs bypass PayPal during refunds and generate synthetic local transaction IDs (`SK-REF-...`).
3. **No Logistics / Carrier Tracking API Integration:** Order fulfillment milestones (`ORDERED` → `PACKED` → `SHIPPED` → `OUT_FOR_DELIVERY` → `DELIVERED`) and `PICKUP_SCHEDULED` steps are advanced manually by merchants (`PATCH /orders/{id}/status`, `PATCH /returns/{id}/decision`) rather than fed by carrier webhooks.
4. **No Background Scheduler / Worker Inside `ecommerce_platform`:** Expired `InventoryReservation` records (`RESERVATION_TTL_MINUTES = 15`) are released lazily during catalog, cart, order, and checkout requests (`release_expired_reservations`), rather than by an active cron/Celery worker.
5. **Best-Effort Fire-and-Forget Bridge Relay:** `_relay_return_event_to_agent` in `returns.py` uses a synchronous 2-second HTTP POST and swallows exceptions on failure without a retry queue or outbox table, so `refund_intelligence_platform` can miss events if temporarily unreachable.
6. **Additive `DATABASE_URL` Normalization with Startup DDL Patching:** `core/config.py` normalizes `postgres://` and `postgresql://` to `postgresql+psycopg://` for psycopg v3, and schema initialization relies on `Base.metadata.create_all` plus additive column patching (`ensure_schema_columns` in `db/database.py`), rather than versioned Alembic migrations with rollback support.
7. **Product-Level Return Window Check Uses First-Line Defaults / Static Seed Data Without Live FX:** Auto-calculated `sandbox_usd_price` on `POST /products/` falls back to an approximate static `price / 85` ratio if omitted, which is intended only for Sandbox demonstration rather than live currency exchange settlement.
8. **Unused `VITE_OPS_CONSOLE_URL` Build Arg:** Configured in `docker-compose.yml`, `render.yaml`, and `merchant_frontend/.env.example`, yet not rendered in `merchant_frontend/src/` (`SellerLayout.jsx`).
9. **Shared Local SQLite State in `tests/test_api_e2e.py`:** Unlike `tests/test_paypal_sandbox.py` (which uses isolated temporary SQLite databases), `tests/test_api_e2e.py` executes against default `DATABASE_URL` (`./data/ecommerce.db`). Running it against a database with depleted stock causes `test_full_ecommerce_lifecycle` to fail at `POST /api/v1/cart/items` (`400 Bad Request`).
10. **`render.yaml` & `index.html` Custom-Domain CSP Coupling:** `ecommerce_platform/render.yaml` specifies `./ecommerce_platform/...` paths assuming deployment from the parent monorepo root. `customer_frontend/index.html` allows `https://*.onrender.com` alongside localhost and PayPal domains, so custom non-Render domains require updating `connect-src` / `img-src`.
11. **Webhook `PAYPAL-TRANSMISSION-SIG` Verification Caveat When `webhook_id` Is Unset:** In `webhooks.py`, if `PAYPAL_WEBHOOK_ID` / merchant `paypal_webhook_id` is blank, cryptographic verification returns `400`/`503` (missing webhook ID) unless skipped in explicitly mocked unit fixtures — merchants must configure a PayPal Webhook ID before live/sandbox webhook traffic works.
