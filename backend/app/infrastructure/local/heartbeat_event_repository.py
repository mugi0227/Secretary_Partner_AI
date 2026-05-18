from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select, update

from app.infrastructure.local.database import HeartbeatEventORM, get_session_factory
from app.interfaces.heartbeat_event_repository import IHeartbeatEventRepository
from app.models.heartbeat import HeartbeatEvent, HeartbeatEventCreate
from app.utils.datetime_utils import now_utc


class SqliteHeartbeatEventRepository(IHeartbeatEventRepository):
    def _orm_to_model(self, orm: HeartbeatEventORM) -> HeartbeatEvent:
        return HeartbeatEvent(
            id=UUID(orm.id),
            user_id=orm.user_id,
            task_id=UUID(orm.task_id) if orm.task_id else None,
            severity=orm.severity,
            risk_score=orm.risk_score,
            notification_id=UUID(orm.notification_id) if orm.notification_id else None,
            metadata=orm.metadata_json or {},
            is_read=bool(orm.is_read),
            read_at=orm.read_at,
            created_at=orm.created_at,
        )

    async def create(self, event: HeartbeatEventCreate) -> HeartbeatEvent:
        async with self._session_factory() as session:
            now = now_utc()
            orm = HeartbeatEventORM(
                id=str(uuid4()),
                user_id=event.user_id,
                task_id=str(event.task_id) if event.task_id else None,
                severity=event.severity.value,
                risk_score=event.risk_score,
                notification_id=str(event.notification_id) if event.notification_id else None,
                metadata_json=event.metadata,
                is_read=event.is_read,
                read_at=event.read_at,
                created_at=now,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    async def list_by_user_since(
        self,
        user_id: str,
        since: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[HeartbeatEvent]:
        async with self._session_factory() as session:
            query = select(HeartbeatEventORM).where(HeartbeatEventORM.user_id == user_id)
            if since:
                query = query.where(HeartbeatEventORM.created_at >= since)
            result = await session.execute(
                query.order_by(desc(HeartbeatEventORM.created_at)).limit(limit)
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def count_by_user_since(self, user_id: str, since: Optional[datetime] = None) -> int:
        async with self._session_factory() as session:
            query = select(func.count()).select_from(HeartbeatEventORM).where(
                HeartbeatEventORM.user_id == user_id
            )
            if since:
                query = query.where(HeartbeatEventORM.created_at >= since)
            result = await session.execute(query)
            return result.scalar() or 0

    async def get_latest_for_task(self, user_id: str, task_id: UUID) -> Optional[HeartbeatEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(HeartbeatEventORM)
                .where(
                    HeartbeatEventORM.user_id == user_id,
                    HeartbeatEventORM.task_id == str(task_id),
                )
                .order_by(desc(HeartbeatEventORM.created_at))
                .limit(1)
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def count_unread(self, user_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(HeartbeatEventORM)
                .where(
                    HeartbeatEventORM.user_id == user_id,
                    HeartbeatEventORM.is_read.is_(False),
                )
            )
            return result.scalar() or 0

    async def list_unread(self, user_id: str) -> list[HeartbeatEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(HeartbeatEventORM)
                .where(
                    HeartbeatEventORM.user_id == user_id,
                    HeartbeatEventORM.is_read.is_(False),
                )
                .order_by(desc(HeartbeatEventORM.created_at))
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def mark_all_read(self, user_id: str) -> int:
        async with self._session_factory() as session:
            now = now_utc()
            result = await session.execute(
                update(HeartbeatEventORM)
                .where(
                    HeartbeatEventORM.user_id == user_id,
                    HeartbeatEventORM.is_read.is_(False),
                )
                .values(is_read=True, read_at=now)
            )
            await session.commit()
            return result.rowcount
