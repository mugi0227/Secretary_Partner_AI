"""
Projects API endpoints.

CRUD operations for projects.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, ProjectRepo, TaskRepo
from app.core.exceptions import NotFoundError
from app.models.project import Project, ProjectCreate, ProjectUpdate, ProjectWithTaskCount
from app.models.project_kpi import ProjectKpiTemplate
from app.services.kpi_calculator import apply_project_kpis
from app.services.kpi_templates import get_kpi_templates

router = APIRouter()


@router.get("/kpi-templates", response_model=list[ProjectKpiTemplate])
async def list_kpi_templates(user: CurrentUser):
    """List KPI templates."""
    return get_kpi_templates()


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project: ProjectCreate,
    user: CurrentUser,
    repo: ProjectRepo,
):
    """Create a new project."""
    return await repo.create(user.id, project)


@router.get("/{project_id}", response_model=ProjectWithTaskCount)
async def get_project(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
    task_repo: TaskRepo,
):
    """Get a project by ID with task counts."""
    # Use list_with_task_count to get task statistics
    all_projects = await repo.list_with_task_count(user.id)
    project = next((p for p in all_projects if p.id == project_id), None)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

    # Apply KPI calculations
    return await apply_project_kpis(user.id, project, task_repo)


@router.get("", response_model=list[ProjectWithTaskCount])
async def list_projects(
    user: CurrentUser,
    repo: ProjectRepo,
    task_repo: TaskRepo,
    status: Optional[str] = Query(None, description="Filter by status"),
):
    """List projects with task counts."""
    projects = await repo.list_with_task_count(user.id, status=status)
    return [await apply_project_kpis(user.id, project, task_repo) for project in projects]


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: UUID,
    update: ProjectUpdate,
    user: CurrentUser,
    repo: ProjectRepo,
):
    """Update a project."""
    try:
        return await repo.update(user.id, project_id, update)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user: CurrentUser,
    repo: ProjectRepo,
):
    """Delete a project."""
    deleted = await repo.delete(user.id, project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

