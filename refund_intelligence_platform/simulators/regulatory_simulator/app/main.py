"""Standalone India & USA Regulatory Rules Simulator FastAPI service (Port 8202, Blueprint 10.4)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.rules_catalog import (
    SIMULATION_DISCLAIMER,
    SIMULATION_LABEL,
    SUPPORTED_COUNTRIES,
    evaluate_transaction_context,
    list_rules,
)


class RegulatoryEvaluateRequest(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=128)
    refund_case_id: str | None = Field(default=None, max_length=128)
    merchant_country: str | None = Field(default=None, max_length=8)
    customer_country: str | None = Field(default=None, max_length=8)
    payment_provider: str = Field(default="PAYPAL", max_length=40)
    transaction_currency: str | None = Field(default=None, max_length=8)
    settlement_currency: str | None = Field(default=None, max_length=8)
    payment_route: str | None = Field(default=None, max_length=40)
    merchant_entity_type: str | None = Field(default=None, max_length=40)
    transaction_type: str = Field(default="REFUND", max_length=40)
    settlement_entity_confirmed: bool | None = None
    business_activity: str | None = Field(default=None, max_length=120)
    refund_delay_hours: float | None = Field(default=None, ge=0)
    evaluation_date: date | None = None


class GenerateReportRequest(BaseModel):
    case_id: str | None = Field(default=None, max_length=128)
    evaluation_id: str | None = Field(default=None, max_length=128)


class RegulatoryStore:
    """Thread-safe in-memory store for regulatory evaluations, obligations, and findings."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._evaluations_by_id: dict[str, dict[str, Any]] = {}
        self._eval_id_by_tx: dict[str, str] = {}
        self._obligations_by_case: dict[str, list[dict[str, Any]]] = {}
        self._violations: list[dict[str, Any]] = []

    def evaluate(self, payload: RegulatoryEvaluateRequest) -> dict[str, Any]:
        ctx = payload.model_dump()
        outcome = evaluate_transaction_context(ctx)
        now = datetime.now(timezone.utc)
        evaluation_id = str(uuid4())
        case_key = payload.refund_case_id or payload.transaction_id

        record = {
            "evaluation_id": evaluation_id,
            "transaction_id": payload.transaction_id,
            "refund_case_id": payload.refund_case_id,
            "jurisdiction": outcome["jurisdiction"],
            "status": outcome["status"],
            "matched_rules": outcome["matched_rules"],
            "unresolved_questions": outcome["unresolved_questions"],
            "obligations": outcome["obligations"],
            "rule_versions": outcome["rule_versions"],
            "transaction_context": ctx,
            "evaluated_at": now,
            "is_simulated": True,
            "simulation_label": SIMULATION_LABEL,
            "disclaimer": SIMULATION_DISCLAIMER,
        }

        with self._lock:
            self._evaluations_by_id[evaluation_id] = record
            self._eval_id_by_tx[payload.transaction_id] = evaluation_id
            self._obligations_by_case[case_key] = list(outcome["obligations"])
            for violation in outcome["violations"]:
                self._violations.append(
                    {
                        "violation_id": f"REG-VIO-{uuid4().hex[:10].upper()}",
                        "evaluation_id": evaluation_id,
                        "transaction_id": payload.transaction_id,
                        "case_id": case_key,
                        "detected_at": now,
                        "is_simulated": True,
                        "disclaimer": SIMULATION_DISCLAIMER,
                        **violation,
                    }
                )
            return dict(record)

    def get_by_transaction_or_eval(self, identifier: str) -> dict[str, Any]:
        with self._lock:
            if identifier in self._evaluations_by_id:
                return dict(self._evaluations_by_id[identifier])
            eval_id = self._eval_id_by_tx.get(identifier)
            if eval_id and eval_id in self._evaluations_by_id:
                return dict(self._evaluations_by_id[eval_id])
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No regulatory evaluation found for '{identifier}'",
            )

    def get_obligations(self, case_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._obligations_by_case.get(case_id, []))

    def get_violations(
        self,
        *,
        case_id: str | None = None,
        jurisdiction: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._violations)
            if case_id:
                items = [v for v in items if v["case_id"] == case_id]
            if jurisdiction:
                code = jurisdiction.strip().upper()
                items = [v for v in items if v["jurisdiction"] == code]
            return items

    def generate_report(self, payload: GenerateReportRequest) -> dict[str, Any]:
        with self._lock:
            if payload.evaluation_id:
                ev = self._evaluations_by_id.get(payload.evaluation_id)
                if not ev:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Evaluation '{payload.evaluation_id}' not found",
                    )
                evaluations = [dict(ev)]
            elif payload.case_id:
                evaluations = [
                    dict(ev)
                    for ev in self._evaluations_by_id.values()
                    if ev.get("refund_case_id") == payload.case_id
                    or ev.get("transaction_id") == payload.case_id
                ]
            else:
                evaluations = [dict(ev) for ev in self._evaluations_by_id.values()]

            violations = [
                v
                for v in self._violations
                if not payload.case_id or v["case_id"] == payload.case_id
            ]
            return {
                "report_id": f"REG-RPT-{uuid4().hex[:10].upper()}",
                "case_id": payload.case_id,
                "generated_at": datetime.now(timezone.utc),
                "evaluation_count": len(evaluations),
                "violation_count": len(violations),
                "evaluations": evaluations,
                "violations": violations,
                "is_simulated": True,
                "simulation_label": SIMULATION_LABEL,
                "disclaimer": SIMULATION_DISCLAIMER,
            }


store = RegulatoryStore()
app = FastAPI(
    title="India & USA Regulatory Rules Simulator",
    version="1.0.0",
    description="Versioned IN/US rules-evaluation simulator (port 8202, not legal advice).",
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "regulatory_simulator",
        "port": 8202,
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.post("/regulatory/evaluate")
def evaluate_regulatory(payload: RegulatoryEvaluateRequest) -> dict[str, Any]:
    return store.evaluate(payload)


@app.get("/regulatory/countries")
def get_countries() -> dict[str, Any]:
    return {
        "countries": SUPPORTED_COUNTRIES,
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.get("/regulatory/rules")
def get_rules(
    jurisdiction: str | None = Query(default=None),
    version: str | None = Query(default=None),
) -> dict[str, Any]:
    rules = list_rules(jurisdiction=jurisdiction, version=version)
    return {
        "rules": rules,
        "total": len(rules),
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.get("/regulatory/transactions/{transaction_or_eval_id}")
def get_transaction_evaluation(transaction_or_eval_id: str) -> dict[str, Any]:
    return store.get_by_transaction_or_eval(transaction_or_eval_id)


@app.get("/regulatory/obligations/{case_id}")
def get_obligations(case_id: str) -> dict[str, Any]:
    obligations = store.get_obligations(case_id)
    return {
        "case_id": case_id,
        "obligations": obligations,
        "total": len(obligations),
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.get("/regulatory/violations")
def get_violations(
    case_id: str | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
) -> dict[str, Any]:
    violations = store.get_violations(case_id=case_id, jurisdiction=jurisdiction)
    return {
        "violations": violations,
        "total": len(violations),
        "is_simulated": True,
        "simulation_label": SIMULATION_LABEL,
        "disclaimer": SIMULATION_DISCLAIMER,
    }


@app.post("/regulatory/reports/generate")
def generate_report(payload: GenerateReportRequest) -> dict[str, Any]:
    return store.generate_report(payload)
