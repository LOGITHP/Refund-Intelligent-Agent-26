import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot, Network, Plus, RefreshCw, Truck } from 'lucide-react';
import { OpsApiError, opsApi } from '../api/client';
import { SimulatedBadge } from '../components/SimulatedBadge';
import { ApiErrorBanner, StatusPill } from '../components/StatusPill';
import { useOpsFetch } from '../hooks/useOpsFetch';
import type {
  CarrierScenario,
  CarrierShipmentRecord,
  IntegrationHealth,
  RefundCaseSummary,
} from '../types/api';
import { formatTimestamp, shortId } from '../utils/format';

const CARRIER_SCENARIOS: Array<{ code: CarrierScenario; label: string; desc: string }> = [
  { code: 'NORMAL_TRANSIT', label: 'Normal Transit', desc: 'Clear exceptions / normal progression' },
  { code: 'PICKUP_OVERDUE', label: 'Pickup Overdue', desc: 'Missed SLA reverse pickup window' },
  { code: 'CARRIER_STALLED', label: 'Carrier Stalled', desc: 'No scan >48h at transit sortation hub' },
  { code: 'DELIVERED_TO_MERCHANT', label: 'Delivered to Merchant', desc: 'Warehouse dock POD received' },
  { code: 'LOST_PACKAGE', label: 'Lost Package', desc: 'Parcel untraceable exception' },
];

export function IntegrationsPage() {
  const [carrierFilter, setCarrierFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedTracking, setSelectedTracking] = useState<string | null>(null);
  const [noteInput, setNoteInput] = useState('');
  const [triggerBusy, setTriggerBusy] = useState<string | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [newCarrier, setNewCarrier] = useState<'BlueDart' | 'Delhivery' | 'FedEx'>('BlueDart');
  const [newOriginCity, setNewOriginCity] = useState('Bengaluru');
  const [newDestCity, setNewDestCity] = useState('Mumbai');
  const [newScenario, setNewScenario] = useState<CarrierScenario>('NORMAL_TRANSIT');
  const [createBusy, setCreateBusy] = useState(false);
  const [pipelineBusy, setPipelineBusy] = useState(false);

  const healthFetcher = useCallback(() => opsApi.getIntegrationsHealth(), []);
  const casesFetcher = useCallback(() => opsApi.listCases(), []);
  const shipmentsFetcher = useCallback(
    () =>
      opsApi.listCarrierShipments({
        carrier_name: carrierFilter || undefined,
        status: statusFilter || undefined,
      }),
    [carrierFilter, statusFilter]
  );

  const {
    data: health,
    loading: healthLoading,
    error: healthError,
    reload: reloadHealth,
  } = useOpsFetch<IntegrationHealth>(healthFetcher);

  const { data: availableCases } = useOpsFetch<RefundCaseSummary[]>(casesFetcher);

  const {
    data: shipments,
    loading: shipmentsLoading,
    error: shipmentsError,
    reload: reloadShipments,
  } = useOpsFetch<CarrierShipmentRecord[]>(shipmentsFetcher);

  const returnCases = (availableCases ?? []).filter((c) => Boolean(c.return_case_id));

  async function handleCreateShipment(e: React.FormEvent) {
    e.preventDefault();
    setTriggerMessage(null);
    setTriggerError(null);
    const chosenCase = returnCases.find((c) => c.id === selectedCaseId);
    if (!chosenCase || !chosenCase.return_case_id) {
      setTriggerError('Select a Refund Case that has an active Return Case first.');
      return;
    }
    setCreateBusy(true);
    try {
      const created = await opsApi.createCarrierShipment({
        return_case_id: chosenCase.return_case_id,
        shipkart_order_id: chosenCase.shipkart_order_id ?? 0,
        carrier_name: newCarrier,
        scenario: newScenario,
        origin_city: newOriginCity.trim() || 'Bengaluru',
        destination_city: newDestCity.trim() || 'Mumbai',
      });
      setSelectedTracking(created.tracking_number);
      setTriggerMessage(
        `Created simulated shipment ${created.tracking_number} for Order #${created.shipkart_order_id} (${created.current_status}).`
      );
      await reloadShipments();
    } catch (err) {
      setTriggerError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Failed to create shipment'
      );
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleRunPipelineForReturn(returnCaseId: string) {
    const matchedCase = (availableCases ?? []).find((c) => c.return_case_id === returnCaseId);
    if (!matchedCase) {
      setTriggerError('Could not find a matching Refund Case for this return shipment.');
      return;
    }
    setPipelineBusy(true);
    setTriggerMessage(null);
    setTriggerError(null);
    try {
      const res = await opsApi.investigateCase(matchedCase.id);
      setTriggerMessage(
        `3-Agent pipeline completed (${res.status}) for Order #${matchedCase.shipkart_order_id ?? '—'} and synced updated explanation to Shipkart.`
      );
    } catch (err) {
      setTriggerError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Failed to run AI pipeline'
      );
    } finally {
      setPipelineBusy(false);
    }
  }

  async function handleTriggerCarrier(trackingNumber: string, scenario: CarrierScenario) {
    setTriggerBusy(scenario);
    setTriggerMessage(null);
    setTriggerError(null);
    try {
      const updated = await opsApi.triggerCarrierScenario(trackingNumber, {
        scenario,
        note: noteInput.trim() || undefined,
      });
      setTriggerMessage(
        `Carrier shipment ${updated.tracking_number} transitioned to ${updated.current_status} (${updated.scenario}).`
      );
      setNoteInput('');
      await reloadShipments();
    } catch (err) {
      setTriggerError(
        err instanceof OpsApiError ? `${err.code}: ${err.message}` : 'Failed to trigger scenario'
      );
    } finally {
      setTriggerBusy(null);
    }
  }

  const activeShipment =
    shipments?.find((s) => s.tracking_number === selectedTracking) ?? shipments?.[0] ?? null;

  const combinedError = healthError || shipmentsError;

  return (
    <div className="space-y-5 apple-anim-fade">
      <div className="bg-white p-4 rounded shadow-sm border border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-gray-800">
            Integrations Health &amp; Carrier Delay Simulator
          </h1>
          <p className="mt-0.5 text-xs text-gray-500">
            Live connector telemetry across core infrastructure, external PayPal/Shipkart rails, and
            simulated logistics/banking/regulatory endpoints.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void reloadHealth();
            void reloadShipments();
          }}
          className="inline-flex items-center gap-1.5 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 hover:bg-gray-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${healthLoading || shipmentsLoading ? 'animate-spin' : ''}`}
          />
          Check All Connectors
        </button>
      </div>

      {combinedError && (
        <ApiErrorBanner
          message={combinedError.message}
          status={combinedError.status}
          onRetry={() => {
            void reloadHealth();
            void reloadShipments();
          }}
        />
      )}

      {/* Connector Health Matrix */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-gray-700" />
            <h2 className="text-sm font-bold text-gray-800">Connector Health Matrix</h2>
          </div>
          {health && (
            <div className="flex items-center gap-2">
              <StatusPill value={health.overall_status} />
              <span className="font-mono text-[11px] text-gray-500">
                {formatTimestamp(health.checked_at)}
              </span>
            </div>
          )}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {health?.connectors && health.connectors.length > 0 ? (
            health.connectors.map((conn) => (
              <div
                key={conn.connector_id}
                className="flex flex-col justify-between rounded border border-gray-200 bg-gray-50 p-3.5"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-xs font-semibold text-gray-900">{conn.name}</p>
                      <p className="font-mono text-[10px] text-gray-500">
                        {conn.category} • {conn.endpoint}
                      </p>
                    </div>
                    {conn.is_simulated && <SimulatedBadge compact />}
                  </div>
                  <p className="mt-2 text-[11px] text-gray-600">{conn.details}</p>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-gray-200 pt-2">
                  <StatusPill value={conn.status} />
                  <span className="font-mono text-[10px] text-gray-500">
                    {conn.latency_ms !== null ? `${conn.latency_ms} ms` : '—'}
                  </span>
                </div>
              </div>
            ))
          ) : (
            <div className="col-span-full py-6 text-center text-xs text-gray-500">
              {healthLoading ? 'Probing platform connectors…' : 'No connector health rows returned.'}
            </div>
          )}
        </div>
      </div>

      {/* Carrier Delay Simulator Panel */}
      <div className="rounded border border-gray-100 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-4">
          <div className="flex items-center gap-2.5">
            <Truck className="h-5 w-5 text-shipkart-blue" />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-gray-800">
                  Carrier Reverse-Logistics Delay Simulator
                </h2>
                <SimulatedBadge />
              </div>
              <p className="text-xs text-gray-600">
                Trigger synthetic reverse-pickup, hub stall, lost parcel, or delivery POD events on
                tracked shipments.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              value={carrierFilter}
              onChange={(e) => setCarrierFilter(e.target.value)}
              className="rounded border border-gray-200 px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">All Carriers</option>
              <option value="BlueDart">BlueDart</option>
              <option value="Delhivery">Delhivery</option>
              <option value="FedEx">FedEx</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="rounded border border-gray-200 px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">All Statuses</option>
              <option value="PICKUP_SCHEDULED">PICKUP_SCHEDULED</option>
              <option value="PICKUP_OVERDUE">PICKUP_OVERDUE</option>
              <option value="IN_TRANSIT">IN_TRANSIT</option>
              <option value="CARRIER_STALLED">CARRIER_STALLED</option>
              <option value="DELIVERED_TO_MERCHANT">DELIVERED_TO_MERCHANT</option>
              <option value="LOST_PACKAGE">LOST_PACKAGE</option>
            </select>
          </div>
        </div>

        {triggerMessage && (
          <div className="mt-4 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 font-mono text-xs text-emerald-900">
            {triggerMessage}
          </div>
        )}
        {triggerError && (
          <div className="mt-4 rounded border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-800">
            {triggerError}
          </div>
        )}

        {/* Quick Create Simulated Carrier Shipment */}
        <form
          onSubmit={(e) => void handleCreateShipment(e)}
          className="mt-4 grid grid-cols-1 gap-3 rounded border border-gray-200 bg-gray-50 p-3.5 sm:grid-cols-2 lg:grid-cols-6"
        >
          <div className="lg:col-span-2">
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Link to Return / Refund Case *
            </label>
            <select
              value={selectedCaseId}
              onChange={(e) => setSelectedCaseId(e.target.value)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="">Select a return case…</option>
              {returnCases.map((c) => (
                <option key={c.id} value={c.id}>
                  Order #{c.shipkart_order_id ?? '—'} • Return #{c.shipkart_return_id ?? '—'} (
                  {shortId(c.return_case_id ?? c.id, 6)})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Carrier
            </label>
            <select
              value={newCarrier}
              onChange={(e) => setNewCarrier(e.target.value as 'BlueDart' | 'Delhivery' | 'FedEx')}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              <option value="BlueDart">BlueDart</option>
              <option value="Delhivery">Delhivery</option>
              <option value="FedEx">FedEx</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Initial State
            </label>
            <select
              value={newScenario}
              onChange={(e) => setNewScenario(e.target.value as CarrierScenario)}
              className="mt-1 w-full rounded border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 focus:border-shipkart-blue focus:outline-none"
            >
              {CARRIER_SCENARIOS.map((sc) => (
                <option key={sc.code} value={sc.code}>
                  {sc.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-gray-600">
              Origin → Warehouse
            </label>
            <div className="mt-1 flex gap-1.5">
              <input
                type="text"
                value={newOriginCity}
                onChange={(e) => setNewOriginCity(e.target.value)}
                placeholder="From"
                className="w-1/2 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs focus:border-shipkart-blue focus:outline-none"
              />
              <input
                type="text"
                value={newDestCity}
                onChange={(e) => setNewDestCity(e.target.value)}
                placeholder="To"
                className="w-1/2 rounded border border-gray-200 bg-white px-2 py-1.5 text-xs focus:border-shipkart-blue focus:outline-none"
              />
            </div>
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={createBusy}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded bg-shipkart-blue px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-shipkart-blueHover disabled:opacity-50"
            >
              <Plus className="h-3.5 w-3.5" />
              {createBusy ? 'Creating…' : 'Create Shipment'}
            </button>
          </div>
        </form>

        <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Shipment List */}
          <div className="space-y-2 lg:col-span-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">
              Simulated Shipments ({shipments?.length ?? 0})
            </p>
            <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {shipments && shipments.length > 0 ? (
                shipments.map((s) => {
                  const isSelected = activeShipment?.tracking_number === s.tracking_number;
                  return (
                    <button
                      type="button"
                      key={s.tracking_number}
                      onClick={() => setSelectedTracking(s.tracking_number)}
                      className={`w-full rounded border p-3 text-left transition-colors ${
                        isSelected
                          ? 'border-shipkart-blue bg-blue-50/40'
                          : 'border-gray-200 bg-white hover:border-shipkart-blue hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs font-semibold text-gray-900">
                          {s.tracking_number}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <SimulatedBadge compact />
                          <StatusPill value={s.current_status} />
                        </div>
                      </div>
                      <p className="mt-1 font-mono text-[11px] text-gray-600">
                        {s.carrier_name} • {s.origin_city} → {s.destination_city} • SK Order #
                        {s.shipkart_order_id}
                      </p>
                      {s.delay_detected && s.delay_reason && (
                        <p className="mt-1 text-[11px] text-rose-700">{s.delay_reason}</p>
                      )}
                    </button>
                  );
                })
              ) : (
                <div className="rounded border border-dashed border-gray-200 p-6 text-center text-xs text-gray-500">
                  {shipmentsLoading ? 'Loading shipments…' : 'No simulated shipments found.'}
                </div>
              )}
            </div>
          </div>

          {/* Scenario Trigger & Event Trace */}
          <div className="rounded border border-gray-200 bg-gray-50 p-4 lg:col-span-7">
            {activeShipment ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-gray-900">
                        {activeShipment.tracking_number}
                      </span>
                      <SimulatedBadge compact />
                    </div>
                    <p className="font-mono text-[11px] text-gray-500">
                      Return Case: {activeShipment.return_case_id} • Scenario:{' '}
                      {activeShipment.scenario}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill value={activeShipment.current_status} />
                    {(() => {
                      const linkedCase = (availableCases ?? []).find(
                        (c) => c.return_case_id === activeShipment.return_case_id
                      );
                      if (!linkedCase) return null;
                      return (
                        <>
                          <button
                            type="button"
                            disabled={pipelineBusy}
                            onClick={() => void handleRunPipelineForReturn(activeShipment.return_case_id)}
                            className="inline-flex items-center gap-1 rounded bg-shipkart-blue px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-shipkart-blueHover disabled:opacity-50"
                          >
                            <Bot className="h-3 w-3" />
                            {pipelineBusy ? 'Syncing AI…' : 'Re-run AI Pipeline'}
                          </button>
                          <Link
                            to={`/operations/cases?caseId=${encodeURIComponent(linkedCase.id)}`}
                            className="rounded border border-gray-300 bg-white px-2.5 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-100"
                          >
                            Inspect Case
                          </Link>
                        </>
                      );
                    })()}
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                    Optional Carrier Operator Note
                  </label>
                  <input
                    type="text"
                    value={noteInput}
                    onChange={(e) => setNoteInput(e.target.value)}
                    placeholder="e.g., Hub linehaul weather hold in Pune"
                    className="mt-1 w-full rounded border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-900 focus:border-shipkart-blue focus:outline-none"
                  />
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                    Trigger Carrier Scenario
                  </p>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {CARRIER_SCENARIOS.map((sc) => (
                      <button
                        type="button"
                        key={sc.code}
                        disabled={triggerBusy !== null}
                        onClick={() =>
                          void handleTriggerCarrier(activeShipment.tracking_number, sc.code)
                        }
                        className="rounded border border-gray-200 bg-white p-2.5 text-left hover:border-shipkart-blue disabled:opacity-50"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[11px] font-semibold text-gray-900">
                            {sc.code}
                          </span>
                          {triggerBusy === sc.code && (
                            <span className="font-mono text-[10px] text-amber-700">Running…</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-[11px] text-gray-500">{sc.desc}</p>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-600">
                    Carrier Scan Events ({activeShipment.events.length})
                  </p>
                  <div className="mt-2 max-h-48 space-y-1.5 overflow-y-auto">
                    {activeShipment.events.map((ev) => (
                      <div
                        key={ev.event_id}
                        className="rounded border border-gray-200 bg-white px-3 py-2 text-xs"
                      >
                        <div className="flex items-center justify-between font-mono text-[11px]">
                          <span className="font-semibold text-gray-900">{ev.status}</span>
                          <span className="text-gray-500">{formatTimestamp(ev.occurred_at)}</span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-gray-700">
                          [{ev.location}] {ev.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="py-12 text-center text-xs text-gray-500">
                Select a simulated shipment on the left to trigger carrier delay scenarios.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
