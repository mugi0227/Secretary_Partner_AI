"""
SQLite implementation of meeting session repository.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, select

from app.infrastructure.local.database import MeetingSessionORM, get_session_factory
from app.interfaces.meeting_session_repository import IMeetingSessionRepository
from app.models.enums import MeetingSessionStatus
from app.models.meeting_session import (
    MeetingSession,
    MeetingSessionCreate,
    MeetingSessionUpdate,
)
from app.utils.datetime_utils import now_utc


class SqliteMeetingSessionRepository(IMeetingSessionRepository):
    """SQLite implementation of meeting session repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: MeetingSessionORM) -> MeetingSession:
        """Convert ORM object to Pydantic model."""
        return MeetingSession(
            id=UUID(orm.id),
            user_id=orm.user_id,
            task_id=UUID(orm.task_id),
            status=MeetingSessionStatus(orm.status),
            current_agenda_index=orm.current_agenda_index,
            transcript=orm.transcript,
            summary=orm.summary,
            started_at=orm.started_at,
            ended_at=orm.ended_at,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(
        self,
        user_id: str,
        data: MeetingSessionCreate,
    ) -> MeetingSession:
        """Create a new meeting session."""
        async with self._session_factory() as session:
            orm = MeetingSessionORM(
                id=str(uuid4()),
                user_id=user_id,
                task_id=str(data.task_id),
                status=MeetingSessionStatus.PREPARATION.value,
                current_agenda_index=None,
                transcript=None,
                summary=None,
                started_at=None,
                ended_at=None,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(
        self,
        user_id: str,
        session_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get a session by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    and_(
                        MeetingSessionORM.id == str(session_id),
                        MeetingSessionORM.user_id == user_id,
                    )
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_by_task(
        self,
        user_id: str,
        task_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get the active session for a task (not COMPLETED)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .where(
                    and_(
                        MeetingSessionORM.task_id == str(task_id),
                        MeetingSessionORM.user_id == user_id,
                        MeetingSessionORM.status != MeetingSessionStatus.COMPLETED.value,
                    )
                )
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_latest_by_task(
        self,
        user_id: str,
        task_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get the most recent session for a task (any status)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .where(
                    and_(
                        MeetingSessionORM.task_id == str(task_id),
                        MeetingSessionORM.user_id == user_id,
                    )
                )
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def update(
        self,
        user_id: str,
        session_id: UUID,
        data: MeetingSessionUpdate,
    ) -> Optional[MeetingSession]:
        """Update a session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    and_(
                        MeetingSessionORM.id == str(session_id),
                        MeetingSessionORM.user_id == user_id,
                    )
                )
            )
            orm = result.scalar_one_or_none()
            if not orm:
                return None

            update_fields = data.model_dump(exclude_unset=True)
            for field, value in update_fields.items():
                if field == "status" and value is not None:
                    setattr(orm, field, value.value)
                elif value is not None:
                    setattr(orm, field, value)

            orm.updated_at = now_utc()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete(
        self,
        user_id: str,
        session_id: UUID,
    ) -> bool:
        """Delete a session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    and_(
                        MeetingSessionORM.id == str(session_id),
                        MeetingSessionORM.user_id == user_id,
                    )
                )
            )
            orm = result.scalar_one_or_none()
            if not orm:
                return False
            await session.delete(orm)
            await session.commit()
            return True

    async def list_by_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MeetingSession]:
        """List sessions for a user, ordered by created_at desc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .where(MeetingSessionORM.user_id == user_id)
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(limit)
                .offset(offset)
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def list_by_recurring_meeting(
        self,
        user_id: str,
        recurring_meeting_id: UUID,
        limit: int = 50,
    ) -> list[MeetingSession]:
        """List COMPLETED sessions for tasks belonging to a recurring meeting."""
        from app.infrastructure.local.database import TaskORM

        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .join(TaskORM, TaskORM.id == MeetingSessionORM.task_id)
                .where(
                    and_(
                        MeetingSessionORM.user_id == user_id,
                        TaskORM.recurring_meeting_id == str(recurring_meeting_id),
                        MeetingSessionORM.status == MeetingSessionStatus.COMPLETED.value,
                    )
                )
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(limit)
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    # ---- Project-aware methods (no user_id filter) ----

    async def get_by_id(
        self,
        session_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get a session by ID without user_id filter."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    MeetingSessionORM.id == str(session_id),
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_active_by_task_id(
        self,
        task_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get the active session (not COMPLETED) for a task without user_id filter."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .where(
                    and_(
                        MeetingSessionORM.task_id == str(task_id),
                        MeetingSessionORM.status != MeetingSessionStatus.COMPLETED.value,
                    )
                )
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_latest_by_task_id(
        self,
        task_id: UUID,
    ) -> Optional[MeetingSession]:
        """Get the most recent session for a task without user_id filter."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .where(MeetingSessionORM.task_id == str(task_id))
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def update_by_id(
        self,
        session_id: UUID,
        data: MeetingSessionUpdate,
    ) -> Optional[MeetingSession]:
        """Update a session without user_id filter."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    MeetingSessionORM.id == str(session_id),
                )
            )
            orm = result.scalar_one_or_none()
            if not orm:
                return None

            update_fields = data.model_dump(exclude_unset=True)
            for field, value in update_fields.items():
                if field == "status" and value is not None:
                    setattr(orm, field, value.value)
                elif value is not None:
                    setattr(orm, field, value)

            orm.updated_at = now_utc()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete_by_id(
        self,
        session_id: UUID,
    ) -> bool:
        """Delete a session without user_id filter."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM).where(
                    MeetingSessionORM.id == str(session_id),
                )
            )
            orm = result.scalar_one_or_none()
            if not orm:
                return False
            await session.delete(orm)
            await session.commit()
            return True

    async def list_completed_by_recurring_meeting_id(
        self,
        recurring_meeting_id: UUID,
        limit: int = 50,
    ) -> list[MeetingSession]:
        """List COMPLETED sessions for a recurring meeting without user_id filter."""
        from app.infrastructure.local.database import TaskORM

        async with self._session_factory() as session:
            result = await session.execute(
                select(MeetingSessionORM)
                .join(TaskORM, TaskORM.id == MeetingSessionORM.task_id)
                .where(
                    and_(
                        TaskORM.recurring_meeting_id == str(recurring_meeting_id),
                        MeetingSessionORM.status == MeetingSessionStatus.COMPLETED.value,
                    )
                )
                .order_by(desc(MeetingSessionORM.created_at))
                .limit(limit)
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]
