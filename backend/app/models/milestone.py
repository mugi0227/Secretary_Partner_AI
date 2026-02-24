"""
Milestone model definitions.

Milestones belong to phases and help track key outcomes.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MilestoneStatus


class MilestoneBase(BaseModel):
    """Base milestone fields."""

    project_id: UUID = Field(..., description="Project ID")
    phase_id: UUID = Field(..., description="Phase ID")
    title: str = Field(..., min_length=1, max_length=200, description="Milestone title")
    description: Optional[str] = Field(None, max_length=2000, description="Milestone description")
    order_in_phase: int = Field(default=1, ge=1, description="Order within the phase")
    due_date: Optional[datetime] = Field(None, description="Target due date")


class MilestoneCreate(MilestoneBase):
    """Schema for creating a milestone."""

    pass


class MilestoneUpdate(BaseModel):
    """Schema for updating a milestone."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[MilestoneStatus] = None
    order_in_phase: Optional[int] = Field(None, ge=1)
    due_date: Optional[datetime] = None


class Milestone(MilestoneBase):
    """Complete milestone model."""

    id: UUID
    user_id: str = Field(..., description="Owner user ID")
    status: MilestoneStatus = Field(MilestoneStatus.ACTIVE)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MilestoneWithProgress(Milestone):
    """Milestone with computed progress metrics."""

    progress: int = Field(default=0, ge=0, le=100)
    total_estimated_minutes: int = Field(default=0, ge=0)
    remaining_minutes: int = Field(default=0, ge=0)
    task_count: int = Field(default=0, ge=0)
    completed_task_count: int = Field(default=0, ge=0)
