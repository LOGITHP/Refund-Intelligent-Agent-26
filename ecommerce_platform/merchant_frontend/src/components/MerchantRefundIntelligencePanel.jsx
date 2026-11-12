import React, { useEffect, useState, useCallback } from 'react';
import {
  Bot,
  Clock,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Truck,
  Landmark,
  Scale,
  FileCheck2,
  ClipboardCheck,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { agentMerchantApi, merchantReturnsApi } from '../services/api';

const INSPECTABLE_STATES = ['DELIVERED_TO_MERCHANT', 'PRODUCT_RECEIVED', 'INSPECTION_PENDING'];
const CONDITION_OPTIONS = [
  'DAMAGED_CONFIRMED',
  'DEFECTIVE_CONFIRMED',
  'GOOD_CONDITION',
  'MISMATCHED_ITEM',
  'NO_DAMAGE_FOUND',
];

const NEXT_PHYSICAL_STEP = {
  RETURN_REQUESTED: 'RETURN_APPROVED',
  RETURN_APPROVED: 'PICKUP_SCHEDULED',
  PICKUP_SCHEDULED: 'PICKED_UP',
  PICKED_UP: 'IN_TRANSIT',
  IN_TRANSIT: 'DELIVERED_TO_MERCHANT',
};

function formatTs(value) {
  if (!value) return 'N/A';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

export default function MerchantRefundIntelligencePanel({
  shipkartReturn,
  merchantNote = '',
  onNoteChange,
  onRefundUpdated,
  defaultOpen = false,
}) {
  const [expanded, setExpanded] = useState(defaultOpen);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [notIndexed, setNotIndexed] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [error, setError] = useState('');
  const [actionMsg, setActionMsg] = useState('');
  const [dossier, setDossier] = useState(null);

  const [investigating, setInvestigating] = useState(false);
  const [acting, setActing] = useState(false);
  const [decisionReason, setDecisionReason] = useState(merchantNote || '');

  // Inspection form
  const [conditionResult, setConditionResult] = useState('DAMAGED_CONFIRMED');
  const [inspectionNotes, setInspectionNotes] = useState('');
  const [inspecting, setInspecting] = useState(false);

  useEffect(() => {
    setDecisionReason(merchantNote || '');
  }, [merchantNote]);

  const loadInvestigation = useCallback(async () => {
    if (!shipkartReturn?.id) return;
    setLoading(true);
    setError('');
    setOffline(false);
    setNotIndexed(false);

    try {
      const listData = await agentMerchantApi.findRefundByReturnId(shipkartReturn.id);
      const match = listData?.items?.[0];
      if (!match?.id) {
        setDossier(null);
        setNotIndexed(true);
        return;
      }
      const data = await agentMerchantApi.getInvestigation(match.id);
      setDossier(data);
    } catch (err) {
      if (err.isOffline) {
        setOffline(true);
      } else {
        setError(err.message || 'Unable to load AI investigation dossier');
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
      loadInvestigation();
    }
  }, [expanded, loadInvestigation]);

  useEffect(() => {
    if (!expanded || !notIndexed || retryCount >= 2) return undefined;
    const delayMs = retryCount === 0 ? 1500 : 3000;
    const timer = setTimeout(() => {
      setRetryCount((prev) => prev + 1);
      loadInvestigation();
    }, delayMs);
    return () => clearTimeout(timer);
  }, [expanded, notIndexed, retryCount, loadInvestigation]);

  const handleRunInvestigation = async () => {
    if (!dossier?.refund_case?.id) return;
    setInvestigating(true);
    setError('');
    setActionMsg('');
    try {
      await agentMerchantApi.runInvestigation(
        dossier.refund_case.id,
        shipkartReturn?.comments || shipkartReturn?.reason || null
      );
      setActionMsg('LangGraph 3-Agent investigation pipeline completed (REF-001 Merchant sign-off required).');
      await loadInvestigation();
      await onRefundUpdated?.();
    } catch (err) {
      setError(err.message || 'Investigation failed');
    } finally {
      setInvestigating(false);
    }
  };

  const handleAdvancePhysicalReturn = async (targetStatus) => {
    if (!dossier?.return_case?.id) return;
    setInspecting(true);
    setError('');
    setActionMsg('');
    try {
      await agentMerchantApi.transitionReturnStatus(
        dossier.return_case.id,
        targetStatus,
        `Updated physical return stage to ${targetStatus}`
      );
      setActionMsg(`Physical return status advanced to ${targetStatus}.`);
      await loadInvestigation();
    } catch (err) {
      setError(err.message || 'Failed updating physical return stage');
    } finally {
      setInspecting(false);
    }
  };

  const handleRecordInspection = async (e) => {
    e.preventDefault();
    if (!dossier?.return_case?.id) return;
    setInspecting(true);
    setError('');
    setActionMsg('');
    try {
      await agentMerchantApi.inspectReturn(dossier.return_case.id, {
        condition_result: conditionResult,
        notes: inspectionNotes.trim() || `Warehouse inspected item: ${conditionResult}`,
        completed: true,
      });
      setActionMsg('Warehouse inspection persisted to ReturnCase timeline.');
      await loadInvestigation();
    } catch (err) {
      setError(err.message || 'Inspection recording failed');
    } finally {
      setInspecting(false);
    }
  };

  const handleApproveAndExecuteRefund = async () => {
    if (!dossier?.refund_case?.id) return;
    const cleanReason = (decisionReason || merchantNote || '').trim();
    if (cleanReason.length < 3) {
      setError('CASE-001 / REF-001: Enter an approval note of at least 3 characters before approving.');
      return;
    }
    setActing(true);
    setError('');
    setActionMsg('');
    try {
      const approval = await agentMerchantApi.approveRefund(dossier.refund_case.id, {
        reason: cleanReason,
        policy_version: 'v1.0',
      });
      const updated = await merchantReturnsApi.executeApprovedRefund(shipkartReturn.id, {
        approval_reference: approval.id,
        merchant_notes: cleanReason,
      });
      setActionMsg(
        `Approved (${approval.id.slice(0, 8)}...) and executed refund TXN: ${updated.refund_transaction_id}`
      );
      await loadInvestigation();
      await onRefundUpdated?.();
    } catch (err) {
      setError(err.message || 'Failed approving & executing refund');
    } finally {
      setActing(false);
    }
  };

  const handleRejectClaim = async () => {
    if (!dossier?.refund_case?.id) return;
    const cleanReason = (decisionReason || merchantNote || '').trim();
    if (cleanReason.length < 3) {
      setError('CASE-001: Explicit rejection explanation (at least 3 characters) is mandatory.');
      return;
    }
    setActing(true);
    setError('');
    setActionMsg('');
    try {
      await agentMerchantApi.rejectRefund(dossier.refund_case.id, {
        reason: cleanReason,
        policy_version: 'v1.0',
      });
      await merchantReturnsApi.decide(shipkartReturn.id, {
        status: 'REJECTED',
        merchant_notes: cleanReason,
      });
      setActionMsg('Claim rejected in both Refund Intelligence and Shipkart.');
      await loadInvestigation();
      await onRefundUpdated?.();
    } catch (err) {
      setError(err.message || 'Failed rejecting claim');
    } finally {
      setActing(false);
    }
  };

  const refundCase = dossier?.refund_case;
  const returnCase = dossier?.return_case;
  const currentEta = dossier?.current_eta;
  const delayEval = dossier?.delay_evaluation;
  const evidenceItems = dossier?.evidence_items || [];
  const executions = dossier?.agent_executions || [];
  const issuerInquiries = dossier?.issuer_inquiries || [];
  const regEvals = dossier?.regulatory_evaluations || [];
  const approvals = dossier?.approvals || [];

  const isTerminalShipkart = ['REFUNDED', 'REJECTED', 'AGENT_REJECTED'].includes(
    shipkartReturn?.status
  );
  const canInspect = returnCase && INSPECTABLE_STATES.includes(returnCase.status);
  const nextPhysicalStatus = returnCase ? NEXT_PHYSICAL_STEP[returnCase.status] : null;

  return (
    <div className="border border-blue-200 rounded bg-slate-50/70 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-blue-50/60 transition"
      >
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-seller-blue flex-shrink-0" />
          <div>
            <p className="text-xs font-bold text-gray-800">
              AI Investigation Dossier &amp; REF-001 Refund Governance
            </p>
            <p className="text-[11px] text-gray-500">
              3-Agent LangGraph risk report, Delay SLA rules, Issuer/Regulatory checks &amp; Human-in-the-Loop approval
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-seller-blue">
          <span>{expanded ? 'Hide Dossier' : 'Open AI Dossier'}</span>
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-blue-200 p-4 space-y-4 apple-panel-enter">
          {offline ? (
            <div className="bg-amber-50 border border-amber-200 rounded p-3 text-xs text-amber-900 flex items-center justify-between gap-2">
              <span>
                Refund Intelligence service is currently unreachable. Manual decision controls remain active below.
              </span>
              <button
                type="button"
                onClick={loadInvestigation}
                className="text-xs font-bold text-seller-blue hover:underline"
              >
                Retry
              </button>
            </div>
          ) : loading && !dossier ? (
            <div className="text-xs text-gray-500 py-4 text-center">
              Loading AI investigation dossier...
            </div>
          ) : notIndexed ? (
            <div className="bg-white border border-gray-200 rounded p-3 text-xs text-gray-600 flex items-center justify-between gap-2">
              <span>No AI investigation case indexed yet for this return.</span>
              <button
                type="button"
                onClick={loadInvestigation}
                className="text-xs font-bold text-seller-blue hover:underline flex items-center gap-1"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Check Again
              </button>
            </div>
          ) : dossier && refundCase ? (
            <>
              {/* Top Dossier Toolbar */}
              <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-gray-200">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span
                    key={refundCase.status}
                    className="apple-badge-pop px-2 py-0.5 rounded font-bold bg-blue-100 text-seller-blue"
                  >
                    Refund Case: {refundCase.status}
                  </span>
                  {returnCase && (
                    <span className="px-2 py-0.5 rounded font-semibold bg-gray-200 text-gray-800">
                      Physical Return: {returnCase.status}
                    </span>
                  )}
                  <span className="text-[11px] font-mono text-gray-500">
                    {String(refundCase.id).slice(0, 8)}... | {refundCase.requested_amount}{' '}
                    {refundCase.currency}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleRunInvestigation}
                    disabled={investigating}
                    className="bg-seller-blue hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold px-3 py-1.5 rounded inline-flex items-center gap-1.5 shadow-sm"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${investigating ? 'animate-spin' : ''}`} />
                    {investigating ? 'Running 3-Agent Pipeline...' : 'Run 3-Agent Investigation'}
                  </button>
                </div>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-2.5 rounded">
                  {error}
                </div>
              )}

              {actionMsg && (
                <div className="bg-green-50 border border-green-200 text-green-800 text-xs p-2.5 rounded flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                  <span>{actionMsg}</span>
                </div>
              )}

              {/* Metrics & Signals Row */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                {/* Delay Owner */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1">
                  <p className="text-[10px] font-bold uppercase text-gray-500 flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-600" /> SLA Delay Owner
                  </p>
                  <p className="font-bold text-gray-900">{delayEval?.delay_owner || 'NONE'}</p>
                  <p className="text-[11px] text-gray-600">
                    {delayEval?.triggered_rules?.length > 0
                      ? delayEval.triggered_rules.join(', ')
                      : 'No SLA breaches triggered'}
                  </p>
                </div>

                {/* Deterministic ETA */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1">
                  <p className="text-[10px] font-bold uppercase text-gray-500 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-seller-blue" /> Deterministic ETA
                  </p>
                  <p className="font-bold text-gray-900">{currentEta?.eta_status || 'UNKNOWN'}</p>
                  <p className="text-[10px] text-gray-500 italic">
                    {currentEta?.disclaimer || 'This is an estimate, not a guaranteed credit date.'}
                  </p>
                </div>

                {/* Issuer / Bank Pipeline */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1">
                  <div className="flex items-center justify-between gap-1">
                    <p className="text-[10px] font-bold uppercase text-gray-500 flex items-center gap-1">
                      <Landmark className="w-3.5 h-3.5 text-seller-blue" /> Issuer Check
                    </p>
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                      SIMULATED
                    </span>
                  </div>
                  {issuerInquiries.length > 0 ? (
                    <>
                      <p className="font-bold text-gray-900">{issuerInquiries[0].status}</p>
                      <p className="text-[10px] font-mono text-gray-500 truncate">
                        {issuerInquiries[0].provider_reference || issuerInquiries[0].institution_code}
                      </p>
                    </>
                  ) : (
                    <p className="text-[11px] text-gray-400">Run investigation to query issuer.</p>
                  )}
                </div>

                {/* Regulatory Compliance Guidance */}
                <div className="bg-white border border-gray-200 rounded p-3 space-y-1">
                  <div className="flex items-center justify-between gap-1">
                    <p className="text-[10px] font-bold uppercase text-gray-500 flex items-center gap-1">
                      <Scale className="w-3.5 h-3.5 text-seller-blue" /> Regulatory Guidance
                    </p>
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-purple-100 text-purple-800">
                      SIMULATED
                    </span>
                  </div>
                  {regEvals.length > 0 ? (
                    <>
                      <p className="font-bold text-gray-900">
                        {regEvals[0].jurisdiction}: {regEvals[0].evaluation_status}
                      </p>
                      <p className="text-[10px] text-gray-400 italic">
                        Simulated guidance — not formal legal advice.
                      </p>
                    </>
                  ) : (
                    <p className="text-[11px] text-gray-400">Run investigation for IN/US evaluation.</p>
                  )}
                </div>
              </div>

              {/* LangGraph Agent Executions & Recommendations */}
              <div className="bg-white border border-gray-200 rounded p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-bold uppercase text-gray-600 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-seller-blue" /> LangGraph 3-Agent Findings (REF-001 Enforced)
                  </p>
                  <span className="text-[10px] text-gray-500">
                    Executions: {executions.length}
                  </span>
                </div>

                {executions.length === 0 ? (
                  <p className="text-[11px] text-gray-400 italic">
                    No LangGraph runs recorded yet. Click "Run 3-Agent Investigation" to analyze evidence, carrier, issuer &amp; regulatory signals.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {executions.slice(0, 3).map((ex) => {
                      const dec = ex.decisions?.[0];
                      return (
                        <div
                          key={ex.id}
                          className="border border-gray-100 bg-slate-50 rounded p-2.5 space-y-1"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-bold text-gray-800">
                              {ex.agent_name} — {ex.status}
                            </span>
                            <span className="text-[10px] font-mono text-gray-500">
                              Model: {ex.model_name || 'N/A'}
                            </span>
                          </div>
                          {dec && (
                            <div className="text-[11px] text-gray-700 space-y-0.5">
                              <p>
                                <strong>Recommendation:</strong> {dec.decision_type} (Confidence:{' '}
                                {Math.round(Number(dec.confidence || 0) * 100)}%,{' '}
                                <span className="text-seller-blue font-semibold">
                                  requires_approval={String(dec.requires_approval)}
                                </span>
                                )
                              </p>
                              {(dec.recommendation?.merchant_brief ||
                                dec.recommendation?.rationale ||
                                dec.recommendation?.customer_explanation ||
                                dec.recommendation?.customer_message ||
                                dec.recommendation?.recommended_action) && (
                                <p className="text-gray-600 leading-relaxed">
                                  {dec.recommendation.merchant_brief ||
                                    dec.recommendation.rationale ||
                                    dec.recommendation.customer_explanation ||
                                    dec.recommendation.customer_message ||
                                    dec.recommendation.recommended_action}
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Warehouse Inspection + Evidence Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <p className="text-[11px] font-bold uppercase text-gray-600 flex items-center gap-1.5">
                    <ClipboardCheck className="w-3.5 h-3.5 text-seller-blue" /> Physical Inspection (STATE-002)
                  </p>
                  {canInspect ? (
                    <form onSubmit={handleRecordInspection} className="space-y-2">
                      <select
                        value={conditionResult}
                        onChange={(e) => setConditionResult(e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1.5 text-xs"
                      >
                        {CONDITION_OPTIONS.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={inspectionNotes}
                        onChange={(e) => setInspectionNotes(e.target.value)}
                        placeholder="Warehouse inspection observations..."
                        className="w-full border border-gray-300 rounded px-2.5 py-1.5 text-xs"
                      />
                      <button
                        type="submit"
                        disabled={inspecting}
                        className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-bold px-3 py-1.5 rounded"
                      >
                        {inspecting ? 'Recording...' : 'Record Warehouse Inspection'}
                      </button>
                    </form>
                  ) : (
                    <div className="space-y-2 text-[11px] text-gray-600">
                      <p>
                        Current physical stage: <strong>{returnCase?.status}</strong>. Warehouse inspection activates once the parcel reaches <code>DELIVERED_TO_MERCHANT</code>.
                      </p>
                      {nextPhysicalStatus && !isTerminalShipkart && (
                        <button
                          type="button"
                          disabled={inspecting}
                          onClick={() => handleAdvancePhysicalReturn(nextPhysicalStatus)}
                          className="bg-gray-100 hover:bg-gray-200 border border-gray-300 text-gray-800 font-bold text-[11px] px-2.5 py-1 rounded inline-flex items-center gap-1"
                        >
                          <Truck className="w-3.5 h-3.5" />
                          Advance Physical Return → {nextPhysicalStatus}
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <div className="bg-white border border-gray-200 rounded p-3 space-y-2">
                  <p className="text-[11px] font-bold uppercase text-gray-600 flex items-center gap-1.5">
                    <FileCheck2 className="w-3.5 h-3.5 text-green-600" /> Verified Evidence &amp; Approvals
                  </p>
                  {evidenceItems.length === 0 ? (
                    <p className="text-[11px] text-gray-400 italic">
                      No SHA-256 verified vault uploads yet.
                    </p>
                  ) : (
                    <ul className="space-y-1 text-[11px]">
                      {evidenceItems.map((ev) => (
                        <li key={ev.evidence_id} className="flex justify-between gap-2 bg-gray-50 px-2 py-1 rounded">
                          <span className="truncate font-medium">{ev.file_name}</span>
                          <span className="font-mono text-[10px] text-gray-500">
                            {ev.verification_status} · {String(ev.sha256_hash || '').slice(0, 10)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {approvals.length > 0 && (
                    <div className="border-t pt-2 space-y-1">
                      <p className="text-[10px] font-bold text-gray-500 uppercase">Immutable Approval Log</p>
                      {approvals.map((app) => (
                        <p key={app.id} className="text-[11px] text-gray-700">
                          <strong>{app.decision}</strong> ({app.approved_amount} {app.currency}) —{' '}
                          {app.reason} · <span className="text-gray-400">{formatTs(app.created_at)}</span>
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Mandatory Merchant Approval Bar (REF-001 & CASE-001) */}
              {!isTerminalShipkart && (
                <div className="bg-white border border-blue-200 rounded p-3 space-y-2.5">
                  <p className="text-[11px] font-bold text-gray-700 uppercase">
                    Human-in-the-Loop Merchant Decision (REF-001 &amp; CASE-001)
                  </p>
                  <input
                    type="text"
                    value={decisionReason}
                    onChange={(e) => {
                      const val = e.target.value;
                      setDecisionReason(val);
                      onNoteChange?.(val);
                    }}
                    placeholder="Mandatory merchant decision rationale (minimum 3 characters)..."
                    className="w-full border border-gray-300 rounded px-3 py-2 text-xs focus:border-seller-blue focus:outline-none"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={handleApproveAndExecuteRefund}
                      disabled={acting}
                      className="bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded inline-flex items-center gap-1.5 shadow"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      {acting ? 'Processing...' : 'Approve & Execute Refund (REF-001)'}
                    </button>
                    <button
                      type="button"
                      onClick={handleRejectClaim}
                      disabled={acting}
                      className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded inline-flex items-center gap-1.5 shadow"
                    >
                      <XCircle className="w-4 h-4" />
                      Reject Claim (CASE-001)
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
