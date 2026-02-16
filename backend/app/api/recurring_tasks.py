"""
Recurring task API endpoints.
"""

from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, RecurringTaskRepo, TaskRepo, UserRepo
from app.core.exceptions import NotFoundError
from app.models.enums import RecurringTaskFrequency
from app.models.recurring_task import RecurringTask, RecurringTaskCreate, RecurringTaskUpdate
from app.services.recurring_task_service import RecurringTaskService
from app.utils.datetime_utils import normalize_timezone, now_utc

router = APIRouter()


def _compute_anchor_date(
    frequency: RecurringTaskFrequency,
    weekday: int | None,
    day_of_month: int | None,
    now: datetime,
) -> date:
    """Compute a sensible anchor_date based on frequency."""
    today = now.date()

    if frequency in (RecurringTaskFrequency.WEEKLY, RecurringTaskFrequency.BIWEEKLY):
        if weekday is not None:
            delta = (weekday - today.weekday()) % 7
            candidate = today + timedelta(days=delta)
            return candidate
        return today

    if frequency in (RecurringTaskFrequency.MONTHLY, RecurringTaskFrequency.BIMONTHLY):
        if day_of_month is not None:
            if today.day <= day_of_month:
                try:
                    return today.replace(day=day_of_month)
                except ValueError:
                    return today
            else:
                month = today.month + 1
                year = today.year
                if month > 12:
                    month = 1
                    year += 1
                try:
                    return date(year, month, day_of_month)
                except ValueError:
                    return date(year, month, 1)
        return today

    return today


@router.post("", response_model=RecurringTask, status_code=status.HTTP_201_CREATED)
async def create_recurring_task(
    payload: RecurringTaskCreate,
    user: CurrentUser,
    repo: RecurringTaskRepo,
    task_repo: TaskRepo,
    user_repo: UserRepo,
):
    """Create a new recurring task definition and generate upcoming instances."""
    try:
        user_account = await user_repo.get(UUID(user.id))
    except (TypeError, ValueError):
        user_account = None
    user_timezone = normalize_timezone(user_account.timezone if user_account else None)
    now_local = now_utc().astimezone(ZoneInfo(user_timezone))
    anchor_date = payload.anchor_date or _compute_anchor_date(
        payload.frequency,
        payload.weekday,
        payload.day_of_month,
        now_local,
    )
    created = await repo.create(
        user.id,
        payload.model_copy(update={"anchor_date": anchor_date}),
    )

    service = RecurringTaskService(
        recurring_repo=repo,
        task_repo=task_repo,
        user_repo=user_repo,
    )
    await service.ensure_upcoming_tasks(user.id)

    return created


@router.get("", response_model=list[RecurringTask])
async def list_recurring_tasks(
    user: CurrentUser,
    repo: RecurringTaskRepo,
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    include_inactive: bool = Query(False, description="Include inactive definitions"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[RecurringTask]:
    """List recurring task definitions."""
    return await repo.list(
        user.id,
        project_id=project_id,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{recurring_task_id}", response_model=RecurringTask)
async def get_recurring_task(
    recurring_task_id: UUID,
    user: CurrentUser,
    repo: RecurringTaskRepo,
) -> RecurringTask:
    """Get a recurring task definition by ID."""
    result = await repo.get(user.id, recurring_task_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecurringTask {recurring_task_id} not found",
        )
    return result


@router.patch("/{recurring_task_id}", response_model=RecurringTask)
async def update_recurring_task(
    recurring_task_id: UUID,
    update: RecurringTaskUpdate,
    user: CurrentUser,
    repo: RecurringTaskRepo,
) -> RecurringTask:
    """Update a recurring task definition."""
    try:
        return await repo.update(user.id, recurring_task_id, update)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete("/{recurring_task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_task(
    recurring_task_id: UUID,
    user: CurrentUser,
    repo: RecurringTaskRepo,
):
    """Delete a recurring task definition."""
    deleted = await repo.delete(user.id, recurring_task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecurringTask {recurring_task_id} not found",
        )


@router.delete("/{recurring_task_id}/generated-tasks")
async def delete_generated_tasks(
    recurring_task_id: UUID,
    user: CurrentUser,
    task_repo: TaskRepo,
):
    """Delete all task instances generated from a recurring task definition."""
    deleted_count = await task_repo.delete_by_recurring_task(user.id, recurring_task_id)
    return {"deleted_count": deleted_count}


@router.post("/{recurring_task_id}/generate-tasks")
async def generate_tasks(
    recurring_task_id: UUID,
    user: CurrentUser,
    repo: RecurringTaskRepo,
    task_repo: TaskRepo,
    user_repo: UserRepo,
    lookahead_days: int = Query(30, ge=1, le=180, description="Generate tasks for the next N days"),
):
    """Manually trigger task generation for a recurring task definition."""
    definition = await repo.get(user.id, recurring_task_id)
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"RecurringTask {recurring_task_id} not found",
        )

    service = RecurringTaskService(
        recurring_repo=repo,
        task_repo=task_repo,
        lookahead_days=lookahead_days,
        user_repo=user_repo,
    )
    return await service.ensure_upcoming_tasks(user.id)
