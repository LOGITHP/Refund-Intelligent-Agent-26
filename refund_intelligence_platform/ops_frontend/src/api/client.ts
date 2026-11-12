import type {
  AgentExecution,
  AgentPipelineRunResult,
  ApiErrorEnvelope,
  AuditLogRecord,
  CarrierScenario,
  CarrierShipmentRecord,
  ComplianceOverviewResponse,
  ComplianceViolationRecord,
  CreateCarrierShipmentPayload,
  CreateIssuerInquiryPayload,
  EtaOverviewResponse,
  IntegrationHealth,
  IssuerInquiryRecord,
  IssuerScenario,
  OverviewMetrics,
  PlatformAuthResponse,
  PlatformAuthStatus,
  PlatformUser,
  RefundCaseDetail,
  RefundCaseSummary,
  RegulatoryEvaluatePayload,
  RegulatoryEvaluationRecord,
  RegulatoryRule,
  TriggerCarrierScenarioPayload,
  TriggerIssuerScenarioPayload,
} from '../types/api';

const OPS_TOKEN_KEY = 'rip_ops_token';
const OPS_USER_KEY = 'rip_ops_user';
export const OPS_TOKEN_EVENT = 'rip-ops-token-changed';

export const AGENT_API_BASE_URL: string =
  import.meta.env.VITE_AGENT_API_URL || 'http://localhost:8100';

export class OpsApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(message: string, status: number, code = 'API_ERROR', requestId?: string) {
    super(message);
    this.name = 'OpsApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export function getStoredToken(): string | null {
  try {
    const raw = localStorage.getItem(OPS_TOKEN_KEY);
    return raw && raw.trim().length > 0 ? raw.trim() : null;
  } catch {
    return null;
  }
}

export function getStoredUser(): PlatformUser | null {
  try {
    const raw = localStorage.getItem(OPS_USER_KEY);
    return raw ? (JSON.parse(raw) as PlatformUser) : null;
  } catch {
    return null;
  }
}

export function setStoredToken(token: string, user?: PlatformUser | null): void {
  localStorage.setItem(OPS_TOKEN_KEY, token.trim());
  if (user) {
    localStorage.setItem(OPS_USER_KEY, JSON.stringify(user));
  }
  window.dispatchEvent(new Event(OPS_TOKEN_EVENT));
}

export function setStoredUser(user: PlatformUser): void {
  localStorage.setItem(OPS_USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(OPS_TOKEN_EVENT));
}

export function clearStoredToken(): void {
  localStorage.removeItem(OPS_TOKEN_KEY);
  localStorage.removeItem(OPS_USER_KEY);
  window.dispatchEvent(new Event(OPS_TOKEN_EVENT));
}

function buildQuery(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val.trim() !== '') {
      sp.set(key, val.trim());
    }
  }
  const encoded = sp.toString();
  return encoded ? `?${encoded}` : '';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function unwrapList<T>(payload: unknown, keys: string[]): T[] {
  if (Array.isArray(payload)) {
    return payload as T[];
  }
  if (isRecord(payload)) {
    for (const key of keys) {
      const candidate = payload[key];
      if (Array.isArray(candidate)) {
        return candidate as T[];
      }
    }
  }
  return [];
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  includeAuth = true
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  if (includeAuth) {
    const token = getStoredToken();
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${AGENT_API_BASE_URL}${path}`, {
      ...init,
      headers,
    });
  } catch (err) {
    const message =
      err instanceof Error
        ? `Unable to reach the Refund Intelligence service: ${err.message}`
        : 'Unable to reach the Refund Intelligence service.';
    throw new OpsApiError(message, 0, 'NETWORK_UNREACHABLE');
  }

  if (!response.ok) {
    if (includeAuth && response.status === 401) {
      clearStoredToken();
    }
    let parsed: ApiErrorEnvelope | null = null;
    try {
      parsed = (await response.json()) as ApiErrorEnvelope;
    } catch {
      parsed = null;
    }
    const errObj = parsed?.error;
    const message =
      errObj?.message ||
      parsed?.detail ||
      `HTTP ${response.status} ${response.statusText}`;
    throw new OpsApiError(
      message,
      response.status,
      errObj?.code || `HTTP_${response.status}`,
      errObj?.request_id
    );
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (await response.json()) as T;
}

export const opsApi = {
  async getAuthStatus(): Promise<PlatformAuthStatus> {
    return requestJson<PlatformAuthStatus>('/api/v1/operations/auth/status', {}, false);
  },

  async setupFirstOperator(payload: {
    email: string;
    password: string;
    full_name: string;
  }): Promise<PlatformAuthResponse> {
    const data = await requestJson<PlatformAuthResponse>(
      '/api/v1/operations/auth/setup',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      false
    );
    if (data.access_token) {
      setStoredToken(data.access_token, data.user);
    }
    return data;
  },

  async login(payload: { email: string; password: string }): Promise<PlatformAuthResponse> {
    const data = await requestJson<PlatformAuthResponse>(
      '/api/v1/operations/auth/login',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      false
    );
    if (data.access_token) {
      setStoredToken(data.access_token, data.user);
    }
    return data;
  },

  async getMe(): Promise<{ user: PlatformUser }> {
    const res = await requestJson<{ user: PlatformUser }>('/api/v1/operations/auth/me');
    if (res.user) {
      setStoredUser(res.user);
    }
    return res;
  },

  logout(): void {
    clearStoredToken();
  },

  async getOverview(): Promise<OverviewMetrics> {
    return requestJson<OverviewMetrics>('/api/v1/operations/overview');
  },

  async listCases(filters?: {
    status?: string;
    delay_owner?: string;
    search?: string;
  }): Promise<RefundCaseSummary[]> {
    const qs = buildQuery({
      status: filters?.status,
      delay_owner: filters?.delay_owner,
      search: filters?.search,
    });
    const payload = await requestJson<unknown>(`/api/v1/operations/cases${qs}`);
    return unwrapList<RefundCaseSummary>(payload, ['cases', 'items', 'results']);
  },

  async getCaseDetail(caseId: string): Promise<RefundCaseDetail> {
    return requestJson<RefundCaseDetail>(`/api/v1/operations/cases/${encodeURIComponent(caseId)}`);
  },

  async investigateCase(caseId: string): Promise<AgentPipelineRunResult> {
    return requestJson<AgentPipelineRunResult>(
      `/api/v1/agents/investigate/${encodeURIComponent(caseId)}`,
      { method: 'POST' }
    );
  },

  async resolveCase(caseId: string): Promise<AgentPipelineRunResult> {
    return requestJson<AgentPipelineRunResult>(
      `/api/v1/agents/resolve/${encodeURIComponent(caseId)}`,
      { method: 'POST' }
    );
  },

  async listAgentExecutions(filters?: {
    case_id?: string;
    agent_name?: string;
    status?: string;
  }): Promise<AgentExecution[]> {
    const qs = buildQuery({
      case_id: filters?.case_id,
      agent_name: filters?.agent_name,
      status: filters?.status,
    });
    const payload = await requestJson<unknown>(`/api/v1/operations/agents/executions${qs}`);
    return unwrapList<AgentExecution>(payload, ['executions', 'items', 'results']);
  },

  async getIntegrationsHealth(): Promise<IntegrationHealth> {
    return requestJson<IntegrationHealth>('/api/v1/operations/integrations/health');
  },

  async getEtaOverview(): Promise<EtaOverviewResponse> {
    return requestJson<EtaOverviewResponse>('/api/v1/operations/eta');
  },

  async recalculateEta(refundCaseId?: string): Promise<{ recalculated_count?: number; status: string }> {
    return requestJson<{ recalculated_count?: number; status: string }>(
      '/api/v1/internal/eta/recalculate',
      {
        method: 'POST',
        body: JSON.stringify(refundCaseId ? { refund_case_id: refundCaseId } : {}),
      }
    );
  },

  async listIssuerInquiries(filters?: {
    refund_case_id?: string;
    scenario?: IssuerScenario | '';
  }): Promise<IssuerInquiryRecord[]> {
    const qs = buildQuery({
      refund_case_id: filters?.refund_case_id,
      scenario: filters?.scenario,
    });
    const payload = await requestJson<unknown>(
      `/api/v1/operations/issuer-simulator/inquiries${qs}`
    );
    return unwrapList<IssuerInquiryRecord>(payload, ['inquiries', 'items', 'results']);
  },

  async createIssuerInquiry(payload: CreateIssuerInquiryPayload): Promise<IssuerInquiryRecord> {
    return requestJson<IssuerInquiryRecord>('/api/v1/operations/issuer-simulator/inquiries', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async triggerIssuerScenario(
    inquiryId: string,
    payload: TriggerIssuerScenarioPayload
  ): Promise<IssuerInquiryRecord> {
    return requestJson<IssuerInquiryRecord>(
      `/api/v1/operations/issuer-simulator/scenarios/${encodeURIComponent(inquiryId)}/trigger`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  async listCarrierShipments(filters?: {
    return_case_id?: string;
    carrier_name?: string;
    status?: string;
  }): Promise<CarrierShipmentRecord[]> {
    const qs = buildQuery({
      return_case_id: filters?.return_case_id,
      carrier_name: filters?.carrier_name,
      status: filters?.status,
    });
    const payload = await requestJson<unknown>(
      `/api/v1/operations/carrier-simulator/shipments${qs}`
    );
    return unwrapList<CarrierShipmentRecord>(payload, ['shipments', 'items', 'results']);
  },

  async createCarrierShipment(
    payload: CreateCarrierShipmentPayload
  ): Promise<CarrierShipmentRecord> {
    return requestJson<CarrierShipmentRecord>('/api/v1/operations/carrier-simulator/shipments', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async triggerCarrierScenario(
    trackingNumber: string,
    payload: TriggerCarrierScenarioPayload | { scenario: CarrierScenario; note?: string }
  ): Promise<CarrierShipmentRecord> {
    return requestJson<CarrierShipmentRecord>(
      `/api/v1/operations/carrier-simulator/shipments/${encodeURIComponent(trackingNumber)}/scenario`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  async listRegulatoryEvaluations(filters?: {
    jurisdiction?: string;
    status?: string;
  }): Promise<RegulatoryEvaluationRecord[]> {
    const qs = buildQuery({
      jurisdiction: filters?.jurisdiction,
      status: filters?.status,
    });
    const payload = await requestJson<unknown>(`/api/v1/operations/regulatory${qs}`);
    return unwrapList<RegulatoryEvaluationRecord>(payload, ['evaluations', 'items', 'results']);
  },

  async listRegulatoryRules(filters?: {
    jurisdiction?: string;
    version?: string;
  }): Promise<RegulatoryRule[]> {
    const qs = buildQuery({
      jurisdiction: filters?.jurisdiction,
      version: filters?.version,
    });
    const payload = await requestJson<unknown>(`/api/v1/operations/regulatory/rules${qs}`);
    return unwrapList<RegulatoryRule>(payload, ['rules', 'items', 'results']);
  },

  async evaluateRegulatory(
    payload: RegulatoryEvaluatePayload
  ): Promise<RegulatoryEvaluationRecord> {
    return requestJson<RegulatoryEvaluationRecord>('/api/v1/operations/regulatory/evaluate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  async getComplianceOverview(): Promise<ComplianceOverviewResponse> {
    const payload = await requestJson<ComplianceOverviewResponse | ComplianceViolationRecord[]>(
      '/api/v1/operations/compliance'
    );
    if (Array.isArray(payload)) {
      return {
        rules: [],
        violations: payload,
        total_open: payload.filter((v) => v.status === 'OPEN').length,
      };
    }
    return payload;
  },

  async listAuditLogs(filters?: {
    resource_type?: string;
    actor_type?: string;
    action?: string;
    resource_id?: string;
  }): Promise<AuditLogRecord[]> {
    const qs = buildQuery({
      resource_type: filters?.resource_type,
      actor_type: filters?.actor_type,
      action: filters?.action,
      resource_id: filters?.resource_id,
    });
    const payload = await requestJson<unknown>(`/api/v1/operations/audit${qs}`);
    return unwrapList<AuditLogRecord>(payload, ['logs', 'audit_logs', 'items', 'results']);
  },

  async syncShipkartPending(): Promise<{
    scanned: number;
    created: number;
    already_present: number;
    synced_case_ids: string[];
    errors: Array<{ shipkart_return_id: number; error: string }>;
  }> {
    return requestJson('/api/v1/operations/sync-shipkart-pending', {
      method: 'POST',
    });
  },
};
