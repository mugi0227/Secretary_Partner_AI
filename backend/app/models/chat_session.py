"""
Chat session and message models.

These models persist chat history for session restore.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatSessionBase(BaseModel):
    """Base chat session fields."""

    session_id: str = Field(..., max_length=100, description="Chat session ID")
    title: str = Field("New Chat", max_length=200, description="Session title")


class ChatSession(ChatSessionBase):
    """Chat session model."""

    user_id: str = Field(..., description="Owner user ID")
    created_at: datetime
    updated_at: datetime


class ChatMessageBase(BaseModel):
    """Base chat message fields."""

    session_id: str = Field(..., max_length=100, description="Chat session ID")
    role: str = Field(..., max_length=20, description="Message role")
    content: str = Field("", max_length=20000, description="Message content")


class ChatMessageCreate(ChatMessageBase):
    """Schema for creating a chat message."""

    pass


class ChatMessage(ChatMessageBase):
    """Chat message model."""

    id: UUID
    user_id: str = Field(..., description="Owner user ID")
    created_at: datetime
