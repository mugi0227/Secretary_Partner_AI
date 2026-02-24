"""
Milestone API endpoints.

Provides CRUD operations for milestones.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    CurrentUser,
    MilestoneRepo,
    PhaseRepo,
    ProjectMemberRepo,
    ProjectRepo,
    TaskRepo,
)
from app.api.permissions import require_project_action, require_project_member
from app.core.exceptions import NotFoundError
from app.models.milestone import Milestone, MilestoneCreate, MilestoneUpdate, MilestoneWithProgress
from app.services.milestone_progress_service import MilestoneProgressService
from app.services.project_permissions import ProjectAction

router = APIRouter(prefix="/milestones", tags=["milestones"])


@router.post("", response_model=Milestone, status_code=status.HTTP_201_CREATED)
async def create_milestone(
    milestone: MilestoneCreate,
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
) -> Milestone:
    """Create a new milestone."""
    await require_project_action(
        user,
        milestone.project_id,
        project_repo,
        member_repo,
        ProjectAction.MILESTONE_MANAGE,
    )
    return await repo.create(user.id, milestone)


@router.get("", response_model=list[MilestoneWithProgress])
async def list_milestones(
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    phase_repo: PhaseRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
    project_id: UUID | None = Query(None, description="Filter milestones by project ID"),
    phase_id: UUID | None = Query(None, description="Filter milestones by phase ID"),
) -> list[MilestoneWithProgress]:
    """List milestones by project or phase."""
    progress_service = MilestoneProgressService(task_repo)
    if project_id:
        access = await require_project_action(
            user,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.MILESTONE_MANAGE,
        )
        owner_id = access.owner_id
        milestones = await repo.list_by_project(owner_id, project_id)
        return await progress_service.enrich_milestones(owner_id, milestones)
    if phase_id:
        project_id = await phase_repo.get_project_id(phase_id)
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Phase {phase_id} not found",
            )
        access = await require_project_member(user, project_id, project_repo, member_repo)
        milestones = await repo.list_by_phase(access.owner_id, phase_id)
        return await progress_service.enrich_milestones(access.owner_id, milestones)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="project_id or phase_id query parameter is required",
    )


@router.get("/{milestone_id}", response_model=MilestoneWithProgress)
async def get_milestone(
    milestone_id: UUID,
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
) -> MilestoneWithProgress:
    """Get a milestone by ID."""
    project_id = await repo.get_project_id(milestone_id)
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Milestone {milestone_id} not found",
        )
    access = await require_project_member(user, project_id, project_repo, member_repo)
    milestone = await repo.get_by_id(access.owner_id, milestone_id, project_id=project_id)
    if not milestone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Milestone {milestone_id} not found",
        )
    progress_service = MilestoneProgressService(task_repo)
    return await progress_service.calculate_milestone_progress(access.owner_id, milestone)


@router.get("/phase/{phase_id}", response_model=list[MilestoneWithProgress])
async def list_milestones_by_phase(
    phase_id: UUID,
    user: CurrentUser,
    repo: MilestoneRepo,
    phase_repo: PhaseRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
) -> list[MilestoneWithProgress]:
    """List milestones for a phase."""
    project_id = await phase_repo.get_project_id(phase_id)
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Phase {phase_id} not found",
        )
    access = await require_project_member(user, project_id, project_repo, member_repo)
    milestones = await repo.list_by_phase(access.owner_id, phase_id)
    progress_service = MilestoneProgressService(task_repo)
    return await progress_service.enrich_milestones(access.owner_id, milestones)


@router.get("/project/{project_id}", response_model=list[MilestoneWithProgress])
async def list_milestones_by_project(
    project_id: UUID,
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
    task_repo: TaskRepo,
) -> list[MilestoneWithProgress]:
    """List milestones for a project."""
    access = await require_project_action(
        user,
        project_id,
        project_repo,
        member_repo,
        ProjectAction.MILESTONE_MANAGE,
    )
    owner_id = access.owner_id
    milestones = await repo.list_by_project(owner_id, project_id)
    progress_service = MilestoneProgressService(task_repo)
    return await progress_service.enrich_milestones(owner_id, milestones)


@router.patch("/{milestone_id}", response_model=Milestone)
async def update_milestone(
    milestone_id: UUID,
    milestone: MilestoneUpdate,
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
) -> Milestone:
    """Update a milestone."""
    project_id = await repo.get_project_id(milestone_id)
    owner_id = user.id
    if project_id:
        access = await require_project_action(
            user,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.MILESTONE_MANAGE,
        )
        owner_id = access.owner_id

    try:
        return await repo.update(owner_id, milestone_id, project_id, milestone)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete("/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    milestone_id: UUID,
    user: CurrentUser,
    repo: MilestoneRepo,
    project_repo: ProjectRepo,
    member_repo: ProjectMemberRepo,
):
    """Delete a milestone."""
    project_id = await repo.get_project_id(milestone_id)
    owner_id = user.id
    if project_id:
        access = await require_project_action(
            user,
            project_id,
            project_repo,
            member_repo,
            ProjectAction.MILESTONE_MANAGE,
        )
        owner_id = access.owner_id

    deleted = await repo.delete(owner_id, milestone_id, project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Milestone {milestone_id} not found",
        )
