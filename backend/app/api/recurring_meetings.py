"""
Recurring meeting API endpoints.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    CheckinRepo,
    CurrentUser,
    ProjectMemberRepo,
    ProjectRepo,
    RecurringMeetingRepo,
    TaskRepo,
    UserRepo,
)
from app.api.permissions import require_project_action
from app.core.exceptions import NotFoundError
from app.models.recurring_meeting import (
    RecurringMeeting,
    RecurringMeetingCreate,
    RecurringMeetingUpdate,
)
from app.services.project_permissions import ProjectAction
from app.services.recurring_meeting_service import RecurringMeetingService
from app.utils.datetime_utils import normalize_timezone, now_utc

router = APIRouter()


def _align_to_weekday(current, target_weekday: int):
    delta = (target_weekday - current.weekday()) % 7
    return current + timedelta(days=delta)


def _compute_anchor_date(start_time, weekday: int, now: datetime):
    candidate_date = _align_to_weekday(now.date(), weekday)
    candidate_dt = datetime.combine(candidate_date, start_time, tzinfo=now.tzinfo)
    if candidate_dt <= now:
        candidate_date += timedelta(days=7)
    return candidate_date


async def _resolve_meeting_access(
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    meeting_id: UUID,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
) -> tuple[RecurringMeeting, str]:
    meeting = await repo.get(user.id, meeting_id)
    if meeting:
        if meeting.project_id:
            access = await require_project_action(
                user,
                meeting.project_id,
                project_repo,
                member_repo,
                ProjectAction.MEETING_AGENDA_MANAGE,
            )
            return meeting, access.owner_id
        return meeting, user.id

    projects = await project_repo.list(user.id, limit=1000)
    for project in projects:
        meeting = await repo.get(user.id, meeting_id, project_id=project.id)
        if meeting:
            access = await require_project_action(
                user,
                project.id,
                project_repo,
                member_repo,
                ProjectAction.MEETING_AGENDA_MANAGE,
            )
            return meeting, access.owner_id

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"RecurringMeeting {meeting_id} not found",
    )


@router.post("", response_model=RecurringMeeting, status_code=status.HTTP_201_CREATED)
async def create_recurring_meeting(
    payload: RecurringMeetingCreate,
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    task_repo: TaskRepo,
    checkin_repo: CheckinRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
):
    """Create a new recurring meeting series."""
    try:
        user_account = await user_repo.get(UUID(user.id))
    except (TypeError, ValueError):
        user_account = None
    user_timezone = normalize_timezone(user_account.timezone if user_account else None)
    now_local = now_utc().astimezone(ZoneInfo(user_timezone))
    anchor_date = payload.anchor_date or _compute_anchor_date(
        payload.start_time,
        payload.weekday,
        now_local,
    )
    if anchor_date.weekday() != payload.weekday:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="anchor_date weekday must match weekday",
        )
    owner_id = user.id
    if payload.project_id:
        access = await require_project_action(
            user,
            payload.project_id,
            project_repo,
            member_repo,
            ProjectAction.MEETING_AGENDA_MANAGE,
        )
        owner_id = access.owner_id
    created = await repo.create(owner_id, payload.model_copy(update={"anchor_date": anchor_date}))
    service = RecurringMeetingService(
        repo, task_repo, checkin_repo,
        project_repo=project_repo, member_repo=member_repo,
        user_repo=user_repo,
    )
    await service.ensure_upcoming_meetings(owner_id)
    return created


@router.get("", response_model=list[RecurringMeeting])
async def list_recurring_meetings(
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    include_inactive: bool = Query(False, description="Include inactive recurring meetings"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[RecurringMeeting]:
    """List recurring meetings."""
    owner_id = user.id
    if project_id:
        access = await require_project_action(
            user,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.MEETING_AGENDA_MANAGE,
        )
        owner_id = access.owner_id
    return await repo.list(
        owner_id,
        project_id=project_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{meeting_id}", response_model=RecurringMeeting)
async def get_recurring_meeting(
    meeting_id: UUID,
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
) -> RecurringMeeting:
    """Get a recurring meeting by ID."""
    meeting, _ = await _resolve_meeting_access(user, repo, meeting_id, project_repo, member_repo)
    return meeting


@router.patch("/{meeting_id}", response_model=RecurringMeeting)
async def update_recurring_meeting(
    meeting_id: UUID,
    update: RecurringMeetingUpdate,
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    task_repo: TaskRepo,
    checkin_repo: CheckinRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
) -> RecurringMeeting:
    """Update a recurring meeting."""
    meeting, owner_id = await _resolve_meeting_access(user, repo, meeting_id, project_repo, member_repo)
    try:
        return await repo.update(owner_id, meeting_id, update, meeting.project_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_meeting(
    meeting_id: UUID,
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Delete a recurring meeting."""
    meeting, owner_id = await _resolve_meeting_access(user, repo, meeting_id, project_repo, member_repo)
    deleted = await repo.delete(owner_id, meeting_id, meeting.project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecurringMeeting {meeting_id} not found",
        )


@router.post("/{meeting_id}/generate-tasks")
async def generate_meeting_tasks(
    meeting_id: UUID,
    user: CurrentUser,
    repo: RecurringMeetingRepo,
    task_repo: TaskRepo,
    checkin_repo: CheckinRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    user_repo: UserRepo,
    lookahead_days: int = Query(30, ge=1, le=180, description="Generate tasks for the next N days"),
):
    """
    Generate meeting tasks for a recurring meeting.

    Args:
        meeting_id: Recurring meeting ID
        lookahead_days: Number of days to look ahead (default: 30)

    Returns:
        Dictionary with created task count and task details
    """
    _, owner_id = await _resolve_meeting_access(user, repo, meeting_id, project_repo, member_repo)

    service = RecurringMeetingService(
        recurring_repo=repo,
        task_repo=task_repo,
        checkin_repo=checkin_repo,
        lookahead_days=lookahead_days,
        project_repo=project_repo,
        member_repo=member_repo,
        user_repo=user_repo,
    )

    result = await service.ensure_upcoming_meetings(owner_id)
    return result
