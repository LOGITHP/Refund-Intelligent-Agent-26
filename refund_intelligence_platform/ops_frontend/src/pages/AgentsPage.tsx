import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot, ChevronDown, ChevronRight, Cpu, Lock, RefreshCw, ShieldAlert } from 'lucide-react';
import { opsApi } from '../api/client';
import { ApiErrorBanner, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { AgentExecution, RefundCaseSummary } from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

export function AgentsPage() {
  const [caseFilter, setCaseFilter] = useState('');
  const [agentFilter, setAgentFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetcher = useCallback(
    () =>
      opsApi.listAgentExecutions({
        case_id: caseFilter || undefined,
        agent_name: agentFilter || undefined,
        status: statusFilter || undefined,
      }),
    [caseFilter, agentFilter, statusFilter]
  );

  const casesFetcher = useCallback(() => opsApi.listCases(), []);
  const { data: availableCases } = useOpsFetch<RefundCaseSummary[]>(casesFetcher);

  const { data: executions, loading, error, reload } =
    useOpsFetch<AgentExecution[]>(fetcher);

  const nimCount =
    executions?.filter((e) => e.model_name.includes('llama') || e.model_name.includes('nvidia'))
      .length ?? 0;
  const fallbackCount =
    executions?.filter((e) => e.model_name === 'deterministic-fallback').length ?? 0;

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            LangGraph 3-Agent Execution Monitor
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Inspect <span className="font-semibold text-gray-700">intake_agent</span>,{' '}
            <span className="font-semibold text-gray-700">investigation_agent</span>, and{' '}
            <span className="font-semibold text-gray-700">resolution_agent</span> runs, NVIDIA NIM
            vs deterministic fallback telemetry, and{' '}
            <span className="font-semibold text-gray-700">requires_approval: true</span> locks.
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

      {/* Telemetry Summary Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              Total Agent Runs
            </p>
            <Bot className="h-4 w-4 text-gray-500" />
          </div>
          <p className="mt-2 font-mono text-2xl font-semibold text-gray-900">
            {executions?.length ?? '—'}
          </p>
          <p className="mt-1 text-xs text-gray-500">LangGraph StateGraph nodes</p>
        </div>

        <div className="rounded border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              NVIDIA NIM vs Fallback
            </p>
            <Cpu className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-3 font-mono text-sm">
            <span className="text-xl font-semibold text-emerald-700">{nimCount} NIM</span>
            <span className="text-gray-400">/</span>
            <span className="text-xl font-semibold text-amber-700">{fallbackCount} Fallback</span>
          </div>
          <p className="mt-1 font-mono text-[11px] text-gray-500">
            nvidia/nemotron-3.5-super-vl-120b-a12b vs deterministic-fallback
          </p>
        </div>

        <div className="rounded border border-gray-100 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              REF-001 Approval Lock
            </p>
            <Lock className="h-4 w-4 text-emerald-600" />
          </div>
          <p className="mt-2 font-mono text-sm font-semibold text-emerald-800">
            requires_approval: true
          </p>
          <p className="mt-1 text-xs text-gray-500">
            Agents propose plans only; PayPal refund execution requires explicit human Merchant approval.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 rounded border border-gray-100 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
        <select
          value={caseFilter}
          onChange={(e) => setCaseFilter(e.target.value)}
          aria-label="Select refund case"
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Refund Cases</option>
          {(availableCases ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              Order #{c.shipkart_order_id ?? '—'} • Return #{c.shipkart_return_id ?? '—'} ({c.status})
            </option>
          ))}
        </select>
        <input
          type="text"
          value={caseFilter}
          onChange={(e) => setCaseFilter(e.target.value)}
          placeholder="Or paste Case UUID…"
          className="rounded border border-gray-200 px-3 py-2 font-mono text-xs text-gray-900 placeholder:text-gray-400 focus:border-shipkart-blue focus:outline-none"
        />
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All 3 Agents</option>
          <option value="intake_agent">intake_agent</option>
          <option value="investigation_agent">investigation_agent</option>
          <option value="resolution_agent">resolution_agent</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Statuses</option>
          <option value="COMPLETED">COMPLETED</option>
          <option value="RUNNING">RUNNING</option>
          <option value="FAILED">FAILED</option>
        </select>
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Executions Table */}
      <div className="overflow-hidden rounded border border-gray-100 bg-white shadow-sm">
        <div className="divide-y divide-gray-100">
          {executions && executions.length > 0 ? (
            executions.map((exec) => {
              const isOpen = expandedId === exec.id;
              const isFallback = exec.model_name === 'deterministic-fallback';
              const durationMs =
                exec.latency_ms ??
                (exec.completed_at
                  ? Math.max(
                      0,
                      new Date(exec.completed_at).getTime() - new Date(exec.started_at).getTime()
                    )
                  : null);

              return (
                <div key={exec.id} className="p-4">
                  <div
                    onClick={() => setExpandedId(isOpen ? null : exec.id)}
                    className="flex cursor-pointer flex-wrap items-center justify-between gap-3"
                  >
                    <div className="flex items-center gap-3">
                      {isOpen ? (
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-400" />
                      )}
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-gray-900">
                            {exec.agent_name}
                          </span>
                          <StatusPill value={exec.status} />
                          <span
                            className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${
                              isFallback
                                ? 'border-amber-200 bg-amber-50 text-amber-800'
                                : 'border-emerald-200 bg-emerald-50 text-emerald-800'
                            }`}
                          >
                            {exec.model_name}
                          </span>
                          <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-600">
                            {exec.prompt_version}
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-[11px] text-gray-500">
                          Case:{' '}
                          <Link
                            to={`/operations/cases?caseId=${encodeURIComponent(exec.case_id)}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-shipkart-blue underline hover:text-shipkart-blueHover"
                          >
                            {shortId(exec.case_id, 12)}
                          </Link>{' '}
                          • Started {formatTimestamp(exec.started_at)}
                          {durationMs !== null ? ` • ${durationMs} ms` : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      {exec.decisions.map((dec) => (
                        <span
                          key={dec.id}
                          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-semibold ${
                            dec.requires_approval
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                              : 'border-rose-300 bg-rose-50 text-rose-900'
                          }`}
                        >
                          {dec.requires_approval ? (
                            <Lock className="h-3 w-3" />
                          ) : (
                            <ShieldAlert className="h-3 w-3" />
                          )}
                          requires_approval: {String(dec.requires_approval)}
                        </span>
                      ))}
                    </div>
                  </div>

                  {isOpen && (
                    <div className="mt-4 space-y-4 border-t border-gray-100 pt-4">
                      {exec.error_code && (
                        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-800">
                          Error Code: {exec.error_code}
                        </div>
                      )}

                      {exec.decisions.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                            Proposed Agent Decisions (AI Recommendation — Never Auto-Executes)
                          </p>
                          {exec.decisions.map((dec) => (
                            <div
                              key={dec.id}
                              className="rounded border border-gray-200 bg-gray-50 p-3 text-xs"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-semibold text-gray-900">
                                    {dec.decision_type}
                                  </span>
                                  <StatusPill value={dec.decision_status} />
                                </div>
                                <span className="font-mono text-[11px] text-gray-600">
                                  Confidence: {dec.confidence}
                                </span>
                              </div>

                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {dec.evidence_references.length > 0 ? (
                                  dec.evidence_references.map((ref) => (
                                    <span
                                      key={ref}
                                      className="rounded border border-gray-200 bg-white px-2 py-0.5 font-mono text-[10px] text-gray-700"
                                    >
                                      {ref}
                                    </span>
                                  ))
                                ) : (
                                  <span className="font-mono text-[10px] text-gray-400">
                                    No evidence_references attached
                                  </span>
                                )}
                              </div>

                              {(() => {
                                const rec = (dec.recommendation ?? {}) as Record<string, unknown>;
                                const merchantBrief =
                                  typeof rec.merchant_brief === 'string'
                                    ? rec.merchant_brief
                                    : typeof rec.rationale === 'string'
                                    ? rec.rationale
                                    : typeof rec.summary === 'string'
                                    ? rec.summary
                                    : null;
                                const customerExplanation =
                                  typeof rec.customer_explanation === 'string'
                                    ? rec.customer_explanation
                                    : typeof rec.customer_message === 'string'
                                    ? rec.customer_message
                                    : null;
                                const followupAction =
                                  typeof rec.followup_action === 'string'
                                    ? rec.followup_action
                                    : null;

                                if (!merchantBrief && !customerExplanation && !followupAction) {
                                  return null;
                                }

                                return (
                                  <div className="mt-2 space-y-1.5 rounded border border-gray-200 bg-white p-3 text-xs text-gray-700">
                                    <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                                      Plain-English AI Brief
                                    </p>
                                    {merchantBrief && (
                                      <p>
                                        <strong className="text-gray-900">Merchant Brief:</strong>{' '}
                                        {merchantBrief}
                                      </p>
                                    )}
                                    {customerExplanation && (
                                      <p>
                                        <strong className="text-gray-900">Customer Update:</strong>{' '}
                                        {customerExplanation}
                                      </p>
                                    )}
                                    {followupAction && (
                                      <p className="text-[11px] text-gray-600">
                                        <strong>Recommended Action:</strong> {followupAction}
                                      </p>
                                    )}
                                  </div>
                                );
                              })()}

                              <details className="mt-2">
                                <summary className="cursor-pointer font-mono text-[10px] font-medium text-gray-500 hover:text-gray-800">
                                  Technical Recommendation JSON
                                </summary>
                                <pre className="mt-1.5 max-h-48 overflow-auto rounded border border-gray-200 bg-white p-2.5 font-mono text-[11px] text-gray-800">
                                  {JSON.stringify(dec.recommendation, null, 2)}
                                </pre>
                              </details>
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                            Input Reference (Verified Context)
                          </p>
                          <pre className="mt-1.5 max-h-56 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] text-gray-800">
                            {JSON.stringify(exec.input_reference, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                            Node Output Payload
                          </p>
                          <pre className="mt-1.5 max-h-56 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] text-gray-800">
                            {JSON.stringify(exec.output_data, null, 2)}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="px-4 py-12 text-center text-xs text-gray-500">
              {loading ? 'Loading agent executions…' : 'No agent executions logged yet.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
