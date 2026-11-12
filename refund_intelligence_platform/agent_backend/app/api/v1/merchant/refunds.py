"""Merchant refund case listing & detailed investigation report routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_merchant_case_access,
    extract_int_claim,
    extract_uuid_claim,
    resolve_refund_case,
    serialize_approval,
    serialize_decision,
    serialize_eta,
    serialize_evidence,
    serialize_execution,
    serialize_inspection,
    serialize_issuer_inquiry,
    serialize_refund_case,
    serialize_regulatory_eval,
    serialize_return_case,
    serialize_shipment,
    serialize_transaction,
)
from app.core.security import require_roles
from app.db.models import (
    AgentDecision,
    AgentExecution,
    ComplianceViolation,
    Evidence,
    IssuerInquiry,
    RefundApproval,
    RefundCase,
    RefundEtaEstimate,
    RefundTransaction,
    RegulatoryEvaluation,
    ReturnCase,
    ReturnInspection,
    ReturnShipment,
)
from app.db.session import get_db
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.timeline_service import TimelineService

router = APIRouter(prefix="/merchant/refunds", tags=["Merchant Refunds"])


@router.get("")
def list_merchant_refunds(
    status_filter: str | None = Query(default=None, alias="status"),
    shipkart_order_id: int | None = Query(default=None),
    shipkart_return_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List refund cases scoped to the authenticated merchant tenant (AUTH-001)."""
    stmt = select(RefundCase).order_by(RefundCase.opened_at.desc()).limit(limit)
    if str(actor.get("role") or "").lower() == "merchant":
        sk_merchant_id = extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        merchant_uuid = extract_uuid_claim(actor, "merchant_id", "sub")
        if sk_merchant_id is not None:
            stmt = stmt.where(
                or_(
                    RefundCase.shipkart_merchant_id == sk_merchant_id,
                    and_(
                        RefundCase.shipkart_merchant_id.is_(None),
                        RefundCase.merchant_id.is_(None),
                    ),
                )
            )
        elif merchant_uuid is not None:
            stmt = stmt.where(RefundCase.merchant_id == merchant_uuid)
        else:
            return {"items": [], "count": 0}

    if status_filter:
        stmt = stmt.where(RefundCase.status == status_filter.strip().upper())
    if shipkart_order_id is not None:
        stmt = stmt.where(RefundCase.shipkart_order_id == shipkart_order_id)
    if shipkart_return_id is not None:
        stmt = stmt.where(RefundCase.shipkart_return_id == shipkart_return_id)

    rows = list(db.scalars(stmt).all())
    return {"items": [serialize_refund_case(r) for r in rows], "count": len(rows)}


def _build_merchant_investigation_payload(db: Session, refund_case: RefundCase) -> dict[str, Any]:
    return_case = (
        db.get(ReturnCase, refund_case.return_case_id)
        if refund_case.return_case_id is not None
        else None
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
    inspections = (
        list(
            db.scalars(
                select(ReturnInspection)
                .where(ReturnInspection.return_case_id == return_case.id)
                .order_by(ReturnInspection.created_at.desc())
            ).all()
        )
        if return_case is not None
        else []
    )
    approvals = list(
        db.scalars(
            select(RefundApproval)
            .where(RefundApproval.refund_case_id == refund_case.id)
            .order_by(RefundApproval.created_at.desc())
        ).all()
    )
    transactions = list(
        db.scalars(
            select(RefundTransaction)
            .where(RefundTransaction.refund_case_id == refund_case.id)
            .order_by(RefundTransaction.created_at.desc())
        ).all()
    )
    evidence_rows = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.refund_case_id == refund_case.id)
            .order_by(Evidence.created_at.desc())
        ).all()
    )
    if return_case is not None:
        seen = {e.id for e in evidence_rows}
        for ev in db.scalars(
            select(Evidence).where(Evidence.return_case_id == return_case.id)
        ).all():
            if ev.id not in seen:
                evidence_rows.append(ev)

    executions = list(
        db.scalars(
            select(AgentExecution)
            .where(AgentExecution.case_id == refund_case.id)
            .order_by(AgentExecution.started_at.desc())
        ).all()
    )
    exec_dicts: list[dict[str, Any]] = []
    for ex in executions:
        decs = list(
            db.scalars(
                select(AgentDecision)
                .where(AgentDecision.execution_id == ex.id)
                .order_by(AgentDecision.created_at.desc())
            ).all()
        )
        d = serialize_execution(ex)
        d["decisions"] = [serialize_decision(dec) for dec in decs]
        exec_dicts.append(d)

    inquiries = list(
        db.scalars(
            select(IssuerInquiry)
            .where(IssuerInquiry.refund_case_id == refund_case.id)
            .order_by(IssuerInquiry.updated_at.desc())
        ).all()
    )
    reg_evals = list(
        db.scalars(
            select(RegulatoryEvaluation)
            .where(RegulatoryEvaluation.refund_case_id == refund_case.id)
            .order_by(RegulatoryEvaluation.evaluated_at.desc())
        ).all()
    )
    violations = list(
        db.scalars(
            select(ComplianceViolation)
            .where(ComplianceViolation.refund_case_id == refund_case.id)
            .order_by(ComplianceViolation.created_at.desc())
        ).all()
    )

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
    timeline = TimelineService().get_unified_timeline(db, refund_case_id=refund_case.id)

    return {
        "refund_case": serialize_refund_case(refund_case),
        "return_case": serialize_return_case(return_case) if return_case else None,
        "shipments": [serialize_shipment(s) for s in shipments],
        "inspections": [serialize_inspection(i) for i in inspections],
        "approvals": [serialize_approval(a) for a in approvals],
        "transactions": [serialize_transaction(t) for t in transactions],
        "evidence_items": [serialize_evidence(e) for e in evidence_rows],
        "agent_executions": exec_dicts,
        "issuer_inquiries": [serialize_issuer_inquiry(inq) for inq in inquiries],
        "regulatory_evaluations": [serialize_regulatory_eval(ev) for ev in reg_evals],
        "compliance_violations": [
            {
                "id": str(v.id),
                "rule_code": v.rule_code,
                "severity": v.severity,
                "description": v.description,
                "status": v.status,
            }
            for v in violations
        ],
        "current_eta": current_eta,
        "delay_evaluation": delay_eval,
        "timeline": timeline,
    }


@router.get("/{refund_id}")
def get_merchant_refund(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a single refund case with ETA and delay status for the owning merchant."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_merchant_case_access(db, refund_case, actor)
    return _build_merchant_investigation_payload(db, refund_case)


@router.get("/{refund_id}/investigation")
def get_merchant_investigation_brief(
    refund_id: str,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return full AI investigation dossier and verified evidence for merchant review."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_merchant_case_access(db, refund_case, actor)
    return _build_merchant_investigation_payload(db, refund_case)

