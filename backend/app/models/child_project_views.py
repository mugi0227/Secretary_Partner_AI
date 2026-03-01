"""
Models for parent-child project cross-view features.

Lightweight summaries for viewing child project tasks from a parent project.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import TaskStatus


class ChildProjectTaskSummary(BaseModel):
    """Lightweight task summary for child project views."""

    id: UUID
    title: str
    status: TaskStatus
    assignee_names: list[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    parent_id: Optional[UUID] = None


class MemberProjectTask(BaseModel):
    """A single task within a child project, for the member view."""

    child_project_id: UUID
    child_project_name: str
    task_id: UUID
    task_title: str
    task_status: TaskStatus
    due_date: Optional[datetime] = None
    parent_id: Optional[UUID] = None


class MemberChildTasksSummary(BaseModel):
    """All tasks for a single member across child projects."""

    member_user_id: str
    member_display_name: str
    tasks_by_project: list[MemberProjectTask] = Field(default_factory=list)
