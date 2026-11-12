import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, Bot, CreditCard, Play, Plus, RefreshCw } from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import { SimulatedBadge } from '../components/SimulatedBadge';
import { ApiErrorBanner, CurrencyAmount, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { CardNetwork, IssuerInquiryRecord, IssuerScenario, RefundCaseSummary } from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

const ALL_ISSUER_SCENARIOS: Array<{ code: IssuerScenario; title: string; summary: string }> = [
  { code: 'NORMAL_POSTING', title: 'Normal Posting', summary: 'Standard T+2 to T+3 card settlement progression' },
  { code: 'DELAYED_POSTING', title: 'Delayed Posting', summary: 'PayPal COMPLETED, bank credit pending at T+5d' },
  { code: 'REFERENCE_MISMATCH', title: 'Reference Mismatch', summary: 'PayPal ref mismatches issuer settlement trace' },
  { code: 'MISSING_TRANSACTION_REFERENCE', title: 'Missing Tx Reference', summary: 'Untraceable without ARN / acquirer trace' },
  { code: 'DUPLICATE_CREDIT', title: 'Duplicate Credit', summary: 'Duplicate refund credit flagged for reconciliation' },
  { code: 'REPLACED_CARD', title: 'Replaced Card', summary: 'Original card closed; issuer rerouting credit' },
  { code: 'ISSUER_UNAVAILABLE', title: 'Issuer Unavailable', summary: 'Simulated 503 bank gateway outage' },
  { code: 'INSUFFICIENT_EVIDENCE', title: 'Insufficient Evidence', summary: 'Requires PayPal receipt & ARN settlement trace' },
];

export function IssuerSimulatorPage() {
  const [scenarioFilter, setScenarioFilter] = useState<IssuerScenario | ''>('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Create Inquiry form (strictly masked last-4 digits only)
  const [refundCaseId, setRefundCaseId] = useState('');
  const [paypalCaptureId, setPaypalCaptureId] = useState('CAP-SIM-1001');
  const [paypalRefundId, setPaypalRefundId] = useState('REF-SIM-1001');
  const [institutionCode, setInstitutionCode] = useState('HDFC_SIM');
  const [cardNetwork, setCardNetwork] = useState<CardNetwork>('VISA');
  const [cardLast4, setCardLast4] = useState('4242');
  const [amount, setAmount] = useState('45.00');
  const [currency, setCurrency] = useState('USD');
  const [initialScenario, setInitialScenario] = useState<IssuerScenario>('DELAYED_POSTING');
  const [createBusy, setCreateBusy] = useState(false);

  const [triggerNote, setTriggerNote] = useState('');
  const [triggerBusy, setTriggerBusy] = useState<IssuerScenario | null>(null);
  const [pipelineBusy, setPipelineBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  const fetcher = useCallback(
    () => opsApi.listIssuerInquiries({ scenario: scenarioFilter || undefined }),
    [scenarioFilter]
  );
  const casesFetcher = useCallback(() => opsApi.listCases(), []);

  const { data: inquiries, loading, error, reload } =
    useOpsFetch<IssuerInquiryRecord[]>(fetcher);
  const { data: availableCases } = useOpsFetch<RefundCaseSummary[]>(casesFetcher);

  const activeInquiry =
    inquiries?.find((i) => (i.inquiry_id || i.id) === selectedId) ?? inquiries?.[0] ?? null;

  function handleSelectCase(caseId: string) {
    setRefundCaseId(caseId);
    const chosen = (availableCases ?? []).find((c) => c.id === caseId);
    if (chosen) {
      if (chosen.paypal_capture_id) {
        setPaypalCaptureId(chosen.paypal_capture_id);
      }
      setAmount(chosen.approved_amount ?? chosen.requested_amount ?? '45.00');
      setCurrency((chosen.paypal_currency || chosen.currency || 'USD').toUpperCase());
    }
  }

  async function handleRunPipelineForCase(targetCaseId: string) {
    setPipelineBusy(true);
    setActionMsg(null);
    setActionErr(null);
    try {
      const res = await opsApi.investigateCase(targetCaseId);
      setActionMsg(
        `3-Agent AI investigation completed (${res.status}) and synced updated bank-posting explanation to Shipkart.`
      );
    } catch (err) {
      setActionErr(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Failed to run AI pipeline'
      );
    } finally {
      setPipelineBusy(false);
    }
  }

  async function handleCreateInquiry(e: React.FormEvent) {
    e.preventDefault();
    setActionMsg(null);
    setActionErr(null);
    const trimmedLast4 = cardLast4.trim();
    if (!/^\d{4}$/.test(trimmedLast4)) {
      setActionErr('card_last4 must be exactly 4 digits (never enter a full card PAN).');
      return;
    }
    if (!refundCaseId.trim()) {
      setActionErr('refund_case_id is required.');
      return;
    }

    setCreateBusy(true);
    try {
      const created = await opsApi.createIssuerInquiry({
        refund_case_id: refundCaseId.trim(),
        paypal_capture_id: paypalCaptureId.trim() || undefined,
        paypal_refund_id: paypalRefundId.trim() || undefined,
        paypal_refund_status: 'COMPLETED',
        institution_code: institutionCode.trim() || 'HDFC_SIM',
        card_network: cardNetwork,
        card_last4: trimmedLast4,
        amount: amount.trim() || undefined,
        currency: currency.trim().toUpperCase(),
        scenario: initialScenario,
      });
      const id = created.inquiry_id || created.id;
      setSelectedId(id);
      setActionMsg(`Created simulated issuer inquiry ${id} (${initialScenario}).`);
      await reload();
    } catch (err) {
      setActionErr(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Failed to create inquiry'
      );
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleTriggerScenario(scenario: IssuerScenario) {
    if (!activeInquiry) return;
    const targetId = activeInquiry.inquiry_id || activeInquiry.id;
    setTriggerBusy(scenario);
    setActionMsg(null);
    setActionErr(null);
    try {
      const updated = await opsApi.triggerIssuerScenario(targetId, {
        scenario,
        note: triggerNote.trim() || undefined,
      });
      setActionMsg(
        `Triggered ${scenario} on ${updated.inquiry_id || updated.id} → status=${updated.status}, posting=${updated.posting_status ?? '—'}.`
      );
      setTriggerNote('');
      await reload();
    } catch (err) {
      setActionErr(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Scenario trigger failed'
      );
    } finally {
      setTriggerBusy(null);
    }
  }

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-bold text-gray-800">
              Issuer / Bank Posting Simulator Console
            </h1>
            <SimulatedBadge />
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            Interactive synthetic card-rail &amp; ARN settlement console. Explicitly separates
            PayPal Refund <span className="font-semibold text-gray-800">COMPLETED</span> from
            Issuer Bank credit posting across all 8 card settlement scenarios.
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

      {/* Masked PAN & Non-Confirmation Rule Banner */}
      <div className="flex items-start gap-3 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-950">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Synthetic Card Rail Safeguards</span>
            <SimulatedBadge compact />
          </div>
          <p>
            Only masked 4-digit card suffixes (<span className="font-mono">•••• 4242</span>) and
            synthetic ARNs (<span className="font-mono">ARN-SIM-*</span>) are accepted. Never enter
            real card PANs. PayPal <span className="font-mono">COMPLETED</span> status does not
            imply <span className="font-mono">credit_posted: true</span>.
          </p>
        </div>
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {actionMsg && (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-2.5 font-mono text-xs text-emerald-900">
          {actionMsg}
        </div>
      )}
      {actionErr && (
        <div className="rounded border border-rose-200 bg-rose-50 px-4 py-2.5 font-mono text-xs text-rose-800">
          {actionErr}
        </div>
      )}

      {/* Create Simulated Inquiry Form */}
      <form
        onSubmit={(e) => void handleCreateInquiry(e)}
        className="rounded border border-gray-100 bg-white p-5 shadow-sm"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Plus className="h-4 w-4 text-shipkart-blue" />
            <h2 className="text-sm font-bold text-gray-800">
              Create Simulated Issuer Inquiry
            </h2>
          </div>
          <SimulatedBadge compact />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              Refund Case *
            </label>
            <select
              value={refundCaseId}
              onChange={(e) => handleSelectCase(e.target.value)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">Select a Refund Case…</option>
              {(availableCases ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  Order #{c.shipkart_order_id ?? '—'} • {c.status} • {c.requested_amount}{' '}
                  {c.currency} ({shortId(c.id, 6)})
                </option>
              ))}
            </select>
            <input
              type="text"
              value={refundCaseId}
              onChange={(e) => setRefundCaseId(e.target.value)}
              placeholder="Or paste Refund Case UUID"
              className="mt-1.5 w-full rounded border border-gray-200 bg-white px-2.5 py-1 font-mono text-[11px] text-gray-800 focus:border-shipkart-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              Institution Code
            </label>
            <input
              type="text"
              value={institutionCode}
              onChange={(e) => setInstitutionCode(e.target.value)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              Card Network / Masked Last4
            </label>
            <div className="mt-1 flex gap-2">
              <select
                value={cardNetwork}
                onChange={(e) => setCardNetwork(e.target.value as CardNetwork)}
                className="rounded border border-gray-200 bg-white px-2 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              >
                <option value="VISA">VISA</option>
                <option value="MASTERCARD">MASTERCARD</option>
                <option value="RUPAY">RUPAY</option>
              </select>
              <input
                type="text"
                maxLength={4}
                pattern="\d{4}"
                value={cardLast4}
                onChange={(e) => setCardLast4(e.target.value)}
                placeholder="4242"
                className="w-20 rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              Initial Scenario
            </label>
            <select
              value={initialScenario}
              onChange={(e) => setInitialScenario(e.target.value as IssuerScenario)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              {ALL_ISSUER_SCENARIOS.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              PayPal Capture ID
            </label>
            <input
              type="text"
              value={paypalCaptureId}
              onChange={(e) => setPaypalCaptureId(e.target.value)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              PayPal Refund ID
            </label>
            <input
              type="text"
              value={paypalRefundId}
              onChange={(e) => setPaypalRefundId(e.target.value)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-gray-600">
              Amount / Currency
            </label>
            <div className="mt-1 flex gap-2">
              <input
                type="text"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              />
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="rounded border border-gray-200 bg-white px-2 py-1.5 font-mono text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
              >
                <option value="USD">USD</option>
                <option value="INR">INR</option>
              </select>
            </div>
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={createBusy}
              className="w-full rounded bg-shipkart-blue px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-shipkart-blueHover disabled:opacity-50"
            >
              {createBusy ? 'Creating…' : 'Open Simulated Inquiry'}
            </button>
          </div>
        </div>
      </form>

      {/* Main Split: Inquiries List + 8-Scenario Trigger Console */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="rounded border border-gray-100 bg-white p-4 shadow-sm lg:col-span-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-bold text-gray-800">
              Issuer Inquiries ({inquiries?.length ?? 0})
            </h2>
            <select
              value={scenarioFilter}
              onChange={(e) => setScenarioFilter(e.target.value as IssuerScenario | '')}
              className="rounded border border-gray-200 bg-white px-2 py-1 font-mono text-[11px] text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">All Scenarios</option>
              {ALL_ISSUER_SCENARIOS.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-3 max-h-[540px] space-y-2 overflow-y-auto pr-1">
            {inquiries && inquiries.length > 0 ? (
              inquiries.map((inq) => {
                const key = inq.inquiry_id || inq.id;
                const isSelected = (activeInquiry?.inquiry_id || activeInquiry?.id) === key;
                return (
                  <button
                    type="button"
                    key={key}
                    onClick={() => setSelectedId(key)}
                    className={`w-full rounded border p-3 text-left transition-colors ${
                      isSelected
                        ? 'border-shipkart-blue bg-blue-50/40'
                        : 'border-gray-200 bg-white hover:border-shipkart-blue hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-semibold text-gray-900">{key}</span>
                      <div className="flex items-center gap-1.5">
                        <SimulatedBadge compact />
                        <StatusPill value={inq.status} />
                      </div>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-gray-600">
                      <span>
                        {inq.institution_code ?? 'BANK_SIM'} • {inq.card_network ?? 'CARD'} ••••{' '}
                        {inq.card_last4 ?? 'XXXX'}
                      </span>
                      {inq.amount && inq.currency && (
                        <CurrencyAmount amount={inq.amount} currency={inq.currency} />
                      )}
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-gray-500">
                      ARN: {inq.arn ?? 'UNASSIGNED'} • Credit Posted:{' '}
                      {String(Boolean(inq.credit_posted))}
                    </p>
                  </button>
                );
              })
            ) : (
              <div className="rounded border border-dashed border-gray-200 p-8 text-center text-xs text-gray-500">
                {loading ? 'Loading simulated inquiries…' : 'No issuer inquiries yet. Create one above.'}
              </div>
            )}
          </div>
        </div>

        {/* 8-Scenario Trigger Console */}
        <div className="rounded border border-gray-100 bg-white p-5 shadow-sm lg:col-span-7">
          {activeInquiry ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <CreditCard className="h-4 w-4 text-shipkart-blue" />
                    <span className="font-mono text-sm font-semibold text-gray-900">
                      {activeInquiry.inquiry_id || activeInquiry.id}
                    </span>
                    <SimulatedBadge compact />
                  </div>
                  <p className="mt-1 font-mono text-xs text-gray-600">
                    {activeInquiry.institution_code ?? 'ISSUER_SIM'} •{' '}
                    {activeInquiry.card_network ?? 'VISA'} ••••{' '}
                    {activeInquiry.card_last4 ?? '4242'} • ARN:{' '}
                    <strong>{activeInquiry.arn ?? 'NONE'}</strong>
                  </p>
                </div>

                <div className="flex flex-col items-end gap-1.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill value={activeInquiry.status} />
                    {activeInquiry.refund_case_id && (
                      <>
                        <button
                          type="button"
                          disabled={pipelineBusy}
                          onClick={() => void handleRunPipelineForCase(activeInquiry.refund_case_id)}
                          className="inline-flex items-center gap-1 rounded bg-shipkart-blue px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-shipkart-blueHover disabled:opacity-50"
                        >
                          <Bot className="h-3 w-3" />
                          {pipelineBusy ? 'Syncing AI…' : 'Re-run AI Pipeline'}
                        </button>
                        <Link
                          to={`/operations/cases?caseId=${encodeURIComponent(activeInquiry.refund_case_id)}`}
                          className="rounded border border-gray-200 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-50"
                        >
                          Inspect Case
                        </Link>
                      </>
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-gray-500">
                    Posting: {activeInquiry.posting_status ?? 'UNKNOWN'} • PayPal:{' '}
                    {activeInquiry.paypal_refund_status ?? 'COMPLETED'}
                  </span>
                </div>
              </div>

              {/* Explicit Rail Separation Readout */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded border border-gray-200 bg-gray-50 p-3">
                  <p className="text-[10px] font-semibold uppercase text-gray-500">
                    PayPal Refund Rail
                  </p>
                  <p className="mt-1 font-mono text-xs font-semibold text-gray-900">
                    {activeInquiry.paypal_refund_status ?? 'COMPLETED'}
                  </p>
                </div>
                <div className="rounded border border-gray-200 bg-gray-50 p-3">
                  <p className="text-[10px] font-semibold uppercase text-gray-500">
                    Issuer Bank Posting
                  </p>
                  <p
                    className={`mt-1 font-mono text-xs font-semibold ${
                      activeInquiry.credit_posted ? 'text-emerald-700' : 'text-amber-800'
                    }`}
                  >
                    {activeInquiry.credit_posted ? 'CREDIT_POSTED' : 'UNCONFIRMED / PENDING'}
                  </p>
                </div>
                <div className="rounded border border-gray-200 bg-gray-50 p-3">
                  <p className="text-[10px] font-semibold uppercase text-gray-500">
                    Manual Reconciliation
                  </p>
                  <p className="mt-1 font-mono text-xs font-semibold text-gray-900">
                    {activeInquiry.requires_manual_reconciliation ? 'REQUIRED' : 'NOT_REQUIRED'}
                  </p>
                </div>
              </div>

              {/* Conditional Diagnostic Details */}
              {(activeInquiry.mismatch_reason ||
                activeInquiry.duplicate_reference_id ||
                activeInquiry.rerouting_via_issuer ||
                (activeInquiry.missing_fields?.length ?? 0) > 0 ||
                (activeInquiry.required_evidence?.length ?? 0) > 0) && (
                <div className="space-y-1 rounded border border-amber-200 bg-amber-50 p-3 font-mono text-[11px] text-amber-950">
                  {activeInquiry.mismatch_reason && (
                    <p>Mismatch: {activeInquiry.mismatch_reason}</p>
                  )}
                  {activeInquiry.duplicate_reference_id && (
                    <p>Duplicate Trace Ref: {activeInquiry.duplicate_reference_id}</p>
                  )}
                  {activeInquiry.rerouting_via_issuer && (
                    <p>
                      Original Card: {activeInquiry.original_card_status} → Rerouting via issuer
                    </p>
                  )}
                  {activeInquiry.missing_fields && activeInquiry.missing_fields.length > 0 && (
                    <p>Missing Fields: {activeInquiry.missing_fields.join(', ')}</p>
                  )}
                  {activeInquiry.required_evidence && activeInquiry.required_evidence.length > 0 && (
                    <p>Required Evidence: {activeInquiry.required_evidence.join(', ')}</p>
                  )}
                </div>
              )}

              {/* Trigger All 8 Scenarios */}
              <div>
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-gray-600">
                    Simulate Any of the 8 Issuer Settlement Scenarios
                  </p>
                  <SimulatedBadge compact />
                </div>
                <input
                  type="text"
                  value={triggerNote}
                  onChange={(e) => setTriggerNote(e.target.value)}
                  placeholder="Optional note for scenario transition…"
                  className="mt-2 w-full rounded border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
                />
                <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {ALL_ISSUER_SCENARIOS.map((sc) => {
                    const isCurrent = activeInquiry.scenario === sc.code;
                    return (
                      <button
                        type="button"
                        key={sc.code}
                        disabled={triggerBusy !== null}
                        onClick={() => void handleTriggerScenario(sc.code)}
                        className={`flex items-start justify-between gap-2 rounded border p-2.5 text-left transition-colors disabled:opacity-50 ${
                          isCurrent
                            ? 'border-amber-400 bg-amber-50'
                            : 'border-gray-200 bg-white hover:border-shipkart-blue'
                        }`}
                      >
                        <div>
                          <p className="font-mono text-[11px] font-semibold text-gray-900">
                            {sc.code}
                          </p>
                          <p className="mt-0.5 text-[11px] text-gray-500">{sc.summary}</p>
                        </div>
                        <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-500" />
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* ARN & Posting Timeline */}
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-gray-600">
                  Simulated Issuer &amp; ARN Event Timeline
                </p>
                <div className="mt-2 space-y-2">
                  {activeInquiry.events && activeInquiry.events.length > 0 ? (
                    activeInquiry.events.map((ev) => (
                      <div
                        key={ev.event_id}
                        className="rounded border border-gray-200 bg-gray-50 p-2.5 text-xs"
                      >
                        <div className="flex items-center justify-between font-mono text-[11px]">
                          <span className="font-semibold text-gray-900">
                            {ev.status} ({ev.posting_status})
                          </span>
                          <span className="text-gray-500">{formatTimestamp(ev.occurred_at)}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-gray-700">{ev.description}</p>
                      </div>
                    ))
                  ) : (
                    <pre className="max-h-48 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] text-gray-800">
                      {JSON.stringify(activeInquiry.response_data, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="py-16 text-center text-xs text-gray-500">
              Select or create a simulated Issuer Inquiry to trigger all 8 bank posting scenarios.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
