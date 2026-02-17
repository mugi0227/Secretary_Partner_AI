"""
SQLite implementation of Project Link Request repository.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.exceptions import NotFoundError
from app.infrastructure.local.database import (
    ProjectLinkRequestORM,
    get_session_factory,
)
from app.interfaces.project_link_request_repository import (
    IProjectLinkRequestRepository,
)
from app.models.project_link import (
    ProjectLinkRequest,
    ProjectLinkRequestCreate,
    ProjectLinkRequestStatus,
)
from app.utils.datetime_utils import now_utc


class SqliteProjectLinkRequestRepository(IProjectLinkRequestRepository):
    """SQLite implementation of project link request repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: ProjectLinkRequestORM) -> ProjectLinkRequest:
        """Convert ORM object to Pydantic model."""
        return ProjectLinkRequest(
            id=UUID(orm.id),
            child_project_id=UUID(orm.child_project_id),
            parent_project_id=UUID(orm.parent_project_id),
            requested_by=orm.requested_by,
            status=ProjectLinkRequestStatus(orm.status),
            member_ids_to_add=orm.member_ids_to_add or [],
            parent_approved=orm.parent_approved or False,
            child_approved=orm.child_approved or False,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(
        self, request: ProjectLinkRequestCreate, requested_by: str
    ) -> ProjectLinkRequest:
        """Create a new project link request."""
        async with self._session_factory() as session:
            orm = ProjectLinkRequestORM(
                id=str(uuid4()),
                child_project_id=str(request.child_project_id),
                parent_project_id=str(request.parent_project_id),
                requested_by=requested_by,
                status=ProjectLinkRequestStatus.PENDING.value,
                member_ids_to_add=request.member_ids_to_add,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, request_id: UUID) -> Optional[ProjectLinkRequest]:
        """Get a project link request by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectLinkRequestORM).where(
                    ProjectLinkRequestORM.id == str(request_id)
                )
            )
            orm = result.scalars().first()
            return self._orm_to_model(orm) if orm else None

    async def list_by_parent(
        self, parent_project_id: UUID, status: Optional[str] = None
    ) -> list[ProjectLinkRequest]:
        """List project link requests by parent project ID."""
        async with self._session_factory() as session:
            query = select(ProjectLinkRequestORM).where(
                ProjectLinkRequestORM.parent_project_id
                == str(parent_project_id)
            )

            if status:
                query = query.where(ProjectLinkRequestORM.status == status)

            query = query.order_by(ProjectLinkRequestORM.created_at.desc())

            result = await session.execute(query)
            return [
                self._orm_to_model(orm) for orm in result.scalars().all()
            ]

    async def approve(self, request_id: UUID) -> ProjectLinkRequest:
        """Approve a project link request."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectLinkRequestORM).where(
                    ProjectLinkRequestORM.id == str(request_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(
                    f"Project link request {request_id} not found"
                )

            orm.status = ProjectLinkRequestStatus.APPROVED.value
            orm.updated_at = now_utc()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def approve_side(
        self, request_id: UUID, side: str
    ) -> ProjectLinkRequest:
        """Approve one side (parent or child) of a link request."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectLinkRequestORM).where(
                    ProjectLinkRequestORM.id == str(request_id)
                )
            )
            orm = result.scalar_one_or_none()
            if not orm:
                raise NotFoundError(
                    f"Project link request {request_id} not found"
                )

            if side == "parent":
                orm.parent_approved = True
            elif side == "child":
                orm.child_approved = True

            if orm.parent_approved and orm.child_approved:
                orm.status = ProjectLinkRequestStatus.APPROVED.value

            orm.updated_at = now_utc()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def list_by_child(
        self, child_project_id: UUID, status: Optional[str] = None
    ) -> list[ProjectLinkRequest]:
        """List project link requests by child project ID."""
        async with self._session_factory() as session:
            query = select(ProjectLinkRequestORM).where(
                ProjectLinkRequestORM.child_project_id
                == str(child_project_id)
            )
            if status:
                query = query.where(ProjectLinkRequestORM.status == status)
            query = query.order_by(ProjectLinkRequestORM.created_at.desc())
            result = await session.execute(query)
            return [
                self._orm_to_model(orm) for orm in result.scalars().all()
            ]

    async def reject(self, request_id: UUID) -> ProjectLinkRequest:
        """Reject a project link request."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ProjectLinkRequestORM).where(
                    ProjectLinkRequestORM.id == str(request_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(
                    f"Project link request {request_id} not found"
                )

            orm.status = ProjectLinkRequestStatus.REJECTED.value
            orm.updated_at = now_utc()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)
