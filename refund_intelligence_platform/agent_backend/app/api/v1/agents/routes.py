"""LangGraph 3-Agent intake, investigation, resolution & execution inspection routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_refund_intelligence_pipeline
from app.agents.intake_agent import intake_node
from app.agents.state import RefundAgentState
from app.api.v1 import (
    assert_customer_case_access,
    assert_merchant_case_access,
    get_carrier_client,
    get_issuer_client,
    get_paypal_client,
    get_regulatory_client,
    get_shipkart_client,
    resolve_refund_case,
    resolve_return_case,
    serialize_decision,
    serialize_execution,
)
from app.core.logging_redact import redact_sensitive_data
from app.core.security import require_roles
from app.db.models import AgentDecision, AgentExecution, Evidence, RefundCase, ReturnCase
from app.db.session import get_db
from app.integrations.paypal_client import PayPalClient
from app.integrations.shipkart_client import ShipkartBridgeClient
from app.integrations.simulators import (
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
)
from app.services.eta_service import ETAService
from app.services.shipkart_sync_service import sync_decision_to_shipkart
from app.services.timeline_service import ensure_utc

router = APIRouter(prefix="/agents", tags=["Agents"])

_AGENT_ROLES = require_roles("customer", "merchant", "operations", "admin", "service")


class AgentIntakeRequest(BaseModel):
    case_id: str | None = None
    refund_case_id: str | None = None
    return_case_id: str | None = None
    customer_query: str | None = None


class AgentRunRequest(BaseModel):
    customer_query: str | None = None


def _enforce_refund_case_ownership(
    db: Session,
    refund_case: RefundCase,
    actor: dict[str, Any],
) -> None:
    role = str(actor.get("role") or "").strip().lower()
    if role == "customer":
        assert_customer_case_access(db, refund_case, actor)
    elif role == "merchant":
        assert_merchant_case_access(db, refund_case, actor)


def _enforce_return_case_ownership(
    db: Session,
    return_case: ReturnCase,
    actor: dict[str, Any],
) -> None:
    role = str(actor.get("role") or "").strip().lower()
    if role == "customer":
        assert_customer_case_access(db, return_case, actor)
    elif role == "merchant":
        assert_merchant_case_access(db, return_case, actor)


def _serialize_execution_with_decisions(db: Session, ex: AgentExecution) -> dict[str, Any]:
    payload = serialize_execution(ex)
    latency_ms: int | None = None
    if ex.started_at is not None and ex.completed_at is not None:
        delta = ensure_utc(ex.completed_at) - ensure_utc(ex.started_at)
        latency_ms = max(0, int(delta.total_seconds() * 1000))
    payload["latency_ms"] = latency_ms

    decisions = list(
        db.scalars(
            select(AgentDecision)
            .where(AgentDecision.execution_id == ex.id)
            .order_by(AgentDecision.created_at.asc())
        ).all()
    )
    payload["decisions"] = [serialize_decision(d) for d in decisions]
    return payload


def _build_clients_dict(
    carrier_client: CarrierSimulatorClient,
    issuer_client: IssuerSimulatorClient,
    regulatory_client: RegulatorySimulatorClient,
    paypal_client: PayPalClient,
    shipkart_client: ShipkartBridgeClient,
) -> dict[str, Any]:
    return {
        "carrier_client": carrier_client,
        "issuer_client": issuer_client,
        "regulatory_client": regulatory_client,
        "paypal_client": paypal_client,
        "shipkart_client": shipkart_client,
    }


def _load_pipeline_executions(
    db: Session,
    refund_case_id: uuid.UUID,
    execution_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    record_ids: list[uuid.UUID] = []
    for rec in execution_records:
        raw_id = rec.get("execution_id")
        if not raw_id:
            continue
        try:
            record_ids.append(uuid.UUID(str(raw_id)))
        except ValueError:
            continue

    if record_ids:
        rows = list(
            db.scalars(select(AgentExecution).where(AgentExecution.id.in_(record_ids))).all()
        )
        by_id = {row.id: row for row in rows}
        ordered = [by_id[eid] for eid in record_ids if eid in by_id]
        return [_serialize_execution_with_decisions(db, ex) for ex in ordered]

    rows = list(
        db.scalars(
            select(AgentExecution)
            .where(AgentExecution.case_id == refund_case_id)
            .order_by(AgentExecution.started_at.desc())
            .limit(3)
        ).all()
    )
    rows.reverse()
    return [_serialize_execution_with_decisions(db, ex) for ex in rows]


@router.post("/intake")
def run_agent_intake(
    payload: AgentIntakeRequest,
    actor: dict[str, Any] = Depends(_AGENT_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
    paypal_client: PayPalClient = Depends(get_paypal_client),
    shipkart_client: ShipkartBridgeClient = Depends(get_shipkart_client),
) -> dict[str, Any]:
    """Run Node 1 (Intake & Evidence Agent) for a case with strict ownership checks."""
    refund_ref = payload.refund_case_id or payload.case_id
    refund_case: RefundCase | None = None
    if refund_ref:
        refund_case = resolve_refund_case(db, refund_ref)
    elif payload.return_case_id:
        return_case = resolve_return_case(db, payload.return_case_id)
        _enforce_return_case_ownership(db, return_case, actor)
        refund_case = db.scalar(
            select(RefundCase)
            .where(RefundCase.return_case_id == return_case.id)
            .order_by(RefundCase.opened_at.desc())
        )
        if refund_case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No paired refund case found for this return case",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="One of refund_case_id, case_id, or return_case_id is required",
        )

    _enforce_refund_case_ownership(db, refund_case, actor)

    evidence_rows_by_id: dict[uuid.UUID, Evidence] = {
        ev.id: ev
        for ev in db.scalars(select(Evidence).where(Evidence.refund_case_id == refund_case.id)).all()
    }
    if refund_case.return_case_id is not None:
        for ev in db.scalars(
            select(Evidence).where(Evidence.return_case_id == refund_case.return_case_id)
        ).all():
            evidence_rows_by_id[ev.id] = ev

    initial_state: RefundAgentState = {
        "refund_case_id": str(refund_case.id),
        "return_case_id": str(refund_case.return_case_id) if refund_case.return_case_id else None,
        "shipkart_order_id": refund_case.shipkart_order_id,
        "shipkart_customer_id": refund_case.shipkart_customer_id,
        "shipkart_merchant_id": refund_case.shipkart_merchant_id,
        "customer_message": str(payload.customer_query or ""),
        "untrusted_ocr_texts": [],
        "evidence_items": [
            {
                "evidence_id": str(ev.id),
                "file_name": ev.file_name,
                "mime_type": ev.mime_type,
                "verification_status": ev.verification_status,
                "sha256_hash": ev.sha256_hash,
                "extracted_metadata": redact_sensitive_data(dict(ev.extracted_metadata or {})),
            }
            for ev in sorted(evidence_rows_by_id.values(), key=lambda e: str(e.id))
        ],
        "intake_result": None,
        "investigation_result": None,
        "resolution_result": None,
        "execution_records": [],
        "errors": [],
    }

    clients = _build_clients_dict(
        carrier_client,
        issuer_client,
        regulatory_client,
        paypal_client,
        shipkart_client,
    )
    out = intake_node(initial_state, config={"configurable": {"db": db, "clients": clients}})
    db.commit()
    db.refresh(refund_case)

    exec_records = list(out.get("execution_records") or [])
    executions = _load_pipeline_executions(db, refund_case.id, exec_records)

    return {
        "case_id": str(refund_case.id),
        "refund_case_id": str(refund_case.id),
        "status": refund_case.status,
        "intake_result": out.get("intake_result"),
        "executions": executions,
        "execution_records": exec_records,
        "errors": list(out.get("errors") or []),
    }


def _execute_full_pipeline_endpoint(
    case_id: str,
    payload: AgentRunRequest | None,
    actor: dict[str, Any],
    db: Session,
    carrier_client: CarrierSimulatorClient,
    issuer_client: IssuerSimulatorClient,
    regulatory_client: RegulatorySimulatorClient,
    paypal_client: PayPalClient,
    shipkart_client: ShipkartBridgeClient,
    *,
    refresh_eta: bool = False,
) -> dict[str, Any]:
    refund_case = resolve_refund_case(db, case_id)
    _enforce_refund_case_ownership(db, refund_case, actor)

    clients = _build_clients_dict(
        carrier_client,
        issuer_client,
        regulatory_client,
        paypal_client,
        shipkart_client,
    )
    result = run_refund_intelligence_pipeline(
        db,
        refund_case.id,
        customer_query=payload.customer_query if payload else None,
        clients=clients,
    )
    if refresh_eta:
        ETAService().compute_and_persist_eta(db, refund_case.id)
        db.commit()
        db.refresh(refund_case)

    shipkart_synced = sync_decision_to_shipkart(db, refund_case, result, shipkart_client=shipkart_client)

    exec_records = list(result.get("execution_records") or [])
    executions = _load_pipeline_executions(db, refund_case.id, exec_records)
    resolution = result.get("resolution_result") or {}
    summary = (
        resolution.get("merchant_brief")
        or resolution.get("customer_explanation")
        or resolution.get("customer_message")
        or resolution.get("rationale")
        or resolution.get("recommended_action")
    )

    return {
        "case_id": str(refund_case.id),
        "refund_case_id": str(refund_case.id),
        "status": result.get("status") or refund_case.status,
        "summary": summary,
        "shipkart_synced": shipkart_synced,
        "executions": executions,
        "execution_records": exec_records,
        "intake_result": result.get("intake_result"),
        "investigation_result": result.get("investigation_result"),
        "resolution_result": result.get("resolution_result"),
        "errors": list(result.get("errors") or []),
    }


@router.post("/investigate/{case_id}")
def investigate_case_with_agents(
    case_id: str,
    payload: AgentRunRequest | None = Body(default=None),
    actor: dict[str, Any] = Depends(_AGENT_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
    paypal_client: PayPalClient = Depends(get_paypal_client),
    shipkart_client: ShipkartBridgeClient = Depends(get_shipkart_client),
) -> dict[str, Any]:
    """Execute the 3-agent LangGraph investigation pipeline (REF-001 always enforced)."""
    return _execute_full_pipeline_endpoint(
        case_id,
        payload,
        actor,
        db,
        carrier_client,
        issuer_client,
        regulatory_client,
        paypal_client,
        shipkart_client,
        refresh_eta=False,
    )


@router.post("/resolve/{case_id}")
def resolve_case_with_agents(
    case_id: str,
    payload: AgentRunRequest | None = Body(default=None),
    actor: dict[str, Any] = Depends(_AGENT_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
    paypal_client: PayPalClient = Depends(get_paypal_client),
    shipkart_client: ShipkartBridgeClient = Depends(get_shipkart_client),
) -> dict[str, Any]:
    """Execute resolution plan pipeline & refresh deterministic ETA snapshot (never bypasses REF-001)."""
    return _execute_full_pipeline_endpoint(
        case_id,
        payload,
        actor,
        db,
        carrier_client,
        issuer_client,
        regulatory_client,
        paypal_client,
        shipkart_client,
        refresh_eta=True,
    )


@router.get("/executions/{execution_id}")
def get_agent_execution(
    execution_id: str,
    actor: dict[str, Any] = Depends(_AGENT_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve a single persisted AgentExecution and its AgentDecisions with ownership guards."""
    try:
        exec_uuid = uuid.UUID(execution_id.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent execution not found",
        ) from exc

    ex = db.get(AgentExecution, exec_uuid)
    if ex is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent execution not found",
        )

    refund_case = db.get(RefundCase, ex.case_id)
    if refund_case is not None:
        _enforce_refund_case_ownership(db, refund_case, actor)
    else:
        return_case = db.get(ReturnCase, ex.case_id)
        if return_case is not None:
            _enforce_return_case_ownership(db, return_case, actor)

    return _serialize_execution_with_decisions(db, ex)


@router.get("/decisions/{case_id}")
def get_case_agent_decisions(
    case_id: str,
    actor: dict[str, Any] = Depends(_AGENT_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve all AgentExecutions & proposed AgentDecisions for a RefundCase."""
    refund_case = resolve_refund_case(db, case_id)
    _enforce_refund_case_ownership(db, refund_case, actor)

    executions = list(
        db.scalars(
            select(AgentExecution)
            .where(AgentExecution.case_id == refund_case.id)
            .order_by(AgentExecution.started_at.desc())
        ).all()
    )
    serialized_execs = [_serialize_execution_with_decisions(db, ex) for ex in executions]
    all_decisions: list[dict[str, Any]] = []
    for ex_dict in serialized_execs:
        all_decisions.extend(ex_dict["decisions"])

    return {
        "case_id": str(refund_case.id),
        "refund_case_id": str(refund_case.id),
        "decisions": all_decisions,
        "executions": serialized_execs,
        "count": len(all_decisions),
    }

