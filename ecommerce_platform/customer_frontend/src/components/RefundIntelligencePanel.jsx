import React, { useEffect, useState, useCallback } from 'react';
import {
  Sparkles,
  Clock,
  ShieldCheck,
  AlertTriangle,
  MessageSquare,
  Send,
  Upload,
  Scale,
  RefreshCw,
  CheckCircle2,
  Truck,
  Landmark,
  FileCheck2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { agentCustomerApi } from '../services/api';

const QUICK_PROMPTS = [
  "Why hasn't my bank credited yet?",
  'What is my refund ETA?',
  'What evidence is verified?',
];

function formatTs(value) {
  if (!value) return 'N/A';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

export default function RefundIntelligencePanel({ shipkartReturn, defaultOpen = false }) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState('');
  const [intel, setIntel] = useState(null);
  const [notIndexed, setNotIndexed] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  const [investigating, setInvestigating] = useState(false);
  const [timelineTab, setTimelineTab] = useState('both');

  // Chat state
  const [question, setQuestion] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);

  // Evidence upload state
  const [uploading, setUploading] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState('');

  // Appeal state
  const [showAppeal, setShowAppeal] = useState(false);
  const [appealReason, setAppealReason] = useState('');
  const [appealSubmitting, setAppealSubmitting] = useState(false);
  const [appealNotice, setAppealNotice] = useState('');

  const loadIntelligence = useCallback(async () => {
    if (!shipkartReturn?.id) return;
    setLoading(true);
    setError('');
    setOffline(false);
    setNotIndexed(false);

    try {
      const listData = await agentCustomerApi.findRefundByReturnId(shipkartReturn.id);
      const match = listData?.items?.[0];
      if (!match?.id) {
        setIntel(null);
        setNotIndexed(true);
        return;
      }
      const dossier = await agentCustomerApi.getIntelligence(match.id);
      setIntel(dossier);
    } catch (err) {
      if (err.isOffline) {
        setOffline(true);
      } else {
        setError(err.message || 'Unable to load Refund Intelligence');
      }
    } finally {
      setLoading(false);
    }
  }, [
    shipkartReturn?.id,
    shipkartReturn?.status,
    shipkartReturn?.agent_reasoning,
    shipkartReturn?.agent_risk_score,
  ]);

  useEffect(() => {
    if (expanded) {
      loadIntelligence();
    }
  }, [expanded, loadIntelligence]);

  useEffect(() => {
    if (!expanded || !notIndexed || retryCount >= 2) return undefined;
    const delayMs = retryCount === 0 ? 1500 : 3000;
    const timer = setTimeout(() => {
      setRetryCount((prev) => prev + 1);
      loadIntelligence();
    }, delayMs);
    return () => clearTimeout(timer);
  }, [expanded, notIndexed, retryCount, loadIntelligence]);

  const handleRunReview = async () => {
    if (!intel?.refund_case?.id) return;
    setInvestigating(true);
    setError('');
    try {
      await agentCustomerApi.runInvestigation(
        intel.refund_case.id,
        shipkartReturn?.comments || shipkartReturn?.reason || null
      );
      await loadIntelligence();
    } catch (err) {
      setError(err.message || 'AI review failed');
    } finally {
      setInvestigating(false);
    }
  };

  const handleAskQuestion = async (qText) => {
    const clean = (qText ?? question).trim();
    if (!clean || !intel?.refund_case?.id) return;
    setChatLoading(true);
    setError('');
    setQuestion('');
    setChatMessages((prev) => [...prev, { role: 'user', text: clean }]);
    try {
      const res = await agentCustomerApi.askChat(intel.refund_case.id, clean);
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: res.answer,
          eta_status: res.eta_status,
          delay_owner: res.delay_owner,
          model_used: res.model_used,
          evidence_references: res.evidence_references || [],
        },
      ]);
      await loadIntelligence();
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: err.message || 'Assistant is currently unavailable.',
          isError: true,
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleUploadEvidence = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !intel?.return_case?.id) return;
    setUploading(true);
    setUploadFeedback('');
    setError('');
    try {
      const uploaded = await agentCustomerApi.uploadVerifiedEvidence(
        intel.return_case.id,
        file,
        intel.refund_case?.id || null
      );
      setUploadFeedback(
        `Verified ${uploaded.file_name} (${uploaded.mime_type}) — SHA-256: ${String(
          uploaded.sha256_hash || ''
        ).slice(0, 16)}...`
      );
      await loadIntelligence();
    } catch (err) {
      setError(err.message || 'Evidence verification failed (allowed: PNG, JPEG, PDF up to 10 MB)');
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleAppealSubmit = async (e) => {
    e.preventDefault();
    if (!intel?.refund_case?.id) return;
    const cleanReason = appealReason.trim();
    if (cleanReason.length < 3) {
      setError('Please enter at least 3 characters explaining your appeal.');
      return;
    }
    setAppealSubmitting(true);
    setAppealNotice('');
    setError('');
    try {
      await agentCustomerApi.submitAppeal(
        intel.refund_case.id,
        cleanReason,
        (intel.evidence_items || []).map((ev) => ev.evidence_id).filter(Boolean)
      );
      setAppealNotice('Appeal submitted and routed for human review.');
      setAppealReason('');
      setShowAppeal(false);
      await loadIntelligence();
    } catch (err) {
      setError(err.message || 'Failed submitting appeal');
    } finally {
      setAppealSubmitting(false);
    }
  };

  const refundCase = intel?.refund_case;
  const eta = intel?.eta;
  const delaySummary = intel?.delay_summary;
  const issuerStatus = intel?.issuer_status;
  const timeline = intel?.timeline;
  const evidenceItems = intel?.evidence_items || [];
  const shipments = intel?.shipments || [];
  const latestSummary = intel?.latest_agent_summary;

  const isPaypalDisbursed =
    ['PAYPAL_COMPLETED', 'REFUND_COMPLETED', 'ISSUER_FOLLOWUP_ACTIVE', 'CONFIRMED_POSTED'].includes(
      refundCase?.status
    ) || shipkartReturn?.status === 'REFUNDED';
  const bankUnconfirmed = isPaypalDisbursed && !issuerStatus?.credit_posted;

  return (
    <div className="border border-blue-100 rounded-sm bg-gradient-to-br from-slate-50 via-white to-blue-50/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-blue-50/40 transition"
      >
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-4 h-4 text-fk-blue flex-shrink-0" />
          <div>
            <p className="text-xs font-bold text-fk-dark">
              Refund Intelligence, ETA &amp; AI Support Assistant
            </p>
            <p className="text-[11px] text-gray-500">
              Live dual timelines (Physical Return vs. Financial Refund), verified evidence, and Q&amp;A
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-bold text-fk-blue">
          <span>{expanded ? 'Hide Intelligence' : 'Inspect Refund Intelligence'}</span>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {!expanded && (shipkartReturn?.agent_reasoning || latestSummary?.customer_message) && (
        <div className="border-t border-blue-100 bg-blue-50/50 px-4 py-2 text-[11px] text-blue-950 flex items-center justify-between gap-3">
          <span className="truncate">
            <strong>AI Review Update:</strong>{' '}
            {latestSummary?.customer_message || shipkartReturn?.agent_reasoning}
          </span>
          {shipkartReturn?.agent_risk_score != null && (
            <span className="text-[10px] font-bold bg-white border border-blue-200 px-2 py-0.5 rounded flex-shrink-0">
              Confidence {Math.round(Number(shipkartReturn.agent_risk_score) * 100)}%
            </span>
          )}
        </div>
      )}

      {expanded && (
        <div className="border-t border-blue-100 p-4 space-y-4 apple-panel-enter">
          {offline ? (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 flex items-center justify-between gap-3">
              <span>
                Refund Intelligence service is currently unreachable. Your Shipkart return progress above remains active.
              </span>
              <button
                type="button"
                onClick={loadIntelligence}
                className="text-xs font-bold text-fk-blue hover:underline flex-shrink-0"
              >
                Retry
              </button>
            </div>
          ) : loading && !intel ? (
            <div className="text-xs text-gray-500 py-4 text-center">
              Loading verified refund intelligence dossier...
            </div>
          ) : notIndexed ? (
            <div className="bg-gray-50 border border-gray-200 rounded p-3 text-xs text-gray-600 flex items-center justify-between gap-3">
              <span>
                This return request has not yet synced to the Refund Intelligence Assistant.
              </span>
              <button
                type="button"
                onClick={loadIntelligence}
                className="text-xs font-bold text-fk-blue hover:underline flex items-center gap-1"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Check Again
              </button>
            </div>
          ) : intel && refundCase ? (
            <>
              {/* Header Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-gray-200">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    key={refundCase.status}
                    className="apple-badge-pop text-[11px] font-bold px-2.5 py-0.5 rounded bg-blue-100 text-fk-blue"
                  >
                    Case Status: {refundCase.status}
                  </span>
                  <span className="text-[11px] font-mono text-gray-500">
                    ID: {String(refundCase.id).slice(0, 8)}...
                  </span>
                  {refundCase.captured_amount != null && (
                    <span className="text-[11px] text-gray-600">
                      Requested: {refundCase.requested_amount} {refundCase.currency}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleRunReview}
                    disabled={investigating}
                    className="inline-flex items-center gap-1.5 text-xs font-bold bg-fk-blue hover:bg-blue-700 disabled:opacity-60 text-white px-3 py-1.5 rounded-sm transition"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${investigating ? 'animate-spin' : ''}`} />
                    {investigating ? 'Analyzing Pipeline...' : 'Refresh AI Review'}
                  </button>
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2.5 rounded">
                  {error}
                </div>
              )}

              {appealNotice && (
                <div className="bg-green-50 border border-green-200 text-green-800 text-xs p-2.5 rounded flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                  <span>{appealNotice}</span>
                </div>
              )}

              {/* Bank Discrepancy Notice (DELAY-006 / Truthfulness Guardrail) */}
              {bankUnconfirmed && (
                <div
                  role="status"
                  className="bg-amber-50 border border-amber-300 rounded p-3 flex items-start gap-2.5 text-xs text-amber-950"
                >
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold">
                      PayPal refund completed — bank/card credit posting is still unconfirmed
                    </p>
                    <p className="text-[11px] text-amber-900 mt-0.5">
                      PayPal disbursement completed, while issuing bank settlement posting shows status{' '}
                      <strong>{issuerStatus?.status || 'UNCONFIRMED'}</strong>. PayPal completion is not a confirmed bank credit posting date.
                    </p>
                  </div>
                </div>
              )}

              {/* 3-Column Overview Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                {/* 1. Payment vs Bank Posting Split */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-gray-600 uppercase text-[10px] flex items-center gap-1">
                      <Landmark className="w-3.5 h-3.5 text-fk-blue" /> PayPal vs. Bank Status
                    </span>
                    {issuerStatus?.is_simulated && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                        SIMULATED BANK
                      </span>
                    )}
                  </div>
                  <div className="space-y-1 text-[11px]">
                    <p>
                      <span className="text-gray-500">PayPal Gateway:</span>{' '}
                      <strong className="text-fk-dark">{refundCase.status}</strong>
                    </p>
                    <p>
                      <span className="text-gray-500">Issuer / Bank Posting:</span>{' '}
                      <strong className={issuerStatus?.credit_posted ? 'text-fk-green' : 'text-amber-700'}>
                        {issuerStatus?.credit_posted ? 'CREDIT_POSTED' : issuerStatus?.status || 'UNCONFIRMED'}
                      </strong>
                    </p>
                    {refundCase.paypal_capture_id && (
                      <p className="text-[10px] text-gray-500 font-mono break-all">
                        Capture: {refundCase.paypal_capture_id}
                      </p>
                    )}
                  </div>
                </div>

                {/* 2. Deterministic ETA Window */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-gray-600 uppercase text-[10px] flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-fk-blue" /> Estimated Refund Window
                    </span>
                    <span
                      className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        eta?.eta_status === 'ESTIMATED'
                          ? 'bg-green-100 text-fk-green'
                          : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {eta?.eta_status || 'UNKNOWN'}
                    </span>
                  </div>
                  {eta?.eta_status === 'ESTIMATED' && eta?.earliest_at && eta?.latest_at ? (
                    <div className="text-[11px] space-y-0.5">
                      <p className="font-semibold text-fk-dark">
                        {formatTs(eta.earliest_at)} — {formatTs(eta.latest_at)}
                      </p>
                      <p className="text-gray-500">Confidence: {eta.confidence_level}</p>
                    </div>
                  ) : (
                    <p className="text-[11px] text-gray-600 leading-relaxed">
                      {eta?.explanation || 'Waiting for verified inspection or gateway milestones before computing ETA.'}
                    </p>
                  )}
                  <p className="text-[10px] italic text-gray-400 border-t pt-1">
                    {eta?.disclaimer || 'This is an estimate, not a guaranteed credit date.'}
                  </p>
                </div>

                {/* 3. Delay Owner & SLA Attribution */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-gray-600 uppercase text-[10px] flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Bottleneck / Delay Owner
                    </span>
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-800">
                      {delaySummary?.delay_owner || 'NONE'}
                    </span>
                  </div>
                  {delaySummary?.has_delays && delaySummary?.delays?.length > 0 ? (
                    <ul className="space-y-1 text-[11px] text-amber-900">
                      {delaySummary.delays.map((d, i) => (
                        <li key={i}>
                          <strong>{d.rule_code}:</strong> {d.description}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-[11px] text-gray-600">
                      No active SLA bottlenecks detected across carrier, merchant, PayPal, or issuer stages.
                    </p>
                  )}
                </div>
              </div>

              {/* Latest Agent Summary */}
              {latestSummary?.customer_message && (
                <div className="bg-blue-50/70 border border-blue-200 rounded p-3 text-xs text-blue-950 space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-fk-blue" />
                      AI Case Assessment ({latestSummary.decision_type})
                    </span>
                    <span className="text-[10px] font-semibold bg-white border border-blue-200 px-2 py-0.5 rounded">
                      Human Merchant Approval Required
                    </span>
                  </div>
                  <p className="text-[11px] leading-relaxed font-medium">
                    {latestSummary.customer_message}
                  </p>
                  {latestSummary.rationale &&
                    latestSummary.rationale !== latestSummary.customer_message && (
                      <p className="text-[11px] text-blue-900/90 leading-relaxed">
                        <strong>Reason:</strong> {latestSummary.rationale}
                      </p>
                    )}
                  {latestSummary.followup_action && (
                    <p className="text-[11px] text-blue-900">
                      <strong>Next Step:</strong> {latestSummary.followup_action}
                    </p>
                  )}
                </div>
              )}

              {/* Shipments (with SIMULATED tag if simulated) */}
              {shipments.length > 0 && (
                <div className="bg-white border border-gray-200 rounded p-3 text-xs space-y-1.5">
                  <p className="font-bold text-gray-600 uppercase text-[10px] flex items-center gap-1.5">
                    <Truck className="w-3.5 h-3.5 text-fk-blue" /> Reverse Pickup Shipment
                  </p>
                  {shipments.map((s) => (
                    <div key={s.id} className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <span>
                        <strong>{s.carrier_name}</strong> ({s.tracking_number}) — Stage:{' '}
                        <strong>{s.status}</strong>
                      </span>
                      {s.is_simulated && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                          SIMULATED CARRIER
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Dual Timelines: Physical Return vs Financial Refund */}
              <div className="bg-white border border-gray-200 rounded p-3 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] font-bold text-gray-600 uppercase">
                    Separated Dual Refund Timelines ({timeline?.total_events || 0} events)
                  </p>
                  <div className="flex gap-1 text-[11px]">
                    {['both', 'physical', 'financial'].map((tab) => (
                      <button
                        key={tab}
                        type="button"
                        onClick={() => setTimelineTab(tab)}
                        className={`px-2 py-0.5 rounded font-semibold capitalize ${
                          timelineTab === tab
                            ? 'bg-fk-blue text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>
                </div>

                <div
                  className={`grid grid-cols-1 ${
                    timelineTab === 'both' ? 'md:grid-cols-2' : ''
                  } gap-3 text-[11px]`}
                >
                  {(timelineTab === 'both' || timelineTab === 'physical') && (
                    <div className="border border-gray-100 bg-gray-50/70 rounded p-2.5 space-y-2">
                      <p className="font-bold text-gray-700">Physical Return Track</p>
                      {(timeline?.physical_return_events || []).length === 0 ? (
                        <p className="text-gray-400 italic">No physical return logistics events recorded yet.</p>
                      ) : (
                        <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
                          {timeline.physical_return_events.map((ev) => (
                            <li key={ev.id} className="border-l-2 border-indigo-400 pl-2">
                              <p className="font-semibold text-gray-800">
                                {ev.event_type}{' '}
                                <span className="text-[10px] font-normal text-gray-500">
                                  ({ev.source_type})
                                </span>
                              </p>
                              <p className="text-gray-600">{ev.description}</p>
                              <p className="text-[10px] text-gray-400">
                                Occurred: {formatTs(ev.occurred_at)} · Recorded: {formatTs(ev.recorded_at)}
                              </p>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  {(timelineTab === 'both' || timelineTab === 'financial') && (
                    <div className="border border-gray-100 bg-gray-50/70 rounded p-2.5 space-y-2">
                      <p className="font-bold text-gray-700">Financial Refund Track</p>
                      {(timeline?.financial_refund_events || []).length === 0 ? (
                        <p className="text-gray-400 italic">No financial refund events recorded yet.</p>
                      ) : (
                        <ul className="space-y-2 max-h-48 overflow-y-auto pr-1">
                          {timeline.financial_refund_events.map((ev) => (
                            <li key={ev.id} className="border-l-2 border-fk-green pl-2">
                              <p className="font-semibold text-gray-800">
                                {ev.event_type}{' '}
                                <span className="text-[10px] font-normal text-gray-500">
                                  ({ev.source_type})
                                </span>
                              </p>
                              <p className="text-gray-600">{ev.description}</p>
                              <p className="text-[10px] text-gray-400">
                                Occurred: {formatTs(ev.occurred_at)} · Recorded: {formatTs(ev.recorded_at)}
                              </p>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Refund Assistant Interactive Q&A Chat */}
              <div className="bg-white border border-gray-200 rounded p-3 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] font-bold text-gray-700 uppercase flex items-center gap-1.5">
                    <MessageSquare className="w-3.5 h-3.5 text-fk-blue" /> Ask Refund Support Assistant
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {QUICK_PROMPTS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        disabled={chatLoading}
                        onClick={() => handleAskQuestion(q)}
                        className="text-[10px] bg-blue-50 hover:bg-blue-100 text-fk-blue font-semibold px-2 py-1 rounded border border-blue-200 transition"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>

                {chatMessages.length > 0 && (
                  <div className="space-y-2 max-h-56 overflow-y-auto bg-slate-50 border border-gray-100 rounded p-2.5 text-xs">
                    {chatMessages.map((m, idx) => (
                      <div
                        key={idx}
                        className={`p-2 rounded ${
                          m.role === 'user'
                            ? 'bg-fk-blue text-white ml-8'
                            : m.isError
                            ? 'bg-red-50 text-red-700 border border-red-200 mr-6'
                            : 'bg-white border border-gray-200 text-gray-800 mr-6'
                        }`}
                      >
                        <p className="leading-relaxed">{m.text}</p>
                        {m.role === 'assistant' && !m.isError && (
                          <div className="mt-1.5 pt-1 border-t border-gray-100 flex flex-wrap gap-2 text-[10px] text-gray-500">
                            <span>ETA: {m.eta_status}</span>
                            <span>Delay Owner: {m.delay_owner}</span>
                            {m.model_used && <span>Model: {m.model_used}</span>}
                            {m.evidence_references?.length > 0 && (
                              <span>Refs: {m.evidence_references.join(', ')}</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleAskQuestion(question);
                  }}
                  className="flex gap-2"
                >
                  <input
                    type="text"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Ask about your refund status, PayPal disbursement vs bank credit, or ETA..."
                    className="flex-1 border border-gray-300 rounded-sm px-3 py-1.5 text-xs focus:outline-none focus:border-fk-blue"
                  />
                  <button
                    type="submit"
                    disabled={chatLoading || !question.trim()}
                    className="bg-fk-blue hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold px-3.5 py-1.5 rounded-sm inline-flex items-center gap-1"
                  >
                    <Send className="w-3.5 h-3.5" />
                    {chatLoading ? 'Sending...' : 'Ask'}
                  </button>
                </form>
              </div>

              {/* Verified Evidence Upload & Formal Appeal */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] font-bold text-gray-700 uppercase flex items-center gap-1.5">
                      <FileCheck2 className="w-3.5 h-3.5 text-fk-green" /> Verified Evidence Vault ({evidenceItems.length})
                    </p>
                    <label className="inline-flex items-center gap-1 text-[11px] font-bold text-fk-blue hover:underline cursor-pointer">
                      <Upload className="w-3.5 h-3.5" />
                      {uploading ? 'Verifying...' : 'Upload PNG/JPEG/PDF'}
                      <input
                        type="file"
                        accept="image/png,image/jpeg,application/pdf"
                        onChange={handleUploadEvidence}
                        disabled={uploading}
                        className="hidden"
                      />
                    </label>
                  </div>
                  {uploadFeedback && (
                    <p className="text-[11px] text-fk-green font-semibold">{uploadFeedback}</p>
                  )}
                  {evidenceItems.length === 0 ? (
                    <p className="text-[11px] text-gray-400 italic">
                      No SHA-256 verified files uploaded to Refund Intelligence Vault yet.
                    </p>
                  ) : (
                    <ul className="space-y-1 text-[11px]">
                      {evidenceItems.map((ev) => (
                        <li
                          key={ev.evidence_id}
                          className="flex items-center justify-between gap-2 bg-gray-50 border border-gray-100 px-2 py-1 rounded"
                        >
                          <span className="truncate font-medium text-gray-800">{ev.file_name}</span>
                          <span className="text-[10px] font-mono text-gray-500 flex-shrink-0">
                            {ev.verification_status} · {String(ev.sha256_hash || '').slice(0, 10)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-bold text-gray-700 uppercase flex items-center gap-1.5">
                      <Scale className="w-3.5 h-3.5 text-fk-orange" /> Dispute / Appeal Review
                    </p>
                    <button
                      type="button"
                      onClick={() => setShowAppeal((prev) => !prev)}
                      className="text-[11px] font-bold text-fk-blue hover:underline"
                    >
                      {showAppeal ? 'Cancel' : 'Submit Appeal'}
                    </button>
                  </div>
                  {showAppeal ? (
                    <form onSubmit={handleAppealSubmit} className="space-y-2">
                      <textarea
                        rows={2}
                        value={appealReason}
                        onChange={(e) => setAppealReason(e.target.value)}
                        placeholder="Describe why this return or refund requires appeal review..."
                        className="w-full border border-gray-300 rounded-sm p-2 text-xs focus:outline-none focus:border-fk-blue"
                      />
                      <button
                        type="submit"
                        disabled={appealSubmitting}
                        className="bg-fk-orange hover:bg-orange-600 disabled:opacity-50 text-white text-xs font-bold px-3 py-1.5 rounded-sm"
                      >
                        {appealSubmitting ? 'Submitting...' : 'Submit Formal Appeal'}
                      </button>
                    </form>
                  ) : (
                    <p className="text-[11px] text-gray-500">
                      Need further review after rejection or bank posting delay? Submit a formal appeal with your verified evidence.
                    </p>
                  )}
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
