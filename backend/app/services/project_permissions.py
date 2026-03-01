from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable
from uuid import UUID

from app.core.exceptions import ForbiddenError, NotFoundError
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.models.enums import ProjectRole
from app.models.project import Project


class ProjectAction(str, Enum):
    PROJECT_READ = "project.read"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    MEMBER_READ = "member.read"
    MEMBER_MANAGE = "member.manage"
    INVITATION_READ = "invitation.read"
    INVITATION_MANAGE = "invitation.manage"
    PHASE_MANAGE = "phase.manage"
    MILESTONE_MANAGE = "milestone.manage"
    CHECKIN_READ = "checkin.read"
    CHECKIN_WRITE = "checkin.write"
    ACHIEVEMENT_READ = "achievement.read"
    ACHIEVEMENT_WRITE = "achievement.write"
    SNAPSHOT_MANAGE = "snapshot.manage"
    MEETING_AGENDA_MANAGE = "meeting_agenda.manage"
    ASSIGNMENT_READ = "assignment.read"
    BLOCKER_READ = "blocker.read"


ALL_PROJECT_ROLES = {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER}
ADMIN_PROJECT_ROLES = {ProjectRole.OWNER, ProjectRole.ADMIN}
READ_ONLY_ROLES = {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER}

PROJECT_ROLE_MATRIX: dict[ProjectAction, set[ProjectRole]] = {
    ProjectAction.PROJECT_READ: READ_ONLY_ROLES,
    ProjectAction.PROJECT_UPDATE: ADMIN_PROJECT_ROLES,
    ProjectAction.PROJECT_DELETE: ADMIN_PROJECT_ROLES,
    ProjectAction.MEMBER_READ: READ_ONLY_ROLES,
    ProjectAction.MEMBER_MANAGE: ADMIN_PROJECT_ROLES,
    ProjectAction.INVITATION_READ: ADMIN_PROJECT_ROLES,
    ProjectAction.INVITATION_MANAGE: ADMIN_PROJECT_ROLES,
    ProjectAction.PHASE_MANAGE: ALL_PROJECT_ROLES,
    ProjectAction.MILESTONE_MANAGE: ALL_PROJECT_ROLES,
    ProjectAction.CHECKIN_READ: READ_ONLY_ROLES,
    ProjectAction.CHECKIN_WRITE: ALL_PROJECT_ROLES,
    ProjectAction.ACHIEVEMENT_READ: READ_ONLY_ROLES,
    ProjectAction.ACHIEVEMENT_WRITE: ALL_PROJECT_ROLES,
    ProjectAction.SNAPSHOT_MANAGE: ALL_PROJECT_ROLES,
    ProjectAction.MEETING_AGENDA_MANAGE: ALL_PROJECT_ROLES,
    ProjectAction.ASSIGNMENT_READ: READ_ONLY_ROLES,
    ProjectAction.BLOCKER_READ: READ_ONLY_ROLES,
}


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    role: ProjectRole
    owner_id: str


def roles_for_action(action: ProjectAction) -> set[ProjectRole]:
    return set(PROJECT_ROLE_MATRIX.get(action, set()))


def role_allows(action: ProjectAction, role: ProjectRole) -> bool:
    return role in roles_for_action(action)


def ensure_project_role(access: ProjectAccess, allowed_roles: Iterable[ProjectRole]) -> ProjectAccess:
    if access.role not in set(allowed_roles):
        raise ForbiddenError("Insufficient project role")
    return access


def ensure_project_action(access: ProjectAccess, action: ProjectAction) -> ProjectAccess:
    if not role_allows(action, access.role):
        raise ForbiddenError("Insufficient project role")
    return access


async def get_project_access(
    user_id: str,
    project_id: UUID,
    project_repo: IProjectRepository,
    member_repo: IProjectMemberRepository,
) -> ProjectAccess:
    project = await project_repo.get(user_id, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")

    if user_id == project.user_id:
        return ProjectAccess(project=project, role=ProjectRole.OWNER, owner_id=project.user_id)

    member = await member_repo.get_by_project_and_member_user_id(project_id, user_id)
    if member:
        return ProjectAccess(project=project, role=member.role, owner_id=project.user_id)

    # repo.get() returned the project but user is not direct owner/member.
    # This means access was granted via ancestor membership (read-only).
    return ProjectAccess(project=project, role=ProjectRole.VIEWER, owner_id=project.user_id)
