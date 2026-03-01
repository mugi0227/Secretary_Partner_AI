from datetime import datetime
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.collaboration import ProjectMember
from app.models.enums import ProjectRole, ProjectStatus, ProjectVisibility
from app.models.project import Project
from app.services.project_permissions import (
    ProjectAccess,
    ProjectAction,
    ensure_project_action,
    get_project_access,
)


class FakeProjectRepo:
    def __init__(self, project: Project | None):
        self._project = project

    async def get(self, user_id: str, project_id: UUID) -> Project | None:
        if not self._project or self._project.id != project_id:
            return None
        return self._project


class FakeProjectMemberRepo:
    def __init__(self, member: ProjectMember | None):
        self._member = member

    async def get_by_project_and_member_user_id(
        self, project_id: UUID, member_user_id: str
    ) -> ProjectMember | None:
        if not self._member:
            return None
        if self._member.project_id != project_id:
            return None
        if self._member.member_user_id != member_user_id:
            return None
        return self._member


def _make_project(user_id: str) -> Project:
    now = datetime.utcnow()
    return Project(
        id=uuid4(),
        user_id=user_id,
        name="Test Project",
        description=None,
        visibility=ProjectVisibility.PRIVATE,
        context_summary=None,
        context=None,
        priority=5,
        goals=[],
        key_points=[],
        kpi_config=None,
        status=ProjectStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _make_member(project_id: UUID, owner_id: str, member_user_id: str, role: ProjectRole) -> ProjectMember:
    now = datetime.utcnow()
    return ProjectMember(
        id=uuid4(),
        user_id=owner_id,
        project_id=project_id,
        member_user_id=member_user_id,
        role=role,
        capacity_hours=None,
        timezone=None,
        created_at=now,
        updated_at=now,
        member_display_name=None,
    )


@pytest.mark.asyncio
async def test_get_project_access_owner():
    owner_id = "owner"
    project = _make_project(owner_id)
    project_repo = FakeProjectRepo(project)
    member_repo = FakeProjectMemberRepo(None)

    access = await get_project_access(owner_id, project.id, project_repo, member_repo)
    assert access.owner_id == owner_id
    assert access.role == ProjectRole.OWNER


@pytest.mark.asyncio
async def test_get_project_access_member():
    owner_id = "owner"
    member_id = "member"
    project = _make_project(owner_id)
    member = _make_member(project.id, owner_id, member_id, ProjectRole.MEMBER)
    project_repo = FakeProjectRepo(project)
    member_repo = FakeProjectMemberRepo(member)

    access = await get_project_access(member_id, project.id, project_repo, member_repo)
    assert access.owner_id == owner_id
    assert access.role == ProjectRole.MEMBER


@pytest.mark.asyncio
async def test_get_project_access_missing_project():
    project_repo = FakeProjectRepo(None)
    member_repo = FakeProjectMemberRepo(None)

    with pytest.raises(NotFoundError):
        await get_project_access("owner", uuid4(), project_repo, member_repo)


@pytest.mark.asyncio
async def test_get_project_access_non_member_returns_viewer():
    """When repo.get() returns a project but user is not direct owner/member,
    get_project_access returns VIEWER (ancestor access fallback)."""
    owner_id = "owner"
    member_id = "member"
    project = _make_project(owner_id)
    project_repo = FakeProjectRepo(project)
    member_repo = FakeProjectMemberRepo(None)

    access = await get_project_access(member_id, project.id, project_repo, member_repo)
    assert access.role == ProjectRole.VIEWER
    assert access.owner_id == owner_id


def test_ensure_project_action_denies_member_update():
    owner_id = "owner"
    project = _make_project(owner_id)
    access_wrapper = ProjectAccess(project=project, role=ProjectRole.MEMBER, owner_id=owner_id)
    with pytest.raises(ForbiddenError):
        ensure_project_action(access_wrapper, ProjectAction.PROJECT_UPDATE)
