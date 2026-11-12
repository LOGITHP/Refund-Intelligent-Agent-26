import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Calculator, Clock, RefreshCw } from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import { ApiErrorBanner, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { EtaOverviewResponse } from '../types/api';
import { formatTimestamp, getDelayOwnerClasses, shortId } from '../utils/format';

const DELAY_RULES = [
  { code: 'DELAY-001', owner: 'CARRIER / MERCHANT', sla: '48h', trigger: 'Pickup overdue since return approval' },
  { code: 'DELAY-002', owner: 'CARRIER', sla: '72h', trigger: 'Carrier transit stalled since last scan' },
  { code: 'DELAY-003', owner: 'MERCHANT', sla: '48h', trigger: 'Warehouse inspection overdue after delivery' },
  { code: 'DELAY-004', owner: 'MERCHANT', sla: '48h', trigger: 'Merchant approval overdue after inspection pass' },
  { code: 'DELAY-005', owner: 'PAYPAL', sla: '24h', trigger: 'PayPal refund submission stuck PENDING' },
  { code: 'DELAY-006', owner: 'ISSUER_OR_BANK', sla: '72h', trigger: 'PayPal COMPLETED while bank credit unconfirmed' },
];

export function EtaPage() {
  const [recalcBusy, setRecalcBusy] = useState(false);
  const [recalcNotice, setRecalcNotice] = useState<string | null>(null);
  const [recalcError, setRecalcError] = useState<string | null>(null);

  const fetcher = useCallback(() => opsApi.getEtaOverview(), []);
  const { data, loading, error, reload } = useOpsFetch<EtaOverviewResponse>(fetcher);

  async function handleRecalculateAll() {
    setRecalcBusy(true);
    setRecalcNotice(null);
    setRecalcError(null);
    try {
      const res = await opsApi.recalculateEta();
      setRecalcNotice(
        `Deterministic ETA recalculation finished (${res.status}${
          res.recalculated_count !== undefined ? `, ${res.recalculated_count} updated` : ''
        }).`
      );
      await reload();
    } catch (err) {
      setRecalcError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'ETA recalculation failed'
      );
    } finally {
      setRecalcBusy(false);
    }
  }

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            Deterministic ETA &amp; SLA Delay Alerts
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Zero-LLM stage-remaining refund ETA snapshots and deterministic{' '}
            <span className="font-semibold text-gray-700">DELAY-001..DELAY-006</span> breach
            detection. Blocked or missing stages explicitly return{' '}
            <span className="font-semibold text-gray-700">NOT_ESTIMABLE</span>.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleRecalculateAll()}
            disabled={recalcBusy}
            className="inline-flex items-center gap-1.5 rounded bg-shipkart-blue px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-shipkart-blueHover disabled:opacity-50"
          >
            <Calculator className="h-3.5 w-3.5" />
            {recalcBusy ? 'Recalculating…' : 'Recalculate All ETAs'}
          </button>
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
      </div>

      {recalcNotice && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-xs text-emerald-900">
          {recalcNotice}
        </div>
      )}
      {recalcError && (
        <div className="rounded border border-rose-200 bg-rose-50 px-4 py-2.5 font-mono text-xs text-rose-800">
          {recalcError}
        </div>
      )}

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Delay Rule Reference Strip */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {DELAY_RULES.map((rule) => (
          <div key={rule.code} className="rounded border border-gray-100 bg-white p-3.5 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-semibold text-gray-900">{rule.code}</span>
              <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[10px] font-semibold text-gray-700">
                SLA {rule.sla}
              </span>
            </div>
            <p className="mt-1 text-xs text-gray-700">{rule.trigger}</p>
            <p className="mt-1 font-mono text-[10px] text-gray-500">Owner: {rule.owner}</p>
          </div>
        ))}
      </div>

      {/* Active Alerts */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <h2 className="text-sm font-bold text-gray-800">
            Active SLA Delay Alerts ({data?.alerts.length ?? 0})
          </h2>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="py-2 pr-3">Rule</th>
                <th className="py-2 pr-3">Owner</th>
                <th className="py-2 pr-3">Refund Case</th>
                <th className="py-2 pr-3">Elapsed / SLA</th>
                <th className="py-2 pr-3">Recommended Action</th>
                <th className="py-2">Description</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data && data.alerts.length > 0 ? (
                data.alerts.map((alert, i) => (
                  <tr key={`${alert.refund_case_id}-${alert.rule_code}-${i}`} className="hover:bg-gray-50">
                    <td className="py-2.5 pr-3 font-mono font-semibold text-amber-900">
                      {alert.rule_code}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span
                        className={`inline-flex rounded border px-2 py-0.5 font-mono text-[11px] font-medium ${getDelayOwnerClasses(
                          alert.delay_owner
                        )}`}
                      >
                        {alert.delay_owner}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      <Link
                        to={`/operations/cases?caseId=${encodeURIComponent(alert.refund_case_id)}`}
                        className="text-shipkart-blue underline hover:text-shipkart-blueHover"
                      >
                        {shortId(alert.refund_case_id)}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-3 font-mono tabular-mono">
                      {alert.hours_elapsed !== null ? `${alert.hours_elapsed}h` : '—'} / {alert.sla_hours}h
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-gray-700">
                      {alert.recommended_action}
                    </td>
                    <td className="py-2.5 text-gray-700">{alert.description}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-gray-500">
                    {loading ? 'Evaluating delay alerts…' : 'No active DELAY-001..006 breaches.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Deterministic ETA Snapshots */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-gray-700" />
          <h2 className="text-sm font-bold text-gray-800">
            Current ETA Snapshots ({data?.estimates.length ?? 0})
          </h2>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {data && data.estimates.length > 0 ? (
            data.estimates.map((eta) => {
              const isUnestimable = eta.eta_status === 'NOT_ESTIMABLE' || !eta.earliest_at;
              return (
                <div key={eta.id} className="rounded border border-gray-100 bg-white p-4 shadow-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link
                      to={`/operations/cases?caseId=${encodeURIComponent(eta.refund_case_id)}`}
                      className="font-mono text-xs font-semibold text-shipkart-blue underline hover:text-shipkart-blueHover"
                    >
                      Case {shortId(eta.refund_case_id, 12)}
                    </Link>
                    <div className="flex items-center gap-2">
                      <StatusPill value={eta.eta_status} />
                      <StatusPill value={eta.confidence_level} />
                    </div>
                  </div>

                  {isUnestimable ? (
                    <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
                      <p className="font-mono font-semibold">NOT_ESTIMABLE — Honest Blocker</p>
                      <p className="mt-1">{eta.explanation}</p>
                    </div>
                  ) : (
                    <div className="mt-3 space-y-1.5 text-xs">
                      <div className="flex flex-wrap gap-4 font-mono text-[11px] text-gray-800">
                        <span>Earliest: {formatTimestamp(eta.earliest_at)}</span>
                        <span>Latest: {formatTimestamp(eta.latest_at)}</span>
                      </div>
                      <p className="text-gray-600">{eta.explanation}</p>
                    </div>
                  )}

                  {eta.basis.length > 0 && (
                    <div className="mt-3 overflow-x-auto border-t border-gray-100 pt-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                        Stage-Remaining Basis
                      </p>
                      <table className="mt-1.5 w-full text-left font-mono text-[11px]">
                        <thead>
                          <tr className="text-gray-400">
                            <th className="py-1 pr-2">Stage</th>
                            <th className="py-1 pr-2">Status</th>
                            <th className="py-1 pr-2">Range (h)</th>
                            <th className="py-1">Detail</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {eta.basis.map((b, idx) => (
                            <tr key={`${eta.id}-basis-${idx}`}>
                              <td className="py-1 pr-2 font-semibold text-gray-800">{b.stage}</td>
                              <td className="py-1 pr-2 text-gray-600">{b.status}</td>
                              <td className="py-1 pr-2 text-gray-700">
                                {b.min_hours}–{b.max_hours}h
                              </td>
                              <td className="py-1 font-sans text-gray-600">{b.detail}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="col-span-full rounded border border-dashed border-gray-200 bg-white p-8 text-center text-xs text-gray-500">
              {loading ? 'Loading ETA snapshots…' : 'No ETA snapshots computed yet.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
