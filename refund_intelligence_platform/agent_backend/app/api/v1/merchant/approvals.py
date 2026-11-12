"""Merchant refund approval & rejection routes (`/api/v1/merchant/refunds/{refund_id}/approve|reject`)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_merchant_case_access,
    extract_int_claim,
    extract_uuid_claim,
    resolve_refund_case,
    serialize_approval,
    serialize_eta,
    serialize_refund_case,
)
from app.core.security import require_roles
from app.db.session import get_db
from app.services.approval_service import ApprovalService
from app.services.eta_service import ETAService

router = APIRouter(prefix="/merchant/refunds", tags=["Merchant Approvals"])


class MerchantApprovalRequest(BaseModel):
    approved_amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    reason: str = Field(..., min_length=3, max_length=2000)
    policy_version: str = Field(default="v1.0", max_length=50)
    approval_reference: str | None = Field(default=None, max_length=150)


class MerchantRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)
    policy_version: str = Field(default="v1.0", max_length=50)


@router.post("/{refund_id}/approve")
def approve_merchant_refund(
    refund_id: str,
    payload: MerchantApprovalRequest,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist an immutable Merchant APPROVED RefundApproval record (satisfies REF-001)."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_merchant_case_access(db, refund_case, actor)

    role = str(actor.get("role") or "").lower()
    sk_merchant_id = (
        extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        if role == "merchant"
        else refund_case.shipkart_merchant_id
    )
    merchant_uuid = (
        extract_uuid_claim(actor, "merchant_id", "sub")
        if role == "merchant"
        else refund_case.merchant_id
    )
    sk_user_id = extract_int_claim(actor, "shipkart_user_id", "user_id", "sub")

    default_currency = (
        refund_case.currency
        or refund_case.original_currency
        or refund_case.paypal_currency
        or "USD"
    )
    approval = ApprovalService.record_merchant_decision(
        db,
        refund_case.id,
        shipkart_merchant_id=sk_merchant_id,
        merchant_id=merchant_uuid,
        shipkart_merchant_user_id=sk_user_id,
        decision="APPROVED",
        approved_amount=payload.approved_amount,
        currency=payload.currency or default_currency,
        reason=payload.reason,
        policy_version=payload.policy_version,
        approval_reference=payload.approval_reference,
    )
    eta_row = ETAService().compute_and_persist_eta(db, refund_case.id)
    db.commit()
    db.refresh(refund_case)

    serialized = serialize_approval(approval)
    serialized["refund_case"] = serialize_refund_case(refund_case)
    serialized["eta"] = serialize_eta(eta_row)
    return serialized


@router.post("/{refund_id}/reject")
def reject_merchant_refund(
    refund_id: str,
    payload: MerchantRejectRequest,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist an immutable Merchant REJECTED RefundApproval enforcing CASE-001 explanation."""
    refund_case = resolve_refund_case(db, refund_id)
    assert_merchant_case_access(db, refund_case, actor)

    role = str(actor.get("role") or "").lower()
    sk_merchant_id = (
        extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        if role == "merchant"
        else refund_case.shipkart_merchant_id
    )
    merchant_uuid = (
        extract_uuid_claim(actor, "merchant_id", "sub")
        if role == "merchant"
        else refund_case.merchant_id
    )
    sk_user_id = extract_int_claim(actor, "shipkart_user_id", "user_id", "sub")

    approval = ApprovalService.record_merchant_decision(
        db,
        refund_case.id,
        shipkart_merchant_id=sk_merchant_id,
        merchant_id=merchant_uuid,
        shipkart_merchant_user_id=sk_user_id,
        decision="REJECTED",
        reason=payload.reason,
        policy_version=payload.policy_version,
    )
    eta_row = ETAService().compute_and_persist_eta(db, refund_case.id)
    db.commit()
    db.refresh(refund_case)

    serialized = serialize_approval(approval)
    serialized["refund_case"] = serialize_refund_case(refund_case)
    serialized["eta"] = serialize_eta(eta_row)
    return serialized

