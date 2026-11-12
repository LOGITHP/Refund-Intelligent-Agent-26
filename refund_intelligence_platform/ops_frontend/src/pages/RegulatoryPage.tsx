import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, HelpCircle, Play, RefreshCw, Scale } from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import { RegulatoryDisclaimerBanner, SimulatedBadge } from '../components/SimulatedBadge';
import { ApiErrorBanner, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type {
  RefundCaseSummary,
  RegulatoryEvaluatePayload,
  RegulatoryEvaluationRecord,
  RegulatoryRule,
} from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

export function RegulatoryPage() {
  const [jurisdictionFilter, setJurisdictionFilter] = useState('');
  const [txId, setTxId] = useState('TX-SIM-2026-001');
  const [refundCaseId, setRefundCaseId] = useState('');
  const [merchantCountry, setMerchantCountry] = useState('IN');
  const [customerCountry, setCustomerCountry] = useState('US');
  const [paymentRoute, setPaymentRoute] = useState<'DOMESTIC' | 'CROSS_BORDER' | ''>('CROSS_BORDER');
  const [entityType, setEntityType] = useState<'BUSINESS' | 'MARKETPLACE' | 'ENTERPRISE' | 'INDIVIDUAL' | ''>('MARKETPLACE');
  const [txCurrency, setTxCurrency] = useState('INR');
  const [settlementCurrency, setSettlementCurrency] = useState('USD');
  const [settlementConfirmed, setSettlementConfirmed] = useState(true);
  const [businessActivity, setBusinessActivity] = useState('E-Commerce Electronics Marketplace');
  const [delayHours, setDelayHours] = useState('130');

  const [evalBusy, setEvalBusy] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [latestResult, setLatestResult] = useState<RegulatoryEvaluationRecord | null>(null);

  const evalsFetcher = useCallback(
    () =>
      opsApi.listRegulatoryEvaluations({
        jurisdiction: jurisdictionFilter || undefined,
      }),
    [jurisdictionFilter]
  );

  const rulesFetcher = useCallback(
    () =>
      opsApi.listRegulatoryRules({
        jurisdiction: jurisdictionFilter || undefined,
      }),
    [jurisdictionFilter]
  );

  const casesFetcher = useCallback(() => opsApi.listCases(), []);
  const { data: availableCases } = useOpsFetch<RefundCaseSummary[]>(casesFetcher);

  const {
    data: evaluations,
    loading: evalsLoading,
    error: evalsError,
    reload: reloadEvals,
  } = useOpsFetch<RegulatoryEvaluationRecord[]>(evalsFetcher);

  const { data: rules, loading: rulesLoading, reload: reloadRules } =
    useOpsFetch<RegulatoryRule[]>(rulesFetcher);

  function applyPreset(preset: 'IN_CROSS_BORDER' | 'IN_DOMESTIC' | 'US_DOMESTIC' | 'INCOMPLETE') {
    if (preset === 'IN_CROSS_BORDER') {
      setMerchantCountry('IN');
      setCustomerCountry('US');
      setPaymentRoute('CROSS_BORDER');
      setEntityType('MARKETPLACE');
      setTxCurrency('INR');
      setSettlementCurrency('USD');
      setSettlementConfirmed(true);
      setBusinessActivity('Cross-Border Retail');
      setDelayHours('130');
    } else if (preset === 'IN_DOMESTIC') {
      setMerchantCountry('IN');
      setCustomerCountry('IN');
      setPaymentRoute('DOMESTIC');
      setEntityType('BUSINESS');
      setTxCurrency('INR');
      setSettlementCurrency('INR');
      setSettlementConfirmed(true);
      setBusinessActivity('Consumer Apparel');
      setDelayHours('48');
    } else if (preset === 'US_DOMESTIC') {
      setMerchantCountry('US');
      setCustomerCountry('US');
      setPaymentRoute('DOMESTIC');
      setEntityType('BUSINESS');
      setTxCurrency('USD');
      setSettlementCurrency('USD');
      setSettlementConfirmed(true);
      setBusinessActivity('Online Marketplace');
      setDelayHours('180');
    } else {
      setMerchantCountry('');
      setCustomerCountry('IN');
      setPaymentRoute('');
      setEntityType('');
      setTxCurrency('INR');
      setSettlementCurrency('USD');
      setSettlementConfirmed(false);
      setBusinessActivity('');
      setDelayHours('24');
    }
  }

  async function handleEvaluate(e: React.FormEvent) {
    e.preventDefault();
    setEvalBusy(true);
    setEvalError(null);
    const payload: RegulatoryEvaluatePayload = {
      transaction_id: txId.trim() || `TX-SIM-${Date.now()}`,
      refund_case_id: refundCaseId.trim() || undefined,
      merchant_country: merchantCountry.trim().toUpperCase() || undefined,
      customer_country: customerCountry.trim().toUpperCase() || undefined,
      payment_provider: 'PAYPAL',
      transaction_currency: txCurrency.trim().toUpperCase() || undefined,
      settlement_currency: settlementCurrency.trim().toUpperCase() || undefined,
      payment_route: paymentRoute || undefined,
      merchant_entity_type: entityType || undefined,
      transaction_type: 'REFUND',
      settlement_entity_confirmed: settlementConfirmed,
      business_activity: businessActivity.trim() || undefined,
      refund_delay_hours: delayHours ? Number(delayHours) : undefined,
    };

    try {
      const result = await opsApi.evaluateRegulatory(payload);
      setLatestResult(result);
      await reloadEvals();
    } catch (err) {
      setEvalError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Regulatory evaluation failed'
      );
    } finally {
      setEvalBusy(false);
    }
  }

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold text-gray-800">
              India &amp; USA Regulatory Rules Simulator
            </h1>
            <SimulatedBadge />
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            Interactive evaluation of India (RBI FEMA / E-Commerce CPA 2020) and USA (CFPB Reg-E /
            FTC Mail-Order) simulated refund obligations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={jurisdictionFilter}
            onChange={(e) => setJurisdictionFilter(e.target.value)}
            className="rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
          >
            <option value="">All Jurisdictions (IN + US)</option>
            <option value="IN">IN (India)</option>
            <option value="US">US (United States)</option>
          </select>
          <button
            type="button"
            onClick={() => {
              void reloadEvals();
              void reloadRules();
            }}
            className="inline-flex items-center gap-1.5 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${evalsLoading || rulesLoading ? 'animate-spin' : ''}`}
            />
            Refresh
          </button>
        </div>
      </div>

      <RegulatoryDisclaimerBanner />

      <div className="grid grid-cols-1 gap-2 rounded border border-gray-100 bg-white px-4 py-3 text-[11px] text-gray-600 shadow-sm sm:grid-cols-3">
        <div>
          <strong className="font-mono text-emerald-800">APPLICABLE:</strong> All country, route,
          and merchant entity facts are confirmed and rules match directly.
        </div>
        <div>
          <strong className="font-mono text-amber-800">POTENTIALLY_APPLICABLE:</strong> Partial
          match — optional context (e.g., business activity) is still unconfirmed.
        </div>
        <div>
          <strong className="font-mono text-gray-800">UNKNOWN:</strong> Required jurisdiction or
          payment-route fields are missing; no assumption is made.
        </div>
      </div>

      {evalsError && (
        <ApiErrorBanner
          message={evalsError.message}
          status={evalsError.status}
          onRetry={() => void reloadEvals()}
        />
      )}

      {/* Interactive Tester + Result */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <form
          onSubmit={(e) => void handleEvaluate(e)}
          className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-shipkart-blue" />
              <h2 className="text-sm font-bold text-gray-800">
                Interactive Regulatory Evaluation Tester
              </h2>
            </div>
            <SimulatedBadge compact />
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => applyPreset('IN_CROSS_BORDER')}
              className="rounded border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-[10px] font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-100"
            >
              Preset: IN Cross-Border
            </button>
            <button
              type="button"
              onClick={() => applyPreset('IN_DOMESTIC')}
              className="rounded border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-[10px] font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-100"
            >
              Preset: IN Domestic
            </button>
            <button
              type="button"
              onClick={() => applyPreset('US_DOMESTIC')}
              className="rounded border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-[10px] font-medium text-gray-700 hover:border-shipkart-blue hover:bg-gray-100"
            >
              Preset: US Reg-E / FTC
            </button>
            <button
              type="button"
              onClick={() => applyPreset('INCOMPLETE')}
              className="rounded border border-amber-200 bg-amber-50 px-2 py-1 font-mono text-[10px] font-medium text-amber-900 hover:bg-amber-100"
            >
              Preset: Incomplete (UNKNOWN)
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Transaction ID *
              </label>
              <input
                type="text"
                required
                value={txId}
                onChange={(e) => setTxId(e.target.value)}
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Link to Refund Case (optional)
              </label>
              <select
                value={refundCaseId}
                onChange={(e) => {
                  const chosenId = e.target.value;
                  setRefundCaseId(chosenId);
                  const chosen = (availableCases ?? []).find((c) => c.id === chosenId);
                  if (chosen) {
                    setTxCurrency(chosen.original_currency || chosen.currency || txCurrency);
                    setSettlementCurrency(chosen.paypal_currency || chosen.currency || settlementCurrency);
                  }
                }}
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              >
                <option value="">None / Standalone Simulation</option>
                {(availableCases ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    Order #{c.shipkart_order_id ?? '—'} • {c.status} ({shortId(c.id, 6)})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Merchant Country (ISO-2)
              </label>
              <input
                type="text"
                maxLength={2}
                value={merchantCountry}
                onChange={(e) => setMerchantCountry(e.target.value)}
                placeholder="IN or US (leave blank for UNKNOWN)"
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Customer Country (ISO-2)
              </label>
              <input
                type="text"
                maxLength={2}
                value={customerCountry}
                onChange={(e) => setCustomerCountry(e.target.value)}
                placeholder="IN or US"
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Payment Route
              </label>
              <select
                value={paymentRoute}
                onChange={(e) =>
                  setPaymentRoute(e.target.value as 'DOMESTIC' | 'CROSS_BORDER' | '')
                }
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              >
                <option value="">(Missing / Unconfirmed)</option>
                <option value="DOMESTIC">DOMESTIC</option>
                <option value="CROSS_BORDER">CROSS_BORDER</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Merchant Entity Type
              </label>
              <select
                value={entityType}
                onChange={(e) =>
                  setEntityType(
                    e.target.value as
                      | 'BUSINESS'
                      | 'MARKETPLACE'
                      | 'ENTERPRISE'
                      | 'INDIVIDUAL'
                      | ''
                  )
                }
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              >
                <option value="">(Missing)</option>
                <option value="BUSINESS">BUSINESS</option>
                <option value="MARKETPLACE">MARKETPLACE</option>
                <option value="ENTERPRISE">ENTERPRISE</option>
                <option value="INDIVIDUAL">INDIVIDUAL</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Transaction / Settlement Currency
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  type="text"
                  value={txCurrency}
                  onChange={(e) => setTxCurrency(e.target.value)}
                  placeholder="INR"
                  className="w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
                />
                <input
                  type="text"
                  value={settlementCurrency}
                  onChange={(e) => setSettlementCurrency(e.target.value)}
                  placeholder="USD"
                  className="w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-gray-600">
                Refund Delay Hours
              </label>
              <input
                type="number"
                min={0}
                value={delayHours}
                onChange={(e) => setDelayHours(e.target.value)}
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-[11px] font-semibold text-gray-600">
                Business Activity
              </label>
              <input
                type="text"
                value={businessActivity}
                onChange={(e) => setBusinessActivity(e.target.value)}
                placeholder="Leave blank to trigger POTENTIALLY_APPLICABLE"
                className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
            <div className="sm:col-span-2 flex items-center justify-between pt-1">
              <label className="inline-flex items-center gap-2 text-xs text-gray-700">
                <input
                  type="checkbox"
                  checked={settlementConfirmed}
                  onChange={(e) => setSettlementConfirmed(e.target.checked)}
                  className="rounded border-gray-300 text-shipkart-blue focus:ring-shipkart-blue"
                />
                <span>Settlement legal entity confirmed</span>
              </label>
              <button
                type="submit"
                disabled={evalBusy}
                className="inline-flex items-center gap-1.5 rounded bg-shipkart-blue px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-shipkart-blueHover disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" />
                {evalBusy ? 'Evaluating…' : 'Evaluate Rules'}
              </button>
            </div>
          </div>

          {evalError && (
            <div className="mt-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-800">
              {evalError}
            </div>
          )}
        </form>

        {/* Evaluation Output Inspector */}
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-800">Evaluation Output</h2>
            <SimulatedBadge compact />
          </div>

          {latestResult ? (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-gray-200 bg-gray-50 p-3">
                <div>
                  <p className="font-mono text-xs font-semibold text-gray-900">
                    Jurisdiction:{' '}
                    {Array.isArray(latestResult.jurisdiction)
                      ? latestResult.jurisdiction.join(', ') || 'NONE'
                      : latestResult.jurisdiction}
                  </p>
                  <p className="font-mono text-[10px] text-gray-500">
                    Evaluated {formatTimestamp(latestResult.evaluated_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill value={latestResult.status || latestResult.evaluation_status} />
                  {latestResult.refund_case_id && (
                    <Link
                      to={`/operations/cases?caseId=${encodeURIComponent(latestResult.refund_case_id)}`}
                      className="rounded border border-gray-200 bg-white px-2 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-50"
                    >
                      Inspect Case
                    </Link>
                  )}
                </div>
              </div>

              {latestResult.unresolved_questions.length > 0 && (
                <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
                  <div className="flex items-center gap-1.5 font-semibold">
                    <HelpCircle className="h-4 w-4 text-amber-700" />
                    <span>Unresolved Questions (No Assumption Made)</span>
                  </div>
                  <ul className="mt-1.5 list-disc space-y-1 pl-5 font-mono text-[11px]">
                    {latestResult.unresolved_questions.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Matched Rules ({latestResult.matched_rules.length})
                </p>
                <div className="mt-2 space-y-2">
                  {latestResult.matched_rules.length > 0 ? (
                    latestResult.matched_rules.map((mr, i) => (
                      <div
                        key={`${mr.rule_id}-${i}`}
                        className="rounded border border-gray-200 bg-gray-50 p-2.5 font-mono text-xs"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-gray-900">{mr.rule_id}</span>
                          {mr.max_refund_sla_hours && (
                            <span className="text-[11px] text-gray-600">
                              Max SLA: {mr.max_refund_sla_hours}h
                            </span>
                          )}
                        </div>
                        {mr.title && <p className="mt-0.5 font-sans text-xs text-gray-700">{mr.title}</p>}
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-gray-500">No matched rules for this context.</p>
                  )}
                </div>
              </div>

              {latestResult.obligations && latestResult.obligations.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                    Obligations
                  </p>
                  <ul className="mt-1.5 space-y-1.5 text-xs text-gray-700">
                    {latestResult.obligations.map((ob) => (
                      <li
                        key={ob.rule_id}
                        className="rounded border border-gray-200 bg-white px-3 py-2"
                      >
                        <span className="font-mono font-semibold text-gray-900">{ob.rule_id}: </span>
                        {ob.obligation}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="py-16 text-center text-xs text-gray-500">
              Submit the evaluation form on the left to inspect IN / US simulated regulatory rules.
            </div>
          )}
        </div>
      </div>

      {/* Versioned Rules Catalog */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-shipkart-blue" />
            <h2 className="text-sm font-bold text-gray-800">
              Versioned Regulatory Rules Catalog ({rules?.length ?? 0})
            </h2>
          </div>
          <SimulatedBadge compact />
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="py-2 pr-3">Rule ID / Version</th>
                <th className="py-2 pr-3">Jurisdiction</th>
                <th className="py-2 pr-3">Title &amp; Authority</th>
                <th className="py-2 pr-3">Routes / Entities</th>
                <th className="py-2">SLA</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rules && rules.length > 0 ? (
                rules.map((r) => (
                  <tr key={r.rule_id} className="hover:bg-gray-50">
                    <td className="py-3 pr-3 font-mono">
                      <div className="font-semibold text-gray-900">{r.rule_id}</div>
                      <div className="text-[10px] text-gray-500">
                        v{r.version} • eff. {r.effective_date}
                      </div>
                    </td>
                    <td className="py-3 pr-3">
                      <StatusPill value={r.jurisdiction} />
                    </td>
                    <td className="py-3 pr-3">
                      <p className="font-medium text-gray-900">{r.title}</p>
                      <p className="text-[11px] text-gray-500">{r.authority}</p>
                      <p className="mt-1 text-[11px] text-gray-700">{r.obligation_summary}</p>
                    </td>
                    <td className="py-3 pr-3 font-mono text-[11px] text-gray-600">
                      <div>{r.payment_routes.join(', ')}</div>
                      <div className="text-[10px] text-gray-500">{r.entity_types.join(', ')}</div>
                    </td>
                    <td className="py-3 font-mono font-semibold text-gray-900">
                      {r.max_refund_sla_hours}h
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-xs text-gray-500">
                    {rulesLoading ? 'Loading regulatory rules…' : 'No regulatory rules found.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Historical Stored Evaluations */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-800">
            Stored Regulatory Evaluations ({evaluations?.length ?? 0})
          </h2>
          <SimulatedBadge compact />
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] uppercase tracking-wider text-gray-500">
                <th className="py-2 pr-3">Evaluation</th>
                <th className="py-2 pr-3">Jurisdiction</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Rule Version</th>
                <th className="py-2 pr-3">Unresolved Questions</th>
                <th className="py-2">Evaluated At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {evaluations && evaluations.length > 0 ? (
                evaluations.map((ev) => (
                  <tr key={ev.id} className="hover:bg-gray-50">
                    <td className="py-2.5 pr-3 font-mono text-[11px] text-gray-900">
                      {ev.evaluation_id || ev.id}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {Array.isArray(ev.jurisdiction) ? ev.jurisdiction.join(', ') : ev.jurisdiction}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusPill value={ev.evaluation_status || ev.status} />
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-[11px]">{ev.rule_version}</td>
                    <td className="py-2.5 pr-3 text-[11px] text-gray-600">
                      {ev.unresolved_questions.length > 0
                        ? ev.unresolved_questions.join(' | ')
                        : 'None'}
                    </td>
                    <td className="py-2.5 font-mono text-[11px] text-gray-500">
                      {formatTimestamp(ev.evaluated_at)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-gray-500">
                    {evalsLoading ? 'Loading evaluations…' : 'No stored regulatory evaluations yet.'}
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
