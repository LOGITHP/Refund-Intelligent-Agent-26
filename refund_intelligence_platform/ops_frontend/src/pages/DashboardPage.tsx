import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  CreditCard,
  RefreshCw,
  Scale,
  ShieldAlert,
} from 'lucide-react';
import { opsApi } from '../api/client';
import { SimulatedBadge } from '../components/SimulatedBadge';
import { ApiErrorBanner, CurrencyAmount, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { OverviewMetrics } from '../types/api';
import { formatTimestamp, getDelayOwnerClasses, shortId } from '../utils/format';

export function DashboardPage() {
  const fetcher = useCallback(() => opsApi.getOverview(), []);
  const { data, loading, error, reload } = useOpsFetch<OverviewMetrics>(fetcher);

  const currenciesRequested = Object.entries(data?.total_requested_by_currency ?? {});
  const currenciesApproved = Object.entries(data?.total_approved_by_currency ?? {});

  return (
    <div className="space-y-6 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            Operations Overview
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Live refund intelligence across Shipkart returns, PayPal Sandbox execution, and
            simulated Carrier / Issuer / Regulatory rails.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.generated_at && (
            <span className="text-[11px] text-gray-500">
              Synced {formatTimestamp(data.generated_at)}
            </span>
          )}
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Guided Operator Workflow */}
      <div className="rounded bg-white p-4 shadow-sm border border-gray-100">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500">
            Operations Workflow (4-Step Lifecycle)
          </p>
          <span className="text-[11px] font-medium text-shipkart-blue">
            AI updates sync automatically to Seller Hub &amp; Storefront
          </span>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Link
            to="/operations/cases"
            className="rounded border border-gray-200 bg-gray-50/70 p-3 apple-card-hover hover:border-shipkart-blue hover:bg-blue-50/30"
          >
            <p className="text-xs font-bold text-gray-800">1. Inspect Refund Case</p>
            <p className="mt-0.5 text-[11px] text-gray-600">
              Review Physical Return vs Financial Refund timelines and customer evidence.
            </p>
          </Link>
          <Link
            to="/operations/integrations"
            className="rounded border border-gray-200 bg-gray-50/70 p-3 apple-card-hover hover:border-shipkart-blue hover:bg-blue-50/30"
          >
            <p className="text-xs font-bold text-gray-800">
              2. Simulate Delay or Bank Trace
            </p>
            <p className="mt-0.5 text-[11px] text-gray-600">
              Test Carrier stalls, Issuer posting delays, or IN/US regulatory rules.
            </p>
          </Link>
          <Link
            to="/operations/agents"
            className="rounded border border-gray-200 bg-gray-50/70 p-3 apple-card-hover hover:border-shipkart-blue hover:bg-blue-50/30"
          >
            <p className="text-xs font-bold text-gray-800">
              3. Run 3-Agent AI Pipeline
            </p>
            <p className="mt-0.5 text-[11px] text-gray-600">
              Generate merchant &amp; customer explanations without touching PayPal funds.
            </p>
          </Link>
          <div className="rounded border border-blue-200 bg-blue-50/60 p-3">
            <p className="text-xs font-bold text-shipkart-navy">
              4. Merchant Approves REF-001
            </p>
            <p className="mt-0.5 text-[11px] text-gray-700">
              Merchant Seller Hub approves &amp; executes PayPal refund via isolated merchant keys.
            </p>
          </div>
        </div>
      </div>

      {/* Primary KPI Grid (Matches Shipkart Seller Hub KPI Cards) */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm apple-card-hover hover:shadow-md hover:-translate-y-0.5">
          <p className="text-xs font-bold uppercase text-gray-500">
            Active / Total Refund Cases
          </p>
          <div className="mt-2 flex items-baseline gap-2 tabular-mono">
            <span className="text-2xl font-extrabold text-gray-900">
              {data?.active_refund_cases ?? '—'}
            </span>
            <span className="text-xs font-medium text-gray-500">
              / {data?.total_refund_cases ?? '—'} refunds ({data?.total_return_cases ?? '—'} returns)
            </span>
          </div>
          <Link
            to="/operations/cases"
            className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-shipkart-blue hover:underline"
          >
            Inspect refund cases <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm apple-card-hover hover:shadow-md hover:-translate-y-0.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase text-gray-500">
              Overdue Cases (DELAY-001..006)
            </p>
            <Clock className="h-4 w-4 text-orange-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2 tabular-mono">
            <span className="text-2xl font-extrabold text-orange-600">
              {data?.overdue_cases_count ?? '—'}
            </span>
            <span className="text-xs text-gray-500">
              Pending Merchant Approval: {data?.pending_merchant_approvals ?? '—'}
            </span>
          </div>
          <Link
            to="/operations/eta"
            className="mt-3 inline-flex items-center gap-1 text-[11px] font-semibold text-orange-600 hover:underline"
          >
            Review SLA alerts &amp; ETAs <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm apple-card-hover hover:shadow-md hover:-translate-y-0.5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold uppercase text-gray-500">
              PayPal Completed • Bank Unconfirmed
            </p>
            <AlertCircle className="h-4 w-4 text-shipkart-blue" />
          </div>
          <div className="mt-2 flex items-baseline gap-2 tabular-mono">
            <span className="text-2xl font-extrabold text-gray-900">
              {data?.paypal_completed_bank_unconfirmed_count ?? '—'}
            </span>
            <span className="text-xs font-semibold text-red-600">
              Violations open: {data?.open_compliance_violations ?? '—'}
            </span>
          </div>
          <p className="mt-3 text-[11px] text-gray-500">
            PayPal completion does not confirm issuer card posting until bank trace settles.
          </p>
        </div>
      </div>

      {/* Currency Separation + Service Status Matrix */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-800">
              Refund Volume by Currency (Separated)
            </h2>
            <span className="font-mono text-[10px] uppercase text-gray-500">
              INR ≠ USD • NUMERIC
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            Original order currency and PayPal settlement currency are never aggregated together.
          </p>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Requested Totals
              </p>
              <div className="mt-2 space-y-1.5">
                {currenciesRequested.length > 0 ? (
                  currenciesRequested.map(([curr, amt]) => (
                    <div key={curr} className="flex items-center justify-between text-sm">
                      <CurrencyAmount amount={amt} currency={curr} />
                    </div>
                  ))
                ) : (
                  <p className="font-mono text-xs text-gray-400">No currency volume yet</p>
                )}
              </div>
            </div>

            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                Approved Totals
              </p>
              <div className="mt-2 space-y-1.5">
                {currenciesApproved.length > 0 ? (
                  currenciesApproved.map(([curr, amt]) => (
                    <div key={curr} className="flex items-center justify-between text-sm">
                      <CurrencyAmount amount={amt} currency={curr} />
                    </div>
                  ))
                ) : (
                  <p className="font-mono text-xs text-gray-400">No approved volume yet</p>
                )}
              </div>
            </div>
          </div>

          {/* Quick Links */}
          <div className="mt-5 grid grid-cols-2 gap-2">
            <Link
              to="/operations/agents"
              className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-50"
            >
              <Bot className="h-4 w-4 text-gray-500" />
              3-Agent Monitor
            </Link>
            <Link
              to="/operations/issuer-simulator"
              className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-50"
            >
              <span className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-gray-500" />
                Issuer Sim
              </span>
              <SimulatedBadge compact />
            </Link>
            <Link
              to="/operations/regulatory"
              className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-50"
            >
              <span className="flex items-center gap-2">
                <Scale className="h-4 w-4 text-gray-500" />
                Regulatory
              </span>
              <SimulatedBadge compact />
            </Link>
            <Link
              to="/operations/compliance"
              className="flex items-center gap-2 rounded border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-50"
            >
              <ShieldAlert className="h-4 w-4 text-gray-500" />
              Compliance &amp; Audit
            </Link>
          </div>
        </div>

        {/* Service Connectivity Matrix */}
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-7">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-800">
              Platform &amp; Simulator Status Matrix
            </h2>
            <Link
              to="/operations/integrations"
              className="text-xs font-semibold text-shipkart-blue hover:underline"
            >
              Full health matrix →
            </Link>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                name: 'NVIDIA NIM LLM',
                sub: 'Nemotron 3.5 Super VL / Fallback',
                status: data?.service_status.nvidia_nim,
                sim: false,
              },
              {
                name: 'PayPal Gateway',
                sub: 'Merchant-Direct via Shipkart Bridge',
                status: data?.service_status.paypal_sandbox,
                sim: false,
              },
              {
                name: 'Shipkart Bridge',
                sub: 'HMAC/JWT Commerce Sync',
                status: data?.service_status.shipkart_bridge,
                sim: false,
              },
              {
                name: 'Issuer Simulator',
                sub: 'Card Posting & ARN Trace',
                status: data?.service_status.issuer_simulator,
                sim: true,
              },
              {
                name: 'Regulatory Sim',
                sub: 'IN / US Compliance Rules',
                status: data?.service_status.regulatory_simulator,
                sim: true,
              },
              {
                name: 'Carrier Simulator',
                sub: 'Reverse Logistics Tracking',
                status: data?.service_status.carrier_simulator,
                sim: true,
              },
            ].map((svc) => (
              <div
                key={svc.name}
                className="flex flex-col justify-between rounded border border-gray-200 bg-gray-50 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold text-gray-900">{svc.name}</p>
                    <p className="font-mono text-[10px] text-gray-500">{svc.sub}</p>
                  </div>
                  {svc.sim && <SimulatedBadge compact />}
                </div>
                <div className="mt-3">
                  <StatusPill value={svc.status ?? (loading ? 'CHECKING' : 'UNKNOWN')} />
                </div>
              </div>
            ))}
          </div>

          {/* Delay Rule Breakdown */}
          <div className="mt-5 border-t border-gray-100 pt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              Active Delay Rules Breakdown (DELAY-001 .. DELAY-006)
            </p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {['DELAY-001', 'DELAY-002', 'DELAY-003', 'DELAY-004', 'DELAY-005', 'DELAY-006'].map(
                (rule) => {
                  const count = data?.delay_breakdown?.[rule] ?? 0;
                  return (
                    <div
                      key={rule}
                      className={`flex items-center gap-2 rounded border px-2.5 py-1.5 font-mono text-xs ${
                        count > 0
                          ? 'border-amber-300 bg-amber-50 text-amber-900'
                          : 'border-gray-200 bg-white text-gray-500'
                      }`}
                    >
                      <span className="font-semibold">{rule}</span>
                      <span className="rounded bg-white/80 px-1.5 py-0.5 text-[11px] font-bold">
                        {count}
                      </span>
                    </div>
                  );
                }
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Active Delay Alerts & Recent Cases */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-800">Active Delay Alerts</h2>
            <Link to="/operations/eta" className="text-xs font-semibold text-shipkart-blue hover:underline">
              View all →
            </Link>
          </div>
          <div className="mt-3 space-y-2.5">
            {data && data.active_alerts.length > 0 ? (
              data.active_alerts.slice(0, 6).map((alert, idx) => (
                <div
                  key={`${alert.refund_case_id}-${alert.rule_code}-${idx}`}
                  className="rounded border border-gray-200 bg-gray-50 p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="rounded border border-amber-300 bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-amber-900">
                        {alert.rule_code}
                      </span>
                      <span
                        className={`rounded border px-1.5 py-0.5 font-mono text-[11px] font-medium ${getDelayOwnerClasses(
                          alert.delay_owner
                        )}`}
                      >
                        {alert.delay_owner}
                      </span>
                    </div>
                    <span className="font-mono text-[11px] text-gray-500">
                      Case {shortId(alert.refund_case_id)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-xs text-gray-700">{alert.description}</p>
                  <p className="mt-1 font-mono text-[10px] text-gray-500">
                    Action: {alert.recommended_action} • SLA {alert.sla_hours}h
                    {alert.hours_elapsed !== null ? ` • Elapsed ${alert.hours_elapsed}h` : ''}
                  </p>
                </div>
              ))
            ) : (
              <div className="flex items-center gap-2 rounded border border-dashed border-gray-200 p-6 text-xs text-gray-500">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span>No active SLA breaches reported.</span>
              </div>
            )}
          </div>
        </div>

        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-7">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-800">Recent Refund Cases</h2>
            <Link to="/operations/cases" className="text-xs font-semibold text-shipkart-blue hover:underline">
              Open Case Explorer →
            </Link>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                  <th className="py-2 pr-3">Case / Order</th>
                  <th className="py-2 pr-3">Return vs Refund</th>
                  <th className="py-2 pr-3">Amount</th>
                  <th className="py-2 pr-3">Delay Owner</th>
                  <th className="py-2">Opened</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data && data.recent_cases.length > 0 ? (
                  data.recent_cases.slice(0, 8).map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="py-2.5 pr-3 font-mono">
                        <Link
                          to={`/operations/cases?caseId=${encodeURIComponent(c.id)}`}
                          className="font-semibold text-shipkart-blue underline hover:text-shipkart-blueHover"
                        >
                          {shortId(c.id)}
                        </Link>
                        {c.shipkart_order_id !== null && (
                          <div className="text-[10px] text-gray-500">
                            SK Order #{c.shipkart_order_id}
                          </div>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex flex-col gap-1">
                          <StatusPill value={c.return_status || 'NO_RETURN'} />
                          <StatusPill value={c.status} />
                        </div>
                      </td>
                      <td className="py-2.5 pr-3">
                        <CurrencyAmount amount={c.requested_amount} currency={c.currency} />
                      </td>
                      <td className="py-2.5 pr-3">
                        <span
                          className={`inline-flex rounded border px-2 py-0.5 font-mono text-[11px] font-medium ${getDelayOwnerClasses(
                            c.delay_owner
                          )}`}
                        >
                          {c.delay_owner}
                        </span>
                      </td>
                      <td className="py-2.5 font-mono text-[11px] text-gray-500">
                        {formatTimestamp(c.opened_at)}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-xs text-gray-500">
                      {loading ? 'Loading cases…' : 'No refund cases recorded yet.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
