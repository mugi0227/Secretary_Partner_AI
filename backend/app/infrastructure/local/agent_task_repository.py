"""
SQLite implementation of AgentTask repository.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.models.agent_task import AgentTask, AgentTaskCreate, AgentTaskUpdate, AgentTaskPayload
from app.models.enums import AgentTaskStatus, ActionType
from app.infrastructure.local.database import AgentTaskORM, get_session_factory


class SqliteAgentTaskRepository(IAgentTaskRepository):
    """SQLite implementation of agent task repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: AgentTaskORM) -> AgentTask:
        """Convert ORM object to Pydantic model."""
        payload_dict = json.loads(orm.payload) if orm.payload else {}
        return AgentTask(
            id=UUID(orm.id),
            user_id=orm.user_id,
            trigger_time=orm.trigger_time,
            action_type=ActionType(orm.action_type),
            status=AgentTaskStatus(orm.status),
            payload=AgentTaskPayload(**payload_dict),
            retry_count=orm.retry_count,
            last_error=orm.last_error,
            executed_at=orm.executed_at,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(self, user_id: str, task: AgentTaskCreate) -> AgentTask:
        """Create a new agent task."""
        async with self._session_factory() as session:
            orm = AgentTaskORM(
                id=str(uuid4()),
                user_id=user_id,
                trigger_time=task.trigger_time,
                action_type=task.action_type.value,
                payload=task.payload.model_dump_json() if task.payload else None,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, task_id: UUID) -> Optional[AgentTask]:
        """Get an agent task by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM).where(
                    and_(AgentTaskORM.id == str(task_id), AgentTaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def list(
        self,
        user_id: str,
        status: Optional[AgentTaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTask]:
        """List agent tasks with optional filters."""
        async with self._session_factory() as session:
            query = select(AgentTaskORM).where(AgentTaskORM.user_id == user_id)

            if status:
                query = query.where(AgentTaskORM.status == status.value)

            query = query.order_by(AgentTaskORM.trigger_time.asc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def get_pending(
        self,
        user_id: str,
        before: datetime,
        limit: int = 10,
    ) -> list[AgentTask]:
        """Get pending agent tasks ready for execution."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM)
                .where(
                    and_(
                        AgentTaskORM.user_id == user_id,
                        AgentTaskORM.status == AgentTaskStatus.PENDING.value,
                        AgentTaskORM.trigger_time <= before,
                    )
                )
                .order_by(AgentTaskORM.trigger_time.asc())
                .limit(limit)
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def update(
        self, user_id: str, task_id: UUID, update: AgentTaskUpdate
    ) -> AgentTask:
        """Update an agent task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM).where(
                    and_(AgentTaskORM.id == str(task_id), AgentTaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"AgentTask {task_id} not found")

            if update.trigger_time:
                orm.trigger_time = update.trigger_time
            if update.status:
                orm.status = update.status.value
            if update.payload:
                orm.payload = update.payload.model_dump_json()

            orm.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def mark_completed(self, task_id: UUID) -> AgentTask:
        """Mark an agent task as completed."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM).where(AgentTaskORM.id == str(task_id))
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"AgentTask {task_id} not found")

            orm.status = AgentTaskStatus.COMPLETED.value
            orm.executed_at = datetime.utcnow()
            orm.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def mark_failed(self, task_id: UUID, error: str) -> AgentTask:
        """Mark an agent task as failed."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM).where(AgentTaskORM.id == str(task_id))
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"AgentTask {task_id} not found")

            orm.retry_count += 1
            orm.last_error = error
            if orm.retry_count >= 3:
                orm.status = AgentTaskStatus.FAILED.value
            orm.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def cancel(self, user_id: str, task_id: UUID) -> bool:
        """Cancel an agent task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskORM).where(
                    and_(
                        AgentTaskORM.id == str(task_id),
                        AgentTaskORM.user_id == user_id,
                        AgentTaskORM.status == AgentTaskStatus.PENDING.value,
                    )
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            orm.status = AgentTaskStatus.CANCELLED.value
            orm.updated_at = datetime.utcnow()
            await session.commit()
            return True
