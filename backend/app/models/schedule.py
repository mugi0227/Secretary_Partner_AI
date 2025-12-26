"""
Schedule models for task planning outputs.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.task import Task


class TaskAllocation(BaseModel):
    """Allocated minutes for a task on a specific day."""

    task_id: UUID
    minutes: int = Field(..., ge=0)


class ScheduleDay(BaseModel):
    """Daily schedule allocation summary."""

    date: date
    capacity_minutes: int
    allocated_minutes: int
    overflow_minutes: int = 0
    task_allocations: list[TaskAllocation] = Field(default_factory=list)


class TaskScheduleInfo(BaseModel):
    """Schedule summary per task."""

    task_id: UUID
    title: str
    project_id: Optional[UUID] = None
    parent_id: Optional[UUID] = None
    parent_title: Optional[str] = None
    due_date: Optional[datetime] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    total_minutes: int
    priority_score: float


class UnscheduledTask(BaseModel):
    """Unscheduled task with reason."""

    task_id: UUID
    reason: str


class ExcludedTask(BaseModel):
    """Excluded task with reason."""

    task_id: UUID
    title: str
    reason: str
    parent_id: Optional[UUID] = None
    parent_title: Optional[str] = None


class ScheduleResponse(BaseModel):
    """Full schedule response."""

    start_date: date
    days: list[ScheduleDay]
    tasks: list[TaskScheduleInfo]
    unscheduled_task_ids: list[UnscheduledTask] = Field(default_factory=list)
    excluded_tasks: list[ExcludedTask] = Field(default_factory=list)


class TodayTaskAllocation(BaseModel):
    """Allocation details for a task on the target day."""

    task_id: UUID
    allocated_minutes: int = Field(..., ge=0)
    total_minutes: int = Field(..., ge=0)
    ratio: float = Field(..., ge=0, le=1)


class TodayTasksResponse(BaseModel):
    """Today's tasks response derived from the schedule."""

    today: date
    today_tasks: list[Task]
    today_allocations: list[TodayTaskAllocation] = Field(default_factory=list)
    top3_ids: list[UUID]
    total_estimated_minutes: int
    capacity_minutes: int
    overflow_minutes: int
    overflow: bool
