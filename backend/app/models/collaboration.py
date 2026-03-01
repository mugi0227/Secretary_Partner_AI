"""
Collaboration models for multi-member projects.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    BlockerStatus,
    CheckinItemCategory,
    CheckinItemUrgency,
    CheckinMood,
    CheckinType,
    InvitationStatus,
    ProjectRole,
    TaskStatus,
)


class ProjectMemberBase(BaseModel):
    """Base fields for project members."""

    project_id: UUID
    member_user_id: str = Field(..., min_length=1, max_length=255)
    role: ProjectRole = ProjectRole.MEMBER
    capacity_hours: Optional[float] = Field(None, ge=0, le=168)
    timezone: Optional[str] = Field(None, max_length=100)


class ProjectMemberCreate(BaseModel):
    """Create a new project member."""

    member_user_id: str = Field(..., min_length=1, max_length=255)
    role: ProjectRole = ProjectRole.MEMBER
    capacity_hours: Optional[float] = Field(None, ge=0, le=168)
    timezone: Optional[str] = Field(None, max_length=100)


class ProjectMemberUpdate(BaseModel):
    """Update project member fields."""

    role: Optional[ProjectRole] = None
    capacity_hours: Optional[float] = Field(None, ge=0, le=168)
    timezone: Optional[str] = Field(None, max_length=100)


class ProjectMember(ProjectMemberBase):
    """Project member with metadata."""

    id: UUID
    user_id: str
    created_at: datetime
    updated_at: datetime
    member_display_name: Optional[str] = None
    member_first_name: Optional[str] = None
    member_last_name: Optional[str] = None

    class Config:
        from_attributes = True


class TaskAssignmentBase(BaseModel):
    """Base fields for task assignments."""

    task_id: UUID
    assignee_id: str = Field(..., min_length=1, max_length=255)
    status: Optional[TaskStatus] = None
    progress: Optional[int] = Field(None, ge=0, le=100)


class TaskAssignmentCreate(BaseModel):
    """Assign a task to a member."""

    assignee_id: str = Field(..., min_length=1, max_length=255)
    status: Optional[TaskStatus] = None
    progress: Optional[int] = Field(None, ge=0, le=100)


class TaskAssignmentsCreate(BaseModel):
    """Assign a task to multiple members."""

    assignee_ids: list[str] = Field(..., min_length=1, description="List of assignee IDs")


class TaskAssignmentUpdate(BaseModel):
    """Update an assignment."""

    assignee_id: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[TaskStatus] = None
    progress: Optional[int] = Field(None, ge=0, le=100)


class TaskAssignment(TaskAssignmentBase):
    """Task assignment with metadata."""

    id: UUID
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CheckinBase(BaseModel):
    """Base fields for member check-ins."""

    project_id: UUID
    member_user_id: str = Field(..., min_length=1, max_length=255)
    checkin_date: date
    checkin_type: CheckinType = Field(CheckinType.WEEKLY, description="weekly/issue/general")
    summary_text: Optional[str] = Field(None, max_length=2000)
    raw_text: str = Field(..., max_length=4000)


class CheckinCreate(BaseModel):
    """Create a new check-in."""

    member_user_id: str = Field(..., min_length=1, max_length=255)
    checkin_date: date
    checkin_type: CheckinType = Field(CheckinType.WEEKLY, description="weekly/issue/general")
    summary_text: Optional[str] = Field(None, max_length=2000)
    raw_text: str = Field(..., max_length=4000)


class Checkin(CheckinBase):
    """Check-in with metadata."""

    id: UUID
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class CheckinSummary(BaseModel):
    """Summary for a set of check-ins."""

    project_id: UUID
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    checkin_count: int
    summary_text: Optional[str] = None
    summary_error: Optional[str] = None
    summary_error_detail: Optional[str] = None
    summary_debug_prompt: Optional[str] = None
    summary_debug_output: Optional[str] = None


class CheckinSummaryRequest(BaseModel):
    """Request payload for generating a check-in summary."""

    member_user_id: Optional[str] = Field(None, min_length=1, max_length=255)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    checkin_type: Optional[CheckinType] = None
    weekly_context: Optional[str] = Field(None, max_length=5000)


class CheckinSummarySave(BaseModel):
    """Save a summarized set of check-ins."""

    summary_text: str = Field(..., min_length=1, max_length=5000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    checkin_count: int = Field(..., ge=0)


# =============================================================================
# V2 Check-in Models (Structured)
# =============================================================================


class CheckinItem(BaseModel):
    """Individual structured check-in item."""

    category: CheckinItemCategory
    content: str = Field(..., min_length=1, max_length=2000)
    related_task_id: Optional[str] = None
    urgency: CheckinItemUrgency = CheckinItemUrgency.MEDIUM


class CheckinItemResponse(CheckinItem):
    """Check-in item with metadata (for API responses)."""

    id: UUID
    related_task_title: Optional[str] = None

    class Config:
        from_attributes = True


class CheckinCreateV2(BaseModel):
    """Create a structured check-in (V2)."""

    member_user_id: str = Field(..., min_length=1, max_length=255)
    checkin_date: date

    # Structured fields
    items: list[CheckinItem] = Field(default_factory=list)
    mood: Optional[CheckinMood] = None
    must_discuss_in_next_meeting: Optional[str] = Field(None, max_length=2000)
    free_comment: Optional[str] = Field(None, max_length=4000)

    # Legacy fields (for backward compatibility)
    checkin_type: Optional[CheckinType] = None
    raw_text: Optional[str] = Field(None, max_length=4000)


class CheckinV2(BaseModel):
    """Structured check-in with metadata (V2)."""

    id: UUID
    user_id: str
    project_id: UUID
    member_user_id: str
    checkin_date: date

    # Structured fields
    items: list[CheckinItemResponse] = Field(default_factory=list)
    mood: Optional[CheckinMood] = None
    must_discuss_in_next_meeting: Optional[str] = None
    free_comment: Optional[str] = None

    # Legacy fields (preserved for compatibility)
    checkin_type: Optional[CheckinType] = None
    summary_text: Optional[str] = None
    raw_text: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True


class CheckinUpdateV2(BaseModel):
    """Update a structured check-in (V2)."""

    # Structured fields (all optional for partial updates)
    items: Optional[list[CheckinItem]] = None
    mood: Optional[CheckinMood] = None
    must_discuss_in_next_meeting: Optional[str] = Field(None, max_length=2000)
    free_comment: Optional[str] = Field(None, max_length=4000)


class CheckinAgendaItems(BaseModel):
    """Structured check-in data for meeting agenda generation."""

    project_id: UUID
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    blockers: list[dict] = Field(default_factory=list)
    discussions: list[dict] = Field(default_factory=list)
    requests: list[dict] = Field(default_factory=list)
    updates: list[dict] = Field(default_factory=list)

    member_moods: dict[str, CheckinMood] = Field(default_factory=dict)
    must_discuss_items: list[dict] = Field(default_factory=list)


class BlockerBase(BaseModel):
    """Base fields for task blockers."""

    task_id: UUID
    created_by: str = Field(..., min_length=1, max_length=255)
    status: BlockerStatus = BlockerStatus.OPEN
    reason: str = Field(..., max_length=2000)
    resolved_by: Optional[str] = Field(None, max_length=255)


class BlockerCreate(BaseModel):
    """Create a new blocker."""

    created_by: str = Field(..., min_length=1, max_length=255)
    reason: str = Field(..., max_length=2000)


class BlockerUpdate(BaseModel):
    """Update blocker status."""

    status: Optional[BlockerStatus] = None
    resolved_by: Optional[str] = Field(None, max_length=255)


class Blocker(BlockerBase):
    """Blocker with metadata."""

    id: UUID
    user_id: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectInvitationBase(BaseModel):
    """Base fields for project invitations."""

    project_id: UUID
    email: str = Field(..., min_length=3, max_length=255)
    role: ProjectRole = ProjectRole.MEMBER
    status: InvitationStatus = InvitationStatus.PENDING
    invited_by: str = Field(..., min_length=1, max_length=255)
    accepted_by: Optional[str] = Field(None, max_length=255)
    token: Optional[str] = Field(None, max_length=255)
    expires_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None


class ProjectInvitationCreate(BaseModel):
    """Create a new project invitation."""

    email: str = Field(..., min_length=3, max_length=255)
    role: ProjectRole = ProjectRole.MEMBER


class ProjectInvitationUpdate(BaseModel):
    """Update invitation status."""

    status: InvitationStatus


class ProjectInvitation(ProjectInvitationBase):
    """Invitation with metadata."""

    id: UUID
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
