"""Customer return request creation & retrieval routes (`/api/v1/returns`)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import run_refund_intelligence_pipeline
from app.api.v1 import (
    assert_customer_case_access,
    extract_int_claim,
    extract_uuid_claim,
    get_carrier_client,
    get_issuer_client,
    get_paypal_client,
    get_regulatory_client,
    get_shipkart_client,
    resolve_return_case,
    serialize_eta,
    serialize_refund_case,
    serialize_return_case,
)
from app.core.security import require_roles
from app.db.base import utcnow
from app.db.models import RefundCase, RefundTimelineEvent, ReturnCase
from app.db.session import get_db
from app.integrations.paypal_client import PayPalClient
from app.integrations.shipkart_client import ShipkartBridgeClient
from app.integrations.simulators import (
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
)
from app.services.audit_service import AuditService
from app.services.compliance_service import ComplianceService
from app.services.eta_service import ETAService
from app.services.return_service import ReturnService

router = APIRouter(prefix="/returns", tags=["Customer Returns"])


class ReturnItemPayload(BaseModel):
    shipkart_order_item_id: int | None = None
    order_item_id: uuid.UUID | None = None
    quantity_requested: int = Field(..., gt=0)
    purchased_quantity: int = Field(..., gt=0)
    unit_price: Decimal | None = None
    refund_amount_requested: Decimal | None = None
    condition_reported: str = "UNKNOWN"


class CreateReturnRequest(BaseModel):
    shipkart_order_id: int | None = None
    shipkart_return_id: int | None = None
    shipkart_customer_id: int | None = None
    shipkart_merchant_id: int | None = None
    order_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    merchant_id: uuid.UUID | None = None
    reason_code: str = Field(..., min_length=2, max_length=50)
    customer_description: str = ""
    case_type: str = "RETURN_REFUND"
    requested_amount: Decimal | None = None
    captured_amount: Decimal | None = None
    currency: str = "USD"
    original_currency: str = "INR"
    paypal_currency: str = "USD"
    paypal_order_id: str | None = None
    paypal_capture_id: str | None = None
    items: list[ReturnItemPayload] = Field(..., min_length=1)
    run_pipeline: bool = False


@router.post("", status_code=status.HTTP_201_CREATED)
def create_return_request(
    payload: CreateReturnRequest,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
    paypal_client: PayPalClient = Depends(get_paypal_client),
    shipkart_client: ShipkartBridgeClient = Depends(get_shipkart_client),
) -> dict[str, Any]:
    """Create a physical return case, paired refund case, and initial deterministic ETA."""
    role = str(actor.get("role") or "").lower()
    actor_sk_customer = extract_int_claim(actor, "shipkart_customer_id", "customer_id", "user_id", "sub")
    actor_uuid = extract_uuid_claim(actor, "customer_id", "sub")

    sk_customer_id = payload.shipkart_customer_id
    customer_uuid = payload.customer_id
    if role == "customer":
        if sk_customer_id is not None and actor_sk_customer is not None and sk_customer_id != actor_sk_customer:
            err = ComplianceService.record_violation_and_raise(
                db,
                rule_code="AUTH-002",
                message="Customer cannot create a return on behalf of another customer.",
                status_code=403,
                severity="HIGH",
                resource_type="return_case",
                actor_type="CUSTOMER",
                shipkart_actor_id=actor_sk_customer,
            )
            db.commit()
            raise err
        if sk_customer_id is None:
            sk_customer_id = actor_sk_customer
        if customer_uuid is None:
            customer_uuid = actor_uuid

    return_case = ReturnService.create_return_case(
        db,
        shipkart_order_id=payload.shipkart_order_id,
        shipkart_customer_id=sk_customer_id,
        shipkart_merchant_id=payload.shipkart_merchant_id,
        shipkart_return_id=payload.shipkart_return_id,
        order_id=payload.order_id,
        customer_id=customer_uuid,
        merchant_id=payload.merchant_id,
        reason_code=payload.reason_code.strip().upper(),
        customer_description=payload.customer_description.strip(),
        items=[item.model_dump() for item in payload.items],
    )

    items_total = sum(
        (Decimal(str(i.refund_amount_requested)) for i in return_case.items),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    req_amount = (
        Decimal(str(payload.requested_amount)).quantize(Decimal("0.01"))
        if payload.requested_amount is not None
        else items_total
    )
    cap_amount = (
        Decimal(str(payload.captured_amount)).quantize(Decimal("0.01"))
        if payload.captured_amount is not None
        else None
    )

    now = utcnow()
    refund_case = RefundCase(
        id=uuid.uuid4(),
        return_case_id=return_case.id,
        order_id=return_case.order_id,
        customer_id=return_case.customer_id,
        merchant_id=return_case.merchant_id,
        shipkart_return_id=return_case.shipkart_return_id,
        shipkart_order_id=return_case.shipkart_order_id,
        shipkart_customer_id=return_case.shipkart_customer_id,
        shipkart_merchant_id=return_case.shipkart_merchant_id,
        case_type=payload.case_type.strip().upper(),
        status="INVESTIGATING",
        requested_amount=req_amount,
        captured_amount=cap_amount,
        currency=payload.currency.strip().upper(),
        original_currency=payload.original_currency.strip().upper(),
        paypal_currency=payload.paypal_currency.strip().upper(),
        paypal_order_id=payload.paypal_order_id,
        paypal_capture_id=payload.paypal_capture_id,
        reason=payload.customer_description.strip() or payload.reason_code.strip().upper(),
        opened_at=now,
    )
    db.add(refund_case)
    db.flush()

    db.add(
        RefundTimelineEvent(
            id=uuid.uuid4(),
            return_case_id=return_case.id,
            refund_case_id=refund_case.id,
            event_type="REFUND_CASE_OPENED",
            source_type="REFUND",
            source_reference=str(refund_case.id),
            description="Paired refund case opened from return request.",
            event_data={"requested_amount": f"{req_amount:.2f}", "currency": refund_case.currency},
            occurred_at=now,
            recorded_at=now,
            verified=True,
        )
    )
    AuditService.record_audit(
        db,
        actor_type=role.upper() or "CUSTOMER",
        shipkart_actor_id=actor_sk_customer,
        action="REFUND_CASE_CREATED",
        resource_type="refund_case",
        resource_id=refund_case.id,
        after_state={"status": refund_case.status, "requested_amount": f"{req_amount:.2f}"},
    )
    eta_snapshot = ETAService().compute_and_persist_eta(db, refund_case.id)
    db.commit()
    db.refresh(return_case)
    db.refresh(refund_case)

    pipeline_result: dict[str, Any] | None = None
    if payload.run_pipeline:
        pipeline_result = run_refund_intelligence_pipeline(
            db,
            refund_case.id,
            customer_query=payload.customer_description or payload.reason_code,
            clients={
                "carrier_client": carrier_client,
                "issuer_client": issuer_client,
                "regulatory_client": regulatory_client,
                "paypal_client": paypal_client,
                "shipkart_client": shipkart_client,
            },
        )

    return {
        "return_case": serialize_return_case(return_case),
        "refund_case": serialize_refund_case(refund_case),
        "eta": serialize_eta(eta_snapshot),
        "pipeline_result": pipeline_result,
    }


@router.get("")
def list_customer_returns(
    shipkart_order_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List physical return cases scoped to the authenticated customer."""
    stmt = select(ReturnCase).order_by(ReturnCase.created_at.desc()).limit(limit)
    if str(actor.get("role") or "").lower() == "customer":
        actor_sk_id = extract_int_claim(actor, "shipkart_customer_id", "customer_id", "user_id", "sub")
        actor_uuid = extract_uuid_claim(actor, "customer_id", "sub")
        if actor_sk_id is not None:
            stmt = stmt.where(ReturnCase.shipkart_customer_id == actor_sk_id)
        elif actor_uuid is not None:
            stmt = stmt.where(ReturnCase.customer_id == actor_uuid)
        else:
            return {"items": [], "count": 0}
    if shipkart_order_id is not None:
        stmt = stmt.where(ReturnCase.shipkart_order_id == shipkart_order_id)
    if status_filter:
        stmt = stmt.where(ReturnCase.status == status_filter.strip().upper())

    rows = list(db.scalars(stmt).all())
    return {"items": [serialize_return_case(r) for r in rows], "count": len(rows)}


@router.get("/{return_id}")
def get_customer_return(
    return_id: str,
    actor: dict[str, Any] = Depends(require_roles("customer", "admin", "service")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a single physical return case enforcing AUTH-002 ownership."""
    return_case = resolve_return_case(db, return_id)
    assert_customer_case_access(db, return_case, actor)
    return {
        "return_case": serialize_return_case(return_case),
        "refund_cases": [serialize_refund_case(rc) for rc in (return_case.refund_cases or [])],
    }

