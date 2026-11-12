"""Root API v1 router aggregating customer, merchant, agent, ops, and internal routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.agents.routes import router as agents_router
from app.api.v1.customer.evidence import router as customer_evidence_router
from app.api.v1.customer.refunds import router as customer_refunds_router
from app.api.v1.customer.returns import router as customer_returns_router
from app.api.v1.internal_and_webhooks import router as internal_and_webhooks_router
from app.api.v1.merchant.approvals import router as merchant_approvals_router
from app.api.v1.merchant.inspections import router as merchant_inspections_router
from app.api.v1.merchant.refunds import router as merchant_refunds_router
from app.api.v1.merchant.returns import router as merchant_returns_router
from app.api.v1.operations.routes import router as operations_router

api_router = APIRouter()
api_router.include_router(customer_returns_router)
api_router.include_router(customer_refunds_router)
api_router.include_router(customer_evidence_router)
api_router.include_router(merchant_returns_router)
api_router.include_router(merchant_inspections_router)
api_router.include_router(merchant_approvals_router)
api_router.include_router(merchant_refunds_router)
api_router.include_router(agents_router)
api_router.include_router(operations_router)
api_router.include_router(internal_and_webhooks_router)

