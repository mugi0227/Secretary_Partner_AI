"""
Tasks API endpoints.

CRUD operations for tasks and task breakdown.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, LLMProvider, MemoryRepo, TaskRepo
from app.core.exceptions import LLMValidationError, NotFoundError
from app.models.breakdown import BreakdownRequest, BreakdownResponse
from app.models.task import Task, TaskCreate, TaskUpdate
from app.services.planner_service import PlannerService

router = APIRouter()


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    task: TaskCreate,
    user: CurrentUser,
    repo: TaskRepo,
):
    """Create a new task."""
    return await repo.create(user.id, task)


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

