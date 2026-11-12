"""Merchant physical return list & detail routes (`/api/v1/merchant/returns`)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.v1 import (
    assert_merchant_case_access,
    extract_int_claim,
    extract_uuid_claim,
    resolve_return_case,
    serialize_evidence,
    serialize_inspection,
    serialize_refund_case,
    serialize_return_case,
    serialize_shipment,
)
from app.core.security import require_roles
from app.db.models import Evidence, RefundCase, ReturnCase, ReturnInspection, ReturnShipment
from app.db.session import get_db

router = APIRouter(prefix="/merchant/returns", tags=["Merchant Returns"])


@router.get("")
def list_merchant_returns(
    status_filter: str | None = Query(default=None, alias="status"),
    shipkart_order_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List return cases scoped to the authenticated merchant tenant (AUTH-001)."""
    stmt = select(ReturnCase).order_by(ReturnCase.created_at.desc()).limit(limit)
    if str(actor.get("role") or "").lower() == "merchant":
        sk_merchant_id = extract_int_claim(actor, "shipkart_merchant_id", "merchant_id", "user_id", "sub")
        merchant_uuid = extract_uuid_claim(actor, "merchant_id", "sub")
        if sk_merchant_id is not None:
            stmt = stmt.where(
                or_(
                    ReturnCase.shipkart_merchant_id == sk_merchant_id,
                    and_(
                        ReturnCase.shipkart_merchant_id.is_(None),
                        ReturnCase.merchant_id.is_(None),
                    ),
                )
            )
        elif merchant_uuid is not None:
            stmt = stmt.where(ReturnCase.merchant_id == merchant_uuid)
        else:
            return {"items": [], "count": 0}

    if status_filter:
        stmt = stmt.where(ReturnCase.status == status_filter.strip().upper())
    if shipkart_order_id is not None:
        stmt = stmt.where(ReturnCase.shipkart_order_id == shipkart_order_id)

    rows = list(db.scalars(stmt).all())
    return {"items": [serialize_return_case(r) for r in rows], "count": len(rows)}


@router.get("/{return_id}")
def get_merchant_return_detail(
    return_id: str,
    actor: dict[str, Any] = Depends(require_roles("merchant", "operations", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve a single return case plus linked shipments, inspections, and evidence (AUTH-001)."""
    return_case = resolve_return_case(db, return_id)
    assert_merchant_case_access(db, return_case, actor)

    shipments = list(
        db.scalars(
            select(ReturnShipment)
            .where(ReturnShipment.return_case_id == return_case.id)
            .order_by(ReturnShipment.created_at.desc())
        ).all()
    )
    inspections = list(
        db.scalars(
            select(ReturnInspection)
            .where(ReturnInspection.return_case_id == return_case.id)
            .order_by(ReturnInspection.created_at.desc())
        ).all()
    )
    evidence_rows = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.return_case_id == return_case.id)
            .order_by(Evidence.created_at.desc())
        ).all()
    )
    linked_refund = db.scalar(
        select(RefundCase)
        .where(RefundCase.return_case_id == return_case.id)
        .order_by(RefundCase.opened_at.desc())
    )

    return {
        "return_case": serialize_return_case(return_case),
        "refund_case": serialize_refund_case(linked_refund) if linked_refund else None,
        "shipments": [serialize_shipment(s) for s in shipments],
        "inspections": [serialize_inspection(i) for i in inspections],
        "evidence_items": [serialize_evidence(e) for e in evidence_rows],
    }

