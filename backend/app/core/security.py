from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User

_DEV_FALLBACK_JWT_SECRET = "local-dev-only-jwt-secret-change-in-production"
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Authenticated user identity for request-scoped ownership checks."""

    id: UUID
    display_name: str
    email: str | None = None


def hash_password(password: str) -> str:
    """Hash a password with per-user random salt using stdlib scrypt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Verify a plaintext password against a stored scrypt hash in constant time."""
    if not stored_hash:
        return False
    parts = stored_hash.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n_val, r_val, p_val = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4].encode("ascii"))
        expected = base64.b64decode(parts[5].encode("ascii"))
    except (ValueError, TypeError):
        return False
    computed = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n_val,
        r=r_val,
        p=p_val,
        dklen=len(expected),
    )
    return hmac.compare_digest(computed, expected)


def resolve_jwt_secret(settings: Settings) -> str:
    """Return signing secret; require an explicit strong secret in production."""
    raw = settings.jwt_secret_key.get_secret_value().strip() if settings.jwt_secret_key else ""
    if settings.app_env == "production" and len(raw) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY (min 32 characters) must be configured when APP_ENV=production"
        )
    if raw:
        return raw
    return _DEV_FALLBACK_JWT_SECRET


def create_access_token(user_id: UUID, settings: Settings) -> str:
    """Create a signed HS256 JWT access token for a user."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, resolve_jwt_secret(settings), algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> UUID:
    """Decode and validate a Bearer JWT access token, returning the user UUID."""
    try:
        payload = jwt.decode(token, resolve_jwt_secret(settings), algorithms=["HS256"])
        if payload.get("type") != "access" or not payload.get("sub"):
            raise ValueError("Invalid token claims")
        return UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Resolve the active user for ownership enforcement.

    Supports `Authorization: Bearer <jwt>` in all modes. When `effective_auth_mode`
    is `jwt`, a valid Bearer token is strictly required and `X-User-Id` is rejected.
    """
    auth_mode = settings.effective_auth_mode

    if x_user_id is not None and (auth_mode != "dev_header" or settings.app_env == "production"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Header user override is disabled",
        )

    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = decode_access_token(token.strip(), settings)
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return CurrentUser(id=user.id, display_name=user.display_name, email=user.email)

    if auth_mode == "jwt":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = settings.local_default_user_id
    if x_user_id is not None:
        try:
            user_id = UUID(x_user_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-User-Id UUID",
            ) from exc

    user = db.get(User, user_id)
    if user is None:
        display_name = (
            settings.local_default_user_name
            if user_id == settings.local_default_user_id
            else f"User {str(user_id)[:8]}"
        )
        user = User(id=user_id, display_name=display_name)
        db.add(user)
        db.commit()
        db.refresh(user)

    return CurrentUser(id=user.id, display_name=user.display_name, email=user.email)
