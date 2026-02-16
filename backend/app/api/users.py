"""
User profile and credential endpoints.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, UserRepo
from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.user import UserUpdate
from app.utils.datetime_utils import is_valid_timezone, normalize_timezone

router = APIRouter()


def _build_display_name(first_name: Optional[str], last_name: Optional[str], fallback: str) -> str:
    parts = [part for part in (last_name, first_name) if part]
    return " ".join(parts) if parts else fallback


class UserProfile(BaseModel):
    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None
    is_developer: bool = False


class UserSearchResult(BaseModel):
    """User search result with limited public info."""
    id: str
    display_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None


class UpdateCredentialsRequest(BaseModel):
    current_password: str = Field(..., min_length=8, max_length=128)
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = Field(None, min_length=3, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    new_password: Optional[str] = Field(None, min_length=8, max_length=128)
    timezone: Optional[str] = Field(None, max_length=50, description="IANA timezone")


@router.get("/search", response_model=list[UserSearchResult])
async def search_users(
    user: CurrentUser,
    user_repo: UserRepo,
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
) -> list[UserSearchResult]:
    """Search users by username, email, or display name."""
    results = await user_repo.search(q, limit)
    return [
        UserSearchResult(
            id=str(u.id),
            display_name=u.display_name,
            username=u.username,
            email=u.email,
        )
        for u in results
    ]


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user: CurrentUser,
    user_repo: UserRepo,
) -> UserProfile:
    settings = get_settings()

    def _check_dev(email: str | None) -> bool:
        return bool(email and email.lower() in settings.developer_emails)

    is_dev = _check_dev(user.email)

    profile = UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        username=None,
        first_name=None,
        last_name=None,
        is_developer=is_dev,
    )
    try:
        user_uuid = UUID(user.id)
    except Exception:
        return profile

    record = await user_repo.get(user_uuid)
    if not record:
        return profile

    resolved_email = record.email or user.email
    is_dev = _check_dev(resolved_email)

    return UserProfile(
        id=str(record.id),
        email=resolved_email,
        display_name=record.display_name or user.display_name,
        username=record.username,
        first_name=record.first_name,
        last_name=record.last_name,
        timezone=normalize_timezone(record.timezone),
        is_developer=is_dev,
    )


@router.patch("/me/credentials", response_model=UserProfile)
async def update_credentials(
    data: UpdateCredentialsRequest,
    user: CurrentUser,
    user_repo: UserRepo,
) -> UserProfile:
    settings = get_settings()
    if settings.AUTH_PROVIDER != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential updates are only available for local auth",
        )

    try:
        user_uuid = UUID(user.id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id",
        )

    record = await user_repo.get(user_uuid)
    if not record or not record.password_hash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not verify_password(data.current_password, record.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid current password",
        )

    update_fields = UserUpdate()

    if data.username:
        username = data.username.strip()
        if username and username != record.username:
            existing = await user_repo.get_by_username(username)
            if existing and existing.id != record.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username already exists",
                )
            update_fields.username = username
            update_fields.provider_sub = username
            update_fields.display_name = username

    if data.email:
        email = data.email.strip().lower()
        if email and email != (record.email or ""):
            existing = await user_repo.get_by_email(email)
            if existing and existing.id != record.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already exists",
                )
            update_fields.email = email

    if data.last_name:
        last_name = data.last_name.strip()
        if last_name and last_name != (record.last_name or ""):
            update_fields.last_name = last_name

    if data.first_name:
        first_name = data.first_name.strip()
        if first_name and first_name != (record.first_name or ""):
            update_fields.first_name = first_name

    if update_fields.first_name is not None or update_fields.last_name is not None:
        next_first = (
            update_fields.first_name
            if update_fields.first_name is not None
            else record.first_name
        )
        next_last = (
            update_fields.last_name
            if update_fields.last_name is not None
            else record.last_name
        )
        fallback = record.display_name or record.username or ""
        update_fields.display_name = _build_display_name(next_first, next_last, fallback)

    if data.new_password:
        update_fields.password_hash = hash_password(data.new_password)

    if data.timezone:
        timezone_val = data.timezone.strip()
        if timezone_val:
            if not is_valid_timezone(timezone_val):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid timezone: {timezone_val}",
                )
            normalized_timezone = normalize_timezone(timezone_val)
            if normalized_timezone != record.timezone:
                update_fields.timezone = normalized_timezone

    if not any(
        value is not None
        for value in (
            update_fields.username,
            update_fields.email,
            update_fields.first_name,
            update_fields.last_name,
            update_fields.password_hash,
            update_fields.timezone,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No changes provided",
        )

    updated = await user_repo.update(user_uuid, update_fields)
    return UserProfile(
        id=str(updated.id),
        email=updated.email,
        display_name=updated.display_name,
        username=updated.username,
        first_name=updated.first_name,
        last_name=updated.last_name,
        timezone=normalize_timezone(updated.timezone),
    )
