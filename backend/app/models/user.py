"""
User account models for authentication mapping.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Create a user account."""

    provider_issuer: str = Field(..., min_length=1, max_length=500)
    provider_sub: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    username: Optional[str] = Field(None, max_length=255)
    password_hash: Optional[str] = Field(None, max_length=255)
    timezone: str = Field(default="UTC", max_length=50, description="IANA timezone (e.g., Asia/Tokyo, America/New_York)")
    enable_weekly_meeting_reminder: bool = Field(default=False, description="Enable weekly meeting registration reminder tasks")


class UserAccount(BaseModel):
    """User account stored in the database."""

    id: UUID
    provider_issuer: str
    provider_sub: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    password_hash: Optional[str] = None
    timezone: str = "UTC"
    enable_weekly_meeting_reminder: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Update user account fields."""

    provider_sub: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=255)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    username: Optional[str] = Field(None, max_length=255)
    password_hash: Optional[str] = Field(None, max_length=255)
    timezone: Optional[str] = Field(None, max_length=50, description="IANA timezone")
    enable_weekly_meeting_reminder: Optional[bool] = Field(None, description="Enable weekly meeting registration reminder tasks")
