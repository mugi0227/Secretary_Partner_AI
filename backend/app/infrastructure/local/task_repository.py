"""
SQLite implementation of Task repository.
"""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.interfaces.task_repository import ITaskRepository
from app.models.task import Task, TaskCreate, TaskUpdate, SimilarTask
from app.models.enums import TaskStatus
from app.infrastructure.local.database import TaskORM, get_session_factory


class SqliteTaskRepository(ITaskRepository):
    """SQLite implementation of task repository."""

    def __init__(self, session_factory=None):
        """
        Initialize repository.

        Args:
            session_factory: Optional session factory (for testing)
        """
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: TaskORM) -> Task:
        """Convert ORM object to Pydantic model."""
        return Task(
            id=UUID(orm.id),
            user_id=orm.user_id,
            project_id=UUID(orm.project_id) if orm.project_id else None,
            title=orm.title,
            description=orm.description,
            status=TaskStatus(orm.status),
            importance=orm.importance,
            urgency=orm.urgency,
            energy_level=orm.energy_level,
            estimated_minutes=orm.estimated_minutes,
            due_date=orm.due_date,
            parent_id=UUID(orm.parent_id) if orm.parent_id else None,
            source_capture_id=UUID(orm.source_capture_id) if orm.source_capture_id else None,
            created_by=orm.created_by,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(self, user_id: str, task: TaskCreate) -> Task:
        """Create a new task."""
        async with self._session_factory() as session:
            orm = TaskORM(
                id=str(uuid4()),
                user_id=user_id,
                project_id=str(task.project_id) if task.project_id else None,
                title=task.title,
                description=task.description,
                importance=task.importance.value,
                urgency=task.urgency.value,
                energy_level=task.energy_level.value,
                estimated_minutes=task.estimated_minutes,
                due_date=task.due_date,
                parent_id=str(task.parent_id) if task.parent_id else None,
                source_capture_id=str(task.source_capture_id) if task.source_capture_id else None,
                created_by=task.created_by.value,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, task_id: UUID) -> Optional[Task]:
        """Get a task by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(
                    and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def list(
        self,
        user_id: str,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
        parent_id: Optional[UUID] = None,
        include_done: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List tasks with optional filters."""
        async with self._session_factory() as session:
            query = select(TaskORM).where(TaskORM.user_id == user_id)

            if project_id is not None:
                query = query.where(TaskORM.project_id == str(project_id))

            if status:
                query = query.where(TaskORM.status == status)
            elif not include_done:
                query = query.where(TaskORM.status != TaskStatus.DONE.value)

            if parent_id is not None:
                query = query.where(TaskORM.parent_id == str(parent_id))

            query = query.order_by(TaskORM.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def update(self, user_id: str, task_id: UUID, update: TaskUpdate) -> Task:
        """Update an existing task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(
                    and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"Task {task_id} not found")

            update_data = update.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if value is not None:
                    if field in ("project_id", "parent_id"):
                        value = str(value) if value else None
                    elif hasattr(value, "value"):  # Enum
                        value = value.value
                    setattr(orm, field, value)

            orm.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete(self, user_id: str, task_id: UUID) -> bool:
        """Delete a task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(
                    and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            await session.delete(orm)
            await session.commit()
            return True

    async def find_similar(
        self,
        user_id: str,
        title: str,
        project_id: UUID | None = None,
        threshold: float = 0.8,
        limit: int = 5,
    ) -> list[SimilarTask]:
        """Find similar tasks using simple string matching within the same project."""
        async with self._session_factory() as session:
            # Filter by user and project (None = Inbox)
            conditions = [TaskORM.user_id == user_id]
            if project_id is not None:
                conditions.append(TaskORM.project_id == str(project_id))
            else:
                # Search in Inbox (tasks without project)
                conditions.append(TaskORM.project_id.is_(None))

            result = await session.execute(
                select(TaskORM).where(and_(*conditions))
            )
            tasks = result.scalars().all()

            similar = []
            for orm in tasks:
                score = SequenceMatcher(None, title.lower(), orm.title.lower()).ratio()
                if score >= threshold:
                    similar.append(SimilarTask(
                        task=self._orm_to_model(orm),
                        similarity_score=score,
                    ))

            similar.sort(key=lambda x: x.similarity_score, reverse=True)
            return similar[:limit]

    async def get_by_capture_id(self, user_id: str, capture_id: UUID) -> list[Task]:
        """Get tasks created from a specific capture."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(
                    and_(
                        TaskORM.user_id == user_id,
                        TaskORM.source_capture_id == str(capture_id),
                    )
                )
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def get_subtasks(self, user_id: str, parent_id: UUID) -> list[Task]:
        """Get all subtasks of a parent task."""
        return await self.list(user_id, parent_id=parent_id, include_done=True)

    async def count(
        self,
        user_id: str,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count tasks matching filters."""
        async with self._session_factory() as session:
            query = select(func.count(TaskORM.id)).where(TaskORM.user_id == user_id)

            if project_id is not None:
                query = query.where(TaskORM.project_id == str(project_id))

            if status:
                query = query.where(TaskORM.status == status)

            result = await session.execute(query)
            return result.scalar() or 0
