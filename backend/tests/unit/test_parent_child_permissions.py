"""
Tests for parent-child project permission features (Phase 1-5).

Covers:
- VIEWER role in permission matrix
- get_project_access ancestor fallback
- ensure_project_action for VIEWER
- invite_from_parent endpoint logic
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.core.exceptions import ForbiddenError
from app.models.collaboration import ProjectMember, ProjectMemberCreate, ProjectMemberUpdate
from app.models.enums import ProjectRole, ProjectStatus, ProjectVisibility
from app.models.project import Project, ProjectCreate
from app.services.project_permissions import (
    ProjectAccess,
    ProjectAction,
    ensure_project_action,
    get_project_access,
    role_allows,
    roles_for_action,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.utcnow()


def _make_project(user_id: str, *, parent_project_id: UUID | None = None) -> Project:
    return Project(
        id=uuid4(),
        user_id=user_id,
        name="Test Project",
        description=None,
        visibility=ProjectVisibility.TEAM,
        context_summary=None,
        context=None,
        priority=5,
        goals=[],
        key_points=[],
        kpi_config=None,
        parent_project_id=parent_project_id,
        status=ProjectStatus.ACTIVE,
        created_at=_now(),
        updated_at=_now(),
    )


def _make_member(
    project_id: UUID,
    owner_id: str,
    member_user_id: str,
    role: ProjectRole = ProjectRole.MEMBER,
) -> ProjectMember:
    return ProjectMember(
        id=uuid4(),
        user_id=owner_id,
        project_id=project_id,
        member_user_id=member_user_id,
        role=role,
        capacity_hours=None,
        timezone=None,
        created_at=_now(),
        updated_at=_now(),
        member_display_name=None,
    )


class FakeProjectRepo:
    """Minimal project repo supporting get() and get_by_id()."""

    def __init__(self, *projects: Project):
        self._by_id: dict[UUID, Project] = {p.id: p for p in projects}

    async def get(self, user_id: str, project_id: UUID) -> Project | None:
        return self._by_id.get(project_id)

    async def get_by_id(self, project_id: UUID) -> Project | None:
        return self._by_id.get(project_id)

    async def create(self, user_id: str, project: ProjectCreate) -> Project:
        created = Project(
            id=uuid4(),
            user_id=user_id,
            name=project.name,
            description=project.description,
            visibility=project.visibility,
            context_summary=project.context_summary,
            context=project.context,
            priority=project.priority,
            goals=project.goals,
            key_points=project.key_points,
            kpi_config=project.kpi_config,
            parent_project_id=project.parent_project_id,
            status=ProjectStatus.ACTIVE,
            created_at=_now(),
            updated_at=_now(),
        )
        self._by_id[created.id] = created
        return created


class FakeMemberRepo:
    """Minimal member repo for permission tests."""

    def __init__(self, *members: ProjectMember):
        self._members = list(members)

    async def get_by_project_and_member_user_id(
        self, project_id: UUID, member_user_id: str
    ) -> ProjectMember | None:
        for m in self._members:
            if m.project_id == project_id and m.member_user_id == member_user_id:
                return m
        return None

    async def list_by_project(self, project_id: UUID) -> list[ProjectMember]:
        return [m for m in self._members if m.project_id == project_id]

    async def create(
        self, owner_id: str, project_id: UUID, data: ProjectMemberCreate
    ) -> ProjectMember:
        m = _make_member(project_id, owner_id, data.member_user_id, data.role or ProjectRole.MEMBER)
        self._members.append(m)
        return m

    async def get(self, owner_id: str, member_id: UUID) -> ProjectMember | None:
        for member in self._members:
            if member.user_id == owner_id and member.id == member_id:
                return member
        return None

    async def update(
        self,
        owner_id: str,
        member_id: UUID,
        data: ProjectMemberUpdate,
    ) -> ProjectMember:
        member = await self.get(owner_id, member_id)
        if not member:
            raise AssertionError("member not found")
        updated = member.model_copy(update=data.model_dump(exclude_unset=True))
        self._members = [updated if m.id == member_id else m for m in self._members]
        return updated

    async def delete(self, owner_id: str, member_id: UUID) -> bool:
        before = len(self._members)
        self._members = [
            member for member in self._members
            if not (member.user_id == owner_id and member.id == member_id)
        ]
        return len(self._members) < before


# ===========================================================================
# Phase 1: VIEWER role & permission matrix
# ===========================================================================


class TestViewerRoleMatrix:
    """VIEWER should be allowed on read actions, denied on write actions."""

    @pytest.mark.parametrize(
        ("action", "expected_roles"),
        [
            (
                ProjectAction.PROJECT_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
            (
                ProjectAction.PROJECT_UPDATE,
                {ProjectRole.OWNER, ProjectRole.ADMIN},
            ),
            (
                ProjectAction.PROJECT_DELETE,
                {ProjectRole.OWNER, ProjectRole.ADMIN},
            ),
            (
                ProjectAction.MEMBER_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
            (
                ProjectAction.MEMBER_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN},
            ),
            (
                ProjectAction.INVITATION_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN},
            ),
            (
                ProjectAction.INVITATION_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN},
            ),
            (
                ProjectAction.PHASE_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.MILESTONE_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.CHECKIN_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
            (
                ProjectAction.CHECKIN_WRITE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.ACHIEVEMENT_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
            (
                ProjectAction.ACHIEVEMENT_WRITE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.SNAPSHOT_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.MEETING_AGENDA_MANAGE,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER},
            ),
            (
                ProjectAction.ASSIGNMENT_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
            (
                ProjectAction.BLOCKER_READ,
                {ProjectRole.OWNER, ProjectRole.ADMIN, ProjectRole.MEMBER, ProjectRole.VIEWER},
            ),
        ],
    )
    def test_project_permission_matrix_is_explicit(
        self,
        action: ProjectAction,
        expected_roles: set[ProjectRole],
    ):
        assert roles_for_action(action) == expected_roles

    @pytest.mark.parametrize(
        "action",
        [
            ProjectAction.PROJECT_READ,
            ProjectAction.MEMBER_READ,
            ProjectAction.CHECKIN_READ,
            ProjectAction.ACHIEVEMENT_READ,
            ProjectAction.ASSIGNMENT_READ,
            ProjectAction.BLOCKER_READ,
        ],
    )
    def test_viewer_allowed_read_actions(self, action: ProjectAction):
        assert role_allows(action, ProjectRole.VIEWER)

    @pytest.mark.parametrize(
        "action",
        [
            ProjectAction.PROJECT_UPDATE,
            ProjectAction.PROJECT_DELETE,
            ProjectAction.MEMBER_MANAGE,
            ProjectAction.INVITATION_MANAGE,
            ProjectAction.INVITATION_READ,
            ProjectAction.PHASE_MANAGE,
            ProjectAction.MILESTONE_MANAGE,
            ProjectAction.CHECKIN_WRITE,
            ProjectAction.ACHIEVEMENT_WRITE,
            ProjectAction.SNAPSHOT_MANAGE,
            ProjectAction.MEETING_AGENDA_MANAGE,
        ],
    )
    def test_viewer_denied_write_actions(self, action: ProjectAction):
        assert not role_allows(action, ProjectRole.VIEWER)

    def test_ensure_project_action_denies_viewer_write(self):
        project = _make_project("owner")
        access = ProjectAccess(project=project, role=ProjectRole.VIEWER, owner_id="owner")
        with pytest.raises(ForbiddenError):
            ensure_project_action(access, ProjectAction.PROJECT_UPDATE)

    def test_ensure_project_action_allows_viewer_read(self):
        project = _make_project("owner")
        access = ProjectAccess(project=project, role=ProjectRole.VIEWER, owner_id="owner")
        result = ensure_project_action(access, ProjectAction.PROJECT_READ)
        assert result.role == ProjectRole.VIEWER


# ===========================================================================
# Phase 1: get_project_access ancestor fallback
# ===========================================================================


class TestGetProjectAccessAncestor:
    """When repo.get() returns a project but user is not direct owner/member,
    get_project_access should return VIEWER (ancestor access)."""

    @pytest.mark.asyncio
    async def test_ancestor_access_returns_viewer(self):
        owner_id = "owner-a"
        ancestor_user = "ancestor-user"
        project = _make_project(owner_id)

        # repo.get() returns the project (simulating ancestor access)
        project_repo = FakeProjectRepo(project)
        # no direct membership
        member_repo = FakeMemberRepo()

        access = await get_project_access(
            ancestor_user, project.id, project_repo, member_repo,
        )
        assert access.role == ProjectRole.VIEWER
        assert access.owner_id == owner_id

    @pytest.mark.asyncio
    async def test_direct_owner_still_returns_owner(self):
        owner_id = "owner-a"
        project = _make_project(owner_id)
        project_repo = FakeProjectRepo(project)
        member_repo = FakeMemberRepo()

        access = await get_project_access(
            owner_id, project.id, project_repo, member_repo,
        )
        assert access.role == ProjectRole.OWNER

    @pytest.mark.asyncio
    async def test_direct_member_returns_member_role(self):
        owner_id = "owner-a"
        member_user_id = "member-b"
        project = _make_project(owner_id)
        member = _make_member(project.id, owner_id, member_user_id, ProjectRole.ADMIN)
        project_repo = FakeProjectRepo(project)
        member_repo = FakeMemberRepo(member)

        access = await get_project_access(
            member_user_id, project.id, project_repo, member_repo,
        )
        assert access.role == ProjectRole.ADMIN


# ===========================================================================
# Parent assignment and owner role guardrails
# ===========================================================================


class TestProjectPermissionGuardrails:
    @pytest.mark.asyncio
    async def test_create_child_project_requires_parent_owner(self):
        from app.api.projects import create_project

        parent = _make_project("parent-owner")
        project_repo = FakeProjectRepo(parent)
        member_repo = FakeMemberRepo()
        user = SimpleNamespace(id="other-user")

        with pytest.raises(HTTPException) as exc_info:
            await create_project(
                ProjectCreate(
                    name="Unauthorized Child",
                    visibility=ProjectVisibility.TEAM,
                    parent_project_id=parent.id,
                ),
                user,
                project_repo,
                member_repo,
            )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_create_child_project_allows_parent_owner(self):
        from app.api.projects import create_project

        parent_owner = "parent-owner"
        parent = _make_project(parent_owner)
        project_repo = FakeProjectRepo(parent)
        member_repo = FakeMemberRepo()
        user = SimpleNamespace(id=parent_owner)

        created = await create_project(
            ProjectCreate(
                name="Authorized Child",
                visibility=ProjectVisibility.TEAM,
                parent_project_id=parent.id,
            ),
            user,
            project_repo,
            member_repo,
        )

        assert created.parent_project_id == parent.id
        assert any(
            member.project_id == created.id
            and member.member_user_id == parent_owner
            and member.role == ProjectRole.OWNER
            for member in member_repo._members
        )

    @pytest.mark.asyncio
    async def test_add_member_rejects_owner_role(self):
        from app.api.projects import add_project_member

        owner_id = "owner"
        project = _make_project(owner_id)
        owner_member = _make_member(project.id, owner_id, owner_id, ProjectRole.OWNER)
        project_repo = FakeProjectRepo(project)
        member_repo = FakeMemberRepo(owner_member)
        user = SimpleNamespace(id=owner_id)
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await add_project_member(
                project.id,
                ProjectMemberCreate(member_user_id="new-member", role=ProjectRole.OWNER),
                user,
                project_repo,
                member_repo,
                user_repo,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_project_owner_member_cannot_be_demoted(self):
        from app.api.projects import update_project_member

        owner_id = "owner"
        project = _make_project(owner_id)
        owner_member = _make_member(project.id, owner_id, owner_id, ProjectRole.OWNER)
        project_repo = FakeProjectRepo(project)
        member_repo = FakeMemberRepo(owner_member)
        user = SimpleNamespace(id=owner_id)

        with pytest.raises(HTTPException) as exc_info:
            await update_project_member(
                project.id,
                owner_member.id,
                ProjectMemberUpdate(role=ProjectRole.MEMBER),
                user,
                project_repo,
                member_repo,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_project_owner_member_cannot_be_removed(self):
        from app.api.projects import delete_project_member

        owner_id = "owner"
        project = _make_project(owner_id)
        owner_member = _make_member(project.id, owner_id, owner_id, ProjectRole.OWNER)
        project_repo = FakeProjectRepo(project)
        member_repo = FakeMemberRepo(owner_member)
        user = SimpleNamespace(id=owner_id)

        with pytest.raises(HTTPException) as exc_info:
            await delete_project_member(
                project.id,
                owner_member.id,
                user,
                project_repo,
                member_repo,
            )

        assert exc_info.value.status_code == 400


# ===========================================================================
# Phase 5: invite_from_parent endpoint
# ===========================================================================


class TestInviteFromParent:
    """Test the invite_from_parent endpoint logic."""

    def _setup(self):
        """Create parent + child projects with members."""
        parent_owner = "parent-owner"
        child_owner = "child-owner"
        parent_member_id = "parent-member-1"

        parent = _make_project(parent_owner)
        child = _make_project(child_owner, parent_project_id=parent.id)

        parent_member = _make_member(parent.id, parent_owner, parent_member_id)
        _make_member(child.id, child_owner, child_owner, ProjectRole.OWNER)

        project_repo = FakeProjectRepo(parent, child)
        member_repo = FakeMemberRepo(parent_member)

        return SimpleNamespace(
            parent=parent,
            child=child,
            parent_owner=parent_owner,
            child_owner=child_owner,
            parent_member_id=parent_member_id,
            project_repo=project_repo,
            member_repo=member_repo,
        )

    @pytest.mark.asyncio
    async def test_successful_invite(self):
        """Parent member can be invited to child project."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id=ctx.parent_member_id,
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        result = await invite_from_parent(
            project_id=ctx.child.id,
            body=body,
            user=user,
            repo=ctx.project_repo,
            member_repo=ctx.member_repo,
            user_repo=user_repo,
        )
        assert result.member_user_id == ctx.parent_member_id
        assert result.role == ProjectRole.MEMBER

    @pytest.mark.asyncio
    async def test_invite_parent_owner(self):
        """Parent owner can also be invited to child project."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id=ctx.parent_owner,
            role=ProjectRole.ADMIN,
        )
        user_repo = AsyncMock()

        result = await invite_from_parent(
            project_id=ctx.child.id,
            body=body,
            user=user,
            repo=ctx.project_repo,
            member_repo=ctx.member_repo,
            user_repo=user_repo,
        )
        assert result.member_user_id == ctx.parent_owner
        assert result.role == ProjectRole.ADMIN

    @pytest.mark.asyncio
    async def test_reject_non_parent_member(self):
        """User not in parent project cannot be invited."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id="random-stranger",
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=ctx.child.id,
                body=body,
                user=user,
                repo=ctx.project_repo,
                member_repo=ctx.member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_already_member(self):
        """Cannot invite someone who is already a direct member."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        # Add parent_member_id as already a child member
        existing = _make_member(ctx.child.id, ctx.child_owner, ctx.parent_member_id)
        ctx.member_repo._members.append(existing)

        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id=ctx.parent_member_id,
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=ctx.child.id,
                body=body,
                user=user,
                repo=ctx.project_repo,
                member_repo=ctx.member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_invite_child_owner(self):
        """Cannot invite the child project owner (they already have full access)."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        # Make child_owner also a parent member so the parent-member check passes
        parent_membership = _make_member(ctx.parent.id, ctx.parent_owner, ctx.child_owner)
        ctx.member_repo._members.append(parent_membership)

        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id=ctx.child_owner,
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=ctx.child.id,
                body=body,
                user=user,
                repo=ctx.project_repo,
                member_repo=ctx.member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_viewer_role(self):
        """VIEWER role cannot be used for direct membership."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        user = SimpleNamespace(id=ctx.child_owner)
        body = InviteParentMemberRequest(
            member_user_id=ctx.parent_member_id,
            role=ProjectRole.VIEWER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=ctx.child.id,
                body=body,
                user=user,
                repo=ctx.project_repo,
                member_repo=ctx.member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_no_parent_project(self):
        """Cannot use invite-from-parent on project without parent."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        # Project with no parent
        orphan = _make_project("orphan-owner")
        project_repo = FakeProjectRepo(orphan)
        member_repo = FakeMemberRepo()

        user = SimpleNamespace(id="orphan-owner")
        body = InviteParentMemberRequest(
            member_user_id="someone",
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=orphan.id,
                body=body,
                user=user,
                repo=project_repo,
                member_repo=member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_viewer_cannot_invite(self):
        """VIEWER (ancestor-only access) should not be able to invite members."""
        from app.api.projects import invite_from_parent
        from app.models.project_link import InviteParentMemberRequest

        ctx = self._setup()
        # ancestor_user has no direct membership on child → VIEWER
        ancestor_user = "ancestor-viewer"
        user = SimpleNamespace(id=ancestor_user)
        body = InviteParentMemberRequest(
            member_user_id=ctx.parent_member_id,
            role=ProjectRole.MEMBER,
        )
        user_repo = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await invite_from_parent(
                project_id=ctx.child.id,
                body=body,
                user=user,
                repo=ctx.project_repo,
                member_repo=ctx.member_repo,
                user_repo=user_repo,
            )
        assert exc_info.value.status_code == 403
