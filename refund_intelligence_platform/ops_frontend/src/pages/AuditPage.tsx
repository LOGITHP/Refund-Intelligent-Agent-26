import { useCallback, useState } from 'react';
import { ChevronDown, ChevronRight, FileSearch, Lock, RefreshCw } from 'lucide-react';
import { opsApi } from '../api/client';
import { ApiErrorBanner } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type { AuditLogRecord } from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

export function AuditPage() {
  const [resourceType, setResourceType] = useState('');
  const [actorType, setActorType] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [resourceIdFilter, setResourceIdFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetcher = useCallback(
    () =>
      opsApi.listAuditLogs({
        resource_type: resourceType || undefined,
        actor_type: actorType || undefined,
        action: actionFilter || undefined,
        resource_id: resourceIdFilter || undefined,
      }),
    [resourceType, actorType, actionFilter, resourceIdFilter]
  );

  const { data: logs, loading, error, reload } = useOpsFetch<AuditLogRecord[]>(fetcher);

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-gray-800">
              Immutable Audit Log Explorer
            </h1>
            <span className="inline-flex items-center gap-1 rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-shipkart-blue">
              <Lock className="h-3 w-3" />
              Append-Only
            </span>
          </div>
          <p className="mt-0.5 text-xs text-gray-500">
            ORM-protected append-only <span className="font-semibold text-gray-700">audit_logs</span>{' '}
            with secret/PII-redacted before/after JSON state diffs.
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

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 rounded border border-gray-100 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
        <select
          value={resourceType}
          onChange={(e) => setResourceType(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Resource Types</option>
          <option value="refund_case">refund_case</option>
          <option value="return_case">return_case</option>
          <option value="refund_approval">refund_approval</option>
          <option value="refund_transaction">refund_transaction</option>
          <option value="evidence">evidence</option>
        </select>

        <select
          value={actorType}
          onChange={(e) => setActorType(e.target.value)}
          className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
        >
          <option value="">All Actor Types</option>
          <option value="MERCHANT">MERCHANT</option>
          <option value="CUSTOMER">CUSTOMER</option>
          <option value="AGENT">AGENT</option>
          <option value="OPERATIONS">OPERATIONS</option>
          <option value="SYSTEM">SYSTEM</option>
        </select>

        <input
          type="text"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          placeholder="Filter action (e.g. COMPLIANCE_BLOCKED)"
          className="rounded border border-gray-200 px-3 py-2 font-mono text-xs text-gray-900 placeholder:text-gray-400 focus:border-shipkart-blue focus:outline-none"
        />

        <input
          type="text"
          value={resourceIdFilter}
          onChange={(e) => setResourceIdFilter(e.target.value)}
          placeholder="Filter Resource UUID…"
          className="rounded border border-gray-200 px-3 py-2 font-mono text-xs text-gray-900 placeholder:text-gray-400 focus:border-shipkart-blue focus:outline-none"
        />
      </div>

      {error && (
        <ApiErrorBanner
          message={error.message}
          status={error.status}
          onRetry={() => void reload()}
        />
      )}

      {/* Audit Entries */}
      <div className="overflow-hidden rounded border border-gray-100 bg-white shadow-sm">
        <div className="divide-y divide-gray-100">
          {logs && logs.length > 0 ? (
            logs.map((log) => {
              const isOpen = expandedId === log.id;
              return (
                <div key={log.id} className="p-4">
                  <div
                    onClick={() => setExpandedId(isOpen ? null : log.id)}
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
                          <FileSearch className="h-3.5 w-3.5 text-gray-500" />
                          <span className="font-mono text-xs font-semibold text-gray-900">
                            {log.action}
                          </span>
                          <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-[10px] font-medium text-gray-700">
                            {log.actor_type}
                            {log.shipkart_actor_id !== null ? ` #${log.shipkart_actor_id}` : ''}
                          </span>
                          <span className="rounded border border-gray-200 px-2 py-0.5 font-mono text-[10px] text-gray-600">
                            {log.resource_type}: {shortId(log.resource_id, 10)}
                          </span>
                        </div>
                        <p className="mt-1 font-mono text-[11px] text-gray-500">
                          {formatTimestamp(log.created_at)}
                          {log.ip_address ? ` • IP ${log.ip_address}` : ''}
                        </p>
                      </div>
                    </div>

                    <span className="font-mono text-[11px] font-medium text-shipkart-blue">
                      {isOpen ? 'Hide JSON diff' : 'Inspect JSON diff'}
                    </span>
                  </div>

                  {isOpen && (
                    <div className="mt-4 grid grid-cols-1 gap-4 border-t border-gray-100 pt-4 lg:grid-cols-2">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                          Before State (Redacted)
                        </p>
                        <pre className="mt-1.5 max-h-64 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] text-gray-800">
                          {log.before_state ? JSON.stringify(log.before_state, null, 2) : 'null'}
                        </pre>
                      </div>
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                          After State (Redacted)
                        </p>
                        <pre className="mt-1.5 max-h-64 overflow-auto rounded border border-gray-200 bg-gray-50 p-3 font-mono text-[11px] text-gray-800">
                          {log.after_state ? JSON.stringify(log.after_state, null, 2) : 'null'}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="px-4 py-12 text-center text-xs text-gray-500">
              {loading ? 'Loading immutable audit trail…' : 'No audit log records match your filter.'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
