import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, ShieldAlert, ShieldCheck } from 'lucide-react';
import { opsApi } from '../api/client';
import { ApiErrorBanner, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { ComplianceOverviewResponse, ComplianceRuleDefinition } from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

const DEFAULT_GUARDRAILS: ComplianceRuleDefinition[] = [
  {
    rule_code: 'REF-001',
    category: 'Financial Authorization',
    description: 'Explicit human Merchant approval (RefundApproval=APPROVED) is mandatory before PayPal refund execution.',
    enforcement: 'HARD_BLOCK_403',
    severity: 'CRITICAL',
  },
  {
    rule_code: 'REF-002',
    category: 'Refund Balance',
    description: 'Refund amount must be > 0 and <= remaining refundable capture balance.',
    enforcement: 'HARD_BLOCK_422',
    severity: 'CRITICAL',
  },
  {
    rule_code: 'REF-003',
    category: 'Idempotency',
    description: 'Every PayPal refund execution requires a unique idempotency_key to prevent double refunds.',
    enforcement: 'HARD_BLOCK_422',
    severity: 'HIGH',
  },
  {
    rule_code: 'REF-004',
    category: 'Capture Linkage',
    description: 'Refund must target the verified original PayPal capture_id on the RefundCase.',
    enforcement: 'HARD_BLOCK_422',
    severity: 'CRITICAL',
  },
  {
    rule_code: 'AUTH-001',
    category: 'Tenant Isolation',
    description: 'Merchant endpoints enforce owning shipkart_merchant_id / merchant_id scoping.',
    enforcement: 'HARD_BLOCK_403',
    severity: 'CRITICAL',
  },
  {
    rule_code: 'AUTH-002',
    category: 'Customer Isolation',
    description: 'Customer endpoints enforce owning shipkart_customer_id / customer_id scoping.',
    enforcement: 'HARD_BLOCK_403',
    severity: 'HIGH',
  },
  {
    rule_code: 'CASE-001',
    category: 'Rejection Auditability',
    description: 'Merchant return/refund rejections require a human-provided reason (>= 3 chars).',
    enforcement: 'HARD_BLOCK_422',
    severity: 'MEDIUM',
  },
  {
    rule_code: 'QTY-001',
    category: 'Return Quantity Integrity',
    description: 'Approved return quantity cannot exceed quantity purchased on the order item.',
    enforcement: 'HARD_BLOCK_422',
    severity: 'HIGH',
  },
  {
    rule_code: 'DATA-001',
    category: 'PII & Secret Redaction',
    description: 'Never log or persist raw card PANs, CVVs, PayPal secrets, or unredacted PII in audit/log tables.',
    enforcement: 'REDACTION_FILTER',
    severity: 'CRITICAL',
  },
];

export function CompliancePage() {
  const [severityFilter, setSeverityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const fetcher = useCallback(() => opsApi.getComplianceOverview(), []);
  const { data, loading, error, reload } = useOpsFetch<ComplianceOverviewResponse>(fetcher);

  const rules = data?.rules && data.rules.length > 0 ? data.rules : DEFAULT_GUARDRAILS;
  const filteredViolations = (data?.violations ?? []).filter((v) => {
    if (severityFilter && v.severity.toUpperCase() !== severityFilter) return false;
    if (statusFilter && v.status.toUpperCase() !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            Compliance Guardrails &amp; Violation Feed
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Hard financial, authorization, and data-protection rules (
            <span className="font-semibold text-gray-700">REF-001..DATA-001</span>) enforced in
            Python before any state transition or PayPal API call.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void reload()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Guardrail Rules Table */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-700" />
          <h2 className="text-sm font-bold text-gray-800">
            Deterministic Policy Guardrails ({rules.length})
          </h2>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="py-2 pr-3">Rule Code</th>
                <th className="py-2 pr-3">Category</th>
                <th className="py-2 pr-3">Severity</th>
                <th className="py-2 pr-3">Enforcement</th>
                <th className="py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rules.map((rule) => (
                <tr key={rule.rule_code} className="hover:bg-gray-50">
                  <td className="py-2.5 pr-3 font-mono font-semibold text-gray-900">
                    {rule.rule_code}
                  </td>
                  <td className="py-2.5 pr-3 text-gray-700">{rule.category}</td>
                  <td className="py-2.5 pr-3">
                    <StatusPill value={rule.severity} />
                  </td>
                  <td className="py-2.5 pr-3 font-mono text-[11px] text-gray-600">
                    {rule.enforcement}
                  </td>
                  <td className="py-2.5 text-gray-700">{rule.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Live Violations Feed */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-rose-600" />
            <h2 className="text-sm font-bold text-gray-800">
              ComplianceViolation Feed ({filteredViolations.length})
            </h2>
          </div>

          <div className="flex items-center gap-2">
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded border border-gray-200 px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">All Severities</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded border border-gray-200 px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">All Statuses</option>
              <option value="OPEN">OPEN</option>
              <option value="RESOLVED">RESOLVED</option>
            </select>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="py-2 pr-3">Rule</th>
                <th className="py-2 pr-3">Severity</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Refund Case</th>
                <th className="py-2 pr-3">Description</th>
                <th className="py-2">Detected</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredViolations.length > 0 ? (
                filteredViolations.map((v) => (
                  <tr key={v.id} className="hover:bg-gray-50">
                    <td className="py-2.5 pr-3 font-mono font-semibold text-gray-900">
                      {v.rule_code}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusPill value={v.severity} />
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusPill value={v.status} />
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {v.refund_case_id ? (
                        <Link
                          to={`/operations/cases?caseId=${encodeURIComponent(v.refund_case_id)}`}
                          className="text-shipkart-blue underline hover:text-shipkart-blueHover"
                        >
                          {shortId(v.refund_case_id)}
                        </Link>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="py-2.5 pr-3 text-gray-700">{v.description}</td>
                    <td className="py-2.5 font-mono text-[11px] text-gray-500">
                      {formatTimestamp(v.created_at)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-gray-500">
                    {loading ? 'Loading compliance feed…' : 'No compliance violations recorded.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
