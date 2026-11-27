from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    CurrentUser,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(value: str) -> str:
    cleaned = value.strip().lower()
    if "@" not in cleaned or "." not in cleaned.split("@", 1)[-1]:
        raise ValueError("Enter a valid email address")
    return cleaned


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Display name cannot be blank")
        return cleaned


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class AuthUserOut(BaseModel):
    id: UUID
    email: str | None = None
    display_name: str
    auth_mode: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: AuthUserOut


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: RegisterRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    """Register a student account with a scrypt-hashed password and issue a JWT."""
    existing = db.execute(
        select(User).where(func.lower(User.email) == payload.email)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, settings)
    return AuthTokenResponse(
        access_token=token,
        expires_in_seconds=settings.jwt_expire_minutes * 60,
        user=AuthUserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            auth_mode=settings.effective_auth_mode,
        ),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login_user(
    payload: LoginRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> AuthTokenResponse:
    """Authenticate an email/password account and issue a Bearer JWT."""
    user = db.execute(
        select(User).where(func.lower(User.email) == payload.email)
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id, settings)
    return AuthTokenResponse(
        access_token=token,
        expires_in_seconds=settings.jwt_expire_minutes * 60,
        user=AuthUserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            auth_mode=settings.effective_auth_mode,
        ),
    )


@router.get("/me", response_model=AuthUserOut)
def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AuthUserOut:
    """Return the currently authenticated user profile and active auth mode."""
    return AuthUserOut(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        auth_mode=settings.effective_auth_mode,
    )
