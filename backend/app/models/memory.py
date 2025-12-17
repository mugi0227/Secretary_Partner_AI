"""
Memory model definitions.

Memories store AI's knowledge about users, projects, and work procedures.
Three scopes: UserMemory, ProjectMemory, WorkMemory
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MemoryScope, MemoryType


class MemoryBase(BaseModel):
    """Base memory fields."""

    content: str = Field(..., min_length=1, max_length=5000, description="記憶内容")
    scope: MemoryScope = Field(..., description="記憶スコープ (USER/PROJECT/WORK)")
    memory_type: MemoryType = Field(..., description="記憶タイプ")
    project_id: Optional[UUID] = Field(None, description="関連プロジェクトID (PROJECT scopeの場合)")
    tags: list[str] = Field(default_factory=list, description="検索用タグ")


class MemoryCreate(MemoryBase):
    """Schema for creating a new memory."""

    source: str = Field("agent", description="記憶の出所 (agent/user/system)")


class Memory(MemoryBase):
    """Complete memory model."""

    id: UUID
    user_id: str = Field(..., description="所有者ユーザーID")
    source: str = Field("agent")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Specialized memory models for convenience


class UserMemory(BaseModel):
    """User-specific memory (facts, preferences, patterns)."""

    id: UUID
    user_id: str
    memory_type: MemoryType  # FACT, PREFERENCE, PATTERN
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class ProjectMemory(BaseModel):
    """Project-specific memory (context, documents)."""

    id: UUID
    user_id: str
    project_id: UUID
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class WorkMemory(BaseModel):
    """Work procedure memory (rules, procedures)."""

    id: UUID
    user_id: str
    memory_type: MemoryType  # RULE
    content: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class MemorySearchResult(BaseModel):
    """Search result for memory queries."""

    memory: Memory
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="関連度スコア")
