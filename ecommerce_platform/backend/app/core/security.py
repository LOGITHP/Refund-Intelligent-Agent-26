from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, Optional
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_service_jwt_token(token: str) -> Dict[str, Any]:
    """Verifies an HS256 inter-service JWT signed with SERVICE_JWT_SECRET."""
    secret = (settings.SERVICE_JWT_SECRET or "").strip()
    if not secret:
        raise jwt.InvalidTokenError("Service JWT secret is not configured")

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=settings.SERVICE_JWT_ISSUER,
        options={"require": ["exp", "iss", "sub"]},
    )
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise jwt.InvalidTokenError("Service JWT missing valid subject")
    return payload


def compute_bridge_hmac(raw_body: bytes, secret: str) -> str:
    """Computes sha256=<hex> HMAC signature for authenticated Shipkart -> Agent bridge relays."""
    if not secret:
        raise ValueError("Bridge shared secret must not be empty")
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _decode_active_user(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        parsed_uid = int(user_id)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == parsed_uid).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user account")
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    return _decode_active_user(token, db)


def get_current_customer(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access privileges required",
        )
    return current_user


def get_current_merchant(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant access privileges required",
        )
    return current_user


def get_current_service_actor(
    token: Optional[str] = Depends(optional_oauth2_scheme),
) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate service credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        return verify_service_jwt_token(token)
    except jwt.PyJWTError:
        raise credentials_exception


def get_merchant_or_service_actor(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    try:
        claims = verify_service_jwt_token(token)
        return {"actor_type": "service", "claims": claims, "user": None}
    except jwt.PyJWTError:
        pass

    user = _decode_active_user(token, db)
    if user.role != UserRole.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Merchant or authorized service privileges required",
        )
    return {"actor_type": "merchant", "claims": {}, "user": user}
