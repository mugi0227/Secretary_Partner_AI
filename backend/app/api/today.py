"""
Today API endpoints.

Smart daily features like Top 3 tasks.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from datetime import date
from app.api.deps import CurrentUser, ProjectRepo, TaskRepo
from app.models.task import Task
from app.services.scheduler_service import SchedulerService

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


def apply_capacity_buffer(
    capacity_hours: Optional[float],
    buffer_hours: Optional[float],
) -> Optional[float]:
    """Apply buffer hours to capacity hours."""
    if buffer_hours is None:
        return capacity_hours
    base_hours = capacity_hours if capacity_hours is not None else SchedulerService().default_capacity_hours
    return max(0.0, base_hours - buffer_hours)


@router.get("/top3", response_model=Top3Response, status_code=status.HTTP_200_OK)
async def get_top3_tasks(
    user: CurrentUser,
    task_repo: TaskRepo,
    project_repo: ProjectRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    capacity_hours: Optional[float] = Query(None, description="Daily capacity in hours (default: 8)"),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
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
    tasks = await task_repo.list(user.id, include_done=True, limit=1000)
    project_priorities = {project.id: project.priority for project in await project_repo.list(user.id, limit=1000)}
    effective_capacity = apply_capacity_buffer(capacity_hours, buffer_hours)

    schedule = scheduler_service.build_schedule(
        tasks,
        project_priorities=project_priorities,
        start_date=date.today(),
        capacity_hours=effective_capacity,
        max_days=30,
    )
    today_result = scheduler_service.get_today_tasks(
        schedule,
        tasks,
        project_priorities=project_priorities,
        today=date.today(),
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
