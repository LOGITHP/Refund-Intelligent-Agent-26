"""Shared API v1 helpers, ownership guards, serializers, and injectable client factories."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data
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
from app.integrations.minio_client import AgentMinIOClient
from app.integrations.paypal_client import PayPalClient
from app.integrations.shipkart_client import ShipkartBridgeClient
from app.integrations.simulators import (
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
)
from app.services.compliance_service import ComplianceService, ComplianceViolationError
from app.services.evidence_service import EvidenceService

ETA_DISCLAIMER = "This is an estimate, not a guaranteed credit date."


def get_evidence_service() -> EvidenceService:
    """Dependency factory for hardened EvidenceService (overrideable in tests)."""
    return EvidenceService(minio_client=AgentMinIOClient())


def get_paypal_client() -> PayPalClient:
    """Dependency factory for PayPal REST client (overrideable in tests)."""
    return PayPalClient()


def get_carrier_client() -> CarrierSimulatorClient:
    """Dependency factory for Carrier Simulator client (overrideable in tests)."""
    return CarrierSimulatorClient(base_url=settings.CARRIER_SIMULATOR_URL)


def get_issuer_client() -> IssuerSimulatorClient:
    """Dependency factory for Issuer Simulator client (overrideable in tests)."""
    return IssuerSimulatorClient(base_url=settings.ISSUER_SIMULATOR_URL)


def get_regulatory_client() -> RegulatorySimulatorClient:
    """Dependency factory for Regulatory Simulator client (overrideable in tests)."""
    return RegulatorySimulatorClient(base_url=settings.REGULATORY_SIMULATOR_URL)


def get_shipkart_client() -> ShipkartBridgeClient:
    """Dependency factory for Shipkart Bridge client (overrideable in tests)."""
    return ShipkartBridgeClient(base_url=settings.SHIPKART_API_URL)


def extract_int_claim(actor: dict[str, Any], *keys: str) -> int | None:
    """Extract the first integer-convertible claim from `actor` across candidate keys."""
    for key in keys:
        val = actor.get(key)
        if val is None or isinstance(val, bool):
            continue
        try:
            return int(val)
        except (TypeError, ValueError):
            continue
    return None


def extract_uuid_claim(actor: dict[str, Any], *keys: str) -> uuid.UUID | None:
    """Extract the first UUID-convertible claim from `actor` across candidate keys."""
    for key in keys:
        val = actor.get(key)
        if not val:
            continue
        try:
            return uuid.UUID(str(val))
        except (TypeError, ValueError):
            continue
    return None


def get_actor_shipkart_id(actor: dict[str, Any]) -> int | None:
    """Resolve the Shipkart numeric user/merchant/customer ID from an actor payload."""
    return extract_int_claim(
        actor,
        "shipkart_user_id",
        "user_id",
        "shipkart_merchant_id",
        "shipkart_customer_id",
        "sub",
    )


def get_actor_type_label(actor: dict[str, Any]) -> str:
    """Map actor role to normalized audit actor_type label."""
    role = str(actor.get("role") or "SYSTEM").strip().upper()
    return role or "SYSTEM"


def assert_customer_case_access(
    db: Session,
    case: ReturnCase | RefundCase,
    actor: dict[str, Any],
) -> None:
    """Enforce AUTH-002 customer ownership while permitting admin/service/operations."""
    role = str(actor.get("role") or "").strip().lower()
    if role in {"admin", "service", "operations"}:
        return

    actor_sk_customer_id = extract_int_claim(
        actor,
        "shipkart_customer_id",
        "customer_id",
        "user_id",
        "sub",
    )
    actor_customer_uuid = extract_uuid_claim(actor, "customer_id", "sub")

    try:
        ComplianceService.assert_customer_access(
            db,
            case=case,
            actor_shipkart_customer_id=actor_sk_customer_id,
            actor_customer_id=actor_customer_uuid,
        )
    except ComplianceViolationError:
        db.commit()
        raise


def assert_merchant_case_access(
    db: Session,
    case: ReturnCase | RefundCase,
    actor: dict[str, Any],
) -> None:
    """Enforce AUTH-001 merchant tenant isolation while permitting admin/service/operations."""
    role = str(actor.get("role") or "").strip().lower()
    if role in {"admin", "service", "operations"}:
        return

    actor_sk_merchant_id = extract_int_claim(
        actor,
        "shipkart_merchant_id",
        "merchant_id",
        "user_id",
        "sub",
    )
    actor_merchant_uuid = extract_uuid_claim(actor, "merchant_id", "sub")

    try:
        ComplianceService.assert_merchant_access(
            db,
            case=case,
            actor_shipkart_merchant_id=actor_sk_merchant_id,
            actor_merchant_id=actor_merchant_uuid,
        )
    except ComplianceViolationError:
        db.commit()
        raise


def resolve_return_case(db: Session, return_id: str) -> ReturnCase:
    """Resolve a ReturnCase by UUID or numeric Shipkart return_id."""
    clean = (return_id or "").strip()
    try:
        uid = uuid.UUID(clean)
        rc = db.get(ReturnCase, uid)
        if rc is not None:
            return rc
    except ValueError:
        if clean.isdigit():
            rc = db.scalar(select(ReturnCase).where(ReturnCase.shipkart_return_id == int(clean)))
            if rc is not None:
                return rc
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return case not found")


def resolve_refund_case(db: Session, refund_id: str) -> RefundCase:
    """Resolve a RefundCase by UUID or numeric Shipkart order_id / return_id."""
    clean = (refund_id or "").strip()
    try:
        uid = uuid.UUID(clean)
        rc = db.get(RefundCase, uid)
        if rc is not None:
            return rc
    except ValueError:
        if clean.isdigit():
            num = int(clean)
            rc = db.scalar(
                select(RefundCase)
                .where(RefundCase.shipkart_order_id == num)
                .order_by(RefundCase.opened_at.desc())
            )
            if rc is None:
                rc = db.scalar(
                    select(RefundCase)
                    .where(RefundCase.shipkart_return_id == num)
                    .order_by(RefundCase.opened_at.desc())
                )
            if rc is not None:
                return rc
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund case not found")


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _dec(val: Decimal | None) -> str | None:
    return f"{Decimal(str(val)):.2f}" if val is not None else None


def serialize_return_case(rc: ReturnCase, *, include_items: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(rc.id),
        "shipkart_return_id": rc.shipkart_return_id,
        "shipkart_order_id": rc.shipkart_order_id,
        "shipkart_customer_id": rc.shipkart_customer_id,
        "shipkart_merchant_id": rc.shipkart_merchant_id,
        "reason_code": rc.reason_code,
        "customer_description": rc.customer_description,
        "status": rc.status,
        "requested_at": _iso(rc.requested_at),
        "approved_at": _iso(rc.approved_at),
        "closed_at": _iso(rc.closed_at),
        "created_at": _iso(rc.created_at),
        "updated_at": _iso(rc.updated_at),
    }
    if include_items:
        payload["items"] = [
            {
                "id": str(item.id),
                "shipkart_order_item_id": item.shipkart_order_item_id,
                "quantity_requested": item.quantity_requested,
                "quantity_approved": item.quantity_approved,
                "condition_reported": item.condition_reported,
                "condition_inspected": item.condition_inspected,
                "refund_amount_requested": _dec(item.refund_amount_requested),
                "refund_amount_approved": _dec(item.refund_amount_approved),
            }
            for item in (rc.items or [])
        ]
    return payload


def serialize_refund_case(rc: RefundCase) -> dict[str, Any]:
    return {
        "id": str(rc.id),
        "return_case_id": str(rc.return_case_id) if rc.return_case_id else None,
        "shipkart_return_id": rc.shipkart_return_id,
        "shipkart_order_id": rc.shipkart_order_id,
        "shipkart_customer_id": rc.shipkart_customer_id,
        "shipkart_merchant_id": rc.shipkart_merchant_id,
        "case_type": rc.case_type,
        "status": rc.status,
        "requested_amount": _dec(rc.requested_amount),
        "approved_amount": _dec(rc.approved_amount),
        "captured_amount": _dec(rc.captured_amount),
        "currency": rc.currency,
        "original_currency": rc.original_currency,
        "paypal_currency": rc.paypal_currency,
        "paypal_order_id": rc.paypal_order_id,
        "paypal_capture_id": rc.paypal_capture_id,
        "reason": rc.reason,
        "resolution_summary": rc.resolution_summary,
        "opened_at": _iso(rc.opened_at),
        "resolved_at": _iso(rc.resolved_at),
    }


def serialize_eta(eta: dict[str, Any] | RefundEtaEstimate) -> dict[str, Any]:
    if isinstance(eta, RefundEtaEstimate):
        return {
            "id": str(eta.id),
            "refund_case_id": str(eta.refund_case_id),
            "eta_status": eta.eta_status,
            "estimated_from": _iso(eta.estimated_from),
            "earliest_at": _iso(eta.earliest_at),
            "latest_at": _iso(eta.latest_at),
            "confidence": eta.confidence_level,
            "confidence_level": eta.confidence_level,
            "basis": list(eta.basis or []),
            "explanation": eta.explanation,
            "disclaimer": ETA_DISCLAIMER,
            "is_current": eta.is_current,
            "created_at": _iso(eta.created_at),
        }
    return {
        "refund_case_id": str(eta.get("refund_case_id")),
        "eta_status": eta.get("eta_status"),
        "estimated_from": _iso(eta.get("estimated_from")),
        "earliest_at": _iso(eta.get("earliest_at")),
        "latest_at": _iso(eta.get("latest_at")),
        "confidence": eta.get("confidence_level"),
        "confidence_level": eta.get("confidence_level"),
        "basis": list(eta.get("basis") or []),
        "explanation": eta.get("explanation", ""),
        "disclaimer": ETA_DISCLAIMER,
    }


def serialize_evidence(ev: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": str(ev.id),
        "id": str(ev.id),
        "return_case_id": str(ev.return_case_id) if ev.return_case_id else None,
        "refund_case_id": str(ev.refund_case_id) if ev.refund_case_id else None,
        "shipkart_uploaded_by": ev.shipkart_uploaded_by,
        "file_name": ev.file_name,
        "storage_key": ev.storage_key,
        "mime_type": ev.mime_type,
        "file_size": ev.file_size,
        "sha256_hash": ev.sha256_hash,
        "source_type": ev.source_type,
        "verification_status": ev.verification_status,
        "extracted_metadata": redact_sensitive_data(dict(ev.extracted_metadata or {})),
        "created_at": _iso(ev.created_at),
    }


def serialize_approval(approval: RefundApproval) -> dict[str, Any]:
    return {
        "id": str(approval.id),
        "refund_case_id": str(approval.refund_case_id),
        "shipkart_merchant_user_id": approval.shipkart_merchant_user_id,
        "decision": approval.decision,
        "approved_amount": _dec(approval.approved_amount),
        "currency": approval.currency,
        "reason": approval.reason,
        "policy_version": approval.policy_version,
        "approval_reference": approval.approval_reference,
        "created_at": _iso(approval.created_at),
    }


def serialize_transaction(tx: RefundTransaction) -> dict[str, Any]:
    return {
        "id": str(tx.id),
        "refund_case_id": str(tx.refund_case_id),
        "paypal_order_id": tx.paypal_order_id,
        "paypal_capture_id": tx.paypal_capture_id,
        "paypal_refund_id": tx.paypal_refund_id,
        "amount": _dec(tx.amount),
        "currency": tx.currency,
        "status": tx.status,
        "idempotency_key": tx.idempotency_key,
        "submitted_at": _iso(tx.submitted_at),
        "completed_at": _iso(tx.completed_at),
        "created_at": _iso(tx.created_at),
    }


def serialize_execution(ex: AgentExecution) -> dict[str, Any]:
    return {
        "id": str(ex.id),
        "case_id": str(ex.case_id),
        "case_type": ex.case_type,
        "agent_name": ex.agent_name,
        "status": ex.status,
        "input_reference": redact_sensitive_data(dict(ex.input_reference or {})),
        "output_data": redact_sensitive_data(dict(ex.output_data or {})),
        "model_name": ex.model_name,
        "prompt_version": ex.prompt_version,
        "started_at": _iso(ex.started_at),
        "completed_at": _iso(ex.completed_at),
        "error_code": ex.error_code,
    }


def serialize_decision(dec: AgentDecision) -> dict[str, Any]:
    return {
        "id": str(dec.id),
        "execution_id": str(dec.execution_id),
        "decision_type": dec.decision_type,
        "recommendation": redact_sensitive_data(dict(dec.recommendation or {})),
        "evidence_references": list(dec.evidence_references or []),
        "confidence": str(dec.confidence),
        "requires_approval": bool(dec.requires_approval),
        "decision_status": dec.decision_status,
        "created_at": _iso(dec.created_at),
    }


def serialize_inspection(insp: ReturnInspection) -> dict[str, Any]:
    return {
        "id": str(insp.id),
        "return_case_id": str(insp.return_case_id),
        "shipkart_inspector_id": insp.shipkart_inspector_id,
        "inspection_status": insp.inspection_status,
        "condition_result": insp.condition_result,
        "notes": insp.notes,
        "completed_at": _iso(insp.completed_at),
        "created_at": _iso(insp.created_at),
    }


def serialize_shipment(ship: ReturnShipment) -> dict[str, Any]:
    return {
        "id": str(ship.id),
        "return_case_id": str(ship.return_case_id),
        "carrier_name": ship.carrier_name,
        "tracking_number": ship.tracking_number,
        "status": ship.status,
        "is_simulated": ship.is_simulated,
        "pickup_at": _iso(ship.pickup_at),
        "delivered_at": _iso(ship.delivered_at),
        "last_synced_at": _iso(ship.last_synced_at),
    }


def serialize_issuer_inquiry(inq: IssuerInquiry) -> dict[str, Any]:
    return {
        "id": str(inq.id),
        "refund_case_id": str(inq.refund_case_id),
        "provider_type": inq.provider_type,
        "provider_reference": inq.provider_reference,
        "institution_code": inq.institution_code,
        "status": inq.status,
        "response_data": redact_sensitive_data(dict(inq.response_data or {})),
        "is_simulated": inq.is_simulated,
        "created_at": _iso(inq.created_at),
        "updated_at": _iso(inq.updated_at),
    }


def serialize_regulatory_eval(ev: RegulatoryEvaluation) -> dict[str, Any]:
    return {
        "id": str(ev.id),
        "refund_case_id": str(ev.refund_case_id) if ev.refund_case_id else None,
        "jurisdiction": ev.jurisdiction,
        "evaluation_status": ev.evaluation_status,
        "rule_version": ev.rule_version,
        "matched_rules": list(ev.matched_rules or []),
        "unresolved_questions": list(ev.unresolved_questions or []),
        "is_simulated": ev.is_simulated,
        "evaluated_at": _iso(ev.evaluated_at),
    }


def serialize_violation(v: ComplianceViolation) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "refund_case_id": str(v.refund_case_id) if v.refund_case_id else None,
        "rule_code": v.rule_code,
        "severity": v.severity,
        "description": v.description,
        "status": v.status,
        "resolved_at": _iso(v.resolved_at),
        "created_at": _iso(v.created_at),
    }

