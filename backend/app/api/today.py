"""
Today API endpoints.

Smart daily features like Top 3 tasks.
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, ProjectRepo, TaskAssignmentRepo, TaskRepo, UserRepo
from app.models.task import Task
from app.services.scheduler_service import SchedulerService
from app.utils.datetime_utils import get_user_today, normalize_timezone

router = APIRouter()


class CapacityInfo(BaseModel):
    """Capacity check information."""
    feasible: bool
    total_minutes: int
    capacity_minutes: int
    overflow_minutes: int
    capacity_usage_percent: int


class Top3Response(BaseModel):
    """Top 3 tasks response with capacity info."""
    tasks: list[Task]
    capacity_info: Optional[CapacityInfo] = None
    overflow_suggestion: str = ""


def get_scheduler_service() -> SchedulerService:
    """Get SchedulerService instance."""
    return SchedulerService()


def parse_capacity_by_weekday(
    capacity_by_weekday: Optional[str],
) -> Optional[list[float]]:
    """Parse capacity_by_weekday query param."""
    if capacity_by_weekday is None:
        return None
    try:
        parsed = json.loads(capacity_by_weekday)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="capacity_by_weekday must be a JSON array of 7 numbers",
        ) from exc
    if not isinstance(parsed, list) or len(parsed) != 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="capacity_by_weekday must be a JSON array of 7 numbers",
        )
    result: list[float] = []
    for entry in parsed:
        try:
            value = float(entry)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="capacity_by_weekday must be a JSON array of 7 numbers",
            ) from exc
        if value < 0 or value > 24:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="capacity_by_weekday values must be between 0 and 24",
            )
        result.append(value)
    return result


def apply_capacity_buffer(
    capacity_hours: Optional[float],
    buffer_hours: Optional[float],
    capacity_by_weekday: Optional[list[float]] = None,
) -> tuple[Optional[float], Optional[list[float]]]:
    """Apply buffer hours to capacity hours."""
    if buffer_hours is None:
        return capacity_hours, capacity_by_weekday
    base_hours = capacity_hours if capacity_hours is not None else SchedulerService().default_capacity_hours
    adjusted_weekday = None
    if capacity_by_weekday:
        adjusted_weekday = [max(0.0, hours - buffer_hours) for hours in capacity_by_weekday]
    return max(0.0, base_hours - buffer_hours), adjusted_weekday


@router.get("/top3", response_model=Top3Response, status_code=status.HTTP_200_OK)
async def get_top3_tasks(
    user: CurrentUser,
    user_repo: UserRepo,
    task_repo: TaskRepo,
    project_repo: ProjectRepo,
    assignment_repo: TaskAssignmentRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    capacity_hours: Optional[float] = Query(None, description="Daily capacity in hours (default: 8)"),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
    capacity_by_weekday: Optional[str] = Query(
        None,
        description="JSON array of 7 daily capacity values (Sun..Sat)",
    ),
    check_capacity: bool = Query(True, description="Check capacity constraints"),
):
    """
    Get today's top 3 priority tasks with capacity awareness.

    Uses intelligent scoring based on:
    - Importance level (HIGH/MEDIUM/LOW)
    - Urgency level (HIGH/MEDIUM/LOW)
    - Due date proximity (overdue, today, tomorrow, this week)
    - Energy level (quick wins for low-energy tasks)
    - Task dependencies (blocked tasks excluded)

    Also checks capacity constraints:
    - Daily work hour limits (default 8 hours)
    - Suggests moving overflow tasks to tomorrow

    Returns:
        Top3Response: Top 3 tasks with capacity information
    """
    # Get user account to access timezone
    from uuid import UUID
    user_account = await user_repo.get(UUID(user.id))
    user_timezone = normalize_timezone(user_account.timezone if user_account else None)
    today = get_user_today(user_timezone)

    # 1. Get assigned tasks
    my_assignments = await assignment_repo.list_for_assignee(user.id)
    assigned_ids = [a.task_id for a in my_assignments]
    assigned_tasks = await task_repo.get_many(assigned_ids)

    # Get all assignments for filtering (includes other users' assignments)
    all_assignments = await assignment_repo.list_all_for_user(user.id)

    # 2. Get personal tasks (Inbox/Memo)
    personal_tasks = await task_repo.list_personal_tasks(user.id, include_done=True, limit=1000)

    # Merge unique tasks
    all_tasks_map = {t.id: t for t in personal_tasks}
    for t in assigned_tasks:
        all_tasks_map[t.id] = t

    tasks = list(all_tasks_map.values())

    project_priorities = {project.id: project.priority for project in await project_repo.list(user.id, limit=1000)}
    parsed_weekly = parse_capacity_by_weekday(capacity_by_weekday)
    effective_capacity, effective_weekly = apply_capacity_buffer(
        capacity_hours,
        buffer_hours,
        parsed_weekly,
    )

    schedule = scheduler_service.build_schedule(
        tasks,
        project_priorities=project_priorities,
        start_date=today,
        capacity_hours=effective_capacity,
        capacity_by_weekday=effective_weekly,
        max_days=30,
        current_user_id=user.id,
        assignments=all_assignments,
        filter_by_assignee=True,
        user_timezone=user_timezone,
    )
    today_result = scheduler_service.get_today_tasks(
        schedule,
        tasks,
        project_priorities=project_priorities,
        today=today,
        user_timezone=user_timezone,
    )

    top3_tasks = [task for task in today_result.today_tasks if task.id in set(today_result.top3_ids)]
    capacity_info = None

    if check_capacity and today_result.capacity_minutes:
        capacity_usage_percent = min(
            100,
            int((today_result.total_estimated_minutes / today_result.capacity_minutes) * 100),
        )
        capacity_info = CapacityInfo(
            feasible=not today_result.overflow,
            total_minutes=today_result.total_estimated_minutes,
            capacity_minutes=today_result.capacity_minutes,
            overflow_minutes=today_result.overflow_minutes,
            capacity_usage_percent=capacity_usage_percent,
        )

    return Top3Response(
        tasks=top3_tasks,
        capacity_info=capacity_info,
        overflow_suggestion="",
    )
