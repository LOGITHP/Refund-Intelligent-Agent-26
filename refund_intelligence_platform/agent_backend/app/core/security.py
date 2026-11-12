"""Service JWT, Shipkart user JWT, HMAC bridge verification, and FastAPI RBAC dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

ALLOWED_USER_ROLES = frozenset({"customer", "merchant", "operations", "admin"})

_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def compute_hmac_signature(raw_body: bytes, secret: str) -> str:
    """Compute hex-encoded HMAC-SHA256 digest for a raw request body."""
    if not secret or not secret.strip():
        raise ValueError("HMAC secret must not be empty")
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def verify_hmac_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify an HMAC-SHA256 signature header (`sha256=<hex>` or raw `<hex>`) in constant time."""
    if not signature_header or not secret or not secret.strip():
        return False

    candidate = signature_header.strip()
    if candidate.lower().startswith("sha256="):
        candidate = candidate[7:].strip()
    if not candidate:
        return False

    expected = compute_hmac_signature(raw_body, secret)
    return hmac.compare_digest(expected.lower(), candidate.lower())


def create_service_jwt(
    subject: str = "refund-agent-core",
    scope: str = "bridge:read_write",
    extra_claims: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> str:
    """Mint an HS256 service-to-service JWT signed with `settings.SERVICE_JWT_SECRET`."""
    secret = settings.SERVICE_JWT_SECRET.strip()
    if not secret:
        raise RuntimeError("SERVICE_JWT_SECRET is not configured")

    ttl = ttl_seconds if ttl_seconds is not None else settings.SERVICE_JWT_EXPIRE_SECONDS
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = dict(extra_claims or {})
    payload.update(
        {
            "sub": subject,
            "iss": settings.SERVICE_JWT_ISSUER,
            "scope": scope,
            "token_type": "service",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        }
    )
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def verify_service_jwt(token: str) -> dict[str, Any]:
    """Validate an incoming service JWT against `settings.SERVICE_JWT_SECRET`."""
    secret = settings.SERVICE_JWT_SECRET.strip()
    if not secret:
        raise RuntimeError("SERVICE_JWT_SECRET is not configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.SERVICE_JWT_ISSUER,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired service token") from exc

    if not payload.get("sub"):
        raise _unauthorized("Service token missing subject")
    return payload


def verify_shipkart_user_token(token: str) -> dict[str, Any]:
    """Decode and validate a Shipkart/platform user JWT signed with `settings.JWT_SECRET_KEY`."""
    secret = settings.JWT_SECRET_KEY.strip()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired user token") from exc

    sub = payload.get("sub")
    user_id = payload.get("user_id")
    if sub is None and user_id is None:
        raise _unauthorized("User token missing subject identifier")

    sub_str = str(sub if sub is not None else user_id)
    role = str(payload.get("role") or "").strip().lower()
    if role not in ALLOWED_USER_ROLES:
        raise _unauthorized("User token missing valid role")

    return {
        **payload,
        "sub": sub_str,
        "user_id": user_id if user_id is not None else sub_str,
        "role": role,
        "token_type": "user",
    }


def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency resolving the authenticated actor (service JWT or user JWT)."""
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials.strip()
    ):
        raise _unauthorized("Missing bearer authentication token")

    token = credentials.credentials.strip()

    if settings.SERVICE_JWT_SECRET.strip():
        try:
            claims = verify_service_jwt(token)
            return {
                **claims,
                "role": str(claims.get("role") or "service").strip().lower(),
                "token_type": "service",
            }
        except HTTPException:
            pass

    if settings.JWT_SECRET_KEY.strip():
        return verify_shipkart_user_token(token)

    raise _unauthorized("Invalid or unverifiable authentication token")


def require_roles(*roles: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """FastAPI dependency factory enforcing that the authenticated actor holds one of `roles`."""
    allowed = {role.strip().lower() for role in roles if role and role.strip()}

    def _role_guard(actor: dict[str, Any] = Depends(get_current_actor)) -> dict[str, Any]:
        actor_role = str(actor.get("role") or "").strip().lower()
        if actor_role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Actor role '{actor_role or 'unknown'}' is not authorized for this resource",
            )
        return actor

    return _role_guard


async def verify_bridge_hmac(
    request: Request,
    x_bridge_signature: str | None = Header(default=None, alias="X-Bridge-Signature"),
) -> bytes:
    """FastAPI dependency validating `X-Bridge-Signature` against the raw request body."""
    secret = settings.BRIDGE_SHARED_SECRET.strip()
    if not secret:
        raise _unauthorized("Bridge HMAC verification secret is not configured")
    if not x_bridge_signature:
        raise _unauthorized("Missing X-Bridge-Signature header")

    raw_body = await request.body()
    if not verify_hmac_signature(raw_body, x_bridge_signature, secret):
        raise _unauthorized("Invalid X-Bridge-Signature header")
    return raw_body


def hash_password(password: str) -> str:
    """Hash a plaintext password using salted scrypt for platform operator storage."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        maxmem=32 * 1024 * 1024,
        dklen=32,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"scrypt$16384$8$1${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored salted scrypt hash in constant time."""
    if not password or not stored_hash:
        return False
    try:
        parts = stored_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        n_val = int(parts[1])
        r_val = int(parts[2])
        p_val = int(parts[3])
        salt = base64.b64decode(parts[4].encode("ascii"))
        expected = base64.b64decode(parts[5].encode("ascii"))
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n_val,
            r=r_val,
            p=p_val,
            maxmem=32 * 1024 * 1024,
            dklen=len(expected),
        )
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def create_platform_user_token(user: Any) -> str:
    """Mint an HS256 JWT for a dedicated PlatformUser (decoupled from Shipkart accounts)."""
    secret = settings.JWT_SECRET_KEY.strip()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured")

    now = datetime.now(timezone.utc)
    ttl_minutes = max(5, int(settings.PLATFORM_JWT_EXPIRE_MINUTES or 720))
    role = str(getattr(user, "role", "operations") or "operations").strip().lower()
    if role not in {"operations", "admin"}:
        role = "operations"
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "platform_user_id": str(user.id),
        "email": str(user.email),
        "full_name": str(getattr(user, "full_name", "Platform Operator") or "Platform Operator"),
        "role": role,
        "token_type": "platform_ops",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)
