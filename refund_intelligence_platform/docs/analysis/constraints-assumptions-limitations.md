# Constraints, Assumptions, and Limitations Analysis

This document strictly separates architectural **Constraints**, operational **Assumptions**, and current implementation **Limitations** verified against `refund_intelligence_platform` (and read-only cross-checks of `ecommerce_platform`).

---

## 1. Constraints

Hard boundaries imposed by system architecture, security controls, provider behavior, and policy rules enforced in code:

1. **Existing Application Remains System of Record (Architectural Constraint)**
   - `ecommerce_platform` (Shipkart) retains ownership of product catalogs, customer/merchant user accounts, orders, `ReturnRequest` records, and per-merchant PayPal API secrets. `refund_intelligence_platform` stores only cross-platform integer foreign references (`shipkart_return_id`, `shipkart_order_id`, `shipkart_customer_id`, `shipkart_merchant_id`, `shipkart_order_item_id`, `shipkart_actor_id`) in PostgreSQL `refund_intelligence`.
2. **Mandatory Human Merchant Approval (`REF-001`, Hard Financial Constraint)**
   - `ComplianceService.assert_merchant_approval_exists` and `RefundService.execute_approved_refund` hard-block PayPal payout execution (`HTTP 403`) unless an immutable `RefundApproval` row with `decision='APPROVED'` exists for that `RefundCase`.
   - `ResolutionOutput` in `app/schemas/agent_io.py` enforces via a Pydantic `model_validator` that `requires_approval` must always be `True`. `shipkart_sync_service.py` hard-codes `"execute_paypal_refund": False` on outbound agent decisions.
3. **No Control Over Issuing Banks or Card Networks (Provider Constraint)**
   - Neither `refund_intelligence_platform` nor PayPal can compel an issuing bank to post a refund credit or verify real cardholder bank-statement posting. `PAYPAL_COMPLETED` (`PAYMENT.CAPTURE.REFUNDED`) strictly means PayPal accepted/completed the refund transaction on its side (`DELAY-006` explicitly guards against claiming bank posting without issuer confirmation).
4. **PayPal Balance, Capture, and Idempotency Guards (`REF-002`, `REF-003`, `REF-004`)**
   - Every refund must reference a verified `paypal_capture_id` (`REF-004`), have a unique `idempotency_key` (`REF-003`), and stay `> 0` and `<= captured_amount - already_refunded` (`REF-002`). Multi-currency amounts (`INR` catalog display vs `USD` PayPal settlement) must remain separated and use `NUMERIC(18, 2)` / `Decimal` (zero float arithmetic).
5. **Tenant & Role Isolation (`AUTH-001`, `AUTH-002`, Operations Auth Isolation)**
   - Customer routes restrict access by `shipkart_customer_id`/`customer_id`; Merchant routes restrict access by `shipkart_merchant_id`/`merchant_id`; Operations endpoints require `"operations"`, `"admin"`, or `"service"` roles (blocking Shipkart `"customer"`/`"merchant"` JWTs with `HTTP 403`).
6. **Append-Only Auditability & Secret Redaction (`DATA-001`)**
   - `refund_approvals` and `audit_logs` prohibit `UPDATE` and `DELETE` via SQLAlchemy ORM event listeners and PostgreSQL `BEFORE UPDATE OR DELETE` triggers (`trg_refund_approvals_immutable`, `trg_audit_logs_immutable`).
   - Logging filters (`RedactingFormatter`, `redact_sensitive_data`), issuer last-4 validation (`CreateInquiryRequest`), and customer chat checks suppress raw PANs, CVVs, bearer tokens, passwords, and PayPal secrets.
7. **Deterministic Control Over Numerical/SLA Outputs**
   - `DelayService` (`DELAY-001`..`DELAY-006`) and `ETAService` execute purely deterministic Python rules. In `investigation_agent.py` and `resolution_agent.py`, any LLM output fields touching ETA, delay owner, triggered rules, or `requires_approval` are overwritten/re-anchored with deterministic outputs after LLM parsing.
8. **No Legal or Regulatory Approval Authority**
   - The `regulatory_simulator` explicitly states on every response: *"This is a software-based rules evaluation simulation, not regulatory approval or legal advice."*

---

## 2. Assumptions

Conditions the platform expects to hold true, marked with their verification status:

| Assumption | Verification Status | Evidence / Basis |
| :--- | :--- | :--- |
| Shipkart (`ecommerce_platform`) is reachable at `SHIPKART_API_URL` (`http://localhost:8000` or `http://host.docker.internal:8000`) when running in integrated mode | **Configured** | `docker-compose.yml`, `.env.example`, `app/core/config.py`, `app/integrations/shipkart_client.py` |
| Shared HMAC (`BRIDGE_SHARED_SECRET`), Service JWT (`SERVICE_JWT_SECRET`), and User JWT (`JWT_SECRET_KEY`) keys match between `ecommerce_platform` and `refund_intelligence_platform` | **Configured** | `.env.example`, `app/core/security.py`, `ecommerce_platform/backend/app/api/v1/endpoints/returns.py` |
| Shipkart passes accurate order, item quantity, capture amount, and `paypal_capture_id` context on return webhook ingestion or bridge lookup | **Verified** (at contract schema level; **Unverified** under arbitrary live merchant misconfiguration) | `BridgeReturnEventPayload` in `internal_and_webhooks.py`, `ShipkartBridgeClient.fetch_order_context` |
| Customer and merchant JWTs issued by Shipkart contain HS256 claims (`sub`/`user_id`, `role`, `exp`, optional `shipkart_customer_id`/`shipkart_merchant_id`) | **Verified** | `verify_shipkart_user_token` and `extract_int_claim` across `app/core/security.py` and `app/api/v1/__init__.py` |
| PayPal captures and refunds for Shipkart orders settle in `USD` (`paypal_currency="USD"`) even when catalog prices are displayed in `INR` (`original_currency="INR"`) | **Configured** | `BridgeReturnEventPayload._normalize_shipkart_flat_payload`, `app/db/models.py`, `tests/integration/test_api_routes.py` |
| Human merchants and operations analysts monitor the Merchant Seller Hub / Ops Command Center to approve pending refunds and review escalated `ComplianceViolation` / `DELAY-*` alerts | **Unverified** (operational process external to code) | `MERCHANT_APPROVAL_PENDING`, `APPEAL_UNDER_REVIEW`, `ops_frontend` dashboards |
| PostgreSQL 16 (host `:5433`), Redis 7 (`:6379`), and MinIO (`:9002`) are running before starting `agent_backend` and Celery workers in full Docker Compose mode | **Configured** | `docker-compose.yml` `depends_on` healthchecks (`postgres`, `redis`) and `agent_backend` startup command |

---

## 3. Limitations

Concrete gaps and simulated behaviors observed in the current codebase:

1. **Downstream Issuer, Carrier, and Regulatory Systems Are All Simulated (`Simulated / mocked`)**
   - `issuer_simulator` (`:8201`), `carrier_simulator` (`:8203`), and `regulatory_simulator` (`:8202`) are standalone FastAPI apps backed by **volatile in-memory Python dictionaries** protected by `threading.Lock`. Restarting those containers wipes all simulator state (although `agent_backend` retains DB snapshots in `return_shipments`, `issuer_inquiries`, and `regulatory_evaluations`).
   - There are **no real bank/issuer APIs** (Visa/Mastercard/RuPay ARN networks) and **no live carrier tracking APIs** (BlueDart/Delhivery/FedEx).
2. **Split PayPal Payout Dispatch Path Between Global Mode and Merchant-Direct Mode**
   - `RefundService.execute_approved_refund` supports an injectable `bridge_executor`, and `ShipkartBridgeClient.submit_approved_refund_execution` exists, **but** `POST /api/v1/payments/paypal/refund` (`app/api/v1/internal_and_webhooks.py`) only injects `PayPalClient` (configured via global `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`) and passes `bridge_executor=None`.
   - When using Merchant-Direct isolation with Shipkart (`PAYPAL_CLIENT_ID` unset on `agent_backend`), payouts are initiated from Shipkart's Seller Hub (`MerchantRefundIntelligencePanel.jsx` -> first calls `agent_backend` `/approve`, then calls Shipkart `/execute-approved-refund`), rather than `agent_backend` proxying payout execution.
3. **PayPal Webhook Cryptographic Verification Bypassed in Dev Mode When `PAYPAL_WEBHOOK_ID` Is Blank**
   - In `POST /api/v1/webhooks/paypal`, if `ENVIRONMENT` is in `{"development", "dev", "local", "test"}` and `PAYPAL_WEBHOOK_ID` is empty, PayPal webhook signature verification is skipped (payload deduplication via `ProcessedWebhookEvent` still runs).
4. **NIM Vision Path Requires `image_b64` in Agent State**
   - `intake_node` supports multimodal image inspection via `NVIDIA_VISION_MODEL` when an `evidence_items` entry includes `image_b64`. However, `run_refund_intelligence_pipeline` (`graph.py`) and `/api/v1/agents/intake` (`agents/routes.py`) populate `evidence_items` from DB metadata (`file_name`, `mime_type`, `sha256_hash`, `extracted_metadata`) without downloading/base64-encoding raw bytes from MinIO, so automatic live OCR on uploaded MinIO images is not wired end-to-end.
5. **No Global Virtual / Simulated Clock Service**
   - Services accept injectable `as_of` (`DelayService`) and `estimated_from` (`ETAService`) parameters for tests, and simulators increment synthetic event timestamps (`+6h`/`+12h`) on `/advance`, while `regulatory_simulator` accepts `evaluation_date`. There is no runtime virtual clock control endpoint to fast-forward live `utcnow()` across APIs and Celery Beat.
6. **Render Blueprint Disables Background Redis/Celery Beat**
   - `render.yaml` configures `CELERY_TASK_ALWAYS_EAGER="true"` and `REDIS_URL=""` on `refund-agent-api-26` (no `celery_worker`, `celery_beat`, `redis`, or `minio` services in the free-tier blueprint). Periodic scheduled sweeps (5m/10m/15m) do not run automatically on Render free tier unless invoked via `/api/v1/internal/*` HTTP endpoints; furthermore, without MinIO configured (`MINIO_ENDPOINT` unset/blank), `EvidenceService` raises `MinIOClientError` unless storage credentials are supplied.
7. **Deterministic Fallback vs Live LLM**
   - Leaving `NVIDIA_API_KEY` blank or receiving `401/403/410/429`/timeout errors cleanly falls back to rule-based structured text (`model_name="deterministic-fallback"`), meaning natural-language richness degrades gracefully to static templates.
8. **No Proactive Notification Delivery Channels & No Auth/Rate-Limit on Simulators**
   - There are no SMTP, SMS, WhatsApp, or Push notification dispatchers; customer updates are purely pull-based via REST UI polling.
   - Simulators (`:8201`, `:8202`, `:8203`) have no authentication middleware and accept unauthenticated requests on their ports; in Docker they sit on `agent_net`, though Compose also publishes ports `8201-8203` to host localhost.
9. **Rule-Based ETA & SLA Prediction**
   - ETA calculation (`ETAService`) uses fixed stage-hour bounds (`12-72h` carrier transit, `4-24h` inspection, `2-24h` approval, `1-12h` PayPal, `24-120h` / `48-168h` / `72-240h` issuer posting) rather than trained ML forecasting models.
10. **Case-Insensitive / Partial-Search Operations Filtering In-Memory**
    - `GET /api/v1/operations/cases` loads `RefundCase` rows ordered by `opened_at DESC` and runs `_build_case_summary` + search/delay_owner filtering in Python before applying `limit`, which is suitable for moderate volumes but not indexed SQL pagination at large scale.
