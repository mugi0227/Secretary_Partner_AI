"""
Task model definitions.

Tasks are the core entity representing user's to-do items.
"""

from datetime import datetime, time, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus


class TouchpointStep(BaseModel):
    """Touchpoint step details for multi-day tasks."""

    title: str = Field(..., min_length=1, max_length=500)
    guide: Optional[str] = Field(None, max_length=2000)
    estimated_minutes: Optional[int] = Field(None, ge=1)


class TaskBase(BaseModel):
    """Base task fields shared across create/read."""

    title: str = Field(..., min_length=1, max_length=500, description="Task title")
    description: Optional[str] = Field(None, max_length=2000, description="Task description")
    purpose: Optional[str] = Field(None, max_length=1000, description="Task purpose")
    project_id: Optional[UUID] = Field(None, description="Project ID (None for Inbox)")
    phase_id: Optional[UUID] = Field(None, description="Phase ID in project")
    importance: Priority = Field(Priority.MEDIUM, description="Importance")
    urgency: Priority = Field(Priority.MEDIUM, description="Urgency")
    energy_level: EnergyLevel = Field(EnergyLevel.LOW, description="Required energy level")
    estimated_minutes: Optional[int] = Field(None, ge=1, description="Estimated minutes")
    due_date: Optional[datetime] = Field(None, description="Due date")
    start_not_before: Optional[datetime] = Field(
        None,
        description="Do not start before this datetime",
    )
    pinned_date: Optional[datetime] = Field(
        None,
        description="Pinned date in schedule",
    )
    parent_id: Optional[UUID] = Field(None, description="Parent task ID")
    order_in_parent: Optional[int] = Field(
        None,
        ge=1,
        description="Ordering among sibling subtasks",
    )
    dependency_ids: list[UUID] = Field(
        default_factory=list,
        description="Task IDs that must be completed first",
    )
    same_day_allowed: bool = Field(
        True,
        description="Allow sibling subtasks on the same day",
    )
    min_gap_days: int = Field(
        0,
        ge=0,
        description="Minimum gap days between sibling subtasks",
    )
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")

    start_time: Optional[datetime] = Field(None, description="Start time for fixed-time task")
    end_time: Optional[datetime] = Field(None, description="End time for fixed-time task")
    is_fixed_time: bool = Field(False, description="Whether task is fixed-time")
    is_all_day: bool = Field(False, description="Whether task spans all day")
    location: Optional[str] = Field(None, max_length=500, description="Meeting location")
    attendees: list[str] = Field(default_factory=list, description="Attendees")
    meeting_notes: Optional[str] = Field(None, max_length=5000, description="Meeting notes")
    recurring_meeting_id: Optional[UUID] = Field(None, description="Recurring meeting ID")
    recurring_task_id: Optional[UUID] = Field(None, description="Recurring task ID")
    milestone_id: Optional[UUID] = Field(None, description="Milestone ID")

    completion_note: Optional[str] = Field(
        None,
        max_length=2000,
        description="Completion note",
    )
    touchpoint_count: Optional[int] = Field(
        None,
        ge=1,
        description="Touchpoint count",
    )
    touchpoint_minutes: Optional[int] = Field(
        None,
        ge=1,
        description="Minutes per touchpoint",
    )
    touchpoint_gap_days: int = Field(
        0,
        ge=0,
        description="Minimum gap days between touchpoints",
    )
    touchpoint_steps: list[TouchpointStep] = Field(
        default_factory=list,
        description="Touchpoint step guides",
    )

    guide: Optional[str] = Field(
        None,
        max_length=2000,
        description="Detailed execution guide",
    )

    requires_all_completion: bool = Field(
        False,
        description="Requires all assignees to mark complete",
    )

    @model_validator(mode="after")
    def validate_fixed_time(self):
        """Validate fixed-time task constraints."""
        if self.is_all_day:
            self.is_fixed_time = True
            if not self.start_time or not self.end_time:
                reference = self.start_time or self.due_date or self.start_not_before
                target_date = reference.date() if reference else datetime.now(timezone.utc).date()
                tzinfo = reference.tzinfo if reference else None
                self.start_time = datetime.combine(target_date, time.min).replace(tzinfo=tzinfo)
                self.end_time = datetime.combine(target_date, time(23, 59, 59)).replace(
                    tzinfo=tzinfo
                )

        if self.is_fixed_time:
            if not self.start_time or not self.end_time:
                raise ValueError("Fixed-time tasks require both start_time and end_time")
            if self.end_time <= self.start_time:
                raise ValueError("end_time must be later than start_time")
            if not self.estimated_minutes:
                duration_seconds = (self.end_time - self.start_time).total_seconds()
                self.estimated_minutes = int(duration_seconds / 60)

        if self.touchpoint_steps and not self.touchpoint_count:
            self.touchpoint_count = len(self.touchpoint_steps)
        if self.touchpoint_steps and self.touchpoint_count:
            if len(self.touchpoint_steps) != self.touchpoint_count:
                raise ValueError("touchpoint_steps length must match touchpoint_count")
        return self


class TaskCreate(TaskBase):
    """Schema for creating a new task."""

    source_capture_id: Optional[UUID] = Field(None, description="Source capture ID")
    created_by: CreatedBy = Field(CreatedBy.USER, description="Creator (USER/AGENT)")


class TaskUpdate(BaseModel):
    """Schema for updating an existing task."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    purpose: Optional[str] = Field(None, max_length=1000)
    project_id: Optional[UUID] = None
    phase_id: Optional[UUID] = None
    status: Optional[TaskStatus] = None
    importance: Optional[Priority] = None
    urgency: Optional[Priority] = None
    energy_level: Optional[EnergyLevel] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)
    due_date: Optional[datetime] = None
    start_not_before: Optional[datetime] = None
    pinned_date: Optional[datetime] = None
    parent_id: Optional[UUID] = None
    order_in_parent: Optional[int] = Field(None, ge=1, description="Ordering among subtasks")
    dependency_ids: Optional[list[UUID]] = None
    same_day_allowed: Optional[bool] = None
    min_gap_days: Optional[int] = Field(None, ge=0)
    source_capture_id: Optional[UUID] = None
    progress: Optional[int] = Field(None, ge=0, le=100, description="Progress percentage")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_fixed_time: Optional[bool] = None
    is_all_day: Optional[bool] = None
    location: Optional[str] = Field(None, max_length=500)
    attendees: Optional[list[str]] = None
    meeting_notes: Optional[str] = Field(None, max_length=5000)
    recurring_meeting_id: Optional[UUID] = None
    recurring_task_id: Optional[UUID] = None
    milestone_id: Optional[UUID] = None
    touchpoint_count: Optional[int] = Field(None, ge=1)
    touchpoint_minutes: Optional[int] = Field(None, ge=1)
    touchpoint_gap_days: Optional[int] = Field(None, ge=0)
    touchpoint_steps: Optional[list[TouchpointStep]] = None
    completion_note: Optional[str] = Field(None, max_length=2000)
    guide: Optional[str] = Field(None, max_length=2000)
    requires_all_completion: Optional[bool] = None


class Task(TaskBase):
    """Complete task model with all fields."""

    id: UUID
    user_id: str = Field(..., description="Owner user ID")
    status: TaskStatus = Field(TaskStatus.TODO, description="Task status")
    source_capture_id: Optional[UUID] = None
    created_by: CreatedBy = Field(CreatedBy.USER)
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = Field(None, description="Completed datetime")
    completed_by: Optional[str] = Field(None, description="User ID who completed the task")
    auto_completed_by_parent_id: Optional[UUID] = Field(
        None,
        description="Parent task ID that auto-completed this task",
    )

    class Config:
        from_attributes = True


class TaskWithSubtasks(Task):
    """Task with its subtasks for hierarchical display."""

    subtasks: list["Task"] = Field(default_factory=list)


class SimilarTask(BaseModel):
    """Similar task result for duplicate detection."""

    task: Task
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Similarity score")


class CompletionCheckResponse(BaseModel):
    """Response for check-completion endpoint."""

    task: Task
    checked_count: int
    total_count: int
