"""
Project model definitions.

Projects group related tasks and maintain context.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProjectStatus


class ProjectBase(BaseModel):
    """Base project fields."""

    name: str = Field(..., min_length=1, max_length=200, description="プロジェクト名")
    description: Optional[str] = Field(None, max_length=2000, description="プロジェクトの説明")
    context_summary: Optional[str] = Field(
        None,
        max_length=5000,
        description="RAGや会話から抽出された文脈サマリー",
    )


class ProjectCreate(ProjectBase):
    """Schema for creating a new project."""

    pass


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[ProjectStatus] = None
    context_summary: Optional[str] = Field(None, max_length=5000)


class Project(ProjectBase):
    """Complete project model."""

    id: UUID
    user_id: str = Field(..., description="所有者ユーザーID")
    status: ProjectStatus = Field(ProjectStatus.ACTIVE)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectWithTaskCount(Project):
    """Project with task statistics."""

    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
