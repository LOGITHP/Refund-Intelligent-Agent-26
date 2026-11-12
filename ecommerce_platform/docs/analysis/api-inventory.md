# API Inventory — `ecommerce_platform` (Shipkart)

All routes verified directly from `backend/app/main.py`, `backend/app/api/v1/api.py`, and `backend/app/api/v1/endpoints/*.py`.
API prefix: `/api/v1` (except `/health`). Interactive OpenAPI docs are exposed at `/docs` and `/redoc`.

Total backend routes registered: **49** (`1` root health + `48` `/api/v1/*` routes).

---

## 1. Root & Health (`backend/app/main.py`)

| Method | Path | Auth / Role | Purpose |
|---|---|---|---|
| `GET` | `/health` | Public | Returns service name, health status, and `storage_connected` (MinIO availability). |

---

## 2. Authentication & Addresses (`/api/v1/auth` — `endpoints/auth.py`)

| Method | Path | Auth / Role | Request Schema | Response Schema |
|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Public | `UserCreate` (`email`, `password`, `full_name`, `role`, optional `phone`, `business_name`) | `TokenResponse` (`201`) |
| `POST` | `/api/v1/auth/login` | Public | `UserLogin` (`email`, `password`) | `TokenResponse` |
| `GET` | `/api/v1/auth/me` | Any User JWT | — | `UserOut` |
| `GET` | `/api/v1/auth/addresses` | Customer JWT | — | `List[AddressOut]` |
| `POST` | `/api/v1/auth/addresses` | Customer JWT | `AddressCreate` | `AddressOut` (`201`) |

---

## 3. Products & Catalog (`/api/v1/products` — `endpoints/products.py`)

| Method | Path | Auth / Role | Notes / DB Effects | Response Schema |
|---|---|---|---|---|
| `GET` | `/api/v1/products/` | Public | Filters: `category`, `search`, `only_assured`, `max_price`, `sort_by`. Runs lazy `release_expired_reservations` & computes `available_stock`, `seller_name`, `paypal_ready`. | `List[ProductOut]` |
| `GET` | `/api/v1/products/merchant/my` | Merchant JWT | Lists active products owned by the authenticated merchant. | `List[ProductOut]` |
| `POST` | `/api/v1/products/claim-starter` | Merchant JWT | Claims unowned (`merchant_id IS NULL`) starter products in batch (optional `product_ids`). | `ClaimStarterOut` |
| `GET` | `/api/v1/products/{product_id}` | Public | Product detail + live `available_stock` & PayPal readiness. | `ProductOut` |
| `POST` | `/api/v1/products/{product_id}/claim` | Merchant JWT | Claims a single unowned starter product (`409` if owned by another merchant). | `ProductOut` |
| `POST` | `/api/v1/products/` | Merchant JWT | Creates listing; auto-derives `sandbox_usd_price = max(1.00, round(price/85))` if omitted. | `ProductOut` (`201`) |
| `PUT` | `/api/v1/products/{product_id}` | Merchant JWT | Updates listing (enforces owner isolation; allows claiming if `merchant_id IS NULL`). | `ProductOut` |
| `DELETE` | `/api/v1/products/{product_id}` | Merchant JWT | Soft-deletes listing (`is_active = False`, owner check). | `204 No Content` |

---

## 4. Shopping Cart (`/api/v1/cart` — `endpoints/cart.py`)

| Method | Path | Auth / Role | Request Schema | Response Schema |
|---|---|---|---|---|
| `GET` | `/api/v1/cart/` | Customer JWT | — | `CartSummary` |
| `POST` | `/api/v1/cart/items` | Customer JWT | `CartItemAdd` (`product_id`, `quantity`); checks available stock (`400` if insufficient). | `CartSummary` (`201`) |
| `PUT` | `/api/v1/cart/items/{item_id}` | Customer JWT | `CartItemUpdate` (`quantity`; `<= 0` deletes item). | `CartSummary` |
| `DELETE` | `/api/v1/cart/items/{item_id}` | Customer JWT | — | `CartSummary` |
| `DELETE` | `/api/v1/cart/` | Customer JWT | — | `CartSummary` |

---

## 5. Orders & Bridge Context (`/api/v1/orders` — `endpoints/orders.py`)

| Method | Path | Auth / Role | Notes / DB Effects | Response Schema |
|---|---|---|---|---|
| `POST` | `/api/v1/orders/` | Customer JWT | **Standard Checkout:** locks product rows, verifies stock, creates `Order` (`ORDERED`, `payment_method="STANDARD_CHECKOUT"`, `payment_status="CONFIRMED"`), `MerchantOrderAllocation` (`STANDARD_CONFIRMED`), deducts stock, clears cart (unless `buy_now_product_id`), stores PDF invoice. | `OrderOut` (`201`) |
| `GET` | `/api/v1/orders/my` | Customer JWT | Customer order history; reconciles expired `PENDING_PAYMENT` reservations. | `List[OrderOut]` |
| `GET` | `/api/v1/orders/merchant` | Merchant JWT | Lists orders containing items owned by the merchant (`merchant_id`). | `List[OrderOut]` |
| `GET` | `/api/v1/orders/{order_id}/bridge-context` | Service JWT | Returns full order, customer stats, shipping address, items, allocations, and payment/capture metadata for `refund_intelligence_platform`. | `OrderBridgeContextOut` |
| `GET` | `/api/v1/orders/{order_id}/paypal-capture-status` | Service JWT | Queries live PayPal `GET /v2/payments/captures/{id}` using owning merchant credentials and returns redacted capture status. | `dict` |
| `GET` | `/api/v1/orders/{order_id}` | Customer or Merchant JWT | Owner or participating merchant order detail. | `OrderOut` |
| `PATCH` | `/api/v1/orders/{order_id}/status` | Merchant JWT | Advances `OrderStatus` (`ORDERED`..`DELIVERED` or `CANCELLED`) and updates `MerchantOrderAllocation.fulfillment_status`. | `OrderOut` |

---

## 6. PayPal Checkout (`/api/v1/payments` — `endpoints/payments.py`)

| Method | Path | Auth / Role | Notes / DB Effects | Response Schema |
|---|---|---|---|---|
| `GET` | `/api/v1/payments/paypal/client-config` | Customer JWT | Supports `buy_now_product_id` & `quantity` or active cart. Groups items by `(merchant_id, is_platform_catalog)`, flags `requires_split_checkout`, returns public `client_id` + `USD` total + eligibility per group (never exposes secrets). | `PayPalClientConfigOut` |
| `POST` | `/api/v1/payments/paypal/create-order` | Customer JWT | **Order-first:** validates address & single merchant group, locks product rows, creates local `Order` (`PENDING_PAYMENT`), 15m `InventoryReservation`, `MerchantOrderAllocation`, UUID `PayPal-Request-Id`s, calls PayPal `POST /v2/checkout/orders`, appends `ORDER_CREATED` ledger event. | `PayPalOrderCreateOut` (`201`) |
| `POST` | `/api/v1/payments/paypal/capture-order` | Customer JWT | Validates caller ownership + `paypal_order_id`, handles idempotent replay if already `PAID`, calls PayPal `POST /v2/checkout/orders/{id}/capture`, checks currency/amount exactness (`CAPTURE_AMOUNT_MISMATCH`), converts reservation (`CAPTURE_EXCEPTION_OUT_OF_STOCK` if expired & out of stock), selectively deletes captured cart items, generates PDF invoice. | `OrderOut` |
| `POST` | `/api/v1/payments/paypal/cancel-order` | Customer JWT | Releases `ACTIVE` reservations (`RELEASED`) and transitions `PENDING_PAYMENT` order to `CANCELLED` / `CANCELLED_BY_BUYER`. | `OrderOut` |

---

## 7. Merchant Payment Settings & Allocations (`/api/v1/merchant` — `endpoints/merchant_payments.py`)

| Method | Path | Auth / Role | Notes / DB Effects | Response Schema |
|---|---|---|---|---|
| `GET` | `/api/v1/merchant/payment-settings` | Merchant JWT | Returns payout preferences + masked PayPal status (`has_client_secret`, `client_secret_last4`, never plaintext secret). | `MerchantPaymentPreferenceOut` |
| `PUT` | `/api/v1/merchant/payment-settings` | Merchant JWT | Validates payout preferences & optional PayPal REST credentials (`verify_before_save=True` runs live OAuth2 test), encrypts secret with AES-256-GCM (`merchant:{id}:paypal` AAD). | `MerchantPaymentPreferenceOut` |
| `POST` | `/api/v1/merchant/payment-settings/verify-paypal` | Merchant JWT | Tests live OAuth2 authentication against PayPal Sandbox/Live with saved or supplied credentials; updates `credential_verified_at`. | `dict` |
| `DELETE` | `/api/v1/merchant/payment-settings/credentials` | Merchant JWT | Disconnects/clears stored PayPal `client_id`, encrypted secret, `last4`, and `webhook_id`. | `MerchantPaymentPreferenceOut` |
| `GET` | `/api/v1/merchant/allocations` | Merchant JWT | Returns per-order INR/USD revenue, fee, net merchant USD, refunded USD, and settlement status. | `List[MerchantOrderAllocationOut]` |

---

## 8. Returns, Refunds & Bridge Actions (`/api/v1/returns` — `endpoints/returns.py`)

| Method | Path | Auth / Role | Notes / DB Effects | Response Schema |
|---|---|---|---|---|
| `POST` | `/api/v1/returns/` | Customer JWT | Validates delivered order + `return_window_days`, calculates proportional USD refund (`refund_paypal_amount`) within remaining capture balance, creates `ReturnRequest` (`REQUESTED`), emits HMAC `RETURN_REQUESTED` to `:8100`. | `ReturnOut` (`201`) |
| `GET` | `/api/v1/returns/my` | Customer JWT | Customer's returns. | `List[ReturnOut]` |
| `GET` | `/api/v1/returns/merchant` | Merchant JWT | Returns scoped to `merchant_id`. | `List[ReturnOut]` |
| `GET` | `/api/v1/returns/bridge/pending` | Service JWT | Returns `REQUESTED` / `UNDER_REVIEW` / `APPROVED` / `PICKUP_SCHEDULED` / `REFUND_INITIATED` cases (optional `merchant_id` filter). | `List[ReturnOut]` |
| `GET` | `/api/v1/returns/{return_id}/paypal-refund-status` | Service JWT | Queries PayPal `GET /v2/payments/refunds/{id}` with owning merchant credentials (handles `SK-REF-*` local IDs cleanly). | `dict` |
| `GET` | `/api/v1/returns/{return_id}` | Customer or Merchant JWT | Owner or participating merchant return detail. | `ReturnOut` |
| `PATCH` | `/api/v1/returns/{return_id}/decision` | Merchant JWT | Merchant updates `ReturnStatus` (`UNDER_REVIEW`, `APPROVED`, `PICKUP_SCHEDULED`, `REFUND_INITIATED`, `REFUNDED`, `REJECTED`); executes PayPal refund if transitioning to `REFUNDED`; relays `RETURN_STATUS_UPDATED`. | `ReturnOut` |
| `POST` | `/api/v1/returns/{return_id}/agent-decision` | Service JWT | **REF-001 Guard:** records `agent_risk_score`, `agent_reasoning`, moves `REQUESTED` -> `UNDER_REVIEW`, appends `AGENT_*` timeline step. Explicitly blocks `execute_paypal_refund=True`. | `ReturnOut` |
| `POST` | `/api/v1/returns/{return_id}/execute-approved-refund` | Merchant JWT OR Service JWT | Requires non-empty `approval_reference`; checks merchant isolation & optional `refund_amount_usd <= remaining_ceiling`; calls PayPal `refund_capture` (or local `SK-REF-*`), marks `REFUNDED`, updates allocation/order/ledger, relays `RETURN_STATUS_UPDATED`. | `ReturnOut` |

---

## 9. PayPal Webhooks (`/api/v1/webhooks` — `endpoints/webhooks.py`)

| Method | Path | Auth / Verification | Notes / DB Effects | Response |
|---|---|---|---|---|
| `POST` | `/api/v1/webhooks/paypal` | PayPal Signature (`verify-webhook-signature`) + HTTPS `*.paypal.com` cert check | Platform/starter catalog webhook handler (6-step verification, 9-event allowlist, `ProcessedWebhookEvent` dedup, authoritative REST re-fetch, `PaymentLedgerEvent` append). | `dict` (`200`) |
| `POST` | `/api/v1/webhooks/paypal/{merchant_id}` | Per-merchant PayPal Signature + `expected_merchant_id` isolation | Merchant-scoped webhook handler; guards against cross-merchant order tampering (`403`). | `dict` (`200`) |

---

## 10. Media & Invoices (`/api/v1/media`, `/api/v1/invoices`)

| Method | Path | Auth / Role | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/media/upload` | Any User JWT | Uploads images (`product-images` for merchants, `return-evidence` for any user) to MinIO / local fallback. |
| `GET` | `/api/v1/media/files/{bucket}/{object_name:path}` | Any User JWT OR Service JWT | Streams stored binary file cleanly via FastAPI proxy (avoids direct Docker `minio:9000` DNS coupling). |
| `GET` | `/api/v1/invoices/{order_id}` | Customer or Merchant JWT (Order Owner/Seller) | Streams or regenerates `INV_{order_number}.pdf` via ReportLab (`409` if `PENDING_PAYMENT`/`CANCELLED`). |

---

## 11. Outbound & Direct Browser Cross-Platform Calls

1. **Backend Outbound Webhook (`returns.py`):** `POST {AGENT_PLATFORM_URL}/api/v1/bridge/shipkart/return-event` with `X-Bridge-Signature: sha256=<hex>` (`BRIDGE_SHARED_SECRET`), 2.0s timeout, best-effort (`RETURN_REQUESTED`, `RETURN_STATUS_UPDATED`).
2. **Customer Browser (`RefundIntelligencePanel.jsx` -> `VITE_AGENT_API_URL` `:8100`):** Calls `GET /api/v1/customer/returns/by-shipkart/{id}`, `GET /api/v1/customer/refunds/{caseId}/timeline`, `POST /api/v1/customer/returns/by-shipkart/{id}/evidence`, `POST /api/v1/customer/returns/by-shipkart/{id}/appeal`, `POST /api/v1/agents/investigate/{caseId}`, `POST /api/v1/agents/customer-chat/{caseId}` reusing Shipkart's customer JWT.
3. **Merchant Browser (`MerchantRefundIntelligencePanel.jsx` -> `VITE_AGENT_API_URL` `:8100`):** Calls `GET /api/v1/merchant/returns/by-shipkart/{id}`, `GET /api/v1/merchant/refunds/{caseId}`, `GET /api/v1/merchant/refunds/{caseId}/dossier`, `POST /api/v1/agents/investigate/{caseId}`, `POST /api/v1/merchant/refunds/{caseId}/approve`, `POST /api/v1/merchant/refunds/{caseId}/reject` reusing Shipkart's merchant JWT.
