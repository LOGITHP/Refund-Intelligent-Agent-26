# API Route Inventory

All routes listed below were extracted directly from registered FastAPI routers and application entrypoints.

- **Agent Core API Base URL (local):** `http://localhost:8100` (API prefix `/api/v1` from `app/core/config.py`)
- **Ops Frontend Vite Client:** calls `/api/v1/operations/*` using isolated `platform_users` bearer JWTs (`ops_frontend/src/api/client.ts`)

---

## 1. Agent Core Service (`agent_backend/app/`)

### Health Probe (`app/main.py`)

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects / Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service liveness & DB `SELECT 1` readiness | Public | None | `{status, service, database, nvidia_configured, paypal_env}` | `200` if DB ok, `503` if unavailable |

### Customer Routes (`app/api/v1/customer/`)

*Auth:* `require_roles("customer", "admin", "service")` with strict `AUTH-002` customer ownership enforcement (`assert_customer_case_access`).

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/returns` | Create physical `ReturnCase`, paired `RefundCase`, and initial ETA | `customer`, `admin`, `service` | JSON `CreateReturnRequest` (`items[]`, `reason_code`, `requested_amount`, `run_pipeline`, optional `shipkart_*`) | `{return_case, refund_case, eta, pipeline_result}` | `201`; creates `ReturnCase`, `ReturnCaseItem`, `RefundCase`, `RefundTimelineEvent`, `AuditLog`, `RefundEtaEstimate`; enforces `QTY-001`, `AUTH-002`; optionally runs 3-agent pipeline |
| `GET` | `/api/v1/returns` | List customer return cases | `customer`, `admin`, `service` | Query: `shipkart_order_id`, `status`, `limit` (`1..200`) | `{items, count}` | Read-only (`AUTH-002` scoped) |
| `GET` | `/api/v1/returns/{return_id}` | Get single return case + paired refund cases | `customer`, `admin`, `service` | Path: `return_id` (UUID or `shipkart_return_id`) | `{return_case, refund_cases}` | Read-only (`403` on wrong tenant, `404` missing) |
| `POST` | `/api/v1/returns/{return_id}/evidence` | Upload validated return/refund evidence file | `customer`, `admin`, `service` | Multipart form: `file`, optional `refund_case_id`, `source_type` | Serialized `Evidence` (`sha256_hash`, `verification_status`, `storage_key`, `extracted_metadata`) | `201`; magic-byte & size (`<=10 MB`) validation, private upload to MinIO `BUCKET_EVIDENCE`, writes `Evidence`, `RefundTimelineEvent`, `AuditLog` |
| `GET` | `/api/v1/refunds` | List customer refund cases | `customer`, `admin`, `service` | Query: `shipkart_order_id`, `shipkart_return_id`, `status`, `limit` (`1..200`) | `{items, count}` | Read-only (`AUTH-002` scoped) |
| `GET` | `/api/v1/refunds/{refund_id}` | Get single refund case | `customer`, `admin`, `service` | Path: `refund_id` (UUID or `shipkart_return_id` / `shipkart_order_id`) | `{refund_case}` | Read-only |
| `GET` | `/api/v1/refunds/{refund_id}/intelligence` | Consolidated customer refund intelligence dossier | `customer`, `admin`, `service` | Path: `refund_id` | `{refund_case, return_case, timeline, eta, delay_summary, issuer_status, shipments, evidence_items, latest_agent_summary}` | Read-only; deterministic `DelayService` + `ETAService` evaluation |
| `GET` | `/api/v1/refunds/{refund_id}/timeline` | Separated physical & financial timelines + merged chronological view | `customer`, `admin`, `service` | Path: `refund_id` | `{physical_return_events, financial_refund_events, merged_events}` | Read-only |
| `GET` | `/api/v1/refunds/{refund_id}/eta` | Compute current deterministic stage-remaining ETA | `customer`, `admin`, `service` | Path: `refund_id` | `{eta_status, earliest_at, latest_at, confidence_level, basis, explanation, disclaimer}` | Read-only |
| `POST` | `/api/v1/refunds/{refund_id}/chat` | Grounded customer refund status Q&A | `customer`, `admin`, `service` | JSON `{question}` (`1..2000` chars) | `{answer, eta_status, delay_owner, model_name, grounded_facts}` | Invokes grounded NIM chat or deterministic template with `DELAY-006` bank-unconfirmed guard; writes `RefundTimelineEvent` + `AuditLog` |
| `POST` | `/api/v1/refunds/{refund_id}/appeals` | Submit customer refund appeal | `customer`, `admin`, `service` | JSON `{reason, evidence_ids[]}` | `{refund_case, appeal_event_id}` | Validates reason (`CASE-001`), sets `RefundCase.status="APPEAL_UNDER_REVIEW"`, writes `RefundTimelineEvent` + `AuditLog` |

### Merchant Routes (`app/api/v1/merchant/`)

*Auth:* `require_roles("merchant", "operations", "admin", "service")` with strict `AUTH-001` tenant isolation (`assert_merchant_case_access`).

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/merchant/returns` | List tenant-scoped physical return cases | `merchant`, `operations`, `admin`, `service` | Query: `status`, `shipkart_order_id`, `limit` (`1..200`) | `{items, count}` | Read-only (`AUTH-001` filtered for merchants) |
| `GET` | `/api/v1/merchant/returns/{return_id}` | Full return dossier with shipments, inspections, evidence | `merchant`, `operations`, `admin`, `service` | Path: `return_id` | `{return_case, refund_case, shipments, inspections, evidence_items}` | Read-only |
| `POST` | `/api/v1/merchant/returns/{return_id}/inspect` | Record warehouse inspection outcome | `merchant`, `operations`, `admin`, `service` | JSON `{condition_result, notes, completed}` | `{inspection, return_case, eta}` | Enforces `STATE-002` inspectable states; inserts `ReturnInspection`, updates `ReturnCase.status`, recalculates ETA, logs timeline & audit |
| `POST` | `/api/v1/merchant/returns/{return_id}/transition` | Advance physical return lifecycle state | `merchant`, `operations`, `admin`, `service` | JSON `{status, reason}` | `{return_case}` | Enforces `ALLOWED_RETURN_TRANSITIONS` (`STATE-001`) and rejection reason (`CASE-001`); writes timeline & audit |
| `GET` | `/api/v1/merchant/refunds` | List tenant-scoped refund cases | `merchant`, `operations`, `admin`, `service` | Query: `status`, `shipkart_order_id`, `shipkart_return_id`, `limit` (`1..200`) | `{items, count}` | Read-only (`AUTH-001` filtered for merchants) |
| `GET` | `/api/v1/merchant/refunds/{refund_id}` | Full refund case dossier for owning merchant | `merchant`, `operations`, `admin`, `service` | Path: `refund_id` | `{refund_case, return_case, shipments, inspections, approvals, transactions, evidence_items, agent_executions, issuer_inquiries, regulatory_evaluations, compliance_violations, current_eta, delay_evaluation, timeline}` | Read-only |
| `GET` | `/api/v1/merchant/refunds/{refund_id}/investigation` | Alias returning AI investigation dossier & evidence | `merchant`, `operations`, `admin`, `service` | Path: `refund_id` | Same full investigation payload as `GET /merchant/refunds/{refund_id}` | Read-only |
| `POST` | `/api/v1/merchant/refunds/{refund_id}/approve` | Record immutable human Merchant refund approval (`REF-001`) | `merchant`, `operations`, `admin`, `service` | JSON `{approved_amount?, currency?, reason, policy_version, approval_reference?}` | Serialized `RefundApproval` + `{refund_case, eta}` | Enforces `REF-002` refundable balance & `CASE-001` reason (`>=3` chars); inserts immutable `RefundApproval(APPROVED)`, sets `APPROVED_BY_MERCHANT`, updates ETA, logs timeline & audit |
| `POST` | `/api/v1/merchant/refunds/{refund_id}/reject` | Record immutable human Merchant refund rejection | `merchant`, `operations`, `admin`, `service` | JSON `{reason, policy_version}` | Serialized `RefundApproval` + `{refund_case, eta}` | Enforces `CASE-001` (`>=3` chars); inserts immutable `RefundApproval(REJECTED)`, sets `REJECTED_BY_MERCHANT`, updates ETA, logs timeline & audit |

### Agent Orchestrator Routes (`app/api/v1/agents/routes.py`)

*Auth:* `require_roles("customer", "merchant", "operations", "admin", "service")` with customer/merchant case ownership guards (`AUTH-001`/`AUTH-002`).

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/agents/intake` | Run Node 1 (`intake_node`) standalone | `customer`, `merchant`, `operations`, `admin`, `service` | JSON `{case_id?, refund_case_id?, return_case_id?, customer_query?}` | `{case_id, refund_case_id, status, intake_result, executions, execution_records, errors}` | Runs injection/duplicate checks + NIM or deterministic fallback; persists `AgentExecution` + proposed `AgentDecision` (`requires_approval=True`) |
| `POST` | `/api/v1/agents/investigate/{case_id}` | Execute full 3-agent LangGraph pipeline (`intake -> investigation -> resolution`) | `customer`, `merchant`, `operations`, `admin`, `service` | JSON `{customer_query?}` (optional) | `{case_id, refund_case_id, status, summary, shipkart_synced, executions, execution_records, intake_result, investigation_result, resolution_result, errors}` | Queries simulator/PayPal/Shipkart read-only APIs, evaluates delays/ETA, persists 3 `AgentExecution`s + `AgentDecision`s + `AuditLog` + `RefundFollowup`s, posts advisory sync to Shipkart (`execute_paypal_refund=False`) |
| `POST` | `/api/v1/agents/resolve/{case_id}` | Execute full 3-agent LangGraph pipeline & persist refreshed ETA snapshot | `customer`, `merchant`, `operations`, `admin`, `service` | JSON `{customer_query?}` (optional) | Same as `/investigate/{case_id}` | Same as `/investigate/{case_id}`, plus `ETAService.compute_and_persist_eta`; **never** bypasses `REF-001` |
| `GET` | `/api/v1/agents/executions/{execution_id}` | Retrieve single agent execution trace & decisions | `customer`, `merchant`, `operations`, `admin`, `service` | Path: `execution_id` (UUID) | Serialized `AgentExecution` + `latency_ms` + `decisions[]` | Read-only (ownership checked) |
| `GET` | `/api/v1/agents/decisions/{case_id}` | List all agent executions & proposed decisions for a case | `customer`, `merchant`, `operations`, `admin`, `service` | Path: `case_id` | `{case_id, refund_case_id, decisions, executions, count}` | Read-only (ownership checked) |

### Operations Command Center & Simulator Console Routes (`app/api/v1/operations/routes.py`)

*Auth:* Except `/auth/status`, `/auth/setup`, `/auth/login`, and dev-only `/auth/demo-session`, all routes require `require_roles("operations", "admin", "service")` (blocking Shipkart `customer`/`merchant` JWTs with `HTTP 403`).

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/operations/auth/status` | Check whether an active `PlatformUser` operator exists | Public | None | `{has_operators, auth_mode}` | Read-only |
| `POST` | `/api/v1/operations/auth/setup` | First-run isolated operator account creation (`409` if any operator exists; `503` if `JWT_SECRET_KEY` missing) | Public (one-time) | JSON `{email, password (>=8 chars), full_name}` | `{access_token, token_type, expires_in, user}` (`201`) | Inserts `PlatformUser` with salted `scrypt` hash, logs `AuditLog`, mints operations JWT |
| `POST` | `/api/v1/operations/auth/login` | Authenticate isolated `PlatformUser` operator | Public | JSON `{email, password}` | `{access_token, token_type, expires_in, user}` | Updates `last_login_at`, logs `AuditLog`, mints HS256 JWT (`role="operations"`) |
| `GET` | `/api/v1/operations/auth/me` | Return authenticated operator profile | `operations`, `admin`, `service` | Bearer JWT | `{user}` | Read-only |
| `POST` | `/api/v1/operations/auth/demo-session` | Mint short-lived dev/test HS256 JWT (`403` outside `development`/`dev`/`local`/`test`) | Public (dev/local/test only) | JSON `{role: "operations"|"merchant", user_id?}` | `{access_token, token_type, expires_in, role, actor_id}` | None (stateless token issuance) |
| `GET` | `/api/v1/operations/overview` | Command Center KPI overview, separated currency totals, SLA/owner breakdown, simulator probes | `operations`, `admin`, `service` | None | `{total_return_cases, total_refund_cases, active_refund_cases, overdue_cases_count, pending_merchant_approvals, open_compliance_violations, paypal_completed_bank_unconfirmed_count, total_requested_by_currency, total_approved_by_currency, delay_breakdown, delay_owner_breakdown, service_status, active_alerts, recent_cases, generated_at}` | Read-only; probes simulator `/health` |
| `GET` | `/api/v1/operations/cases` | Search & filter refund cases with delay/ETA summary | `operations`, `admin`, `service` | Query: `status`, `delay_owner`, `search`, `limit` (`1..500`) | `{cases, items, count}` | Read-only |
| `GET` | `/api/v1/operations/cases/{refund_case_id}` | Full operational drill-down across returns, shipments, inspections, ETA, delays, agents, simulators, violations | `operations`, `admin`, `service` | Path: `refund_case_id` | Enriched summary + `return_case`, `shipments`, `inspections`, `transactions`, `approvals`, `evidence_items`, timelines, `current_eta`, `delay_alerts`, `agent_executions`, `issuer_inquiries`, `regulatory_evaluations`, `compliance_violations` | Read-only |
| `GET` | `/api/v1/operations/agents/executions` | List LangGraph agent executions with latency & decisions | `operations`, `admin`, `service` | Query: `case_id`, `agent_name`, `status`, `limit` (`1..500`) | `{executions, count}` | Read-only |
| `GET` | `/api/v1/operations/integrations/health` | Live connector health across Postgres, MinIO, Redis/Celery, NIM, PayPal, Shipkart, and 3 simulators | `operations`, `admin`, `service` | None | `{overall_status, checked_at, connectors[]}` | Read-only (`SELECT 1` + simulator `/health` probes) |
| `GET` | `/api/v1/operations/eta` | Current ETA snapshots + active `DELAY-001`..`006` alerts | `operations`, `admin`, `service` | None | `{estimates, alerts, generated_at}` | Read-only |
| `GET` | `/api/v1/operations/issuer-simulator/inquiries` | List `[Simulated]` issuer inquiries merged with DB `IssuerInquiry` records | `operations`, `admin`, `service` | Query: `refund_case_id`, `scenario`, `status` | `{inquiries, count, is_simulated: true, simulation_label}` | Calls `issuer_simulator` `:8201` |
| `POST` | `/api/v1/operations/issuer-simulator/inquiries` | Create `[Simulated]` issuer inquiry (`card_last4` masked 4 digits enforced) & persist DB row | `operations`, `admin`, `service` | JSON `CreateIssuerInquiryRequest` (`refund_case_id`, `card_network`: `VISA|MASTERCARD|RUPAY`, `card_last4`, `scenario`, etc.) | Simulator response (`201`, `is_simulated: true`) | Calls `issuer_simulator` `POST /issuer/inquiries`; inserts `IssuerInquiry` if case UUID exists |
| `POST` | `/api/v1/operations/issuer-simulator/scenarios/{inquiry_id}/trigger` | Trigger 1 of 8 `[Simulated]` issuer scenarios & sync DB | `operations`, `admin`, `service` | Path: `inquiry_id`; JSON `{scenario, note?}` | Updated simulated inquiry (`is_simulated: true`) | Calls `issuer_simulator`; updates `IssuerInquiry`; if credit posted without manual reconciliation, sets `RefundCase.status="CONFIRMED_POSTED"`, records `RefundTimelineEvent` & updates ETA |
| `GET` | `/api/v1/operations/carrier-simulator/shipments` | List `[Simulated]` reverse shipments | `operations`, `admin`, `service` | Query: `return_case_id`, `shipkart_order_id`, `carrier_name`, `status` | `{shipments, count, is_simulated: true, simulation_label}` | Calls `carrier_simulator` `:8203` |
| `POST` | `/api/v1/operations/carrier-simulator/shipments` | Create `[Simulated]` reverse shipment & sync DB | `operations`, `admin`, `service` | JSON `{return_case_id, shipkart_order_id, carrier_name: "BlueDart"|"Delhivery"|"FedEx", tracking_number?, scenario, origin_city, destination_city}` | Simulator shipment payload (`201`) | Calls `carrier_simulator`; inserts `ReturnShipment` (`is_simulated=True`), `RefundTimelineEvent`, refreshes ETA |
| `POST` | `/api/v1/operations/carrier-simulator/shipments/{tracking_number}/scenario` | Trigger `[Simulated]` carrier delay/delivery scenario & sync DB | `operations`, `admin`, `service` | Path: `tracking_number`; JSON `{scenario, note?}` | Updated simulator shipment payload | Calls `carrier_simulator`; updates `ReturnShipment`, adds `RefundTimelineEvent`, recalculates ETA |
| `GET` | `/api/v1/operations/regulatory` | List persisted `[Simulated]` India/USA regulatory evaluations | `operations`, `admin`, `service` | Query: `jurisdiction`, `status`, `limit` (`1..500`) | `{evaluations, count, is_simulated: true, disclaimer}` | Read-only |
| `GET` | `/api/v1/operations/regulatory/rules` | Fetch versioned IN/US rules catalog from `[Simulated]` Regulatory Simulator | `operations`, `admin`, `service` | Query: `jurisdiction`, `version` | `{rules, total, is_simulated: true, disclaimer}` | Calls `regulatory_simulator` `GET /regulatory/rules` |
| `POST` | `/api/v1/operations/regulatory/evaluate` | Evaluate refund context via `[Simulated]` Regulatory Simulator & persist result | `operations`, `admin`, `service` | JSON `RegulatoryEvaluateRequest` | Enriched evaluation + `obligations[]`, `unresolved_questions[]`, `disclaimer` | Calls `regulatory_simulator` `POST /regulatory/evaluate`; inserts `RegulatoryEvaluation` |
| `GET` | `/api/v1/operations/compliance` | List deterministic compliance rule catalog (`REF-001`..`DATA-001`) and violations | `operations`, `admin`, `service` | None | `{rules, violations, total_open}` | Read-only |
| `GET` | `/api/v1/operations/audit` | Query append-only redacted `AuditLog` entries | `operations`, `admin`, `service` | Query: `resource_type`, `actor_type`, `action`, `resource_id`, `limit` (`1..500`) | `{logs, count}` | Read-only |

### Payment Execution, Webhooks, Internal Scheduler & Bridge Routes (`app/api/v1/internal_and_webhooks.py`)

| Method | Actual Route | Purpose | Auth / Role | Request | Response | Side Effects / Idempotency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/payments/paypal/refund` | Execute idempotent PayPal refund via global `PayPalClient` | `merchant`, `operations`, `admin`, `service` | JSON `{refund_case_id, idempotency_key, paypal_capture_id?}` | Serialized `RefundTransaction` | Enforces `AUTH-001`, `REF-001`, `REF-002`, `REF-003` (`idempotency_key` deduplication), `REF-004`, `SELECT FOR UPDATE`; creates `RefundTransaction`, timeline, audit; calls PayPal REST `/v2/payments/captures/{id}/refund` |
| `POST` | `/api/v1/webhooks/paypal` | Ingest PayPal refund webhook idempotently (`PAY-002`) | PayPal Webhook Signature (`verify-webhook-signature`, skipped only in dev/local/test if `PAYPAL_WEBHOOK_ID` blank) | Raw JSON PayPal event (`id`/`event_id`, `event_type`, `resource`) | `{deduplicated, provider, provider_event_id, event_type, processing_status, refund_transaction_id, refund_case_id, transaction_status, case_status}` | Deduplicates on `(provider="paypal", provider_event_id)` in `ProcessedWebhookEvent`; updates `RefundTransaction`/`RefundCase`; logs `RefundTimelineEvent` |
| `POST` | `/api/v1/internal/eta/recalculate` | Recompute deterministic ETA for one or all active cases | `operations`, `admin`, `service` | Optional JSON `{refund_case_id?}` | `{status, recalculated_count, estimates[]}` | Inserts new `RefundEtaEstimate` (`is_current=True`), deactivates prior snapshots |
| `POST` | `/api/v1/internal/eta/calculate` | Compute & persist ETA for a single case | `operations`, `admin`, `service` | JSON `{refund_case_id}` | Serialized `RefundEtaEstimate` | Inserts new `RefundEtaEstimate` |
| `POST` | `/api/v1/internal/delays/detect` | Evaluate `DELAY-001`..`DELAY-006` across one or all active cases | `operations`, `admin`, `service` | Optional JSON `{refund_case_id?}` | `{status, evaluated, overdue_cases, alerts[]}` | Records deduplicated `SLA_BREACH_DELAY-*` `RefundTimelineEvent` rows |
| `POST` | `/api/v1/internal/reconciliation/run` | Poll PayPal API for all `PENDING` `RefundTransaction` rows | `operations`, `admin`, `service` | None | `{status, checked, reconciled}` | Updates changed transactions/cases via `ReconciliationService` |
| `POST` | `/api/v1/internal/followups/schedule` | Schedule a future deterministic followup job | `operations`, `admin`, `service` | JSON `{refund_case_id, target_type, target_reference?, action_type, delay_hours}` | `{id, refund_case_id, target_type, action_type, status, scheduled_at}` (`201`) | Inserts `RefundFollowup(status="SCHEDULED")` |
| `POST` | `/api/v1/internal/followups/run` | Execute due scheduled followups (`scheduled_at <= now()`) | `operations`, `admin`, `service` | None | `{status, processed, executed, rescheduled}` | Re-evaluates delays & ETA; marks `EXECUTED` or reschedules `+4h` (up to 3 attempts) |
| `GET` | `/api/v1/internal/audit/events` | Internal redacted audit event reader | `operations`, `admin`, `service` | Query: `resource_type`, `action`, `limit` (`1..500`) | `{events, count}` | Read-only |
| `POST` | `/api/v1/bridge/shipkart/return-event` | Ingest Shipkart return/status events idempotently on `shipkart_return_id` | HMAC-SHA256 `X-Bridge-Signature` (`BRIDGE_SHARED_SECRET`) | JSON `BridgeReturnEventPayload` (accepts flat Shipkart format or nested `items[]`) | `{created, updated, shipkart_return_id, return_case_id, refund_case_id, status}` (`201` create / `200` update) | On create: inserts `ReturnCase`, `ReturnCaseItem`, `RefundCase`, ETA, timeline, audit, and enqueues `run_agent_pipeline_task` (outside pytest); on status sync: maps `APPROVED`/`REJECTED`/`REFUND_INITIATED`/`REFUNDED` & updates ETA |

---

## 2. Outbound Shipkart Bridge Endpoints Called by Agent Backend (`app/integrations/shipkart_client.py`)

Authenticated via short-lived HS256 Service JWT (`SERVICE_JWT_SECRET`, optional `X-Bridge-Signature` on JSON bodies) targeting `SHIPKART_API_URL` (`http://localhost:8000` / `http://host.docker.internal:8000`):

- `GET /api/v1/orders/{order_id}/bridge-context` (`fetch_order_context`)
- `GET /api/v1/orders/{order_id}/paypal-capture-status` (`fetch_paypal_capture_status` — Merchant-Direct capture visibility without exposing merchant PayPal secrets)
- `GET /api/v1/returns/{return_id}/paypal-refund-status` (`fetch_paypal_refund_status` — Merchant-Direct refund polling)
- `GET /api/v1/returns/bridge/pending` (`fetch_pending_returns`)
- `GET /api/v1/media/files/{path}` (`fetch_media_bytes` — path-traversal guarded)
- `POST /api/v1/returns/{return_id}/agent-decision` (`post_agent_recommendation` — invoked automatically by `shipkart_sync_service.py` with `execute_paypal_refund=False`)
- `POST /api/v1/returns/{return_id}/execute-approved-refund` (`submit_approved_refund_execution` — method implemented on `ShipkartBridgeClient`; invoked directly from Shipkart Seller Hub rather than `agent_backend` routes)

---

## 3. Standalone Simulator Services (`simulators/`) — All `Simulated / mocked`

None of the simulator endpoints perform real external network calls or real banking/logistics mutations; all state resides in in-memory Python dictionaries and resets on container restart.

### Issuer / Bank Simulator (`simulators/issuer_simulator/app/main.py` — Port `8201`)

| Method | Route | Purpose | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health probe (`is_simulated: true`) | Unauthenticated |
| `POST` | `/issuer/inquiries` | Create synthetic issuer inquiry (`201`) | Enforces 4-digit `card_last4` (`422` if >4 digits or PAN-like); supports `VISA`, `MASTERCARD`, `RUPAY`; generates synthetic `ARN-SIM-*` |
| `GET` | `/issuer/inquiries` | List synthetic inquiries | Filterable by `refund_case_id`, `paypal_refund_id`, `paypal_capture_id`, `scenario`, `status` |
| `GET` | `/issuer/inquiries/{inquiry_id}` | Fetch synthetic inquiry state | `404` if unknown |
| `GET` | `/issuer/inquiries/{inquiry_id}/timeline` | Fetch synthetic issuer event history | Returns synthetic timestamps advancing in `+6h` steps |
| `POST` | `/issuer/inquiries/{inquiry_id}/advance` | Advance synthetic posting state machine | Returns **HTTP `503`** for `ISSUER_UNAVAILABLE`; transitions `NORMAL_POSTING`/`DELAYED_POSTING`/`REPLACED_CARD` toward `CREDIT_POSTED` |
| `POST` | `/issuer/scenarios/{inquiry_id}/trigger` | Force 1 of 8 test scenarios on an inquiry | `NORMAL_POSTING`, `DELAYED_POSTING`, `REFERENCE_MISMATCH`, `MISSING_TRANSACTION_REFERENCE` (`MISSING_REFERENCE` alias), `DUPLICATE_CREDIT`, `REPLACED_CARD`, `ISSUER_UNAVAILABLE`, `INSUFFICIENT_EVIDENCE` |

### India / USA Regulatory Rules Simulator (`simulators/regulatory_simulator/app/main.py` — Port `8202`)

| Method | Route | Purpose | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health probe (`is_simulated: true` + legal disclaimer) | Unauthenticated |
| `POST` | `/regulatory/evaluate` | Evaluate refund context against IN/US rules | Evaluates `merchant_country`, `customer_country`, `payment_route`, `merchant_entity_type`, `settlement_entity_confirmed`, `business_activity`, `refund_delay_hours`, optional `evaluation_date`; returns `UNKNOWN`/`MANUAL_REVIEW_REQUIRED`/`POTENTIALLY_APPLICABLE` if fields are missing |
| `GET` | `/regulatory/countries` | List supported `IN` and `US` scopes & frameworks | Includes non-legal-advice disclaimer |
| `GET` | `/regulatory/rules` | List versioned rules (`IN-RBI-FEMA-2026.1`, `IN-CPA-ECOM-2020.1`, `US-REG-E-2026.1`, `US-FTC-MAIL-2026.1`) | Filterable by `jurisdiction` and `version` |
| `GET` | `/regulatory/transactions/{transaction_or_eval_id}` | Retrieve past simulated evaluation | Lookup by `evaluation_id` or `transaction_id` |
| `GET` | `/regulatory/obligations/{case_id}` | Retrieve simulated compliance obligations for a case | Read-only |
| `GET` | `/regulatory/violations` | List simulated rule findings/SLA breaches | Filterable by `case_id`, `jurisdiction` |
| `POST` | `/regulatory/reports/generate` | Compile simulated regulatory report payload | Filtered by `case_id` or `evaluation_id` |

### Carrier Reverse-Logistics Simulator (`simulators/carrier_simulator/app/main.py` — Port `8203`)

| Method | Route | Purpose | Notes |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health probe (`is_simulated: true`) | Unauthenticated |
| `POST` | `/carrier/shipments` | Create simulated reverse-pickup shipment (`201`) | Supports `BlueDart`, `Delhivery`, `FedEx`; generates `TRK-SK-*` tracking IDs |
| `GET` | `/carrier/shipments` | List simulated shipments | Filterable by `return_case_id`, `shipkart_order_id`, `carrier_name`, `status` |
| `GET` | `/carrier/shipments/{tracking_number}` | Retrieve simulated shipment & scan timeline | `404` if unknown |
| `POST` | `/carrier/shipments/{tracking_number}/advance` | Advance tracking along `PICKUP_SCHEDULED -> PICKED_UP -> IN_TRANSIT -> OUT_FOR_DELIVERY -> DELIVERED_TO_MERCHANT` | Respects stalled/lost scenarios |
| `POST` | `/carrier/shipments/{tracking_number}/scenario` | Force carrier scenario | `NORMAL_TRANSIT`, `PICKUP_OVERDUE`, `CARRIER_STALLED`, `DELIVERED_TO_MERCHANT`, `LOST_PACKAGE` |
