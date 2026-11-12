"""Standalone Carrier Logistics Simulator FastAPI service (Port 8203)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

SIMULATION_LABEL = "SIMULATED"

CarrierName = Literal["BlueDart", "Delhivery", "FedEx"]
ScenarioName = Literal[
    "NORMAL_TRANSIT",
    "PICKUP_OVERDUE",
    "CARRIER_STALLED",
    "DELIVERED_TO_MERCHANT",
    "LOST_PACKAGE",
]

NORMAL_PROGRESSION = [
    "PICKUP_SCHEDULED",
    "PICKED_UP",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED_TO_MERCHANT",
]

SCENARIO_STATUS_METADATA: dict[str, dict[str, Any]] = {
    "NORMAL_TRANSIT": {
        "delay_detected": False,
        "delay_reason": None,
        "location_template": "{origin} Sortation Hub",
        "description": "Shipment progressing normally through carrier network.",
    },
    "PICKUP_OVERDUE": {
        "status": "PICKUP_OVERDUE",
        "delay_detected": True,
        "delay_reason": "Carrier pickup missed scheduled SLA window by 36 hours.",
        "location_template": "{origin} Pickup Point",
        "description": "Scheduled reverse pickup did not occur within carrier SLA window.",
    },
    "CARRIER_STALLED": {
        "status": "CARRIER_STALLED",
        "delay_detected": True,
        "delay_reason": "No carrier scan recorded at regional transit hub for >48 hours.",
        "location_template": "Regional Transit Hub",
        "description": "Shipment stalled at intermediate sortation hub awaiting linehaul.",
    },
    "DELIVERED_TO_MERCHANT": {
        "status": "DELIVERED_TO_MERCHANT",
        "delay_detected": False,
        "delay_reason": None,
        "location_template": "{destination} Merchant Warehouse",
        "description": "Return parcel delivered to merchant warehouse dock.",
    },
    "LOST_PACKAGE": {
        "status": "LOST_PACKAGE",
        "delay_detected": True,
        "delay_reason": "Carrier declared parcel untraceable after hub exception.",
        "location_template": "Exception Investigation Desk",
        "description": "Carrier opened lost-in-transit claim after missed hub scans.",
    },
}


def _normalize_scenario(raw: str) -> str:
    normalized = raw.strip().upper()
    if normalized not in SCENARIO_STATUS_METADATA:
        allowed = ", ".join(sorted(SCENARIO_STATUS_METADATA))
        raise ValueError(f"Unsupported carrier scenario '{raw}'. Allowed: {allowed}")
    return normalized


class CreateShipmentRequest(BaseModel):
    return_case_id: str = Field(..., min_length=1, max_length=128)
    shipkart_order_id: int | str
    carrier_name: CarrierName = "BlueDart"
    tracking_number: str | None = Field(default=None, min_length=4, max_length=64)
    scenario: str = "NORMAL_TRANSIT"
    origin_city: str = Field(default="Bengaluru", min_length=1, max_length=80)
    destination_city: str = Field(default="Mumbai", min_length=1, max_length=80)

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        return _normalize_scenario(value)

    @field_validator("tracking_number")
    @classmethod
    def validate_tracking_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned.startswith("TRK-SK-"):
            raise ValueError("tracking_number must start with 'TRK-SK-'")
        return cleaned


class TriggerScenarioRequest(BaseModel):
    scenario: str
    note: str | None = None

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        return _normalize_scenario(value)


class CarrierEvent(BaseModel):
    event_id: str
    status: str
    location: str
    description: str
    occurred_at: datetime
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class ShipmentResponse(BaseModel):
    tracking_number: str
    return_case_id: str
    shipkart_order_id: int | str
    carrier_name: CarrierName
    scenario: ScenarioName
    current_status: str
    origin_city: str
    destination_city: str
    delay_detected: bool
    delay_reason: str | None
    pickup_at: datetime | None
    delivered_at: datetime | None
    events: list[CarrierEvent]
    created_at: datetime
    updated_at: datetime
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class ShipmentListResponse(BaseModel):
    shipments: list[ShipmentResponse]
    total: int
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


def _event_description(status_code: str, carrier_name: str, origin: str, dest: str) -> tuple[str, str]:
    descriptions = {
        "PICKUP_SCHEDULED": (
            f"{origin} Pickup Zone",
            f"Reverse pickup manifest created with {carrier_name}.",
        ),
        "PICKED_UP": (
            f"{origin} Pickup Zone",
            f"Parcel collected by {carrier_name} courier agent.",
        ),
        "IN_TRANSIT": (
            f"{origin} -> {dest} Linehaul",
            f"Parcel departed origin facility via {carrier_name} linehaul.",
        ),
        "OUT_FOR_DELIVERY": (
            f"{dest} Delivery Station",
            f"Parcel out for final delivery to merchant facility in {dest}.",
        ),
        "DELIVERED_TO_MERCHANT": (
            f"{dest} Merchant Warehouse",
            "Parcel delivered to merchant receiving dock (simulated POD).",
        ),
    }
    return descriptions.get(status_code, (origin, f"Carrier status updated to {status_code}."))


class CarrierStore:
    """Thread-safe in-memory carrier tracking store."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._shipments: dict[str, dict[str, Any]] = {}

    def _next_timestamp(self, record: dict[str, Any], hours: int = 6) -> datetime:
        events = record["events"]
        base = events[-1]["occurred_at"] if events else datetime.now(timezone.utc)
        return base + timedelta(hours=hours)

    def _append_event(
        self,
        record: dict[str, Any],
        *,
        event_status: str,
        location: str,
        description: str,
        occurred_at: datetime | None = None,
    ) -> None:
        ts = occurred_at or self._next_timestamp(record)
        record["events"].append(
            {
                "event_id": f"CAR-EVT-{uuid4().hex[:10].upper()}",
                "status": event_status,
                "location": location,
                "description": description,
                "occurred_at": ts,
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
            }
        )
        record["current_status"] = event_status
        record["updated_at"] = ts
        if event_status == "PICKED_UP" and record["pickup_at"] is None:
            record["pickup_at"] = ts
        if event_status == "DELIVERED_TO_MERCHANT":
            record["delivered_at"] = ts

    def create(self, payload: CreateShipmentRequest) -> dict[str, Any]:
        with self._lock:
            tracking = payload.tracking_number or f"TRK-SK-{uuid4().hex[:10].upper()}"
            if tracking in self._shipments:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Shipment '{tracking}' already exists",
                )

            now = datetime.now(timezone.utc)
            record: dict[str, Any] = {
                "tracking_number": tracking,
                "return_case_id": payload.return_case_id,
                "shipkart_order_id": payload.shipkart_order_id,
                "carrier_name": payload.carrier_name,
                "scenario": payload.scenario,
                "current_status": "PICKUP_SCHEDULED",
                "origin_city": payload.origin_city,
                "destination_city": payload.destination_city,
                "delay_detected": False,
                "delay_reason": None,
                "pickup_at": None,
                "delivered_at": None,
                "events": [],
                "created_at": now,
                "updated_at": now,
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
            }
            loc, desc = _event_description(
                "PICKUP_SCHEDULED",
                payload.carrier_name,
                payload.origin_city,
                payload.destination_city,
            )
            self._append_event(
                record,
                event_status="PICKUP_SCHEDULED",
                location=loc,
                description=desc,
                occurred_at=now,
            )

            if payload.scenario != "NORMAL_TRANSIT":
                self._apply_scenario_locked(record, payload.scenario)

            self._shipments[tracking] = record
            return dict(record)

    def _apply_scenario_locked(
        self,
        record: dict[str, Any],
        scenario: str,
        note: str | None = None,
    ) -> None:
        record["scenario"] = scenario
        meta = SCENARIO_STATUS_METADATA[scenario]
        record["delay_detected"] = bool(meta["delay_detected"])
        record["delay_reason"] = meta["delay_reason"]

        if scenario == "NORMAL_TRANSIT":
            if record["current_status"] in ("PICKUP_OVERDUE", "CARRIER_STALLED", "LOST_PACKAGE"):
                self._append_event(
                    record,
                    event_status="IN_TRANSIT",
                    location=f"{record['origin_city']} Sortation Hub",
                    description=note or "Carrier cleared exception and resumed normal transit.",
                )
            return

        target_status = meta["status"]
        location = meta["location_template"].format(
            origin=record["origin_city"],
            destination=record["destination_city"],
        )
        description = note or meta["description"]

        # Ensure realistic intermediate pickup scan before in-transit faults or delivery
        if target_status in ("CARRIER_STALLED", "LOST_PACKAGE", "DELIVERED_TO_MERCHANT"):
            if record["pickup_at"] is None:
                loc, desc = _event_description(
                    "PICKED_UP",
                    record["carrier_name"],
                    record["origin_city"],
                    record["destination_city"],
                )
                self._append_event(record, event_status="PICKED_UP", location=loc, description=desc)

        self._append_event(
            record,
            event_status=target_status,
            location=location,
            description=description,
        )

    def list_all(
        self,
        *,
        return_case_id: str | None = None,
        shipkart_order_id: str | None = None,
        carrier_name: str | None = None,
        shipment_status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._shipments.values())
            if return_case_id is not None:
                items = [s for s in items if s["return_case_id"] == return_case_id]
            if shipkart_order_id is not None:
                items = [s for s in items if str(s["shipkart_order_id"]) == str(shipkart_order_id)]
            if carrier_name is not None:
                items = [s for s in items if s["carrier_name"] == carrier_name]
            if shipment_status is not None:
                items = [s for s in items if s["current_status"] == shipment_status]
            return [dict(item) for item in items]

    def get(self, tracking_number: str) -> dict[str, Any]:
        with self._lock:
            record = self._shipments.get(tracking_number)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Shipment '{tracking_number}' not found",
                )
            return dict(record)

    def advance(self, tracking_number: str) -> dict[str, Any]:
        with self._lock:
            record = self._shipments.get(tracking_number)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Shipment '{tracking_number}' not found",
                )

            current = record["current_status"]
            scenario = record["scenario"]

            if scenario == "PICKUP_OVERDUE" and current == "PICKUP_SCHEDULED":
                self._apply_scenario_locked(record, "PICKUP_OVERDUE")
            elif scenario == "CARRIER_STALLED" and current in ("PICKUP_SCHEDULED", "PICKED_UP", "IN_TRANSIT"):
                self._apply_scenario_locked(record, "CARRIER_STALLED")
            elif scenario == "LOST_PACKAGE" and current != "LOST_PACKAGE":
                self._apply_scenario_locked(record, "LOST_PACKAGE")
            elif current in NORMAL_PROGRESSION:
                idx = NORMAL_PROGRESSION.index(current)
                if idx < len(NORMAL_PROGRESSION) - 1:
                    next_status = NORMAL_PROGRESSION[idx + 1]
                    loc, desc = _event_description(
                        next_status,
                        record["carrier_name"],
                        record["origin_city"],
                        record["destination_city"],
                    )
                    self._append_event(record, event_status=next_status, location=loc, description=desc)
            return dict(record)

    def trigger_scenario(
        self,
        tracking_number: str,
        payload: TriggerScenarioRequest,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._shipments.get(tracking_number)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Shipment '{tracking_number}' not found",
                )
            self._apply_scenario_locked(record, payload.scenario, note=payload.note)
            return dict(record)


store = CarrierStore()
app = FastAPI(
    title="Carrier Logistics Simulator",
    version="1.0.0",
    description="Simulated reverse-logistics carrier tracking service (port 8203).",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "carrier_simulator",
        "port": 8203,
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
    }


@app.post(
    "/carrier/shipments",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shipment(payload: CreateShipmentRequest) -> dict[str, Any]:
    return store.create(payload)


@app.get("/carrier/shipments", response_model=ShipmentListResponse)
def list_shipments(
    return_case_id: str | None = Query(default=None),
    shipkart_order_id: str | None = Query(default=None),
    carrier_name: str | None = Query(default=None),
    shipment_status: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    items = store.list_all(
        return_case_id=return_case_id,
        shipkart_order_id=shipkart_order_id,
        carrier_name=carrier_name,
        shipment_status=shipment_status,
    )
    return {
        "shipments": items,
        "total": len(items),
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
    }


@app.get("/carrier/shipments/{tracking_number}", response_model=ShipmentResponse)
def get_shipment(tracking_number: str) -> dict[str, Any]:
    return store.get(tracking_number)


@app.post("/carrier/shipments/{tracking_number}/advance", response_model=ShipmentResponse)
def advance_shipment(tracking_number: str) -> dict[str, Any]:
    return store.advance(tracking_number)


@app.post("/carrier/shipments/{tracking_number}/scenario", response_model=ShipmentResponse)
def trigger_shipment_scenario(
    tracking_number: str,
    payload: TriggerScenarioRequest,
) -> dict[str, Any]:
    return store.trigger_scenario(tracking_number, payload)
