import React, { useEffect, useState, useRef } from 'react';
import { RefreshCw, CheckCircle, XCircle, Image as ImageIcon } from 'lucide-react';
import { agentMerchantApi, merchantReturnsApi, resolveMediaUrl } from '../services/api';
import { useStaggeredReveal } from '../motion/useStaggeredReveal';
import MerchantRefundIntelligencePanel from '../components/MerchantRefundIntelligencePanel';

const RETURN_STAGES = [
  'REQUESTED',
  'UNDER_REVIEW',
  'APPROVED',
  'PICKUP_SCHEDULED',
  'REFUND_INITIATED',
  'REFUNDED',
];

export default function Returns() {
  const [returns, setReturns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notesMap, setNotesMap] = useState({});
  const [processingId, setProcessingId] = useState(null);
  const listRef = useRef(null);

  useStaggeredReveal(listRef, {
    triggerKey: `${loading}-${returns.map((r) => r.id).join(',')}`,
  });

  const loadReturns = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await merchantReturnsApi.myReturns();
      setReturns(data);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadReturns();
  }, []);

  const handleDecision = async (returnId, status) => {
    setProcessingId(returnId);
    const cleanNote = (notesMap[returnId] || '').trim();
    try {
      if (status === 'REJECTED' && cleanNote.length < 3) {
        alert('CASE-001: Please enter a merchant rejection reason (at least 3 characters).');
        return;
      }

      if (status === 'REFUNDED') {
        if (cleanNote.length < 3) {
          alert('REF-001 / CASE-001: Please enter an approval note (at least 3 characters) before executing a refund.');
          return;
        }
        let approvalReference = null;
        try {
          const listData = await agentMerchantApi.findRefundByReturnId(returnId);
          const refundCaseId = listData?.items?.[0]?.id;
          if (refundCaseId) {
            const approval = await agentMerchantApi.approveRefund(refundCaseId, {
              reason: cleanNote,
              policy_version: 'v1.0',
            });
            approvalReference = approval.id;
          }
        } catch (agentErr) {
          if (!agentErr?.isOffline) {
            throw agentErr;
          }
        }
        if (approvalReference) {
          await merchantReturnsApi.executeApprovedRefund(returnId, {
            approval_reference: approvalReference,
            merchant_notes: cleanNote,
          });
        } else {
          await merchantReturnsApi.decide(returnId, {
            status: 'REFUNDED',
            merchant_notes: cleanNote,
          });
        }
        await loadReturns(true);
        return;
      }

      await merchantReturnsApi.decide(returnId, {
        status,
        merchant_notes: cleanNote || `Updated to ${status} by Merchant Console`,
      });
      await loadReturns(true);
    } catch (err) {
      alert(err.message || 'Failed updating return claim');
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h2 className="font-bold text-base text-gray-800">Returns & Refund Dispute Console</h2>
          <p className="text-xs text-gray-500">
            Inspect customer evidence photos, validate claims, and resolve refund status
          </p>
        </div>
        <div className="flex items-center gap-2 bg-blue-50 text-seller-blue border border-blue-200 px-3 py-1.5 rounded text-xs font-bold">
          <span>Active Return Claims: {returns.length}</span>
        </div>
      </div>

      {loading ? (
        <div className="bg-white p-8 text-center text-xs text-gray-500 rounded shadow-sm">
          Loading return requests...
        </div>
      ) : returns.length === 0 ? (
        <div className="bg-white p-12 text-center text-xs text-gray-500 rounded shadow-sm">
          <RefreshCw className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          No return requests submitted yet. Once a customer order is marked Delivered, they can request a return.
        </div>
      ) : (
        <div ref={listRef} className="space-y-4">
          {returns.map((ret) => {
            const stageIdx = RETURN_STAGES.indexOf(ret.status);
            const isRejected = ret.status === 'REJECTED' || ret.status === 'AGENT_REJECTED';
            const isRefunded = ret.status === 'REFUNDED';
            const progressPct = isRejected
              ? 100
              : stageIdx >= 0
              ? Math.round(((stageIdx + 1) / RETURN_STAGES.length) * 100)
              : 0;

            return (
              <div key={ret.id} data-staggered-item>
                <div className="bg-white rounded shadow-sm border border-gray-100 p-5 space-y-4 apple-card-hover hover:shadow-md">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b pb-3 gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-gray-900">{ret.return_number}</span>
                        <span
                          key={ret.status}
                          className={`apple-badge-pop text-xs font-bold px-2.5 py-0.5 rounded ${
                            isRefunded || ret.status === 'APPROVED'
                              ? 'bg-green-100 text-green-700'
                              : isRejected
                              ? 'bg-red-100 text-red-700'
                              : 'bg-amber-100 text-amber-800'
                          }`}
                        >
                          {ret.status}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        Created: {new Date(ret.created_at).toLocaleString()}
                      </p>
                    </div>

                    <div className="sm:text-right">
                      <p className="text-xs text-gray-400">Refund Liability</p>
                      <p className="text-lg font-bold text-red-600">₹{ret.refund_amount.toLocaleString('en-IN')}</p>
                      {ret.refund_transaction_id && (
                        <p className="text-[11px] font-mono text-gray-500">TXN: {ret.refund_transaction_id}</p>
                      )}
                    </div>
                  </div>

                  {/* Compact horizontal refund-lifecycle progress bar */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-gray-500">
                      <span className="uppercase tracking-wider text-[10px]">Refund Lifecycle</span>
                      <span
                        className={
                          isRefunded
                            ? 'text-green-600 font-bold'
                            : isRejected
                            ? 'text-red-600 font-bold'
                            : 'text-seller-blue font-bold'
                        }
                      >
                        {isRejected
                          ? 'Claim Rejected'
                          : isRefunded
                          ? 'Refund Completed (100%)'
                          : `${ret.status.replace(/_/g, ' ')} (${progressPct}%)`}
                      </span>
                    </div>
                    <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-[width] duration-[550ms] motion-reduce:transition-none ${
                          isRefunded
                            ? 'bg-green-600'
                            : isRejected
                            ? 'bg-red-500'
                            : 'bg-gradient-to-r from-blue-600 via-indigo-500 to-blue-600 apple-gradient-track'
                        }`}
                        style={{
                          width: `${progressPct}%`,
                          transitionTimingFunction: 'var(--ease-apple-decel)',
                        }}
                      />
                    </div>
                    {!isRejected && (
                      <div className="flex justify-between text-[10px] text-gray-400">
                        {RETURN_STAGES.map((stg, idx) => {
                          const isPassed = stageIdx >= idx;
                          const isCurrent = stageIdx === idx;
                          const stageLabels = {
                            REQUESTED: 'Requested',
                            UNDER_REVIEW: 'Review',
                            APPROVED: 'Approved',
                            PICKUP_SCHEDULED: 'Pickup',
                            REFUND_INITIATED: 'Initiated',
                            REFUNDED: 'Refunded',
                          };
                          return (
                            <span
                              key={stg}
                              className={`${
                                isCurrent
                                  ? 'text-seller-blue font-bold'
                                  : isPassed
                                  ? 'text-gray-700 font-medium'
                                  : 'text-gray-400'
                              }`}
                            >
                              {stageLabels[stg] || stg}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {isRejected && (
                      <p className="text-[10px] text-red-500 font-medium">
                        This return claim was rejected and the refund lifecycle terminated.
                      </p>
                    )}
                  </div>

                  {/* Reason & Customer Comments */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div className="bg-gray-50 p-3.5 rounded border space-y-1">
                      <p className="font-bold text-gray-600 uppercase">Customer Claim Details</p>
                      <p className="text-sm font-semibold text-gray-900">{ret.reason}</p>
                      <p className="text-gray-600 italic">"{ret.comments || 'No additional comments'}"</p>
                    </div>

                    {/* Evidence Photos */}
                    <div className="bg-gray-50 p-3.5 rounded border space-y-2">
                      <p className="font-bold text-gray-600 uppercase flex items-center gap-1.5">
                        <ImageIcon className="w-3.5 h-3.5 text-seller-blue" /> Customer Evidence Photos
                      </p>
                      {ret.evidence_urls?.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {ret.evidence_urls.map((url, idx) => (
                            <a
                              key={idx}
                              href={resolveMediaUrl(url)}
                              target="_blank"
                              rel="noreferrer"
                              className="w-20 h-20 border rounded overflow-hidden hover:ring-2 ring-seller-blue transition bg-white"
                            >
                              <img src={resolveMediaUrl(url)} alt="Evidence" className="w-full h-full object-cover" />
                            </a>
                          ))}
                        </div>
                      ) : (
                        <p className="text-gray-400 italic">No defect images uploaded by customer.</p>
                      )}
                    </div>
                  </div>

                  {/* Automated Assessment Note if present */}
                  {ret.agent_reasoning && (
                    <div className="bg-blue-50 border border-blue-200 p-3 rounded text-xs text-blue-900">
                      <strong>Automated Review Assessment (Score: {ret.agent_risk_score}):</strong> {ret.agent_reasoning}
                    </div>
                  )}

                  {/* Connected AI Investigation Dossier & REF-001 Approval Controls */}
                  <MerchantRefundIntelligencePanel
                    shipkartReturn={ret}
                    merchantNote={notesMap[ret.id] || ''}
                    onNoteChange={(val) => setNotesMap((prev) => ({ ...prev, [ret.id]: val }))}
                    defaultOpen={ret.status === 'REQUESTED' || ret.status === 'UNDER_REVIEW'}
                    onRefundUpdated={() => loadReturns(true)}
                  />

                  {/* Physical Return & Unified Decision Controls */}
                  {ret.status !== 'REFUNDED' && ret.status !== 'REJECTED' && ret.status !== 'AGENT_REJECTED' && (
                    <div className="border-t pt-4 space-y-3">
                      <input
                        type="text"
                        placeholder="Add Merchant inspection note / reasoning (synced with AI Dossier & visible to customer)..."
                        value={notesMap[ret.id] || ''}
                        onChange={(e) => setNotesMap({ ...notesMap, [ret.id]: e.target.value })}
                        className="w-full border border-gray-300 rounded px-3 py-2 text-xs focus:border-seller-blue focus:outline-none"
                      />

                      <div className="flex flex-wrap gap-2">
                        {ret.status === 'REQUESTED' || ret.status === 'UNDER_REVIEW' ? (
                          <>
                            <button
                              onClick={() => handleDecision(ret.id, 'APPROVED')}
                              disabled={processingId === ret.id}
                              className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold px-4 py-2 rounded flex items-center gap-1.5 shadow"
                            >
                              <CheckCircle className="w-3.5 h-3.5" /> Approve Return Pickup
                            </button>
                            <button
                              onClick={() => handleDecision(ret.id, 'REJECTED')}
                              disabled={processingId === ret.id}
                              className="bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-4 py-2 rounded flex items-center gap-1.5 shadow"
                            >
                              <XCircle className="w-3.5 h-3.5" /> Reject Claim
                            </button>
                          </>
                        ) : null}

                        {ret.status === 'APPROVED' && (
                          <button
                            onClick={() => handleDecision(ret.id, 'PICKUP_SCHEDULED')}
                            disabled={processingId === ret.id}
                            className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold px-4 py-2 rounded shadow"
                          >
                            Mark Item Picked Up
                          </button>
                        )}

                        {(ret.status === 'APPROVED' || ret.status === 'PICKUP_SCHEDULED') && (
                          <button
                            onClick={() => handleDecision(ret.id, 'REFUND_INITIATED')}
                            disabled={processingId === ret.id}
                            className="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-4 py-2 rounded shadow"
                          >
                            Initiate Refund
                          </button>
                        )}

                        {ret.status === 'REFUND_INITIATED' && (
                          <button
                            onClick={() => handleDecision(ret.id, 'REFUNDED')}
                            disabled={processingId === ret.id}
                            className="bg-green-600 hover:bg-green-700 text-white text-xs font-bold px-4 py-2 rounded flex items-center gap-1.5 shadow"
                          >
                            <CheckCircle className="w-3.5 h-3.5" /> Execute REF-001 Refund via Payment Gateway
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
