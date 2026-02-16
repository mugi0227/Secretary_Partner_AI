"""
Local authentication endpoints (register/login).
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, UserRepo
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import UserCreate
from app.utils.datetime_utils import normalize_timezone

router = APIRouter()

_NATIVE_LINK_CODE_TTL_SECONDS = 120
_NATIVE_LINK_CODE_BYTES = 18
_NATIVE_LINK_MAX_ACTIVE_CODES = 1000


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    timezone: str = Field(default="UTC", max_length=50, description="IANA timezone")


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class AuthUser(BaseModel):
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


@dataclass
class _NativeLinkRecord:
    token: str
    user: AuthUser
    expires_at: datetime


_native_link_lock = asyncio.Lock()
_native_link_store: dict[str, _NativeLinkRecord] = {}


class NativeLinkStartResponse(BaseModel):
    code: str
    expires_at: datetime


class NativeLinkExchangeRequest(BaseModel):
    code: str = Field(..., min_length=8, max_length=512)


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _build_display_name(first_name: Optional[str], last_name: Optional[str], fallback: str) -> str:
    parts = [part for part in (last_name, first_name) if part]
    return " ".join(parts) if parts else fallback


def _ensure_local_auth(settings: Settings) -> None:
    if settings.AUTH_PROVIDER != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local auth is not enabled",
        )
    if not settings.LOCAL_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LOCAL_JWT_SECRET is not configured",
        )


def _get_whitelist_emails(settings: Settings) -> set[str]:
    """Get the set of whitelisted emails (lowercase, stripped)."""
    raw = settings.REGISTRATION_WHITELIST_EMAILS.strip()
    if not raw:
        return set()
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _check_email_whitelist(email: str, settings: Settings) -> None:
    """Check if email is in the whitelist. Raises HTTPException if not allowed."""
    whitelist = _get_whitelist_emails(settings)
    if not whitelist:
        return  # No whitelist configured, allow all
    if email.lower() not in whitelist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This email address is not allowed to register",
        )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    return parts[1].strip()


def _hash_native_link_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _cleanup_expired_native_links(now: datetime) -> None:
    expired_keys = [
        code_hash for code_hash, record in _native_link_store.items() if record.expires_at <= now
    ]
    for code_hash in expired_keys:
        _native_link_store.pop(code_hash, None)


def _evict_oldest_native_link() -> None:
    if not _native_link_store:
        return
    oldest_code_hash = min(
        _native_link_store.items(),
        key=lambda item: item[1].expires_at,
    )[0]
    _native_link_store.pop(oldest_code_hash, None)


def _clear_native_link_store() -> None:
    _native_link_store.clear()


@router.post("/native-link/start", response_model=NativeLinkStartResponse)
async def start_native_link(
    user: CurrentUser,
    authorization: Annotated[str | None, Header()] = None,
) -> NativeLinkStartResponse:
    token = _extract_bearer_token(authorization)
    now = _utcnow()
    expires_at = now + timedelta(seconds=_NATIVE_LINK_CODE_TTL_SECONDS)
    code = secrets.token_urlsafe(_NATIVE_LINK_CODE_BYTES)
    code_hash = _hash_native_link_code(code)

    async with _native_link_lock:
        _cleanup_expired_native_links(now)
        if len(_native_link_store) >= _NATIVE_LINK_MAX_ACTIVE_CODES:
            _evict_oldest_native_link()
        _native_link_store[code_hash] = _NativeLinkRecord(
            token=token,
            user=AuthUser(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
            ),
            expires_at=expires_at,
        )

    return NativeLinkStartResponse(code=code, expires_at=expires_at)


@router.post("/native-link/exchange", response_model=AuthResponse)
async def exchange_native_link(data: NativeLinkExchangeRequest) -> AuthResponse:
    code = data.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code is required",
        )

    now = _utcnow()
    code_hash = _hash_native_link_code(code)

    async with _native_link_lock:
        _cleanup_expired_native_links(now)
        record = _native_link_store.pop(code_hash, None)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired code",
        )

    return AuthResponse(
        access_token=record.token,
        token_type="bearer",
        user=record.user,
    )


@router.post("/register", response_model=AuthResponse)
async def register(
    data: RegisterRequest,
    user_repo: UserRepo,
) -> AuthResponse:
    settings = get_settings()
    _ensure_local_auth(settings)

    username = data.username.strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required",
        )
    email = _normalize_email(data.email)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required",
        )

    # Check whitelist before any other validation
    _check_email_whitelist(email, settings)

    existing_username = await user_repo.get_by_username(username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    existing_email = await user_repo.get_by_email(email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    password_hash = hash_password(data.password)
    first_name = data.first_name.strip() if data.first_name else None
    last_name = data.last_name.strip() if data.last_name else None
    display_name = _build_display_name(first_name, last_name, username)
    user = await user_repo.create(
        UserCreate(
            provider_issuer="local",
            provider_sub=username,
            email=email,
            display_name=display_name,
            first_name=first_name,
            last_name=last_name,
            username=username,
            password_hash=password_hash,
            timezone=normalize_timezone(data.timezone),
        )
    )
    token = create_access_token(str(user.id), settings)
    return AuthResponse(
        access_token=token,
        user=AuthUser(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            username=user.username,
        ),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    user_repo: UserRepo,
) -> AuthResponse:
    settings = get_settings()
    _ensure_local_auth(settings)

    identifier = data.identifier.strip()
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Identifier is required",
        )
    user = None
    if "@" in identifier:
        user = await user_repo.get_by_email(_normalize_email(identifier))
    if not user:
        user = await user_repo.get_by_username(identifier)

    if not user or not user.password_hash or user.provider_issuer != "local":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(str(user.id), settings)
    return AuthResponse(
        access_token=token,
        user=AuthUser(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            username=user.username,
        ),
    )
