"""Merchant warehouse inspection & return status routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_merchant_case_access,
    extract_int_claim,
    extract_uuid_claim,
    resolve_return_case,
    serialize_eta,
    serialize_inspection,
    serialize_return_case,
)
from app.core.security import require_roles
from app.db.models import RefundCase
from app.db.session import get_db
from app.services.eta_service import ETAService
from app.services.return_service import ReturnService

router = APIRouter(prefix="/merchant/returns", tags=["Merchant Inspections"])


class InspectionRequest(BaseModel):
    condition_result: str = Field(..., min_length=2, max_length=40)
    notes: str = Field(default="", max_length=2000)
    completed: bool = True


class ReturnStatusTransitionRequest(BaseModel):
    status: str = Field(..., min_length=2, max_length=40)
    reason: str | None = Field(default=None, max_length=2000)


@router.post("/{return_id}/inspect")
def record_warehouse_inspection(
    return_id: str,
    payload: InspectionRequest,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record warehouse inspection for a delivered return item enforcing AUTH-001 & STATE-002."""
    return_case = resolve_return_case(db, return_id)
    assert_merchant_case_access(db, return_case, actor)

    role = str(actor.get("role") or "").lower()
    sk_merchant_id = (
        extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        if role == "merchant"
        else return_case.shipkart_merchant_id
    )
    merchant_uuid = (
        extract_uuid_claim(actor, "merchant_id", "sub")
        if role == "merchant"
        else return_case.merchant_id
    )
    inspector_sk_id = extract_int_claim(actor, "shipkart_user_id", "user_id", "sub")

    inspection = ReturnService.record_inspection(
        db,
        return_case.id,
        shipkart_merchant_id=sk_merchant_id,
        merchant_id=merchant_uuid,
        shipkart_inspector_id=inspector_sk_id,
        condition_result=payload.condition_result,
        notes=payload.notes,
        completed=payload.completed,
    )
    db.refresh(return_case)

    linked_refund = db.scalar(
        select(RefundCase)
        .where(RefundCase.return_case_id == return_case.id)
        .order_by(RefundCase.opened_at.desc())
    )
    eta_payload = None
    if linked_refund is not None:
        eta_row = ETAService().compute_and_persist_eta(db, linked_refund.id)
        db.commit()
        eta_payload = serialize_eta(eta_row)

    return {
        "inspection": serialize_inspection(inspection),
        "return_case": serialize_return_case(return_case),
        "eta": eta_payload,
    }


@router.post("/{return_id}/transition")
def transition_merchant_return(
    return_id: str,
    payload: ReturnStatusTransitionRequest,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Transition return lifecycle status enforcing AUTH-001 & CASE-001 rejection reasons."""
    return_case = resolve_return_case(db, return_id)
    assert_merchant_case_access(db, return_case, actor)

    role = str(actor.get("role") or "").lower()
    sk_merchant_id = (
        extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        if role == "merchant"
        else None
    )
    sk_actor_id = extract_int_claim(actor, "shipkart_user_id", "user_id", "sub")

    updated = ReturnService.transition_return_status(
        db,
        return_case,
        payload.status,
        actor_type=role.upper() or "MERCHANT",
        shipkart_actor_id=sk_actor_id,
        actor_shipkart_merchant_id=sk_merchant_id,
        reason=payload.reason,
    )
    return {"return_case": serialize_return_case(updated)}

