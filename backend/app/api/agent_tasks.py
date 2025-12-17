"""
Agent Tasks API endpoints.

Endpoints for managing autonomous agent actions.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, AgentTaskRepo
from app.core.exceptions import NotFoundError
from app.models.agent_task import AgentTask, AgentTaskCreate, AgentTaskUpdate
from app.models.enums import AgentTaskStatus

router = APIRouter()


@router.post("", response_model=AgentTask, status_code=status.HTTP_201_CREATED)
async def create_agent_task(
    task: AgentTaskCreate,
    user: CurrentUser,
    repo: AgentTaskRepo,
):
    """Create a new agent task."""
    return await repo.create(user.id, task)


@router.get("/{task_id}", response_model=AgentTask)
async def get_agent_task(
    task_id: UUID,
    user: CurrentUser,
    repo: AgentTaskRepo,
):
    """Get an agent task by ID."""
    task = await repo.get(user.id, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentTask {task_id} not found",
        )
    return task


@router.get("", response_model=list[AgentTask])
async def list_agent_tasks(
    user: CurrentUser,
    repo: AgentTaskRepo,
    status: Optional[AgentTaskStatus] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List agent tasks with optional filters."""
    return await repo.list(
        user.id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.patch("/{task_id}", response_model=AgentTask)
async def update_agent_task(
    task_id: UUID,
    update: AgentTaskUpdate,
    user: CurrentUser,
    repo: AgentTaskRepo,
):
    """Update an agent task."""
    try:
        return await repo.update(user.id, task_id, update)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_agent_task(
    task_id: UUID,
    user: CurrentUser,
    repo: AgentTaskRepo,
):
    """Cancel an agent task."""
    cancelled = await repo.cancel(user.id, task_id)
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AgentTask {task_id} not found or already completed",
        )

