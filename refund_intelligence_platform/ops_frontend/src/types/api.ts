export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

export type CurrencyCode = 'INR' | 'USD' | string;

export type DelayOwner =
  | 'CUSTOMER'
  | 'CARRIER'
  | 'MERCHANT'
  | 'PAYPAL'
  | 'ISSUER_OR_BANK'
  | 'UNKNOWN'
  | 'NONE'
  | string;

export type DelayRuleCode =
  | 'DELAY-001'
  | 'DELAY-002'
  | 'DELAY-003'
  | 'DELAY-004'
  | 'DELAY-005'
  | 'DELAY-006'
  | string;

export type EtaStatus = 'ESTIMATED' | 'NOT_ESTIMABLE' | 'COMPLETED' | string;

export type CardNetwork = 'VISA' | 'MASTERCARD' | 'RUPAY';

export type IssuerScenario =
  | 'NORMAL_POSTING'
  | 'DELAYED_POSTING'
  | 'REFERENCE_MISMATCH'
  | 'MISSING_TRANSACTION_REFERENCE'
  | 'DUPLICATE_CREDIT'
  | 'REPLACED_CARD'
  | 'ISSUER_UNAVAILABLE'
  | 'INSUFFICIENT_EVIDENCE';

export type CarrierScenario =
  | 'NORMAL_TRANSIT'
  | 'PICKUP_OVERDUE'
  | 'CARRIER_STALLED'
  | 'DELIVERED_TO_MERCHANT'
  | 'LOST_PACKAGE';

export type AgentName = 'intake_agent' | 'investigation_agent' | 'resolution_agent' | string;

export interface ApiErrorDetail {
  code: string;
  message: string;
  request_id?: string;
  details?: Record<string, JsonValue>;
}

export interface ApiErrorEnvelope {
  error?: ApiErrorDetail;
  detail?: string;
}

export interface PlatformUser {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active?: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
}

export interface PlatformAuthStatus {
  has_operators: boolean;
  auth_mode: string;
}

export interface PlatformAuthResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  user: PlatformUser;
}

export interface CreateCarrierShipmentPayload {
  return_case_id: string;
  shipkart_order_id: number | string;
  carrier_name: 'BlueDart' | 'Delhivery' | 'FedEx';
  tracking_number?: string;
  scenario: CarrierScenario;
  origin_city: string;
  destination_city: string;
}

export interface ServiceStatusMatrix {
  nvidia_nim: string;
  paypal_sandbox: string;
  shipkart_bridge: string;
  issuer_simulator: string;
  regulatory_simulator: string;
  carrier_simulator: string;
  postgres?: string;
  redis_celery?: string;
  minio?: string;
}

export interface DelayAlert {
  id?: string;
  refund_case_id: string;
  shipkart_order_id?: number | null;
  rule_code: DelayRuleCode;
  delay_owner: DelayOwner;
  recommended_action: string;
  sla_hours: number;
  hours_elapsed: number | null;
  description: string;
  evidence: Record<string, JsonValue>;
  detected_at?: string;
}

export interface RefundCaseSummary {
  id: string;
  return_case_id: string | null;
  shipkart_return_id: number | null;
  shipkart_order_id: number | null;
  shipkart_customer_id: number | null;
  shipkart_merchant_id: number | null;
  case_type: string;
  status: string;
  return_status: string | null;
  requested_amount: string;
  approved_amount: string | null;
  captured_amount: string | null;
  currency: CurrencyCode;
  original_currency: CurrencyCode;
  paypal_currency: CurrencyCode;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  delay_owner: DelayOwner;
  triggered_delay_rules: DelayRuleCode[];
  eta_status: EtaStatus | null;
  paypal_completed?: boolean;
  issuer_credit_confirmed?: boolean;
  opened_at: string;
  resolved_at: string | null;
}

export interface OverviewMetrics {
  total_return_cases: number;
  total_refund_cases: number;
  active_refund_cases: number;
  overdue_cases_count: number;
  pending_merchant_approvals: number;
  open_compliance_violations: number;
  paypal_completed_bank_unconfirmed_count: number;
  total_requested_by_currency: Record<string, string>;
  total_approved_by_currency: Record<string, string>;
  delay_breakdown: Record<string, number>;
  delay_owner_breakdown: Record<string, number>;
  service_status: ServiceStatusMatrix;
  active_alerts: DelayAlert[];
  recent_cases: RefundCaseSummary[];
  generated_at: string;
}

export interface ReturnCaseSnapshot {
  id: string;
  shipkart_return_id: number | null;
  shipkart_order_id: number | null;
  reason_code: string;
  customer_description: string;
  status: string;
  requested_at: string;
  approved_at: string | null;
  closed_at: string | null;
}

export interface ReturnShipmentRecord {
  id: string;
  return_case_id: string;
  carrier_name: string;
  tracking_number: string;
  carrier_reference: string | null;
  status: string;
  is_simulated: boolean;
  pickup_at: string | null;
  delivered_at: string | null;
  last_synced_at: string | null;
  created_at: string;
}

export interface ReturnInspectionRecord {
  id: string;
  return_case_id: string;
  inspector_id: string | null;
  shipkart_inspector_id: number | null;
  inspection_status: string;
  condition_result: string;
  notes: string;
  completed_at: string | null;
  created_at: string;
}

export interface RefundTransactionRecord {
  id: string;
  refund_case_id: string;
  paypal_order_id: string | null;
  paypal_capture_id: string;
  paypal_refund_id: string | null;
  amount: string;
  currency: CurrencyCode;
  status: string;
  idempotency_key: string;
  submitted_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface RefundApprovalRecord {
  id: string;
  refund_case_id: string;
  shipkart_merchant_user_id: number | null;
  decision: string;
  approved_amount: string | null;
  currency: CurrencyCode;
  reason: string;
  policy_version: string;
  approval_reference: string | null;
  created_at: string;
}

export interface EvidenceRecord {
  id: string;
  return_case_id: string | null;
  refund_case_id: string | null;
  file_name: string;
  mime_type: string;
  file_size: number;
  sha256_hash: string;
  source_type: string;
  verification_status: string;
  extracted_metadata: Record<string, JsonValue>;
  created_at: string;
}

export interface TimelineEvent {
  id: string;
  return_case_id: string | null;
  refund_case_id: string | null;
  timeline_track?: 'PHYSICAL_RETURN' | 'FINANCIAL_REFUND' | string;
  event_type: string;
  source_type: string;
  source_reference: string | null;
  description: string;
  event_data: Record<string, JsonValue>;
  occurred_at: string;
  recorded_at: string;
  verified: boolean;
}

export interface EtaStageBasis {
  stage: string;
  status: string;
  min_hours: number;
  max_hours: number;
  detail: string;
}

export interface EtaEstimate {
  id: string;
  refund_case_id: string;
  eta_status: EtaStatus;
  estimated_from: string;
  earliest_at: string | null;
  latest_at: string | null;
  confidence_level: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  basis: EtaStageBasis[];
  explanation: string;
  blocking_reasons?: string[];
  is_current: boolean;
  created_at: string;
}

export interface AgentDecision {
  id: string;
  execution_id: string;
  decision_type: string;
  recommendation: Record<string, JsonValue>;
  evidence_references: string[];
  confidence: string;
  requires_approval: boolean;
  decision_status: string;
  created_at: string;
}

export interface AgentExecution {
  id: string;
  case_id: string;
  case_type: string;
  agent_name: AgentName;
  status: string;
  input_reference: Record<string, JsonValue>;
  output_data: Record<string, JsonValue>;
  model_name: string;
  prompt_version: string;
  started_at: string;
  completed_at: string | null;
  latency_ms?: number | null;
  error_code: string | null;
  decisions: AgentDecision[];
}

export interface IssuerTimelineEvent {
  event_id: string;
  status: string;
  posting_status: string;
  description: string;
  occurred_at: string;
  is_simulated: boolean;
  simulation_label?: string;
}

export interface IssuerInquiryRecord {
  id: string;
  inquiry_id?: string;
  refund_case_id: string;
  provider_type: string;
  provider_reference: string | null;
  institution_code: string | null;
  paypal_capture_id?: string | null;
  paypal_refund_id?: string | null;
  paypal_refund_status?: string;
  card_network?: CardNetwork;
  card_last4?: string;
  arn?: string | null;
  amount?: string | null;
  currency?: CurrencyCode;
  scenario?: IssuerScenario | string;
  status: string;
  posting_status?: string;
  issuer_service_status?: string;
  credit_posted?: boolean;
  delay_days?: number;
  expected_posting_window?: string | null;
  requires_manual_reconciliation?: boolean;
  mismatch_reason?: string | null;
  duplicate_reference_id?: string | null;
  original_card_status?: string;
  rerouting_via_issuer?: boolean;
  missing_fields?: string[];
  required_evidence?: string[];
  events?: IssuerTimelineEvent[];
  request_data: Record<string, JsonValue>;
  response_data: Record<string, JsonValue>;
  is_simulated: boolean;
  simulation_label?: string;
  created_at: string;
  updated_at: string;
}

export interface CarrierEvent {
  event_id: string;
  status: string;
  location: string;
  description: string;
  occurred_at: string;
  is_simulated: boolean;
  simulation_label?: string;
}

export interface CarrierShipmentRecord {
  tracking_number: string;
  return_case_id: string;
  shipkart_order_id: number | string;
  carrier_name: 'BlueDart' | 'Delhivery' | 'FedEx' | string;
  scenario: CarrierScenario;
  current_status: string;
  origin_city: string;
  destination_city: string;
  delay_detected: boolean;
  delay_reason: string | null;
  pickup_at: string | null;
  delivered_at: string | null;
  events: CarrierEvent[];
  created_at: string;
  updated_at: string;
  is_simulated: boolean;
  simulation_label?: string;
}

export interface RegulatoryRule {
  rule_id: string;
  version: string;
  jurisdiction: string;
  title: string;
  authority: string;
  effective_date: string;
  payment_routes: string[];
  entity_types: string[];
  max_refund_sla_hours: number;
  obligation_summary: string;
  notes: string;
}

export interface MatchedRegulatoryRule {
  rule_id: string;
  version?: string;
  jurisdiction?: string;
  title?: string;
  authority?: string;
  max_refund_sla_hours?: number;
}

export interface RegulatoryObligation {
  rule_id: string;
  version: string;
  jurisdiction: string;
  obligation: string;
  max_refund_sla_hours: number;
}

export interface RegulatoryEvaluationRecord {
  id: string;
  evaluation_id?: string;
  refund_case_id: string | null;
  transaction_id?: string;
  jurisdiction: string | string[];
  evaluation_status: string;
  status?: string;
  transaction_context: Record<string, JsonValue>;
  rule_version: string;
  matched_rules: MatchedRegulatoryRule[];
  unresolved_questions: string[];
  obligations?: RegulatoryObligation[];
  is_simulated: boolean;
  simulation_label?: string;
  disclaimer?: string;
  evaluated_at: string;
}

export interface ComplianceViolationRecord {
  id: string;
  refund_case_id: string | null;
  rule_code: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  description: string;
  status: 'OPEN' | 'RESOLVED' | 'ACKNOWLEDGED' | string;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface ComplianceRuleDefinition {
  rule_code: string;
  category: string;
  description: string;
  enforcement: string;
  severity: string;
}

export interface ComplianceOverviewResponse {
  rules: ComplianceRuleDefinition[];
  violations: ComplianceViolationRecord[];
  total_open: number;
}

export interface AuditLogRecord {
  id: string;
  actor_id: string | null;
  shipkart_actor_id: number | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string;
  before_state: Record<string, JsonValue> | null;
  after_state: Record<string, JsonValue> | null;
  ip_address: string | null;
  created_at: string;
}

export interface IntegrationConnectorHealth {
  connector_id: string;
  name: string;
  category: 'CORE' | 'EXTERNAL' | 'SIMULATOR' | string;
  endpoint: string;
  status: 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'UNCONFIGURED' | string;
  latency_ms: number | null;
  is_simulated: boolean;
  details: string;
  last_checked_at: string;
}

export interface IntegrationHealth {
  overall_status: 'HEALTHY' | 'DEGRADED' | 'DOWN' | string;
  checked_at: string;
  connectors: IntegrationConnectorHealth[];
}

export interface RefundCaseDetail extends RefundCaseSummary {
  reason: string;
  resolution_summary: string | null;
  return_case: ReturnCaseSnapshot | null;
  shipments: ReturnShipmentRecord[];
  inspections: ReturnInspectionRecord[];
  transactions: RefundTransactionRecord[];
  approvals: RefundApprovalRecord[];
  evidence_items: EvidenceRecord[];
  physical_timeline: TimelineEvent[];
  financial_timeline: TimelineEvent[];
  timeline_events: TimelineEvent[];
  current_eta: EtaEstimate | null;
  delay_alerts: DelayAlert[];
  agent_executions: AgentExecution[];
  issuer_inquiries: IssuerInquiryRecord[];
  regulatory_evaluations: RegulatoryEvaluationRecord[];
  compliance_violations: ComplianceViolationRecord[];
}

export interface EtaOverviewResponse {
  estimates: EtaEstimate[];
  alerts: DelayAlert[];
  generated_at: string;
}

export interface CreateIssuerInquiryPayload {
  refund_case_id: string;
  paypal_capture_id?: string;
  paypal_refund_id?: string;
  paypal_refund_status?: string;
  institution_code: string;
  card_network: CardNetwork;
  card_last4: string;
  amount?: string;
  currency: CurrencyCode;
  scenario: IssuerScenario;
}

export interface TriggerIssuerScenarioPayload {
  scenario: IssuerScenario;
  note?: string;
}

export interface TriggerCarrierScenarioPayload {
  scenario: CarrierScenario;
  note?: string;
}

export interface RegulatoryEvaluatePayload {
  transaction_id: string;
  refund_case_id?: string;
  merchant_country?: string;
  customer_country?: string;
  payment_provider: string;
  transaction_currency?: string;
  settlement_currency?: string;
  payment_route?: 'DOMESTIC' | 'CROSS_BORDER' | '';
  merchant_entity_type?: 'BUSINESS' | 'MARKETPLACE' | 'ENTERPRISE' | 'INDIVIDUAL' | '';
  transaction_type?: string;
  settlement_entity_confirmed?: boolean;
  business_activity?: string;
  refund_delay_hours?: number;
}

export interface AgentPipelineRunResult {
  case_id: string;
  status: string;
  executions: AgentExecution[];
  summary?: string;
}
