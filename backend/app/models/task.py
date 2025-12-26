"""
Task model definitions.

Tasks are the core entity representing user's to-do items.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus


class TaskBase(BaseModel):
    """Base task fields shared across create/read."""

    title: str = Field(..., min_length=1, max_length=500, description="タスクタイトル")
    description: Optional[str] = Field(None, max_length=2000, description="タスクの詳細説明")
    project_id: Optional[UUID] = Field(None, description="所属プロジェクトID (InboxならNull)")
    importance: Priority = Field(Priority.MEDIUM, description="重要度 (HIGH/MEDIUM/LOW)")
    urgency: Priority = Field(Priority.MEDIUM, description="緊急度 (HIGH/MEDIUM/LOW)")
    energy_level: EnergyLevel = Field(
        EnergyLevel.LOW, description="必要エネルギー (HIGH=重い, LOW=軽い)"
    )
    estimated_minutes: Optional[int] = Field(
        None, ge=1, le=480, description="見積もり時間（分）"
    )
    due_date: Optional[datetime] = Field(None, description="期限")
    parent_id: Optional[UUID] = Field(None, description="親タスクID（サブタスクの場合）")
    dependency_ids: list[UUID] = Field(
        default_factory=list, description="このタスクより先に終わらせるべきタスクのID"
    )


class TaskCreate(TaskBase):
    """Schema for creating a new task."""

    source_capture_id: Optional[UUID] = Field(
        None, description="元となったCaptureのID（重複排除用）"
    )
    created_by: CreatedBy = Field(CreatedBy.USER, description="作成者 (USER/AGENT)")


class TaskUpdate(BaseModel):
    """Schema for updating an existing task."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    project_id: Optional[UUID] = None
    status: Optional[TaskStatus] = None
    importance: Optional[Priority] = None
    urgency: Optional[Priority] = None
    energy_level: Optional[EnergyLevel] = None
    estimated_minutes: Optional[int] = Field(None, ge=1, le=480)
    due_date: Optional[datetime] = None
    parent_id: Optional[UUID] = None
    dependency_ids: Optional[list[UUID]] = None
    source_capture_id: Optional[UUID] = None


class Task(TaskBase):
    """Complete task model with all fields."""

    id: UUID
    user_id: str = Field(..., description="所有者ユーザーID")
    status: TaskStatus = Field(TaskStatus.TODO, description="ステータス")
    source_capture_id: Optional[UUID] = None
    created_by: CreatedBy = Field(CreatedBy.USER)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskWithSubtasks(Task):
    """Task with its subtasks for hierarchical display."""

    subtasks: list["Task"] = Field(default_factory=list)


class SimilarTask(BaseModel):
    """Similar task result for duplicate detection."""

    task: Task
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="類似度スコア")
