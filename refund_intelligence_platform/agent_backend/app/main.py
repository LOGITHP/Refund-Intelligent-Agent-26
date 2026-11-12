"""FastAPI application entrypoint for Refund Intelligence Platform Agent Backend."""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging_redact import RedactingFormatter, redact_sensitive_data
from app.core.security import hash_password
from app.db.base import utcnow
from app.db.models import PlatformUser
from app.db.session import SessionLocal, get_db
from app.integrations.paypal_client import PayPalAPIError
from app.integrations.shipkart_client import ShipkartBridgeError
from app.integrations.simulators import SimulatorClientError
from app.services.compliance_service import ComplianceViolationError
from app.services.evidence_service import EvidenceValidationError

logger = logging.getLogger("refund_intelligence")


def _configure_redacted_logging() -> None:
    """Attach RedactingFormatter across console handlers without breaking test capture."""
    formatter = RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler) and type(handler) is logging.StreamHandler:
                handler.setFormatter(formatter)

    app_logger = logging.getLogger("app")
    if app_logger.level == logging.NOTSET:
        app_logger.setLevel(logging.INFO)


def _bootstrap_platform_operator() -> None:
    """Idempotently seed an initial PlatformUser when explicitly configured via env vars."""
    email = (settings.PLATFORM_ADMIN_EMAIL or "").strip().lower()
    password = (settings.PLATFORM_ADMIN_PASSWORD or "").strip()
    if not email or len(password) < 8:
        return
    try:
        with SessionLocal() as db:
            existing = db.scalar(select(PlatformUser).where(PlatformUser.email == email))
            if existing is None:
                db.add(
                    PlatformUser(
                        id=uuid.uuid4(),
                        email=email,
                        full_name="Platform Operations Lead",
                        password_hash=hash_password(password),
                        role="operations",
                        is_active=True,
                        created_at=utcnow(),
                    )
                )
                db.commit()
    except Exception as exc:
        logger.warning("Skipping env platform operator seed: %s", redact_sensitive_data(str(exc)))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_redacted_logging()
    _bootstrap_platform_operator()
    logger.info(
        "Starting Refund Intelligence Platform API (env=%s, paypal_env=%s, nvidia_configured=%s)",
        settings.ENVIRONMENT,
        settings.PAYPAL_ENV,
        settings.is_nvidia_configured,
    )
    yield


def _json_safe(data: Any) -> Any:
    return json.loads(json.dumps(redact_sensitive_data(data), default=str))


def _request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return str(rid)
    new_id = uuid.uuid4().hex
    request.state.request_id = new_id
    return new_id


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    safe_details = _json_safe(details) if details is not None else {}
    if not isinstance(safe_details, dict):
        safe_details = {"items": safe_details}
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": str(redact_sensitive_data(message)),
                "request_id": _request_id(request),
                "details": safe_details,
            }
        },
    )


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id_middleware(request: Request, call_next: Any):
    incoming = (request.headers.get("X-Request-ID") or "").strip()
    req_id = incoming or uuid.uuid4().hex
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


@app.exception_handler(ComplianceViolationError)
async def compliance_violation_handler(
    request: Request,
    exc: ComplianceViolationError,
) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.rule_code,
        message=exc.message,
        details=exc.details,
    )


@app.exception_handler(EvidenceValidationError)
async def evidence_validation_handler(
    request: Request,
    exc: EvidenceValidationError,
) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.error_code,
        message=str(exc),
        details=exc.detail if exc.detail is not None else {},
    )


@app.exception_handler(PayPalAPIError)
async def paypal_error_handler(request: Request, exc: PayPalAPIError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        code="PAYPAL_API_ERROR",
        message=str(exc),
        details={"provider_detail": exc.detail} if exc.detail is not None else {},
    )


@app.exception_handler(SimulatorClientError)
async def simulator_error_handler(request: Request, exc: SimulatorClientError) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        code="SIMULATOR_ERROR",
        message=str(exc),
        details={"simulator_detail": exc.detail} if exc.detail is not None else {},
    )


@app.exception_handler(ShipkartBridgeError)
async def shipkart_bridge_error_handler(
    request: Request,
    exc: ShipkartBridgeError,
) -> JSONResponse:
    return _error_response(
        request,
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        code="SHIPKART_BRIDGE_ERROR",
        message=str(exc),
        details={"bridge_detail": exc.detail} if exc.detail is not None else {},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    detail = exc.detail
    message = detail if isinstance(detail, str) else "HTTP request error"
    details = {} if isinstance(detail, str) else detail
    return _error_response(
        request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=message,
        details=details,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return _error_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details={"errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = _request_id(request)
    logger.exception(
        "Unhandled server exception request_id=%s error=%s",
        req_id,
        redact_sensitive_data(str(exc)),
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_SERVER_ERROR",
        message="An internal server error occurred",
        details={},
    )


@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)) -> JSONResponse:
    """Service liveness and database readiness probe."""
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    payload = {
        "status": "ok" if db_ok else "degraded",
        "service": "refund-intelligence-agent-core",
        "database": "ok" if db_ok else "unavailable",
        "nvidia_configured": settings.is_nvidia_configured,
        "paypal_env": settings.PAYPAL_ENV,
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


app.include_router(api_router, prefix=settings.API_V1_STR)

