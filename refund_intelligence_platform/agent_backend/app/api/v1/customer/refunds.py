"""Customer refund status, dual timeline, deterministic ETA, grounded chat, and appeal routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import answer_customer_chat_question
from app.api.v1 import (
    assert_customer_case_access,
    extract_int_claim,
    extract_uuid_claim,
    get_actor_shipkart_id,
    get_actor_type_label,
    resolve_refund_case,
    serialize_decision,
    serialize_eta,
    serialize_evidence,
    serialize_refund_case,
    serialize_return_case,
    serialize_shipment,
)
from app.core.logging_redact import redact_sensitive_data
from app.core.security import require_roles
from app.db.base import utcnow
from app.db.models import (
    AgentDecision,
    AgentExecution,
    Evidence,
    IssuerInquiry,
    RefundCase,
    RefundEtaEstimate,
    RefundTimelineEvent,
    ReturnCase,
    ReturnShipment,
)
from app.db.session import get_db
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.timeline_service import TimelineService

router = APIRouter(prefix="/refunds", tags=["Customer Refunds"])


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AppealRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


@router.get("")
def list_customer_refunds(
    shipkart_order_id: int | None = Query(default=None),
    shipkart_return_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List refund cases scoped to the authenticated customer."""
    stmt = select(RefundCase).order_by(RefundCase.opened_at.desc()).limit(limit)
    if str(actor.get("role") or "").lower() == "customer":
        actor_sk_id = extract_int_claim(actor, "shipkart_customer_id", "customer_id", "user_id", "sub")
        actor_uuid = extract_uuid_claim(actor, "customer_id", "sub")
        if actor_sk_id is not None:
            stmt = stmt.where(RefundCase.shipkart_customer_id == actor_sk_id)
        elif actor_uuid is not None:
            stmt = stmt.where(RefundCase.customer_id == actor_uuid)
        else:
            return {"items": [], "count": 0}
    if shipkart_order_id is not None:
        stmt = stmt.where(RefundCase.shipkart_order_id == shipkart_order_id)
    if shipkart_return_id is not None:
        stmt = stmt.where(RefundCase.shipkart_return_id == shipkart_return_id)
    if status_filter:
        stmt = stmt.where(RefundCase.status == status_filter.strip().upper())

    rows = list(db.scalars(stmt).all())
    return {"items": [serialize_refund_case(r) for r in rows], "count": len(rows)}


@router.get("/{refund_id}")
def get_customer_refund(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a single refund case (by UUID or Shipkart order/return ID) enforcing AUTH-002."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)
    return {"refund_case": serialize_refund_case(refund_case)}


@router.get("/{refund_id}/intelligence")
def get_customer_refund_intelligence(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return customer-safe consolidated refund intelligence (timeline, ETA, delays, chat summary)."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)

    return_case = (
        db.get(ReturnCase, refund_case.return_case_id)
        if refund_case.return_case_id is not None
        else None
    )
    timeline = TimelineService().get_unified_timeline(db, refund_case_id=refund_case.id)

    eta_row = db.scalar(
        select(RefundEtaEstimate)
        .where(
            RefundEtaEstimate.refund_case_id == refund_case.id,
            RefundEtaEstimate.is_current.is_(True),
        )
        .order_by(RefundEtaEstimate.created_at.desc())
    )
    current_eta = (
        serialize_eta(eta_row)
        if eta_row is not None
        else serialize_eta(ETAService().compute_eta(db, refund_case.id))
    )

    delay_eval = DelayService().evaluate_delays(db, refund_case.id)
    latest_inq = db.scalar(
        select(IssuerInquiry)
        .where(IssuerInquiry.refund_case_id == refund_case.id)
        .order_by(IssuerInquiry.updated_at.desc(), IssuerInquiry.created_at.desc())
    )
    shipments = (
        list(
            db.scalars(
                select(ReturnShipment)
                .where(ReturnShipment.return_case_id == return_case.id)
                .order_by(ReturnShipment.created_at.desc())
            ).all()
        )
        if return_case is not None
        else []
    )
    ev_by_id: dict[uuid.UUID, Evidence] = {
        ev.id: ev
        for ev in db.scalars(select(Evidence).where(Evidence.refund_case_id == refund_case.id)).all()
    }
    if return_case is not None:
        for ev in db.scalars(select(Evidence).where(Evidence.return_case_id == return_case.id)).all():
            ev_by_id[ev.id] = ev
    evidence_rows = sorted(ev_by_id.values(), key=lambda e: str(e.created_at), reverse=True)

    executions = list(
        db.scalars(
            select(AgentExecution)
            .where(AgentExecution.case_id == refund_case.id)
            .order_by(AgentExecution.started_at.desc())
        ).all()
    )
    latest_customer_summary: dict[str, Any] | None = None
    for ex in executions:
        dec = db.scalar(
            select(AgentDecision)
            .where(AgentDecision.execution_id == ex.id)
            .order_by(AgentDecision.created_at.desc())
        )
        if dec is not None:
            rec = redact_sensitive_data(dict(dec.recommendation or {}))
            latest_customer_summary = {
                "decision_type": dec.decision_type,
                "customer_message": (
                    rec.get("customer_explanation")
                    or rec.get("customer_message")
                    or rec.get("rationale")
                    or rec.get("recommended_action")
                ),
                "rationale": rec.get("rationale"),
                "followup_action": rec.get("followup_action"),
                "evidence_references": list(rec.get("evidence_references") or []),
                "recommended_action": rec.get("recommended_action"),
                "confidence": str(dec.confidence),
                "requires_approval": True,
                "decision_status": dec.decision_status,
                "created_at": dec.created_at.isoformat() if dec.created_at else None,
            }
            break

    return {
        "refund_case": serialize_refund_case(refund_case),
        "return_case": serialize_return_case(return_case) if return_case else None,
        "timeline": timeline,
        "eta": current_eta,
        "delay_summary": {
            "delay_owner": str(delay_eval.get("delay_owner") or "NONE"),
            "has_delays": bool(delay_eval.get("has_delays")),
            "triggered_rules": list(delay_eval.get("triggered_rules") or []),
            "delays": [
                {
                    "rule_code": str(d.get("rule_code") or ""),
                    "delay_owner": str(d.get("delay_owner") or "UNKNOWN"),
                    "description": str(d.get("description") or ""),
                }
                for d in (delay_eval.get("delays") or [])
            ],
        },
        "issuer_status": {
            "status": latest_inq.status if latest_inq else "UNCONFIRMED",
            "credit_posted": bool((latest_inq.response_data or {}).get("credit_posted")) if latest_inq else False,
            "is_simulated": bool(latest_inq.is_simulated) if latest_inq else True,
        },
        "shipments": [serialize_shipment(s) for s in shipments],
        "evidence_items": [serialize_evidence(e) for e in evidence_rows],
        "latest_agent_summary": latest_customer_summary,
    }


@router.get("/{refund_id}/timeline")
def get_customer_refund_timeline(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return separated physical return and financial refund timelines."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)
    return TimelineService().get_unified_timeline(db, refund_case_id=refund_case.id)


@router.get("/{refund_id}/eta")
def get_customer_refund_eta(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return deterministic stage-remaining ETA window with non-guarantee disclaimer."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)
    computed = ETAService().compute_eta(db, refund_case.id)
    return serialize_eta(computed)


@router.post("/{refund_id}/chat")
def chat_about_refund(
    refund_id: str,
    payload: ChatRequest,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Answer a customer refund status question grounded in verified DB facts and ETA."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)

    result = answer_customer_chat_question(db, refund_case.id, payload.question)
    now = utcnow()
    actor_sk_id = get_actor_shipkart_id(actor)
    redacted_q = redact_sensitive_data(payload.question)
    redacted_a = redact_sensitive_data(result.get("answer", ""))

    db.add(
        RefundTimelineEvent(
            id=uuid.uuid4(),
            return_case_id=refund_case.return_case_id,
            refund_case_id=refund_case.id,
            event_type="CUSTOMER_CHAT_INTERACTION",
            source_type=get_actor_type_label(actor),
            description="Customer queried Refund Intelligence Assistant.",
            event_data={
                "question": redacted_q,
                "eta_status": result.get("eta_status"),
                "delay_owner": result.get("delay_owner"),
            },
            occurred_at=now,
            recorded_at=now,
            verified=True,
        )
    )
    AuditService.record_audit(
        db,
        actor_type=get_actor_type_label(actor),
        shipkart_actor_id=actor_sk_id,
        action="CUSTOMER_REFUND_CHAT",
        resource_type="refund_case",
        resource_id=refund_case.id,
        after_state={
            "question": redacted_q,
            "answer_preview": str(redacted_a)[:200],
            "eta_status": result.get("eta_status"),
        },
    )
    db.commit()
    return result


@router.post("/{refund_id}/appeals")
def submit_refund_appeal(
    refund_id: str,
    payload: AppealRequest,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Submit a customer appeal, recording timeline event, audit entry, and review state."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_customer_case_access(db, refund_case, actor)

    actor_sk_id = get_actor_shipkart_id(actor)
    clean_reason = ComplianceService.assert_rejection_reason(
        db,
        reason=payload.reason,
        refund_case_id=refund_case.id,
        resource_type="refund_case",
        resource_id=refund_case.id,
        actor_type=get_actor_type_label(actor),
        shipkart_actor_id=actor_sk_id,
    )

    now = utcnow()
    before_status = refund_case.status
    refund_case.status = "APPEAL_UNDER_REVIEW"

    ev = RefundTimelineEvent(
        id=uuid.uuid4(),
        return_case_id=refund_case.return_case_id,
        refund_case_id=refund_case.id,
        event_type="APPEAL_SUBMITTED",
        source_type=get_actor_type_label(actor),
        description=f"Customer submitted refund appeal: {clean_reason}",
        event_data={
            "reason": clean_reason,
            "evidence_ids": [str(eid) for eid in payload.evidence_ids],
        },
        occurred_at=now,
        recorded_at=now,
        verified=True,
    )
    db.add(ev)
    AuditService.record_audit(
        db,
        actor_type=get_actor_type_label(actor),
        shipkart_actor_id=actor_sk_id,
        action="CUSTOMER_APPEAL_SUBMITTED",
        resource_type="refund_case",
        resource_id=refund_case.id,
        before_state={"status": before_status},
        after_state={
            "status": refund_case.status,
            "reason": clean_reason,
            "evidence_ids": [str(eid) for eid in payload.evidence_ids],
        },
    )
    db.commit()
    db.refresh(refund_case)

    return {
        "refund_case": serialize_refund_case(refund_case),
        "appeal_event_id": str(ev.id),
    }

