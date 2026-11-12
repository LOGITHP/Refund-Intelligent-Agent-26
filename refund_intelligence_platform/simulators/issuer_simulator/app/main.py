"""Standalone Issuer / Bank Simulator FastAPI service (Port 8201, Blueprint Section 10.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

SIMULATION_LABEL = "SIMULATED"

CardNetwork = Literal["VISA", "MASTERCARD", "RUPAY"]

SCENARIO_ALIASES = {
    "MISSING_REFERENCE": "MISSING_TRANSACTION_REFERENCE",
}

ALL_SCENARIOS = {
    "NORMAL_POSTING",
    "DELAYED_POSTING",
    "REFERENCE_MISMATCH",
    "MISSING_TRANSACTION_REFERENCE",
    "DUPLICATE_CREDIT",
    "REPLACED_CARD",
    "ISSUER_UNAVAILABLE",
    "INSUFFICIENT_EVIDENCE",
}


def _normalize_scenario(raw: str) -> str:
    upper = raw.strip().upper()
    canonical = SCENARIO_ALIASES.get(upper, upper)
    if canonical not in ALL_SCENARIOS:
        allowed = ", ".join(sorted(ALL_SCENARIOS))
        raise ValueError(f"Unsupported issuer scenario '{raw}'. Allowed: {allowed}")
    return canonical


def _generate_arn(seed_hex: str | None = None) -> str:
    token = (seed_hex or uuid4().hex)[:12].upper()
    return f"ARN-SIM-{token}"


class CreateInquiryRequest(BaseModel):
    refund_case_id: str = Field(..., min_length=1, max_length=128)
    paypal_capture_id: str | None = Field(default=None, max_length=128)
    paypal_refund_id: str | None = Field(default=None, max_length=128)
    paypal_refund_status: str = Field(default="COMPLETED", max_length=40)
    institution_code: str = Field(default="HDFC_SIM", min_length=2, max_length=80)
    card_network: CardNetwork = "VISA"
    card_last4: str = Field(default="4242")
    amount: str | None = Field(default=None, max_length=32)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    scenario: str = "NORMAL_POSTING"

    @field_validator("card_last4")
    @classmethod
    def validate_masked_last4(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) != 4 or not cleaned.isdigit():
            raise ValueError("card_last4 must be exactly 4 digits (never submit full card PANs)")
        return cleaned

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        return _normalize_scenario(value)


class TriggerScenarioRequest(BaseModel):
    scenario: str
    note: str | None = None

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        return _normalize_scenario(value)


class IssuerTimelineEvent(BaseModel):
    event_id: str
    status: str
    posting_status: str
    description: str
    occurred_at: datetime
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class IssuerInquiryResponse(BaseModel):
    inquiry_id: str
    refund_case_id: str
    paypal_capture_id: str | None
    paypal_refund_id: str | None
    paypal_refund_status: str
    institution_code: str
    card_network: CardNetwork
    card_last4: str
    arn: str | None
    amount: str | None
    currency: str
    scenario: str
    status: str
    posting_status: str
    issuer_service_status: str
    credit_posted: bool
    delay_days: int
    expected_posting_window: str | None
    requires_manual_reconciliation: bool
    mismatch_reason: str | None
    duplicate_reference_id: str | None
    original_card_status: str
    rerouting_via_issuer: bool
    missing_fields: list[str]
    required_evidence: list[str]
    step_index: int
    created_at: datetime
    updated_at: datetime
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class IssuerInquiryListResponse(BaseModel):
    inquiries: list[IssuerInquiryResponse]
    total: int
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class IssuerTimelineResponse(BaseModel):
    inquiry_id: str
    scenario: str
    status: str
    events: list[IssuerTimelineEvent]
    is_simulated: bool = True
    simulation_label: str = SIMULATION_LABEL


class IssuerStore:
    """Thread-safe in-memory store simulating all 8 Blueprint Section 10.3 scenarios."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._inquiries: dict[str, dict[str, Any]] = {}
        self._timelines: dict[str, list[dict[str, Any]]] = {}

    def _next_ts(self, inquiry_id: str, hours: int = 12) -> datetime:
        events = self._timelines.get(inquiry_id, [])
        base = events[-1]["occurred_at"] if events else datetime.now(timezone.utc)
        return base + timedelta(hours=hours)

    def _append_event(
        self,
        inquiry_id: str,
        *,
        status_code: str,
        posting_status: str,
        description: str,
        occurred_at: datetime | None = None,
    ) -> None:
        ts = occurred_at or self._next_ts(inquiry_id)
        self._timelines.setdefault(inquiry_id, []).append(
            {
                "event_id": f"ISS-EVT-{uuid4().hex[:10].upper()}",
                "status": status_code,
                "posting_status": posting_status,
                "description": description,
                "occurred_at": ts,
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
            }
        )

    def _apply_scenario_state(
        self,
        record: dict[str, Any],
        scenario: str,
        *,
        note: str | None = None,
        initial: bool = False,
    ) -> None:
        record["scenario"] = scenario
        record["step_index"] = 0
        record["issuer_service_status"] = "AVAILABLE"
        record["credit_posted"] = False
        record["delay_days"] = 0
        record["expected_posting_window"] = "T+2 to T+3 business days"
        record["requires_manual_reconciliation"] = False
        record["mismatch_reason"] = None
        record["duplicate_reference_id"] = None
        record["original_card_status"] = "ACTIVE"
        record["rerouting_via_issuer"] = False
        record["missing_fields"] = []
        record["required_evidence"] = []

        if scenario == "NORMAL_POSTING":
            record["status"] = "INITIATED"
            record["posting_status"] = "PENDING_SETTLEMENT"
            record["arn"] = None
            desc = note or "Issuer inquiry opened for normal card refund posting."
        elif scenario == "DELAYED_POSTING":
            record["status"] = "DELAYED_POSTING"
            record["posting_status"] = "ISSUER_CREDIT_PENDING"
            record["arn"] = record["arn"] or _generate_arn()
            record["delay_days"] = 5
            record["expected_posting_window"] = "T+5 to T+7 business days (delayed)"
            desc = note or (
                "PayPal refund marked COMPLETED, but issuing bank posting remains pending at T+5d."
            )
        elif scenario == "REFERENCE_MISMATCH":
            record["status"] = "REFERENCE_MISMATCH"
            record["posting_status"] = "ON_HOLD"
            record["arn"] = record["arn"] or _generate_arn()
            record["requires_manual_reconciliation"] = True
            record["mismatch_reason"] = (
                "PayPal refund reference does not match issuer settlement trace ID."
            )
            desc = note or record["mismatch_reason"]
        elif scenario == "MISSING_TRANSACTION_REFERENCE":
            record["status"] = "MISSING_TRANSACTION_REFERENCE"
            record["posting_status"] = "UNTRACEABLE"
            record["arn"] = None
            record["missing_fields"] = ["arn", "acquirer_reference_number"]
            desc = note or "Issuer cannot locate settlement without ARN or acquirer trace."
        elif scenario == "DUPLICATE_CREDIT":
            record["status"] = "DUPLICATE_CREDIT"
            record["posting_status"] = "DUPLICATE_DETECTED"
            record["arn"] = record["arn"] or _generate_arn()
            record["credit_posted"] = True
            record["duplicate_reference_id"] = _generate_arn()
            record["requires_manual_reconciliation"] = True
            desc = note or "Duplicate refund credit detected on cardholder ledger."
        elif scenario == "REPLACED_CARD":
            record["status"] = "REPLACED_CARD"
            record["posting_status"] = "REROUTING_TO_REPLACEMENT_CARD"
            record["arn"] = record["arn"] or _generate_arn()
            record["original_card_status"] = "CLOSED_REPLACED"
            record["rerouting_via_issuer"] = True
            record["expected_posting_window"] = "T+5 to T+10 business days (card reroute)"
            desc = note or "Original card closed/replaced; issuing bank rerouting credit."
        elif scenario == "ISSUER_UNAVAILABLE":
            record["status"] = "UNAVAILABLE"
            record["posting_status"] = "UNKNOWN"
            record["issuer_service_status"] = "UNAVAILABLE"
            record["arn"] = None
            record["expected_posting_window"] = None
            desc = note or "Simulated issuer banking gateway is temporarily unavailable."
        else:  # INSUFFICIENT_EVIDENCE
            record["status"] = "INSUFFICIENT_EVIDENCE"
            record["posting_status"] = "AWAITING_EVIDENCE"
            record["required_evidence"] = ["paypal_refund_receipt", "arn_or_settlement_trace"]
            desc = note or "Issuer requires PayPal refund receipt and ARN trace to investigate."

        ts = record["created_at"] if initial else self._next_ts(record["inquiry_id"])
        record["updated_at"] = ts
        self._append_event(
            record["inquiry_id"],
            status_code=record["status"],
            posting_status=record["posting_status"],
            description=desc,
            occurred_at=ts,
        )

    def create(self, payload: CreateInquiryRequest) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(timezone.utc)
            inquiry_id = f"INQ-{uuid4().hex[:12].upper()}"
            record: dict[str, Any] = {
                "inquiry_id": inquiry_id,
                "refund_case_id": payload.refund_case_id,
                "paypal_capture_id": payload.paypal_capture_id,
                "paypal_refund_id": payload.paypal_refund_id,
                "paypal_refund_status": payload.paypal_refund_status,
                "institution_code": payload.institution_code,
                "card_network": payload.card_network,
                "card_last4": payload.card_last4,
                "arn": None,
                "amount": payload.amount,
                "currency": payload.currency.upper(),
                "scenario": payload.scenario,
                "status": "INITIATED",
                "posting_status": "PENDING_SETTLEMENT",
                "issuer_service_status": "AVAILABLE",
                "credit_posted": False,
                "delay_days": 0,
                "expected_posting_window": None,
                "requires_manual_reconciliation": False,
                "mismatch_reason": None,
                "duplicate_reference_id": None,
                "original_card_status": "ACTIVE",
                "rerouting_via_issuer": False,
                "missing_fields": [],
                "required_evidence": [],
                "step_index": 0,
                "created_at": now,
                "updated_at": now,
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
            }
            self._inquiries[inquiry_id] = record
            self._apply_scenario_state(record, payload.scenario, initial=True)
            return dict(record)

    def list_all(
        self,
        *,
        refund_case_id: str | None = None,
        paypal_refund_id: str | None = None,
        paypal_capture_id: str | None = None,
        scenario: str | None = None,
        inquiry_status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._inquiries.values())
            if refund_case_id is not None:
                items = [i for i in items if i["refund_case_id"] == refund_case_id]
            if paypal_refund_id is not None:
                items = [i for i in items if i["paypal_refund_id"] == paypal_refund_id]
            if paypal_capture_id is not None:
                items = [i for i in items if i["paypal_capture_id"] == paypal_capture_id]
            if scenario is not None:
                norm = _normalize_scenario(scenario)
                items = [i for i in items if i["scenario"] == norm]
            if inquiry_status is not None:
                items = [i for i in items if i["status"] == inquiry_status]
            return [dict(item) for item in items]

    def get(self, inquiry_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._inquiries.get(inquiry_id)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Issuer inquiry '{inquiry_id}' not found",
                )
            return dict(record)

    def get_timeline(self, inquiry_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._inquiries.get(inquiry_id)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Issuer inquiry '{inquiry_id}' not found",
                )
            return {
                "inquiry_id": inquiry_id,
                "scenario": record["scenario"],
                "status": record["status"],
                "events": list(self._timelines.get(inquiry_id, [])),
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
            }

    def advance(self, inquiry_id: str) -> dict[str, Any] | JSONResponse:
        with self._lock:
            record = self._inquiries.get(inquiry_id)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Issuer inquiry '{inquiry_id}' not found",
                )

            scenario = record["scenario"]
            if scenario == "ISSUER_UNAVAILABLE":
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error_code": "ISSUER_UNAVAILABLE",
                        "status": "UNAVAILABLE",
                        "posting_status": "UNKNOWN",
                        "inquiry_id": inquiry_id,
                        "message": "Simulated issuing bank gateway is unavailable (HTTP 503).",
                        "is_simulated": True,
                        "simulation_label": SIMULATION_LABEL,
                    },
                )

            step = record["step_index"] + 1
            record["step_index"] = step

            if scenario == "NORMAL_POSTING":
                if step == 1:
                    record["arn"] = record["arn"] or _generate_arn()
                    record["status"] = "SETTLEMENT_RECEIVED"
                    record["posting_status"] = "PENDING_POSTING"
                    desc = f"Issuer acknowledged settlement instruction ({record['arn']})."
                else:
                    record["status"] = "CREDIT_POSTED"
                    record["posting_status"] = "POSTED"
                    record["credit_posted"] = True
                    desc = f"Refund credit posted to synthetic {record['card_network']} ****{record['card_last4']}."
            elif scenario == "DELAYED_POSTING":
                if step == 1:
                    record["status"] = "DELAYED_POSTING"
                    record["posting_status"] = "ISSUER_CREDIT_PENDING"
                    record["delay_days"] = 6
                    record["credit_posted"] = False
                    desc = "Issuer settlement queue still delayed at T+6d; credit unconfirmed."
                else:
                    record["status"] = "CREDIT_POSTED"
                    record["posting_status"] = "POSTED"
                    record["credit_posted"] = True
                    desc = "Delayed issuer batch cleared; credit posted to synthetic card account."
            elif scenario == "REPLACED_CARD":
                if step == 1:
                    record["status"] = "CREDIT_POSTED"
                    record["posting_status"] = "POSTED_TO_REPLACEMENT_CARD"
                    record["credit_posted"] = True
                    desc = "Issuer completed reroute and posted credit to replacement card."
                else:
                    desc = "Credit already posted to replacement card."
            else:
                # Hold/error states remain blocked until scenario resolved or evidence provided
                desc = f"Inquiry remains in {record['status']} ({record['posting_status']})."

            ts = self._next_ts(inquiry_id)
            record["updated_at"] = ts
            self._append_event(
                inquiry_id,
                status_code=record["status"],
                posting_status=record["posting_status"],
                description=desc,
                occurred_at=ts,
            )
            return dict(record)

    def trigger_scenario(
        self,
        inquiry_id: str,
        payload: TriggerScenarioRequest,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._inquiries.get(inquiry_id)
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Issuer inquiry '{inquiry_id}' not found",
                )
            self._apply_scenario_state(record, payload.scenario, note=payload.note)
            return dict(record)


store = IssuerStore()
app = FastAPI(
    title="Issuer / Bank Simulator",
    version="1.0.0",
    description="Simulated card-issuer / bank refund posting inquiry service (port 8201).",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "issuer_simulator",
        "port": 8201,
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
    }


@app.post(
    "/issuer/inquiries",
    response_model=IssuerInquiryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_inquiry(payload: CreateInquiryRequest) -> dict[str, Any]:
    return store.create(payload)


@app.get("/issuer/inquiries", response_model=IssuerInquiryListResponse)
def list_inquiries(
    refund_case_id: str | None = Query(default=None),
    paypal_refund_id: str | None = Query(default=None),
    paypal_capture_id: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    inquiry_status: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    try:
        items = store.list_all(
            refund_case_id=refund_case_id,
            paypal_refund_id=paypal_refund_id,
            paypal_capture_id=paypal_capture_id,
            scenario=scenario,
            inquiry_status=inquiry_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "inquiries": items,
        "total": len(items),
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
    }


@app.get("/issuer/inquiries/{inquiry_id}", response_model=IssuerInquiryResponse)
def get_inquiry(inquiry_id: str) -> dict[str, Any]:
    return store.get(inquiry_id)


@app.get("/issuer/inquiries/{inquiry_id}/timeline", response_model=IssuerTimelineResponse)
def get_inquiry_timeline(inquiry_id: str) -> dict[str, Any]:
    return store.get_timeline(inquiry_id)


@app.post("/issuer/inquiries/{inquiry_id}/advance")
def advance_inquiry(inquiry_id: str):
    return store.advance(inquiry_id)


@app.post("/issuer/scenarios/{inquiry_id}/trigger", response_model=IssuerInquiryResponse)
def trigger_scenario(inquiry_id: str, payload: TriggerScenarioRequest) -> dict[str, Any]:
    return store.trigger_scenario(inquiry_id, payload)
