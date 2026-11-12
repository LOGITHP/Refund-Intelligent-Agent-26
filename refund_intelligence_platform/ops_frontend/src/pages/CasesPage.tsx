import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  Lock,
  PackageCheck,
  RefreshCw,
  Search,
  Wallet,
  X,
} from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import { SimulatedBadge } from '../components/SimulatedBadge';
import { ApiErrorBanner, CurrencyAmount, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { RefundCaseDetail, RefundCaseSummary, TimelineEvent } from '../types/api';
import { formatTimestamp, getDelayOwnerClasses, shortId } from '../utils/format';

function isPhysicalEvent(ev: TimelineEvent): boolean {
  if (ev.timeline_track) {
    return ev.timeline_track.toUpperCase() === 'PHYSICAL_RETURN';
  }
  const t = ev.event_type.toUpperCase();
  const src = ev.source_type.toUpperCase();
  return (
    src.includes('CARRIER') ||
    src.includes('WAREHOUSE') ||
    src.includes('INSPECTOR') ||
    t.startsWith('RETURN_') ||
    t.startsWith('PICKUP_') ||
    t.startsWith('CARRIER_') ||
    t.startsWith('SHIPMENT_') ||
    t.startsWith('INSPECTION_') ||
    t === 'DELIVERED_TO_MERCHANT'
  );
}

function TimelineColumn({
  title,
  subtitle,
  icon,
  events,
  emptyText,
}: {
  title: string;
  subtitle: string;
  icon: JSX.Element;
  events: TimelineEvent[];
  emptyText: string;
}) {
  return (
    <div className="rounded border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-center gap-2">
        {icon}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-900">{title}</h4>
          <p className="text-[11px] text-gray-500">{subtitle}</p>
        </div>
      </div>

      <div className="mt-3 space-y-2.5">
        {events.length > 0 ? (
          events.map((ev) => (
            <div key={ev.id} className="rounded border border-gray-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[11px] font-semibold text-gray-900">
                  {ev.event_type}
                </span>
                <div className="flex items-center gap-1.5">
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                      ev.verified
                        ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                        : 'bg-gray-100 text-gray-600 border border-gray-200'
                    }`}
                  >
                    {ev.verified ? 'VERIFIED' : 'REPORTED'}
                  </span>
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-600">
                    {ev.source_type}
                  </span>
                </div>
              </div>
              <p className="mt-1 text-xs text-gray-700">{ev.description}</p>
              <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] text-gray-500">
                <span>Occurred: {formatTimestamp(ev.occurred_at)}</span>
                {ev.source_reference && <span>Ref: {ev.source_reference}</span>}
              </div>
            </div>
          ))
        ) : (
          <p className="rounded border border-dashed border-gray-200 bg-white p-4 text-center text-xs text-gray-500">
            {emptyText}
          </p>
        )}
      </div>
    </div>
  );
}

export function CasesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [ownerFilter, setOwnerFilter] = useState('');

  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get('caseId'));
  const [detail, setDetail] = useState<RefundCaseDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<'investigate' | 'resolve' | null>(null);
  const [actionBanner, setActionBanner] = useState<string | null>(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const fetcher = useCallback(
    () =>
      opsApi.listCases({
        status: statusFilter || undefined,
        delay_owner: ownerFilter || undefined,
        search: search || undefined,
      }),
    [statusFilter, ownerFilter, search]
  );

  const { data: cases, loading, error, reload } = useOpsFetch<RefundCaseSummary[]>(fetcher);

  const loadDetail = useCallback(async (caseId: string) => {
    setDetailLoading(true);
    setDetailError(null);
    setActionBanner(null);
    try {
      const d = await opsApi.getCaseDetail(caseId);
      setDetail(d);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load case detail');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      void loadDetail(selectedId);
    } else {
      setDetail(null);
    }
  }, [selectedId, loadDetail]);

  function openCase(id: string) {
    setSelectedId(id);
    setSearchParams({ caseId: id });
  }

  function closeCase() {
    setSelectedId(null);
    setSearchParams({});
  }

  async function handleRunAgent(kind: 'investigate' | 'resolve') {
    if (!selectedId) return;
    setActionBusy(kind);
    setActionBanner(null);
    setDetailError(null);
    try {
      const res =
        kind === 'investigate'
          ? await opsApi.investigateCase(selectedId)
          : await opsApi.resolveCase(selectedId);
      setActionBanner(
        `Agent ${kind} completed (${res.status}). ${res.executions?.length ?? 0} execution(s) recorded.`
      );
      await loadDetail(selectedId);
      await reload();
    } catch (err) {
      setDetailError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Agent invocation failed'
      );
    } finally {
      setActionBusy(null);
    }
  }

  async function handleSyncShipkart() {
    setSyncBusy(true);
    setSyncMsg(null);
    setSyncError(null);
    try {
      const res = await opsApi.syncShipkartPending();
      setSyncMsg(
        `Shipkart Sync: scanned ${res.scanned}, imported ${res.created}, already indexed ${res.already_present}${
          res.errors.length > 0 ? ` (${res.errors.length} failed)` : ''
        }.`
      );
      if (res.errors.length > 0) {
        setSyncError(res.errors.map((e) => `#${e.shipkart_return_id}: ${e.error}`).join(' | '));
      }
      await reload();
    } catch (err) {
      setSyncError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Shipkart bridge sync failed'
      );
    } finally {
      setSyncBusy(false);
    }
  }

  const physicalEvents =
    detail?.physical_timeline && detail.physical_timeline.length > 0
      ? detail.physical_timeline
      : (detail?.timeline_events ?? []).filter(isPhysicalEvent);

  const financialEvents =
    detail?.financial_timeline && detail.financial_timeline.length > 0
      ? detail.financial_timeline
      : (detail?.timeline_events ?? []).filter((ev) => !isPhysicalEvent(ev));

  return (
    <div className="space-y-4 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            Refund Cases Explorer
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Separated Physical Return vs Financial Refund lifecycles, deterministic ETAs, and
            3-agent investigation drill-down.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleSyncShipkart()}
            disabled={syncBusy || loading}
            className="inline-flex items-center gap-1.5 rounded border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncBusy ? 'animate-spin' : ''}`} />
            {syncBusy ? 'Syncing Shipkart…' : 'Sync from Shipkart'}
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

      {syncMsg && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
          {syncMsg}
        </div>
      )}
      {syncError && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {syncError}
        </div>
      )}

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 rounded border border-gray-100 bg-white p-4 shadow-sm md:grid-cols-4">
        <div className="relative md:col-span-2">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            id="cases-search"
            name="search"
            type="text"
            aria-label="Search refund cases"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search case ID, Shipkart order ID, PayPal capture/order ID…"
            className="w-full rounded border border-gray-200 py-2 pl-9 pr-3 text-xs text-gray-900 placeholder:text-gray-400 focus:border-shipkart-blue focus:outline-none"
          />
        </div>

        <select
          id="cases-status-filter"
          name="statusFilter"
          aria-label="Filter by refund status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Refund Statuses</option>
          <option value="INVESTIGATING">INVESTIGATING</option>
          <option value="MERCHANT_REVIEW_PENDING">MERCHANT_REVIEW_PENDING</option>
          <option value="APPROVED">APPROVED</option>
          <option value="PAYPAL_PENDING">PAYPAL_PENDING</option>
          <option value="PAYPAL_COMPLETED">PAYPAL_COMPLETED</option>
          <option value="CONFIRMED_POSTED">CONFIRMED_POSTED</option>
          <option value="REJECTED">REJECTED</option>
        </select>

        <select
          id="cases-owner-filter"
          name="ownerFilter"
          aria-label="Filter by delay owner"
          value={ownerFilter}
          onChange={(e) => setOwnerFilter(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Delay Owners</option>
          <option value="CARRIER">CARRIER</option>
          <option value="MERCHANT">MERCHANT</option>
          <option value="PAYPAL">PAYPAL</option>
          <option value="ISSUER_OR_BANK">ISSUER_OR_BANK</option>
          <option value="CUSTOMER">CUSTOMER</option>
          <option value="UNKNOWN">UNKNOWN</option>
          <option value="NONE">NONE</option>
        </select>
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Cases Table */}
      <div className="overflow-hidden rounded border border-gray-100 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-gray-200 bg-gray-50 text-[11px] uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-4 py-3">Case / Shipkart IDs</th>
                <th className="px-4 py-3">Physical Return</th>
                <th className="px-4 py-3">Financial Refund</th>
                <th className="px-4 py-3">Amounts (Orig vs PayPal)</th>
                <th className="px-4 py-3">Delay Owner</th>
                <th className="px-4 py-3">ETA Status</th>
                <th className="px-4 py-3">Opened</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cases && cases.length > 0 ? (
                cases.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => openCase(c.id)}
                    className={`cursor-pointer transition-colors hover:bg-gray-50 ${
                      selectedId === c.id ? 'bg-blue-50/40' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-mono">
                      <div className="font-semibold text-gray-900">{shortId(c.id, 10)}</div>
                      <div className="mt-0.5 text-[10px] text-gray-500">
                        Order #{c.shipkart_order_id ?? '—'} • Return #{c.shipkart_return_id ?? '—'}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={c.return_status || 'NO_RETURN'} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusPill value={c.status} />
                        {c.paypal_completed && !c.issuer_credit_confirmed && (
                          <span className="font-mono text-[10px] text-amber-800">
                            PayPal Done • Bank Unconfirmed
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="space-y-1">
                        <CurrencyAmount
                          amount={c.requested_amount}
                          currency={c.currency || c.original_currency}
                        />
                        {(c.paypal_capture_id || c.paypal_order_id || c.captured_amount || c.currency === 'USD') &&
                          c.paypal_currency &&
                          c.paypal_currency !== (c.original_currency || c.currency) && (
                            <div className="text-[10px] text-gray-500">
                              PayPal:{' '}
                              <CurrencyAmount
                                amount={
                                  c.currency === c.paypal_currency
                                    ? (c.approved_amount ?? c.requested_amount)
                                    : (c.captured_amount ?? c.requested_amount)
                                }
                                currency={c.paypal_currency}
                                muted
                              />
                            </div>
                          )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded border px-2 py-0.5 font-mono text-[11px] font-medium ${getDelayOwnerClasses(
                          c.delay_owner
                        )}`}
                      >
                        {c.delay_owner}
                      </span>
                      {c.triggered_delay_rules.length > 0 && (
                        <div className="mt-1 font-mono text-[10px] text-amber-800">
                          {c.triggered_delay_rules.join(', ')}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill value={c.eta_status || 'NOT_ESTIMABLE'} />
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-gray-500">
                      {formatTimestamp(c.opened_at)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-xs text-gray-500">
                    {loading ? 'Loading refund cases…' : 'No matching refund cases found.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Case Drill-Down Drawer (portaled to document.body above layout header/sidebar stacking contexts) */}
      {selectedId &&
        createPortal(
          <div
            className="fixed inset-0 z-50 flex justify-end bg-shipkart-navy/50 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) closeCase();
            }}
          >
            <div className="flex h-full w-full max-w-4xl flex-col bg-white shadow-2xl">
              <div className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-gray-200 px-6 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-bold text-gray-900">
                      Case Drill-Down
                    </h2>
                    <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700 break-all">
                      {selectedId}
                    </span>
                  </div>
                  {detail && (
                    <p className="mt-0.5 font-mono text-xs text-gray-500 break-all">
                      Shipkart Order #{detail.shipkart_order_id ?? '—'} • PayPal Capture:{' '}
                      {detail.paypal_capture_id ?? '—'}
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRunAgent('investigate')}
                    disabled={actionBusy !== null || detailLoading}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded bg-shipkart-blue px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-shipkart-blueHover disabled:opacity-50"
                  >
                    <Bot className="h-3.5 w-3.5" />
                    {actionBusy === 'investigate'
                      ? 'Investigating…'
                      : 'Re-run 3-Agent Investigation'}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRunAgent('resolve')}
                    disabled={actionBusy !== null || detailLoading}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded border border-gray-300 bg-white px-3 py-1.5 text-xs font-semibold text-gray-800 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {actionBusy === 'resolve' ? 'Resolving…' : 'Run Resolution Plan'}
                  </button>
                  <button
                    type="button"
                    aria-label="Close case drill-down"
                    onClick={closeCase}
                    className="shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

            <div className="flex-1 space-y-6 overflow-y-auto p-6">
              {detailLoading && (
                <p className="font-mono text-xs text-gray-500">Loading case evidence &amp; timelines…</p>
              )}
              {detailError && (
                <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 font-mono text-xs text-rose-800">
                  {detailError}
                </div>
              )}
              {actionBanner && (
                <div className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900">
                  <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                  <span>{actionBanner}</span>
                </div>
              )}

              {detail && (
                <>
                  {/* Explicit PayPal vs Bank Credit Distinction Banner */}
                  {detail.paypal_completed && !detail.issuer_credit_confirmed && (
                    <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 p-4 text-xs text-amber-950">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                      <div>
                        <p className="font-semibold">
                          PayPal Refund COMPLETED — Issuer Bank Credit Posting Still Unconfirmed
                        </p>
                        <p className="mt-0.5 text-amber-900">
                          PayPal capture/refund completion is strictly distinct from cardholder bank
                          account posting. Check simulated Issuer Inquiries below before advising the
                          customer that funds have landed in their bank.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Summary Cards */}
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                        Physical Return Status
                      </p>
                      <div className="mt-1.5">
                        <StatusPill value={detail.return_case?.status || detail.return_status || 'NO_RETURN'} />
                      </div>
                      <p className="mt-1.5 font-mono text-[11px] text-gray-600">
                        Reason: {detail.return_case?.reason_code || '—'}
                      </p>
                    </div>

                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                        Financial Refund Status
                      </p>
                      <div className="mt-1.5">
                        <StatusPill value={detail.status} />
                      </div>
                      <div className="mt-1.5">
                        <CurrencyAmount amount={detail.requested_amount} currency={detail.currency} />
                      </div>
                    </div>

                    <div className="rounded border border-gray-200 bg-gray-50 p-3">
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                        Delay Attribution
                      </p>
                      <div className="mt-1.5">
                        <span
                          className={`inline-flex rounded border px-2 py-0.5 font-mono text-[11px] font-medium ${getDelayOwnerClasses(
                            detail.delay_owner
                          )}`}
                        >
                          {detail.delay_owner}
                        </span>
                      </div>
                      <p className="mt-1.5 font-mono text-[11px] text-gray-600">
                        Rules: {detail.triggered_delay_rules.join(', ') || 'NONE'}
                      </p>
                    </div>
                  </div>

                  {/* Deterministic ETA Card */}
                  <div className="rounded border border-gray-200 bg-white p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-600" />
                        <h3 className="text-sm font-bold text-gray-800">
                          Deterministic Refund ETA
                        </h3>
                      </div>
                      <StatusPill value={detail.current_eta?.eta_status || 'NOT_ESTIMABLE'} />
                    </div>

                    {!detail.current_eta || detail.current_eta.eta_status === 'NOT_ESTIMABLE' ? (
                      <div className="mt-3 rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
                        <p className="font-mono font-semibold">NOT_ESTIMABLE (Honest Blocker)</p>
                        <p className="mt-1">
                          {detail.current_eta?.explanation ||
                            'Deterministic ETA cannot be computed due to missing or blocked workflow stage.'}
                        </p>
                        {detail.current_eta?.blocking_reasons &&
                          detail.current_eta.blocking_reasons.length > 0 && (
                            <p className="mt-1 font-mono text-[11px]">
                              Blockers: {detail.current_eta.blocking_reasons.join(', ')}
                            </p>
                          )}
                      </div>
                    ) : (
                      <div className="mt-3 space-y-2 text-xs">
                        <div className="flex flex-wrap items-center gap-4 font-mono">
                          <span>
                            Window: <strong>{formatTimestamp(detail.current_eta.earliest_at)}</strong> →{' '}
                            <strong>{formatTimestamp(detail.current_eta.latest_at)}</strong>
                          </span>
                          <span>Confidence: {detail.current_eta.confidence_level}</span>
                        </div>
                        <p className="text-gray-700">{detail.current_eta.explanation}</p>
                      </div>
                    )}
                  </div>

                  {/* SEPARATED PHYSICAL RETURN vs FINANCIAL REFUND TIMELINES */}
                  <div>
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-sm font-bold text-gray-800">
                        Separated Physical Return vs Financial Refund Timelines
                      </h3>
                      <span className="font-mono text-[11px] text-gray-500">
                        Physical ≠ Financial
                      </span>
                    </div>
                    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                      <TimelineColumn
                        title="Physical Return Timeline"
                        subtitle="Carrier reverse pickup, transit, warehouse receipt & QC inspection"
                        icon={<PackageCheck className="h-4 w-4 text-indigo-600" />}
                        events={physicalEvents}
                        emptyText="No physical return events recorded."
                      />
                      <TimelineColumn
                        title="Financial Refund Timeline"
                        subtitle="Merchant approval, PayPal refund execution & Issuer bank settlement"
                        icon={<Wallet className="h-4 w-4 text-emerald-600" />}
                        events={financialEvents}
                        emptyText="No financial refund events recorded."
                      />
                    </div>
                  </div>

                  {/* Verified Facts vs AI Recommendations */}
                  <div className="rounded border border-gray-200 bg-white p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-bold text-gray-800">
                        Verified Facts vs AI Agent Recommendations
                      </h3>
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-800">
                        <Lock className="h-3 w-3" />
                        requires_approval: true enforced
                      </span>
                    </div>

                    <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
                      <div className="rounded border border-gray-200 bg-gray-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                          Verified Deterministic Facts
                        </p>
                        <ul className="mt-2 space-y-1.5 font-mono text-[11px] text-gray-800">
                          <li>Approvals recorded: {detail.approvals.length}</li>
                          <li>PayPal transactions: {detail.transactions.length}</li>
                          <li>Shipments synced: {detail.shipments.length}</li>
                          <li>Inspections: {detail.inspections.length}</li>
                          <li>Evidence files (SHA-256): {detail.evidence_items.length}</li>
                        </ul>
                      </div>

                      <div className="rounded border border-gray-200 bg-gray-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                          AI Agent Recommendations (Non-Executing)
                        </p>
                        {detail.agent_executions.length > 0 ? (
                          <div className="mt-2 space-y-2">
                            {detail.agent_executions.map((exec) => (
                              <div key={exec.id} className="rounded border border-gray-200 bg-white p-2.5">
                                <div className="flex items-center justify-between font-mono text-[11px]">
                                  <span className="font-semibold text-gray-900">{exec.agent_name}</span>
                                  <span className="text-gray-500">{exec.model_name}</span>
                                </div>
                                {exec.decisions.map((dec) => {
                                  const rec = (dec.recommendation ?? {}) as Record<string, unknown>;
                                  const merchantBrief =
                                    typeof rec.merchant_brief === 'string'
                                      ? rec.merchant_brief
                                      : typeof rec.rationale === 'string'
                                      ? rec.rationale
                                      : typeof rec.summary === 'string'
                                      ? rec.summary
                                      : null;
                                  const customerBrief =
                                    typeof rec.customer_explanation === 'string'
                                      ? rec.customer_explanation
                                      : typeof rec.customer_message === 'string'
                                      ? rec.customer_message
                                      : null;
                                  const followup =
                                    typeof rec.followup_action === 'string'
                                      ? rec.followup_action
                                      : null;

                                  return (
                                    <div key={dec.id} className="mt-1.5 border-t border-gray-100 pt-1.5 text-[11px]">
                                      <div className="flex items-center justify-between">
                                        <span className="font-mono font-semibold text-gray-800">
                                          {dec.decision_type}
                                        </span>
                                        <span className="rounded bg-amber-50 px-1.5 py-0.5 font-mono text-[10px] text-amber-900">
                                          requires_approval: {String(dec.requires_approval)}
                                        </span>
                                      </div>
                                      {merchantBrief && (
                                        <p className="mt-1.5 text-gray-700">
                                          <strong className="text-gray-900">Merchant Brief:</strong>{' '}
                                          {merchantBrief}
                                        </p>
                                      )}
                                      {customerBrief && (
                                        <p className="mt-1 text-gray-700">
                                          <strong className="text-gray-900">Customer Update:</strong>{' '}
                                          {customerBrief}
                                        </p>
                                      )}
                                      {followup && (
                                        <p className="mt-1 text-[10px] text-gray-600">
                                          <strong>Next Step:</strong> {followup}
                                        </p>
                                      )}
                                      {dec.evidence_references.length > 0 && (
                                        <p className="mt-1 font-mono text-[10px] text-gray-500">
                                          Evidence refs: {dec.evidence_references.join(', ')}
                                        </p>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-2 text-xs text-gray-500">
                            No agent executions yet. Click &quot;Re-run 3-Agent Investigation&quot; above.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Simulated Issuer / Regulatory Attached Records */}
                  {(detail.issuer_inquiries.length > 0 ||
                    detail.regulatory_evaluations.length > 0) && (
                    <div className="rounded border border-amber-200 bg-amber-50/40 p-4">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-bold text-gray-800">
                          Attached Simulator Context
                        </h3>
                        <SimulatedBadge compact />
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {detail.issuer_inquiries.map((inq) => (
                          <div key={inq.id} className="rounded border border-amber-200 bg-white p-3 font-mono text-xs">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold">Issuer {inq.institution_code ?? 'SIM'}</span>
                              <StatusPill value={inq.status} />
                            </div>
                            <p className="mt-1 text-[11px] text-gray-600">
                              Scenario: {inq.scenario ?? '—'} • ARN: {inq.arn ?? '—'}
                            </p>
                          </div>
                        ))}
                        {detail.regulatory_evaluations.map((reg) => (
                          <div key={reg.id} className="rounded border border-amber-200 bg-white p-3 font-mono text-xs">
                            <div className="flex items-center justify-between">
                              <span className="font-semibold">
                                Reg {Array.isArray(reg.jurisdiction) ? reg.jurisdiction.join('/') : reg.jurisdiction}
                              </span>
                              <StatusPill value={reg.evaluation_status} />
                            </div>
                            <p className="mt-1 text-[11px] text-gray-600">
                              Rule Version: {reg.rule_version}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>,
          document.body
        )}
    </div>
  );
}
