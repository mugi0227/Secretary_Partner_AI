"""
Project model definitions.

Projects group related tasks and maintain context.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ProjectStatus
from app.models.project_kpi import ProjectKpiConfig


class ProjectBase(BaseModel):
    """Base project fields."""

    name: str = Field(..., min_length=1, max_length=200, description="プロジェクト名")
    description: Optional[str] = Field(None, max_length=2000, description="プロジェクトの説明")
    context_summary: Optional[str] = Field(
        None,
        max_length=5000,
        description="RAGや会話から抽出された文脈サマリー",
    )
    context: Optional[str] = Field(
        None,
        description="詳細コンテキスト（README的な内容、Markdown形式）",
    )
    priority: int = Field(
        default=5,
        ge=1,
        le=10,
        description="プロジェクト優先度（1=低、10=高）",
    )
    goals: list[str] = Field(
        default_factory=list,
        description="プロジェクトのゴールリスト",
    )
    key_points: list[str] = Field(
        default_factory=list,
        description="重要なポイント・注意事項リスト",
    )
    kpi_config: Optional[ProjectKpiConfig] = Field(
        None,
        description="KPI configuration",
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
    context: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    goals: Optional[list[str]] = None
    key_points: Optional[list[str]] = None
    kpi_config: Optional[ProjectKpiConfig] = None


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
