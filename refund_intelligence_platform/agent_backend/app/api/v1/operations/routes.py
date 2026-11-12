"""Operations Command Center, Simulator Consoles, Regulatory, Compliance & Audit routes."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

import jwt
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1 import (
    ETA_DISCLAIMER,
    get_carrier_client,
    get_issuer_client,
    get_regulatory_client,
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
    serialize_violation,
)
from app.core.config import settings
from app.core.logging_redact import redact_sensitive_data
from app.core.security import (
    create_platform_user_token,
    hash_password,
    require_roles,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import (
    AgentDecision,
    AgentExecution,
    AuditLog,
    ComplianceViolation,
    Evidence,
    IssuerInquiry,
    PlatformUser,
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
from app.integrations.simulators import (
    REGULATORY_DISCLAIMER,
    CarrierSimulatorClient,
    IssuerSimulatorClient,
    RegulatorySimulatorClient,
    SimulatorClientError,
)
from app.services.audit_service import AuditService
from app.services.delay_service import DelayService
from app.services.eta_service import ETAService
from app.services.timeline_service import TimelineService, ensure_utc

router = APIRouter(prefix="/operations", tags=["Operations"])

_OPS_ROLES = require_roles("operations", "admin", "service")
_DEV_DEMO_ENVS = frozenset({"development", "dev", "local", "test"})
_TERMINAL_CASE_STATUSES = frozenset(
    {
        "CONFIRMED_POSTED",
        "ISSUER_POSTED",
        "REJECTED",
        "REJECTED_BY_MERCHANT",
        "RETURN_REJECTED",
        "CANCELLED",
        "CLOSED_REJECTED",
        "REFUND_FAILED",
    }
)
_REJECTED_STATUSES = frozenset(
    {"REJECTED", "REJECTED_BY_MERCHANT", "RETURN_REJECTED", "CANCELLED", "CLOSED_REJECTED"}
)
_PAYPAL_COMPLETED_STATUSES = frozenset(
    {"PAYPAL_COMPLETED", "REFUND_COMPLETED", "CONFIRMED_POSTED", "ISSUER_POSTED"}
)
_ISSUER_POSTED_STATUSES = frozenset({"CREDIT_POSTED", "CONFIRMED_POSTED", "POSTED"})
_ALL_DELAY_RULES = (
    "DELAY-001",
    "DELAY-002",
    "DELAY-003",
    "DELAY-004",
    "DELAY-005",
    "DELAY-006",
)
_ALL_DELAY_OWNERS = (
    "CUSTOMER",
    "CARRIER",
    "MERCHANT",
    "PAYPAL",
    "ISSUER_OR_BANK",
    "UNKNOWN",
    "NONE",
)

COMPLIANCE_RULES_CATALOG: list[dict[str, str]] = [
    {
        "rule_code": "REF-001",
        "category": "Financial Authorization",
        "description": (
            "Explicit human Merchant approval (RefundApproval=APPROVED) is mandatory before "
            "PayPal refund execution."
        ),
        "enforcement": "HARD_BLOCK_403",
        "severity": "CRITICAL",
    },
    {
        "rule_code": "REF-002",
        "category": "Refund Balance",
        "description": "Refund amount must be > 0 and <= remaining refundable capture balance.",
        "enforcement": "HARD_BLOCK_422",
        "severity": "CRITICAL",
    },
    {
        "rule_code": "REF-003",
        "category": "Idempotency",
        "description": "Every PayPal refund execution requires a unique idempotency_key.",
        "enforcement": "HARD_BLOCK_422",
        "severity": "HIGH",
    },
    {
        "rule_code": "REF-004",
        "category": "Capture Linkage",
        "description": "Refund must target the verified original PayPal capture_id on the RefundCase.",
        "enforcement": "HARD_BLOCK_422",
        "severity": "CRITICAL",
    },
    {
        "rule_code": "AUTH-001",
        "category": "Tenant Isolation",
        "description": "Merchant endpoints enforce owning shipkart_merchant_id / merchant_id scoping.",
        "enforcement": "HARD_BLOCK_403",
        "severity": "CRITICAL",
    },
    {
        "rule_code": "AUTH-002",
        "category": "Customer Isolation",
        "description": "Customer endpoints enforce owning shipkart_customer_id / customer_id scoping.",
        "enforcement": "HARD_BLOCK_403",
        "severity": "HIGH",
    },
    {
        "rule_code": "CASE-001",
        "category": "Rejection Auditability",
        "description": "Merchant return/refund rejections require a human-provided reason (>= 3 chars).",
        "enforcement": "HARD_BLOCK_422",
        "severity": "MEDIUM",
    },
    {
        "rule_code": "QTY-001",
        "category": "Return Quantity Integrity",
        "description": "Approved return quantity cannot exceed quantity purchased on the order item.",
        "enforcement": "HARD_BLOCK_422",
        "severity": "HIGH",
    },
    {
        "rule_code": "DATA-001",
        "category": "PII & Secret Redaction",
        "description": "Never log or persist raw card PANs, CVVs, PayPal secrets, or unredacted PII.",
        "enforcement": "REDACTION_FILTER",
        "severity": "CRITICAL",
    },
]


class DemoSessionRequest(BaseModel):
    role: Literal["operations", "merchant"] = "operations"
    user_id: int | None = None


class PlatformOperatorSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(default="Platform Operations Lead", min_length=2, max_length=150)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or "." not in cleaned.split("@", 1)[-1]:
            raise ValueError("A valid email address is required")
        return cleaned


class PlatformOperatorLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class CreateIssuerInquiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refund_case_id: str = Field(..., min_length=1, max_length=128)
    paypal_capture_id: str | None = Field(default=None, max_length=128)
    paypal_refund_id: str | None = Field(default=None, max_length=128)
    paypal_refund_status: str = Field(default="COMPLETED", max_length=40)
    institution_code: str = Field(default="HDFC_SIM", min_length=2, max_length=80)
    card_network: Literal["VISA", "MASTERCARD", "RUPAY"] = "VISA"
    card_last4: str = Field(default="4242")
    amount: str | None = Field(default=None, max_length=32)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    scenario: str = "NORMAL_POSTING"

    @field_validator("card_last4")
    @classmethod
    def _validate_card_last4(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) != 4 or not cleaned.isdigit():
            raise ValueError("card_last4 must be exactly 4 digits (never submit full card PANs)")
        return cleaned


class TriggerScenarioRequest(BaseModel):
    scenario: str = Field(..., min_length=2, max_length=80)
    note: str | None = None


class CreateCarrierShipmentRequest(BaseModel):
    return_case_id: str = Field(..., min_length=1, max_length=128)
    shipkart_order_id: int | str
    carrier_name: Literal["BlueDart", "Delhivery", "FedEx"] = "BlueDart"
    tracking_number: str | None = Field(default=None, max_length=64)
    scenario: str = "NORMAL_TRANSIT"
    origin_city: str = "Bengaluru"
    destination_city: str = "Mumbai"


class RegulatoryEvaluateRequest(BaseModel):
    transaction_id: str = Field(..., min_length=1, max_length=128)
    refund_case_id: str | None = None
    merchant_country: str | None = None
    customer_country: str | None = None
    payment_provider: str = "PAYPAL"
    transaction_currency: str | None = None
    settlement_currency: str | None = None
    payment_route: str | None = None
    merchant_entity_type: str | None = None
    transaction_type: str = "REFUND"
    settlement_entity_confirmed: bool | None = None
    business_activity: str | None = None
    refund_delay_hours: float | None = Field(default=None, ge=0)


def _json_safe(data: Any) -> Any:
    return json.loads(json.dumps(redact_sensitive_data(data), default=str))


def _iso_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return utcnow().isoformat()


def _normalize_jurisdiction_char2(raw: Any, context: dict[str, Any] | None = None) -> str:
    candidate = ""
    if isinstance(raw, list):
        for item in raw:
            s = str(item or "").strip().upper()
            if s and s not in {"NONE", "UNKNOWN"}:
                candidate = s
                break
    elif isinstance(raw, str):
        cleaned = raw.strip().upper()
        if cleaned and cleaned not in {"NONE", "UNKNOWN"}:
            candidate = cleaned

    if not candidate and context:
        for key in ("merchant_country", "customer_country"):
            val = str(context.get(key) or "").strip().upper()
            if val and val not in {"NONE", "UNKNOWN"}:
                candidate = val
                break

    if not candidate:
        return "NA"
    if len(candidate) == 1:
        return f"{candidate}X"
    return candidate[:2]


def _probe_simulator_health(client: Any) -> tuple[str, int | None, str]:
    t0 = time.perf_counter()
    try:
        res = client.health()
        latency_ms = int((time.perf_counter() - t0) * 1000)
    except SimulatorClientError as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return "DOWN", latency_ms, str(exc)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return "DOWN", latency_ms, str(exc)

    if not isinstance(res, dict) or res.get("degraded"):
        msg = (res or {}).get("message") if isinstance(res, dict) else "Simulator degraded"
        return "DOWN", latency_ms, str(msg or "Simulator unavailable")
    return "HEALTHY", latency_ms, "Simulated endpoint reachable"


def _compute_paypal_and_issuer_flags(
    db: Session,
    refund_case: RefundCase,
) -> tuple[bool, bool, list[RefundTransaction], list[IssuerInquiry]]:
    txs = list(
        db.scalars(
            select(RefundTransaction)
            .where(RefundTransaction.refund_case_id == refund_case.id)
            .order_by(RefundTransaction.created_at.desc())
        ).all()
    )
    inquiries = list(
        db.scalars(
            select(IssuerInquiry)
            .where(IssuerInquiry.refund_case_id == refund_case.id)
            .order_by(IssuerInquiry.updated_at.desc(), IssuerInquiry.created_at.desc())
        ).all()
    )
    case_status = (refund_case.status or "").upper()
    paypal_completed = (
        any((tx.status or "").upper() == "COMPLETED" for tx in txs)
        or case_status in _PAYPAL_COMPLETED_STATUSES
    )
    issuer_credit_confirmed = case_status in {"CONFIRMED_POSTED", "ISSUER_POSTED"}
    for inq in inquiries:
        inq_status = (inq.status or "").upper()
        resp_data = inq.response_data or {}
        posting_status = str(resp_data.get("posting_status") or "").upper()
        if (
            inq_status in _ISSUER_POSTED_STATUSES
            or resp_data.get("credit_posted") is True
            or posting_status in {"POSTED", "POSTED_TO_REPLACEMENT_CARD"}
        ):
            issuer_credit_confirmed = True
            break

    return paypal_completed, issuer_credit_confirmed, txs, inquiries


def _enrich_eta_dict(eta: RefundEtaEstimate | dict[str, Any]) -> dict[str, Any]:
    out = serialize_eta(eta)
    blocking: list[str] = []
    for entry in out.get("basis") or []:
        if isinstance(entry, dict) and isinstance(entry.get("blocking_reasons"), list):
            blocking.extend(str(r) for r in entry["blocking_reasons"])
    if blocking:
        out["blocking_reasons"] = list(dict.fromkeys(blocking))
    return out


def _build_case_summary(
    db: Session,
    rc: RefundCase,
    *,
    delay_svc: DelayService | None = None,
    eta_svc: ETAService | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    delay_engine = delay_svc or DelayService()
    eta_engine = eta_svc or ETAService()

    return_case = db.get(ReturnCase, rc.return_case_id) if rc.return_case_id else None
    paypal_completed, issuer_credit_confirmed, _, _ = _compute_paypal_and_issuer_flags(db, rc)
    delay_eval = delay_engine.evaluate_delays(db, rc.id)

    eta_row = db.scalar(
        select(RefundEtaEstimate)
        .where(RefundEtaEstimate.refund_case_id == rc.id, RefundEtaEstimate.is_current.is_(True))
        .order_by(RefundEtaEstimate.created_at.desc())
    )
    eta_status = eta_row.eta_status if eta_row is not None else eta_engine.compute_eta(db, rc.id)["eta_status"]

    summary = serialize_refund_case(rc)
    summary["return_status"] = return_case.status if return_case is not None else None
    summary["delay_owner"] = str(delay_eval.get("delay_owner") or "NONE")
    summary["triggered_delay_rules"] = list(delay_eval.get("triggered_rules") or [])
    summary["eta_status"] = eta_status
    summary["paypal_completed"] = paypal_completed
    summary["issuer_credit_confirmed"] = issuer_credit_confirmed
    return summary, delay_eval


def _format_delay_alert(rc: RefundCase, delay: dict[str, Any], now_iso: str) -> dict[str, Any]:
    return {
        "refund_case_id": str(rc.id),
        "shipkart_order_id": rc.shipkart_order_id,
        "rule_code": str(delay.get("rule_code") or "DELAY-000"),
        "delay_owner": str(delay.get("delay_owner") or "UNKNOWN"),
        "recommended_action": str(delay.get("recommended_action") or "REVIEW_CASE"),
        "sla_hours": int(delay.get("sla_hours") or 0),
        "hours_elapsed": delay.get("hours_elapsed"),
        "description": str(delay.get("description") or ""),
        "evidence": _json_safe(delay.get("evidence") or {}),
        "detected_at": now_iso,
    }


def _enrich_issuer_inquiry_from_db(inq: IssuerInquiry) -> dict[str, Any]:
    base = serialize_issuer_inquiry(inq)
    resp = redact_sensitive_data(dict(inq.response_data or {}))
    req = redact_sensitive_data(dict(inq.request_data or {}))
    merged = {
        **base,
        "inquiry_id": resp.get("inquiry_id") or inq.provider_reference or str(inq.id),
        "paypal_capture_id": resp.get("paypal_capture_id") or req.get("paypal_capture_id"),
        "paypal_refund_id": resp.get("paypal_refund_id") or req.get("paypal_refund_id"),
        "paypal_refund_status": resp.get("paypal_refund_status") or req.get("paypal_refund_status") or "COMPLETED",
        "card_network": resp.get("card_network") or req.get("card_network"),
        "card_last4": resp.get("card_last4") or req.get("card_last4"),
        "arn": resp.get("arn"),
        "amount": resp.get("amount") or req.get("amount"),
        "currency": resp.get("currency") or req.get("currency"),
        "scenario": resp.get("scenario") or inq.status,
        "posting_status": resp.get("posting_status"),
        "issuer_service_status": resp.get("issuer_service_status"),
        "credit_posted": resp.get("credit_posted", False),
        "delay_days": resp.get("delay_days"),
        "expected_posting_window": resp.get("expected_posting_window"),
        "requires_manual_reconciliation": resp.get("requires_manual_reconciliation"),
        "mismatch_reason": resp.get("mismatch_reason"),
        "duplicate_reference_id": resp.get("duplicate_reference_id"),
        "original_card_status": resp.get("original_card_status"),
        "rerouting_via_issuer": resp.get("rerouting_via_issuer"),
        "missing_fields": resp.get("missing_fields") or [],
        "required_evidence": resp.get("required_evidence") or [],
        "events": resp.get("events") or [],
        "request_data": req,
        "simulation_label": resp.get("simulation_label") or "SIMULATED",
    }
    return merged


def _enrich_regulatory_eval_from_db(ev: RegulatoryEvaluation) -> dict[str, Any]:
    base = serialize_regulatory_eval(ev)
    base["evaluation_id"] = str(ev.id)
    base["status"] = ev.evaluation_status
    base["transaction_context"] = redact_sensitive_data(dict(ev.transaction_context or {}))
    base["obligations"] = []
    base["simulation_label"] = "SIMULATED"
    base["disclaimer"] = REGULATORY_DISCLAIMER
    return base


def _serialize_platform_user(user: PlatformUser) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": bool(user.is_active),
        "created_at": _iso_dt(user.created_at),
        "last_login_at": _iso_dt(user.last_login_at),
    }


@router.get("/auth/status")
def get_platform_auth_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Report whether at least one dedicated PlatformUser operator exists (public check)."""
    operator_count = int(
        db.scalar(select(func.count(PlatformUser.id)).where(PlatformUser.is_active.is_(True))) or 0
    )
    return {
        "has_operators": operator_count > 0,
        "auth_mode": "email_password_jwt",
    }


@router.post("/auth/setup", status_code=status.HTTP_201_CREATED)
def setup_first_platform_operator(
    payload: PlatformOperatorSetupRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create the initial PlatformUser operator when no operators exist yet (409 otherwise)."""
    existing_count = int(db.scalar(select(func.count(PlatformUser.id))) or 0)
    if existing_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Platform operator already configured. Please sign in with your credentials.",
        )

    if not settings.JWT_SECRET_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform JWT signing key is not configured",
        )

    now = utcnow()
    user = PlatformUser(
        id=uuid.uuid4(),
        email=payload.email,
        full_name=payload.full_name.strip() or "Platform Operations Lead",
        password_hash=hash_password(payload.password),
        role="operations",
        is_active=True,
        created_at=now,
        last_login_at=now,
    )
    db.add(user)
    db.flush()

    AuditService.record_audit(
        db,
        actor_id=user.id,
        actor_type="OPERATIONS",
        action="PLATFORM_OPERATOR_CREATED",
        resource_type="platform_user",
        resource_id=user.id,
        after_state={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)

    token = create_platform_user_token(user)
    ttl_seconds = max(5, int(settings.PLATFORM_JWT_EXPIRE_MINUTES or 720)) * 60
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl_seconds,
        "user": _serialize_platform_user(user),
    }


@router.post("/auth/login")
def login_platform_operator(
    payload: PlatformOperatorLoginRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate a PlatformUser via email + password and issue an HS256 operations JWT."""
    if not settings.JWT_SECRET_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Platform JWT signing key is not configured",
        )

    user = db.scalar(select(PlatformUser).where(PlatformUser.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid platform operator email or password",
        )

    user.last_login_at = utcnow()
    AuditService.record_audit(
        db,
        actor_id=user.id,
        actor_type="OPERATIONS",
        action="PLATFORM_OPERATOR_LOGIN",
        resource_type="platform_user",
        resource_id=user.id,
        after_state={"email": user.email, "role": user.role},
    )
    db.commit()
    db.refresh(user)

    token = create_platform_user_token(user)
    ttl_seconds = max(5, int(settings.PLATFORM_JWT_EXPIRE_MINUTES or 720)) * 60
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl_seconds,
        "user": _serialize_platform_user(user),
    }


@router.get("/auth/me")
def get_current_platform_operator(
    actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the authenticated platform operations profile without leaking credentials."""
    platform_uid = actor.get("platform_user_id") or actor.get("sub")
    user: PlatformUser | None = None
    if platform_uid:
        try:
            user = db.get(PlatformUser, uuid.UUID(str(platform_uid)))
        except ValueError:
            user = None
    if user is not None:
        return {"user": _serialize_platform_user(user)}
    return {
        "user": {
            "id": str(actor.get("sub") or "operations"),
            "email": str(actor.get("email") or "operations@platform.local"),
            "full_name": str(actor.get("full_name") or "Platform Service Operator"),
            "role": str(actor.get("role") or "operations"),
            "is_active": True,
        }
    }


@router.post("/auth/demo-session")
def create_operations_demo_session(
    payload: DemoSessionRequest | None = Body(default=None),
) -> dict[str, Any]:
    """Mint a short-lived signed HS256 JWT exclusively in development/local/test modes."""
    env_name = (settings.ENVIRONMENT or "").strip().lower()
    if env_name not in _DEV_DEMO_ENVS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo session endpoint is disabled outside development/local/test environments",
        )

    secret = settings.JWT_SECRET_KEY.strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY is not configured for demo session issuance",
        )

    req = payload or DemoSessionRequest()
    actor_id = req.user_id if req.user_id is not None else (9001 if req.role == "operations" else 201)
    now = datetime.now(timezone.utc)
    ttl = 3600
    claims: dict[str, Any] = {
        "sub": str(actor_id),
        "user_id": actor_id,
        "role": req.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    if req.role == "merchant":
        claims["shipkart_merchant_id"] = actor_id

    token = jwt.encode(claims, secret, algorithm=settings.JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ttl,
        "role": req.role,
        "actor_id": str(actor_id),
    }


@router.get("/overview")
def get_operations_overview(
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
) -> dict[str, Any]:
    """Operations Command Center KPI overview with separated currency aggregation & SLA breakdown."""
    total_return_cases = int(db.scalar(select(func.count(ReturnCase.id))) or 0)
    refund_cases = list(db.scalars(select(RefundCase).order_by(RefundCase.opened_at.desc())).all())
    open_violations = int(
        db.scalar(select(func.count(ComplianceViolation.id)).where(ComplianceViolation.status == "OPEN"))
        or 0
    )

    requested_by_curr: dict[str, Decimal] = {}
    approved_by_curr: dict[str, Decimal] = {}
    delay_breakdown: dict[str, int] = {code: 0 for code in _ALL_DELAY_RULES}
    delay_owner_breakdown: dict[str, int] = {owner: 0 for owner in _ALL_DELAY_OWNERS}

    active_refund_cases = 0
    overdue_cases_count = 0
    pending_merchant_approvals = 0
    paypal_completed_bank_unconfirmed_count = 0
    active_alerts: list[dict[str, Any]] = []
    recent_cases: list[dict[str, Any]] = []

    delay_svc = DelayService()
    eta_svc = ETAService()
    now_iso = utcnow().isoformat()

    for idx, rc in enumerate(refund_cases):
        status_upper = (rc.status or "").upper()
        is_active = status_upper not in _TERMINAL_CASE_STATUSES
        if is_active:
            active_refund_cases += 1

        req_curr = (rc.currency or rc.original_currency or "USD").strip().upper()
        requested_by_curr[req_curr] = (
            requested_by_curr.get(req_curr, Decimal("0.00"))
            + Decimal(str(rc.requested_amount or "0.00"))
        ).quantize(Decimal("0.01"))

        if rc.approved_amount is not None:
            latest_approved = db.scalar(
                select(RefundApproval)
                .where(
                    RefundApproval.refund_case_id == rc.id,
                    RefundApproval.decision == "APPROVED",
                )
                .order_by(RefundApproval.created_at.desc())
            )
            app_curr = (
                (latest_approved.currency if latest_approved is not None else None)
                or rc.currency
                or rc.original_currency
                or "USD"
            ).strip().upper()
            approved_by_curr[app_curr] = (
                approved_by_curr.get(app_curr, Decimal("0.00"))
                + Decimal(str(rc.approved_amount))
            ).quantize(Decimal("0.01"))

        has_approval = (
            db.scalar(
                select(func.count(RefundApproval.id)).where(RefundApproval.refund_case_id == rc.id)
            )
            or 0
        ) > 0
        if not has_approval and status_upper not in _REJECTED_STATUSES:
            pending_merchant_approvals += 1

        summary, delay_eval = _build_case_summary(db, rc, delay_svc=delay_svc, eta_svc=eta_svc)
        if summary.get("paypal_completed") and not summary.get("issuer_credit_confirmed"):
            paypal_completed_bank_unconfirmed_count += 1

        if is_active:
            delays = list(delay_eval.get("delays") or [])
            if delays:
                overdue_cases_count += 1
                for delay in delays:
                    rule_code = str(delay.get("rule_code") or "")
                    if rule_code:
                        delay_breakdown[rule_code] = delay_breakdown.get(rule_code, 0) + 1
                    active_alerts.append(_format_delay_alert(rc, delay, now_iso))

            owner = str(delay_eval.get("delay_owner") or "NONE")
            delay_owner_breakdown[owner] = delay_owner_breakdown.get(owner, 0) + 1

        if idx < 10:
            recent_cases.append(summary)

    issuer_status, _, _ = _probe_simulator_health(issuer_client)
    reg_status, _, _ = _probe_simulator_health(regulatory_client)
    carrier_status, _, _ = _probe_simulator_health(carrier_client)

    service_status = {
        "nvidia_nim": "CONFIGURED" if settings.is_nvidia_configured else "FALLBACK_ONLY",
        "paypal_sandbox": (
            "CONFIGURED"
            if settings.is_paypal_configured
            else ("MERCHANT_DIRECT" if settings.is_bridge_configured else "UNCONFIGURED")
        ),
        "shipkart_bridge": "CONFIGURED" if settings.is_bridge_configured else "UNCONFIGURED",
        "issuer_simulator": issuer_status,
        "regulatory_simulator": reg_status,
        "carrier_simulator": carrier_status,
        "postgres": "HEALTHY",
        "redis_celery": "CONFIGURED" if settings.REDIS_URL.strip() else "UNCONFIGURED",
        "minio": "CONFIGURED" if settings.MINIO_ACCESS_KEY.strip() else "UNCONFIGURED",
    }

    return {
        "total_return_cases": total_return_cases,
        "total_refund_cases": len(refund_cases),
        "active_refund_cases": active_refund_cases,
        "overdue_cases_count": overdue_cases_count,
        "pending_merchant_approvals": pending_merchant_approvals,
        "open_compliance_violations": open_violations,
        "paypal_completed_bank_unconfirmed_count": paypal_completed_bank_unconfirmed_count,
        "total_requested_by_currency": {k: f"{v:.2f}" for k, v in sorted(requested_by_curr.items())},
        "total_approved_by_currency": {k: f"{v:.2f}" for k, v in sorted(approved_by_curr.items())},
        "delay_breakdown": delay_breakdown,
        "delay_owner_breakdown": delay_owner_breakdown,
        "service_status": service_status,
        "active_alerts": active_alerts,
        "recent_cases": recent_cases,
        "generated_at": now_iso,
    }


@router.get("/cases")
def list_operations_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    delay_owner: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List RefundCases with return status, delay owner, ETA status, and search filtering."""
    stmt = select(RefundCase).order_by(RefundCase.opened_at.desc())
    if status_filter and status_filter.strip():
        stmt = stmt.where(RefundCase.status == status_filter.strip().upper())

    cases = list(db.scalars(stmt).all())
    delay_svc = DelayService()
    eta_svc = ETAService()

    clean_owner = delay_owner.strip().upper() if delay_owner and delay_owner.strip() else None
    clean_search = search.strip().lower() if search and search.strip() else None

    results: list[dict[str, Any]] = []
    for rc in cases:
        if clean_search:
            haystack = " ".join(
                [
                    str(rc.id),
                    str(rc.return_case_id or ""),
                    str(rc.shipkart_order_id or ""),
                    str(rc.shipkart_return_id or ""),
                    str(rc.paypal_order_id or ""),
                    str(rc.paypal_capture_id or ""),
                ]
            ).lower()
            if clean_search not in haystack:
                continue

        summary, _ = _build_case_summary(db, rc, delay_svc=delay_svc, eta_svc=eta_svc)
        if clean_owner and summary["delay_owner"].upper() != clean_owner:
            continue

        results.append(summary)
        if len(results) >= limit:
            break

    return {
        "cases": results,
        "items": results,
        "count": len(results),
    }


@router.get("/cases/{refund_case_id}")
def get_operations_case_detail(
    refund_case_id: str,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Full case drill-down: separated timelines, shipments, inspections, ETA, agents, simulators."""
    rc = resolve_refund_case(db, refund_case_id)
    summary, delay_eval = _build_case_summary(db, rc)

    return_case = db.get(ReturnCase, rc.return_case_id) if rc.return_case_id else None
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
    transactions = list(
        db.scalars(
            select(RefundTransaction)
            .where(RefundTransaction.refund_case_id == rc.id)
            .order_by(RefundTransaction.created_at.desc())
        ).all()
    )
    approvals = list(
        db.scalars(
            select(RefundApproval)
            .where(RefundApproval.refund_case_id == rc.id)
            .order_by(RefundApproval.created_at.desc())
        ).all()
    )

    ev_by_id: dict[uuid.UUID, Evidence] = {
        ev.id: ev
        for ev in db.scalars(select(Evidence).where(Evidence.refund_case_id == rc.id)).all()
    }
    if return_case is not None:
        for ev in db.scalars(select(Evidence).where(Evidence.return_case_id == return_case.id)).all():
            ev_by_id[ev.id] = ev
    evidence_rows = sorted(ev_by_id.values(), key=lambda e: ensure_utc(e.created_at), reverse=True)

    timeline = TimelineService().get_unified_timeline(db, refund_case_id=rc.id)

    def _tag_track(ev: dict[str, Any]) -> dict[str, Any]:
        tagged = dict(ev)
        tagged["timeline_track"] = ev.get("track")
        return tagged

    physical_timeline = [_tag_track(e) for e in timeline["physical_return_events"]]
    financial_timeline = [_tag_track(e) for e in timeline["financial_refund_events"]]
    merged_timeline = [_tag_track(e) for e in timeline["merged_events"]]

    current_eta_row = db.scalar(
        select(RefundEtaEstimate)
        .where(RefundEtaEstimate.refund_case_id == rc.id, RefundEtaEstimate.is_current.is_(True))
        .order_by(RefundEtaEstimate.created_at.desc())
    )
    current_eta = (
        _enrich_eta_dict(current_eta_row)
        if current_eta_row is not None
        else _enrich_eta_dict(ETAService().compute_eta(db, rc.id))
    )

    executions = list(
        db.scalars(
            select(AgentExecution)
            .where(AgentExecution.case_id == rc.id)
            .order_by(AgentExecution.started_at.desc())
        ).all()
    )
    serialized_executions: list[dict[str, Any]] = []
    for ex in executions:
        ex_dict = serialize_execution(ex)
        latency_ms: int | None = None
        if ex.started_at and ex.completed_at:
            latency_ms = max(0, int((ensure_utc(ex.completed_at) - ensure_utc(ex.started_at)).total_seconds() * 1000))
        ex_dict["latency_ms"] = latency_ms
        decs = list(
            db.scalars(
                select(AgentDecision)
                .where(AgentDecision.execution_id == ex.id)
                .order_by(AgentDecision.created_at.asc())
            ).all()
        )
        ex_dict["decisions"] = [serialize_decision(d) for d in decs]
        serialized_executions.append(ex_dict)

    inquiries = list(
        db.scalars(
            select(IssuerInquiry)
            .where(IssuerInquiry.refund_case_id == rc.id)
            .order_by(IssuerInquiry.updated_at.desc(), IssuerInquiry.created_at.desc())
        ).all()
    )
    reg_evals = list(
        db.scalars(
            select(RegulatoryEvaluation)
            .where(RegulatoryEvaluation.refund_case_id == rc.id)
            .order_by(RegulatoryEvaluation.evaluated_at.desc())
        ).all()
    )
    violations = list(
        db.scalars(
            select(ComplianceViolation)
            .where(ComplianceViolation.refund_case_id == rc.id)
            .order_by(ComplianceViolation.created_at.desc())
        ).all()
    )

    now_iso = utcnow().isoformat()
    delay_alerts = [_format_delay_alert(rc, d, now_iso) for d in (delay_eval.get("delays") or [])]

    return {
        **summary,
        "return_case": serialize_return_case(return_case) if return_case is not None else None,
        "shipments": [
            {**serialize_shipment(s), "carrier_reference": s.carrier_reference, "created_at": _iso_dt(s.created_at)}
            for s in shipments
        ],
        "inspections": [
            {**serialize_inspection(i), "inspector_id": str(i.inspector_id) if i.inspector_id else None}
            for i in inspections
        ],
        "transactions": [serialize_transaction(t) for t in transactions],
        "approvals": [serialize_approval(a) for a in approvals],
        "evidence_items": [serialize_evidence(e) for e in evidence_rows],
        "physical_timeline": physical_timeline,
        "financial_timeline": financial_timeline,
        "timeline_events": merged_timeline,
        "current_eta": current_eta,
        "delay_alerts": delay_alerts,
        "agent_executions": serialized_executions,
        "issuer_inquiries": [_enrich_issuer_inquiry_from_db(i) for i in inquiries],
        "regulatory_evaluations": [_enrich_regulatory_eval_from_db(r) for r in reg_evals],
        "compliance_violations": [
            {**serialize_violation(v), "resolved_by": str(v.resolved_by) if v.resolved_by else None}
            for v in violations
        ],
    }


@router.get("/agents/executions")
def list_operations_agent_executions(
    case_id: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List persisted LangGraph agent executions with nested decisions & latency telemetry."""
    stmt = select(AgentExecution).order_by(AgentExecution.started_at.desc()).limit(limit)
    if case_id and case_id.strip():
        try:
            case_uuid = uuid.UUID(case_id.strip())
            stmt = stmt.where(AgentExecution.case_id == case_uuid)
        except ValueError:
            return {"executions": [], "count": 0}
    if agent_name and agent_name.strip():
        stmt = stmt.where(AgentExecution.agent_name == agent_name.strip())
    if status_filter and status_filter.strip():
        stmt = stmt.where(AgentExecution.status == status_filter.strip().upper())

    rows = list(db.scalars(stmt).all())
    executions: list[dict[str, Any]] = []
    for ex in rows:
        item = serialize_execution(ex)
        latency_ms: int | None = None
        if ex.started_at and ex.completed_at:
            latency_ms = max(0, int((ensure_utc(ex.completed_at) - ensure_utc(ex.started_at)).total_seconds() * 1000))
        item["latency_ms"] = latency_ms
        decs = list(
            db.scalars(
                select(AgentDecision)
                .where(AgentDecision.execution_id == ex.id)
                .order_by(AgentDecision.created_at.asc())
            ).all()
        )
        item["decisions"] = [serialize_decision(d) for d in decs]
        executions.append(item)

    return {"executions": executions, "count": len(executions)}


@router.get("/integrations/health")
def get_integrations_health(
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
) -> dict[str, Any]:
    """Inspect connector health across DB, PayPal, NVIDIA, Shipkart Bridge, MinIO, and Simulators."""
    now_iso = utcnow().isoformat()
    connectors: list[dict[str, Any]] = []

    db_t0 = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_status = "HEALTHY"
        db_detail = "SQLAlchemy database connection active"
    except Exception as exc:
        db_status = "DOWN"
        db_detail = f"Database probe failed: {exc}"
    db_ms = int((time.perf_counter() - db_t0) * 1000)
    connectors.append(
        {
            "connector_id": "postgres",
            "name": "PostgreSQL Ledger",
            "category": "CORE",
            "endpoint": "Encrypted Relational Ledger",
            "status": db_status,
            "latency_ms": db_ms,
            "is_simulated": False,
            "details": db_detail,
            "last_checked_at": now_iso,
        }
    )

    connectors.append(
        {
            "connector_id": "minio",
            "name": "Evidence Object Vault",
            "category": "CORE",
            "endpoint": "Private Encrypted Object Store",
            "status": "HEALTHY" if settings.MINIO_ACCESS_KEY.strip() else "UNCONFIGURED",
            "latency_ms": None,
            "is_simulated": False,
            "details": (
                f"Private buckets '{settings.BUCKET_EVIDENCE}' and '{settings.BUCKET_REPORTS}' ready"
                if settings.MINIO_ACCESS_KEY.strip()
                else "Evidence object vault credentials not configured in current environment"
            ),
            "last_checked_at": now_iso,
        }
    )

    connectors.append(
        {
            "connector_id": "redis",
            "name": "Async Task Worker & Scheduler",
            "category": "CORE",
            "endpoint": "Background Job Queue & SLA Beat",
            "status": "HEALTHY" if settings.REDIS_URL.strip() else "UNCONFIGURED",
            "latency_ms": None,
            "is_simulated": False,
            "details": "Celery async reconciliation & SLA breach monitor active",
            "last_checked_at": now_iso,
        }
    )

    connectors.append(
        {
            "connector_id": "nvidia_nim",
            "name": "NVIDIA NIM Reasoning & Vision",
            "category": "EXTERNAL",
            "endpoint": "NVIDIA NIM Cloud Inference API",
            "status": "HEALTHY" if settings.is_nvidia_configured else "DEGRADED",
            "latency_ms": None,
            "is_simulated": False,
            "details": (
                f"Model {settings.NVIDIA_REASONING_MODEL} active"
                if settings.is_nvidia_configured
                else "Deterministic structured fallback active (NVIDIA API key not configured)"
            ),
            "last_checked_at": now_iso,
        }
    )

    paypal_status = (
        "HEALTHY"
        if (settings.is_paypal_configured or settings.is_bridge_configured)
        else "UNCONFIGURED"
    )
    paypal_details = (
        "Platform PayPal gateway ready (merchant credentials strictly isolated)"
        if settings.is_paypal_configured
        else (
            "Per-merchant direct PayPal refunds active via signed Shipkart Service-JWT bridge (no merchant keys stored or exposed here)"
            if settings.is_bridge_configured
            else "PayPal gateway bridge is not configured"
        )
    )
    connectors.append(
        {
            "connector_id": "paypal",
            "name": f"PayPal Refund Gateway ({settings.PAYPAL_ENV})",
            "category": "EXTERNAL",
            "endpoint": "Merchant-Direct PayPal Bridge (Zero Secret Exposure)",
            "status": paypal_status,
            "latency_ms": None,
            "is_simulated": False,
            "details": paypal_details,
            "last_checked_at": now_iso,
        }
    )

    connectors.append(
        {
            "connector_id": "shipkart",
            "name": "Shipkart E-Commerce Bridge",
            "category": "EXTERNAL",
            "endpoint": "Signed HMAC & Service JWT Bridge",
            "status": "HEALTHY" if settings.is_bridge_configured else "UNCONFIGURED",
            "latency_ms": None,
            "is_simulated": False,
            "details": (
                "HMAC-SHA256 + Service JWT bridge active"
                if settings.is_bridge_configured
                else "Bridge shared secret / service JWT secret not configured"
            ),
            "last_checked_at": now_iso,
        }
    )

    for cid, name, label, cli in (
        ("issuer_simulator", "Issuer / Bank Simulator", "Synthetic Bank & Card Posting Rail", issuer_client),
        ("regulatory_simulator", "India/USA Regulatory Simulator", "India & USA Compliance Rule Engine", regulatory_client),
        ("carrier_simulator", "Carrier Reverse-Logistics Simulator", "Synthetic Reverse-Logistics Rail", carrier_client),
    ):
        sim_status, sim_ms, sim_detail = _probe_simulator_health(cli)
        connectors.append(
            {
                "connector_id": cid,
                "name": name,
                "category": "SIMULATOR",
                "endpoint": label,
                "status": sim_status,
                "latency_ms": sim_ms,
                "is_simulated": True,
                "details": sim_detail,
                "last_checked_at": now_iso,
            }
        )

    statuses = {c["status"] for c in connectors}
    if db_status == "DOWN":
        overall_status = "DOWN"
    elif "DOWN" in statuses or "DEGRADED" in statuses:
        overall_status = "DEGRADED"
    else:
        overall_status = "HEALTHY"

    return {
        "overall_status": overall_status,
        "checked_at": now_iso,
        "connectors": connectors,
    }


@router.get("/eta")
def get_operations_eta_overview(
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return current deterministic ETA snapshots and active DELAY-001..DELAY-006 SLA alerts."""
    now_iso = utcnow().isoformat()
    cases = list(db.scalars(select(RefundCase).order_by(RefundCase.opened_at.desc())).all())
    delay_svc = DelayService()
    eta_svc = ETAService()

    estimates: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []

    for rc in cases:
        eta_row = db.scalar(
            select(RefundEtaEstimate)
            .where(RefundEtaEstimate.refund_case_id == rc.id, RefundEtaEstimate.is_current.is_(True))
            .order_by(RefundEtaEstimate.created_at.desc())
        )
        if eta_row is not None:
            estimates.append(_enrich_eta_dict(eta_row))
        else:
            computed = eta_svc.compute_eta(db, rc.id)
            eta_dict = _enrich_eta_dict(computed)
            eta_dict["id"] = str(rc.id)
            eta_dict["is_current"] = True
            eta_dict["created_at"] = now_iso
            estimates.append(eta_dict)

        if (rc.status or "").upper() not in _TERMINAL_CASE_STATUSES:
            report = delay_svc.evaluate_delays(db, rc.id)
            for delay in report.get("delays") or []:
                alerts.append(_format_delay_alert(rc, delay, now_iso))

    return {
        "estimates": estimates,
        "alerts": alerts,
        "generated_at": now_iso,
    }


@router.get("/issuer-simulator/inquiries")
def list_operations_issuer_inquiries(
    refund_case_id: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
) -> dict[str, Any]:
    """List simulated issuer/bank posting inquiries merged with persisted DB records."""
    sim_resp = issuer_client.list_inquiries(
        refund_case_id=refund_case_id,
        scenario=scenario,
        status=status_filter,
    )
    sim_list = list(sim_resp.get("inquiries") or [])
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in sim_list:
        if not isinstance(item, dict):
            continue
        item_copy = redact_sensitive_data(dict(item))
        key = str(item_copy.get("inquiry_id") or item_copy.get("id") or "")
        if key:
            item_copy.setdefault("id", key)
            item_copy.setdefault("inquiry_id", key)
            seen_ids.add(key)
        normalized.append(item_copy)

    stmt = select(IssuerInquiry).order_by(IssuerInquiry.updated_at.desc())
    if refund_case_id and refund_case_id.strip():
        try:
            stmt = stmt.where(IssuerInquiry.refund_case_id == uuid.UUID(refund_case_id.strip()))
        except ValueError:
            stmt = stmt.where(IssuerInquiry.refund_case_id == uuid.UUID(int=0))

    for db_inq in db.scalars(stmt).all():
        enriched = _enrich_issuer_inquiry_from_db(db_inq)
        key = str(enriched.get("inquiry_id") or enriched.get("id") or "")
        if key and key in seen_ids:
            continue
        if scenario and str(enriched.get("scenario") or "").upper() != scenario.strip().upper():
            continue
        if status_filter and str(enriched.get("status") or "").upper() != status_filter.strip().upper():
            continue
        normalized.append(enriched)

    return {
        "inquiries": normalized,
        "count": len(normalized),
        "is_simulated": True,
        "simulation_label": "SIMULATED",
    }


@router.post("/issuer-simulator/inquiries", status_code=status.HTTP_201_CREATED)
def create_operations_issuer_inquiry(
    payload: CreateIssuerInquiryRequest,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
) -> dict[str, Any]:
    """Create a simulated issuer inquiry (masked card_last4 only) and persist DB link if found."""
    sim_resp = issuer_client.create_inquiry(
        refund_case_id=payload.refund_case_id,
        paypal_capture_id=payload.paypal_capture_id,
        paypal_refund_id=payload.paypal_refund_id,
        paypal_refund_status=payload.paypal_refund_status,
        institution_code=payload.institution_code,
        card_network=payload.card_network,
        card_last4=payload.card_last4,
        amount=payload.amount,
        currency=payload.currency.strip().upper(),
        scenario=payload.scenario.strip().upper(),
    )
    sanitized = _json_safe(sim_resp)
    inq_id = str(sanitized.get("inquiry_id") or sanitized.get("id") or f"INQ-{uuid.uuid4().hex[:8].upper()}")
    sanitized["id"] = inq_id
    sanitized["inquiry_id"] = inq_id
    sanitized.setdefault("is_simulated", True)
    sanitized.setdefault("simulation_label", "SIMULATED")

    try:
        case_uuid = uuid.UUID(payload.refund_case_id.strip())
    except ValueError:
        case_uuid = None

    if case_uuid is not None:
        refund_case = db.get(RefundCase, case_uuid)
        if refund_case is not None:
            db_inq = IssuerInquiry(
                id=uuid.uuid4(),
                refund_case_id=refund_case.id,
                provider_type="SIMULATOR",
                provider_reference=inq_id,
                institution_code=payload.institution_code,
                status=str(sanitized.get("status") or "INITIATED"),
                request_data=_json_safe(payload.model_dump()),
                response_data=sanitized,
                is_simulated=True,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(db_inq)
            db.commit()

    return sanitized


@router.post("/issuer-simulator/scenarios/{inquiry_id}/trigger")
def trigger_operations_issuer_scenario(
    inquiry_id: str,
    payload: TriggerScenarioRequest,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    issuer_client: IssuerSimulatorClient = Depends(get_issuer_client),
) -> dict[str, Any]:
    """Trigger one of the 8 Blueprint issuer posting scenarios on a simulated inquiry."""
    sim_resp = issuer_client.trigger_scenario(
        inquiry_id,
        payload.scenario.strip().upper(),
        note=payload.note,
    )
    sanitized = _json_safe(sim_resp)
    resolved_id = str(sanitized.get("inquiry_id") or sanitized.get("id") or inquiry_id)
    sanitized["id"] = resolved_id
    sanitized["inquiry_id"] = resolved_id
    sanitized.setdefault("is_simulated", True)

    db_inq = db.scalar(
        select(IssuerInquiry).where(IssuerInquiry.provider_reference == resolved_id)
    )
    if db_inq is None:
        try:
            db_inq = db.get(IssuerInquiry, uuid.UUID(resolved_id))
        except ValueError:
            db_inq = None

    if db_inq is not None:
        db_inq.status = str(sanitized.get("status") or db_inq.status)
        db_inq.response_data = sanitized
        db_inq.updated_at = utcnow()
        refund_case = db.get(RefundCase, db_inq.refund_case_id)
        if refund_case is not None:
            credit_posted = bool(sanitized.get("credit_posted")) or db_inq.status.upper() in _ISSUER_POSTED_STATUSES
            if credit_posted and not sanitized.get("requires_manual_reconciliation"):
                refund_case.status = "CONFIRMED_POSTED"
            TimelineService().record_event(
                db,
                refund_case_id=refund_case.id,
                return_case_id=refund_case.return_case_id,
                event_type=f"ISSUER_{db_inq.status.upper()}",
                source_type="ISSUER_SIMULATOR",
                source_reference=f"{resolved_id}:{db_inq.status}:{sanitized.get('scenario', '')}",
                description=(
                    f"Simulated issuer inquiry {resolved_id} transitioned to {db_inq.status} "
                    f"(credit_posted={bool(sanitized.get('credit_posted'))})."
                ),
                occurred_at=utcnow(),
                event_data=sanitized,
                verified=True,
            )
            ETAService().compute_and_persist_eta(db, refund_case.id)
        db.commit()

    return sanitized


@router.get("/carrier-simulator/shipments")
def list_operations_carrier_shipments(
    return_case_id: str | None = Query(default=None),
    shipkart_order_id: str | None = Query(default=None),
    carrier_name: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
) -> dict[str, Any]:
    """List simulated reverse-logistics shipments from Carrier Simulator."""
    resp = carrier_client.list_shipments(
        return_case_id=return_case_id,
        shipkart_order_id=shipkart_order_id,
        carrier_name=carrier_name,
        status=status_filter,
    )
    shipments = list(resp.get("shipments") or [])
    return {
        "shipments": shipments,
        "count": len(shipments),
        "is_simulated": True,
        "simulation_label": "SIMULATED",
    }


@router.post("/carrier-simulator/shipments", status_code=status.HTTP_201_CREATED)
def create_operations_carrier_shipment(
    payload: CreateCarrierShipmentRequest,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
) -> dict[str, Any]:
    """Create a simulated carrier reverse-pickup shipment and sync matching ReturnCase."""
    resp = carrier_client.create_shipment(
        return_case_id=payload.return_case_id,
        shipkart_order_id=payload.shipkart_order_id,
        carrier_name=payload.carrier_name,
        tracking_number=payload.tracking_number,
        scenario=payload.scenario,
        origin_city=payload.origin_city,
        destination_city=payload.destination_city,
    )
    sanitized = _json_safe(resp)
    tracking_no = str(sanitized.get("tracking_number") or payload.tracking_number or "").strip()
    sim_status = str(sanitized.get("current_status") or sanitized.get("status") or "LABEL_CREATED").upper()

    return_case: ReturnCase | None = None
    refund_case: RefundCase | None = None
    try:
        ref_uuid = uuid.UUID(payload.return_case_id.strip())
        return_case = db.get(ReturnCase, ref_uuid)
        if return_case is None:
            refund_case = db.get(RefundCase, ref_uuid)
            if refund_case is not None and refund_case.return_case_id is not None:
                return_case = db.get(ReturnCase, refund_case.return_case_id)
    except ValueError:
        return_case = None

    if return_case is not None and tracking_no:
        if refund_case is None:
            refund_case = db.scalar(
                select(RefundCase)
                .where(RefundCase.return_case_id == return_case.id)
                .order_by(RefundCase.opened_at.desc())
            )
        existing_ship = db.scalar(
            select(ReturnShipment).where(ReturnShipment.tracking_number == tracking_no)
        )
        now = utcnow()
        if existing_ship is None:
            db.add(
                ReturnShipment(
                    id=uuid.uuid4(),
                    return_case_id=return_case.id,
                    carrier_name=payload.carrier_name,
                    tracking_number=tracking_no,
                    carrier_reference=str(sanitized.get("shipment_id") or tracking_no),
                    status=sim_status,
                    is_simulated=True,
                    pickup_at=now if sim_status in {"PICKED_UP", "IN_TRANSIT", "DELIVERED_TO_MERCHANT"} else None,
                    delivered_at=now if sim_status == "DELIVERED_TO_MERCHANT" else None,
                    last_synced_at=now,
                    created_at=now,
                )
            )
        TimelineService().record_event(
            db,
            refund_case_id=refund_case.id if refund_case else None,
            return_case_id=return_case.id,
            event_type=f"CARRIER_{sim_status}",
            source_type="CARRIER_SIMULATOR",
            source_reference=f"{tracking_no}:{sim_status}",
            description=f"Simulated carrier shipment {tracking_no} created ({payload.carrier_name}, status={sim_status}).",
            occurred_at=now,
            event_data=sanitized,
            verified=True,
        )
        if refund_case is not None:
            ETAService().compute_and_persist_eta(db, refund_case.id)
        db.commit()

    return sanitized


@router.post("/carrier-simulator/shipments/{tracking_number}/scenario")
def trigger_operations_carrier_scenario(
    tracking_number: str,
    payload: TriggerScenarioRequest,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    carrier_client: CarrierSimulatorClient = Depends(get_carrier_client),
) -> dict[str, Any]:
    """Trigger a synthetic carrier delay/delivery scenario and sync matching ReturnShipment row."""
    resp = carrier_client.trigger_scenario(
        tracking_number,
        payload.scenario.strip().upper(),
        note=payload.note,
    )
    sanitized = _json_safe(resp)

    db_ship = db.scalar(
        select(ReturnShipment).where(ReturnShipment.tracking_number == tracking_number)
    )
    if db_ship is not None:
        now = utcnow()
        new_status = str(sanitized.get("current_status") or sanitized.get("status") or db_ship.status).upper()
        db_ship.status = new_status
        db_ship.last_synced_at = now
        if new_status == "DELIVERED_TO_MERCHANT" and db_ship.delivered_at is None:
            db_ship.delivered_at = now
        elif new_status == "PICKED_UP" and db_ship.pickup_at is None:
            db_ship.pickup_at = now

        refund_case = db.scalar(
            select(RefundCase)
            .where(RefundCase.return_case_id == db_ship.return_case_id)
            .order_by(RefundCase.opened_at.desc())
        )
        TimelineService().record_event(
            db,
            refund_case_id=refund_case.id if refund_case else None,
            return_case_id=db_ship.return_case_id,
            event_type=f"CARRIER_{new_status}",
            source_type="CARRIER_SIMULATOR",
            source_reference=f"{tracking_number}:{new_status}:{payload.scenario.strip().upper()}",
            description=(
                f"Simulated carrier shipment {tracking_number} updated to {new_status} "
                f"(scenario={payload.scenario.strip().upper()})."
            ),
            occurred_at=now,
            event_data=sanitized,
            verified=True,
        )
        if refund_case is not None:
            ETAService().compute_and_persist_eta(db, refund_case.id)
        db.commit()

    return sanitized


@router.get("/regulatory")
def list_operations_regulatory_evaluations(
    jurisdiction: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List persisted India/USA regulatory evaluations."""
    stmt = select(RegulatoryEvaluation).order_by(RegulatoryEvaluation.evaluated_at.desc()).limit(limit)
    if jurisdiction and jurisdiction.strip():
        stmt = stmt.where(RegulatoryEvaluation.jurisdiction == jurisdiction.strip().upper()[:2])
    if status_filter and status_filter.strip():
        stmt = stmt.where(RegulatoryEvaluation.evaluation_status == status_filter.strip().upper())

    rows = list(db.scalars(stmt).all())
    return {
        "evaluations": [_enrich_regulatory_eval_from_db(ev) for ev in rows],
        "count": len(rows),
        "is_simulated": True,
        "disclaimer": REGULATORY_DISCLAIMER,
    }


@router.get("/regulatory/rules")
def list_operations_regulatory_rules(
    jurisdiction: str | None = Query(default=None),
    version: str | None = Query(default=None),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
) -> dict[str, Any]:
    """Retrieve versioned IN/US regulatory catalog rules from the Regulatory Simulator."""
    resp = regulatory_client.get_rules(jurisdiction=jurisdiction, version=version)
    rules = list(resp.get("rules") or [])
    return {
        "rules": rules,
        "total": len(rules),
        "is_simulated": True,
        "disclaimer": resp.get("disclaimer") or REGULATORY_DISCLAIMER,
    }


@router.post("/regulatory/evaluate")
def evaluate_operations_regulatory(
    payload: RegulatoryEvaluateRequest,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
    regulatory_client: RegulatorySimulatorClient = Depends(get_regulatory_client),
) -> dict[str, Any]:
    """Evaluate a refund context against the Regulatory Simulator and persist the evaluation."""
    ctx = payload.model_dump(exclude_none=True)
    sim_resp = regulatory_client.evaluate(ctx)
    sanitized = _json_safe(sim_resp)

    raw_status = sanitized.get("status") or sanitized.get("evaluation_status") or "UNKNOWN"
    eval_status = str(raw_status).strip().upper()
    raw_jurisdiction = sanitized.get("jurisdiction")
    jurisdiction_char2 = _normalize_jurisdiction_char2(raw_jurisdiction, ctx)

    raw_versions = sanitized.get("rule_versions") or sanitized.get("rule_version") or "unknown"
    if isinstance(raw_versions, list):
        rule_version = ",".join(str(v) for v in raw_versions if v)[:80] or "unknown"
    else:
        rule_version = str(raw_versions)[:80]

    case_uuid: uuid.UUID | None = None
    if payload.refund_case_id:
        try:
            candidate = uuid.UUID(payload.refund_case_id.strip())
            if db.get(RefundCase, candidate) is not None:
                case_uuid = candidate
        except ValueError:
            case_uuid = None

    row = RegulatoryEvaluation(
        id=uuid.uuid4(),
        refund_case_id=case_uuid,
        jurisdiction=jurisdiction_char2,
        evaluation_status=eval_status,
        transaction_context=ctx,
        rule_version=rule_version,
        matched_rules=list(sanitized.get("matched_rules") or []),
        unresolved_questions=list(sanitized.get("unresolved_questions") or []),
        is_simulated=bool(sanitized.get("is_simulated", True)),
        evaluated_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    out = _enrich_regulatory_eval_from_db(row)
    out["jurisdiction"] = raw_jurisdiction if raw_jurisdiction is not None else jurisdiction_char2
    out["transaction_id"] = payload.transaction_id
    out["obligations"] = list(sanitized.get("obligations") or [])
    out["evaluation_id"] = str(sanitized.get("evaluation_id") or row.id)
    out["disclaimer"] = str(sanitized.get("disclaimer") or REGULATORY_DISCLAIMER)
    return out


@router.get("/compliance")
def get_operations_compliance_overview(
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return deterministic policy rules catalog and persisted ComplianceViolation records."""
    violations = list(
        db.scalars(
            select(ComplianceViolation).order_by(ComplianceViolation.created_at.desc()).limit(200)
        ).all()
    )
    total_open = sum(1 for v in violations if (v.status or "").upper() == "OPEN")
    return {
        "rules": COMPLIANCE_RULES_CATALOG,
        "violations": [
            {**serialize_violation(v), "resolved_by": str(v.resolved_by) if v.resolved_by else None}
            for v in violations
        ],
        "total_open": total_open,
    }


@router.get("/audit")
def list_operations_audit_logs(
    resource_type: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return append-only redacted AuditLog entries with filtering."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if resource_type and resource_type.strip():
        stmt = stmt.where(AuditLog.resource_type == resource_type.strip())
    if actor_type and actor_type.strip():
        stmt = stmt.where(AuditLog.actor_type == actor_type.strip().upper())
    if action and action.strip():
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if resource_id and resource_id.strip():
        try:
            stmt = stmt.where(AuditLog.resource_id == uuid.UUID(resource_id.strip()))
        except ValueError:
            return {"logs": [], "count": 0}

    rows = list(db.scalars(stmt).all())
    logs = [
        {
            "id": str(row.id),
            "actor_id": str(row.actor_id) if row.actor_id else None,
            "shipkart_actor_id": row.shipkart_actor_id,
            "actor_type": row.actor_type,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id),
            "before_state": redact_sensitive_data(row.before_state),
            "after_state": redact_sensitive_data(row.after_state),
            "ip_address": row.ip_address,
            "created_at": _iso_dt(row.created_at),
        }
        for row in rows
    ]
    return {"logs": logs, "count": len(logs)}


@router.post("/sync-shipkart-pending")
def sync_pending_returns_from_shipkart(
    background_tasks: BackgroundTasks,
    _actor: dict[str, Any] = Depends(_OPS_ROLES),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Pull active returns from Shipkart via Service JWT and idempotently provision missing cases."""
    import os
    from app.api.v1.internal_and_webhooks import (
        BridgeReturnEventPayload,
        _trigger_pipeline_bg,
        upsert_shipkart_return_event,
    )
    from app.integrations.shipkart_client import ShipkartBridgeClient, ShipkartBridgeError

    if not settings.SERVICE_JWT_SECRET.strip() or not settings.SHIPKART_API_URL.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SHIPKART_API_URL and SERVICE_JWT_SECRET must both be configured to sync pending returns.",
        )

    client = ShipkartBridgeClient(timeout=25.0)
    try:
        pending = client.fetch_pending_returns()
    except ShipkartBridgeError as exc:
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    created_count = 0
    existing_count = 0
    errors: list[dict[str, Any]] = []
    synced_case_ids: list[str] = []

    for ret in pending:
        ret_id = ret.get("id")
        order_id = ret.get("order_id")
        if ret_id is None or order_id is None:
            continue
        existing_rc = db.scalar(select(ReturnCase).where(ReturnCase.shipkart_return_id == int(ret_id)))
        if existing_rc is not None:
            existing_count += 1
            continue
        try:
            order_ctx = client.fetch_order_context(int(order_id))
            matched_item = next(
                (i for i in (order_ctx.get("items") or []) if i.get("id") == ret.get("order_item_id")),
                None,
            )
            qty = int(matched_item.get("quantity") or 1) if matched_item else 1
            payload = BridgeReturnEventPayload.model_validate(
                {
                    "event_type": "RETURN_REQUESTED",
                    "shipkart_return_id": int(ret_id),
                    "shipkart_order_id": int(order_id),
                    "shipkart_order_item_id": ret.get("order_item_id"),
                    "shipkart_customer_id": int(ret.get("user_id") or order_ctx.get("user_id") or 0),
                    "shipkart_merchant_id": ret.get("merchant_id") or (matched_item.get("merchant_id") if matched_item else None),
                    "reason": ret.get("reason") or "RETURN_REQUEST",
                    "comments": ret.get("comments") or "",
                    "evidence_urls": list(ret.get("evidence_urls") or []),
                    "quantity_requested": qty,
                    "purchased_quantity": qty,
                    "unit_price": str(matched_item["price"]) if matched_item and matched_item.get("price") is not None else None,
                    "refund_amount": str(ret.get("refund_amount") or "0.00"),
                    "refund_currency": ret.get("refund_currency") or order_ctx.get("original_currency") or "INR",
                    "refund_paypal_amount": (
                        str(ret["refund_paypal_amount"])
                        if ret.get("refund_paypal_amount") is not None
                        else None
                    ),
                    "captured_amount": (
                        str(order_ctx["paypal_amount"])
                        if order_ctx.get("paypal_amount") is not None
                        else None
                    ),
                    "original_currency": order_ctx.get("original_currency") or "INR",
                    "paypal_currency": order_ctx.get("paypal_currency") or "USD",
                    "paypal_capture_id": order_ctx.get("paypal_capture_id"),
                    "paypal_order_id": order_ctx.get("paypal_order_id"),
                    "status": ret.get("status") or "REQUESTED",
                    "refund_transaction_id": ret.get("refund_transaction_id"),
                    "merchant_notes": ret.get("merchant_notes"),
                }
            )
            created, _updated, _rc, refund_case = upsert_shipkart_return_event(db, payload)
            if created and refund_case is not None:
                created_count += 1
                synced_case_ids.append(str(refund_case.id))
                if "PYTEST_CURRENT_TEST" not in os.environ:
                    background_tasks.add_task(
                        _trigger_pipeline_bg,
                        str(refund_case.id),
                        payload.customer_description or payload.reason_code,
                    )
        except Exception as exc:
            db.rollback()
            errors.append({"shipkart_return_id": ret_id, "error": redact_sensitive_data(str(exc))})

    return {
        "scanned": len(pending),
        "created": created_count,
        "already_present": existing_count,
        "synced_case_ids": synced_case_ids,
        "errors": errors,
    }

