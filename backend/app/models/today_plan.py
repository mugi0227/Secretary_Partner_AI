"""Models for user-selected daily task planning."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.task import Task

TodayPlanBucket = Literal["selected", "recommended", "scheduled", "blocked"]


class TodayPlanReason(BaseModel):
    """Stable reason code and human-readable label for a daily task recommendation."""

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)


class TodayPlanScoreComponent(BaseModel):
    """Explainable score contribution for a daily task recommendation."""

    code: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    points: float = 0.0
    detail: str | None = None


class TodayPlanTask(BaseModel):
    """Task decorated with daily planning metadata."""

    task: Task
    bucket: TodayPlanBucket
    selected: bool
    score: float = 0.0
    score_summary: str = ""
    score_breakdown: list[TodayPlanScoreComponent] = Field(default_factory=list)
    reasons: list[TodayPlanReason] = Field(default_factory=list)
    allocated_minutes: int = Field(0, ge=0)
    remaining_minutes: int = Field(0, ge=0)


class TodayPlanCapacity(BaseModel):
    """Capacity summary for the daily plan."""

    feasible: bool
    total_minutes: int
    capacity_minutes: int
    meeting_minutes: int = 0
    overflow_minutes: int = 0
    capacity_usage_percent: int = 0


class TodayPlanResponse(BaseModel):
    """Daily plan with recommendations separate from user selections."""

    today: date
    selected: list[TodayPlanTask] = Field(default_factory=list)
    recommendations: list[TodayPlanTask] = Field(default_factory=list)
    scheduled: list[TodayPlanTask] = Field(default_factory=list)
    blocked: list[TodayPlanTask] = Field(default_factory=list)
    capacity: TodayPlanCapacity


class TodaySelectionUpdate(BaseModel):
    """Replace or extend the user's selected tasks for today."""

    task_ids: list[UUID] = Field(default_factory=list)
    replace: bool = Field(True, description="Replace existing selected tasks for today")
