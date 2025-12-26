"""
Tasks API endpoints.

CRUD operations for tasks and task breakdown.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, LLMProvider, MemoryRepo, ProjectRepo, TaskRepo
from app.core.exceptions import LLMValidationError, NotFoundError
from app.models.breakdown import BreakdownRequest, BreakdownResponse
from app.models.schedule import ScheduleResponse, TodayTasksResponse
from app.models.task import Task, TaskCreate, TaskUpdate
from app.services.planner_service import PlannerService
from app.services.scheduler_service import SchedulerService

router = APIRouter()


def get_scheduler_service() -> SchedulerService:
    """Get SchedulerService instance."""
    return SchedulerService()


def apply_capacity_buffer(
    scheduler_service: SchedulerService,
    capacity_hours: Optional[float],
    buffer_hours: Optional[float],
) -> Optional[float]:
    """Apply buffer hours to capacity hours."""
    if buffer_hours is None:
        return capacity_hours
    base_hours = capacity_hours if capacity_hours is not None else scheduler_service.default_capacity_hours
    return max(0.0, base_hours - buffer_hours)


async def load_project_priorities(project_repo: ProjectRepo, user_id: str) -> dict[UUID, int]:
    """Load project priorities for scheduling."""
    projects = await project_repo.list(user_id, limit=1000)
    return {project.id: project.priority for project in projects}


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Create a new task."""
    return await repo.create(user.id, task)


@router.get("", response_model=list[Task])
async def list_tasks(
    user: CurrentUser,
    repo: TaskRepo,
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    include_done: bool = Query(False, description="Include completed tasks"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List tasks with optional filters."""
    return await repo.list(
        user.id,
        project_id=project_id,
        status=status,
        include_done=include_done,
        limit=limit,
        offset=offset,
    )


@router.get("/schedule", response_model=ScheduleResponse)
async def get_task_schedule(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    start_date: Optional[date] = Query(None, description="Schedule start date"),
    capacity_hours: Optional[float] = Query(None, description="Daily capacity in hours (default: 8)"),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
    max_days: int = Query(60, ge=1, le=365, description="Maximum days to schedule"),
):
    """Build a multi-day schedule for tasks."""
    tasks = await repo.list(user.id, include_done=True, limit=1000)
    project_priorities = await load_project_priorities(project_repo, user.id)
    effective_capacity = apply_capacity_buffer(scheduler_service, capacity_hours, buffer_hours)
    return scheduler_service.build_schedule(
        tasks,
        project_priorities=project_priorities,
        start_date=start_date,
        capacity_hours=effective_capacity,
        max_days=max_days,
    )


@router.get("/today", response_model=TodayTasksResponse)
async def get_today_tasks(
    user: CurrentUser,
    repo: TaskRepo,
    project_repo: ProjectRepo,
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
    target_date: Optional[date] = Query(None, description="Target date (default: today)"),
    capacity_hours: Optional[float] = Query(None, description="Daily capacity in hours (default: 8)"),
    buffer_hours: Optional[float] = Query(None, description="Daily buffer hours"),
    max_days: int = Query(30, ge=1, le=365, description="Maximum days to schedule"),
):
    """Get today's tasks derived from the schedule."""
    tasks = await repo.list(user.id, include_done=True, limit=1000)
    project_priorities = await load_project_priorities(project_repo, user.id)
    effective_capacity = apply_capacity_buffer(scheduler_service, capacity_hours, buffer_hours)
    schedule = scheduler_service.build_schedule(
        tasks,
        project_priorities=project_priorities,
        start_date=target_date,
        capacity_hours=effective_capacity,
        max_days=max_days,
    )
    return scheduler_service.get_today_tasks(
        schedule,
        tasks,
        project_priorities=project_priorities,
        today=target_date or date.today(),
    )


@router.get("/{task_id}", response_model=Task)
async def get_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Get a task by ID."""
    task = await repo.get(user.id, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )
    return task


@router.patch("/{task_id}", response_model=Task)
async def update_task(
    task_id: UUID,
    update: TaskUpdate,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Update a task."""
    try:
        return await repo.update(user.id, task_id, update)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Delete a task."""
    deleted = await repo.delete(user.id, task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )


@router.post("/{task_id}/breakdown", response_model=BreakdownResponse)
async def breakdown_task(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
    memory_repo: MemoryRepo,
    llm_provider: LLMProvider,
    request: BreakdownRequest = BreakdownRequest(),
):
    """
    Break down a task into micro-steps.

    Uses the Planner Agent to decompose large tasks into
    manageable 5-15 minute steps for ADHD users.

    Optionally creates subtasks from the breakdown.
    """
    try:
        service = PlannerService(
            llm_provider=llm_provider,
            task_repo=repo,
            memory_repo=memory_repo,
        )
        return await service.breakdown_task(
            user_id=user.id,
            task_id=task_id,
            create_subtasks=request.create_subtasks,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except LLMValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse LLM output: {e.message}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Breakdown failed: {str(e)}",
        )


@router.get("/{task_id}/subtasks", response_model=list[Task])
async def get_subtasks(
    task_id: UUID,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Get all subtasks of a parent task."""
    return await repo.get_subtasks(user.id, task_id)

