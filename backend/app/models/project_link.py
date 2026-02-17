"""
Project link request model definitions.

Manages approval workflow for parent-child project relationships.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectLinkRequestStatus(str, Enum):
    """Status of a project link request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProjectLinkRequest(BaseModel):
    """Project link request model."""

    id: UUID
    child_project_id: UUID
    parent_project_id: UUID
    requested_by: str = Field(..., description="リクエストしたユーザーID")
    status: ProjectLinkRequestStatus = Field(ProjectLinkRequestStatus.PENDING)
    member_ids_to_add: list[str] = Field(
        default_factory=list,
        description="親プロジェクトに追加するメンバーID一覧",
    )
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectLinkRequestCreate(BaseModel):
    """Schema for creating a project link request."""

    child_project_id: UUID
    parent_project_id: UUID
    member_ids_to_add: list[str] = Field(default_factory=list)
