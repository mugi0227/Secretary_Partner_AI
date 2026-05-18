"""
SQLite implementation of Task repository.
"""

from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy import delete as sa_delete

from app.core.exceptions import NotFoundError
from app.infrastructure.local.database import TaskORM, get_session_factory
from app.interfaces.task_repository import ITaskRepository
from app.models.enums import TaskStatus
from app.models.task import SimilarTask, Task, TaskCreate, TaskUpdate
from app.services.progress_calculator import summarize_progress
from app.utils.datetime_utils import ensure_utc, now_utc


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
            phase_id=UUID(orm.phase_id) if orm.phase_id else None,
            title=orm.title,
            description=orm.description,
            purpose=orm.purpose if hasattr(orm, "purpose") else None,
            status=TaskStatus(orm.status),
            importance=orm.importance,
            urgency=orm.urgency,
            energy_level=orm.energy_level,
            estimated_minutes=orm.estimated_minutes,
            due_date=ensure_utc(orm.due_date),
            start_not_before=ensure_utc(orm.start_not_before),
            pinned_date=ensure_utc(orm.pinned_date) if hasattr(orm, "pinned_date") else None,
            parent_id=UUID(orm.parent_id) if orm.parent_id else None,
            order_in_parent=orm.order_in_parent,
            dependency_ids=[UUID(dep_id) for dep_id in (orm.dependency_ids or [])],
            same_day_allowed=(
                bool(orm.same_day_allowed)
                if hasattr(orm, "same_day_allowed") and orm.same_day_allowed is not None
                else True
            ),
            min_gap_days=(
                orm.min_gap_days
                if hasattr(orm, "min_gap_days") and orm.min_gap_days is not None
                else 0
            ),
            progress=orm.progress if hasattr(orm, "progress") and orm.progress is not None else 0,
            source_capture_id=UUID(orm.source_capture_id) if orm.source_capture_id else None,
            created_by=orm.created_by,
            created_at=ensure_utc(orm.created_at),
            updated_at=ensure_utc(orm.updated_at),
            start_time=ensure_utc(orm.start_time),
            end_time=ensure_utc(orm.end_time),
            is_fixed_time=bool(orm.is_fixed_time),
            is_all_day=(
                bool(orm.is_all_day)
                if hasattr(orm, "is_all_day") and orm.is_all_day is not None
                else False
            ),
            location=orm.location,
            attendees=orm.attendees or [],
            meeting_notes=orm.meeting_notes,
            recurring_meeting_id=UUID(orm.recurring_meeting_id) if orm.recurring_meeting_id else None,
            recurring_task_id=(
                UUID(orm.recurring_task_id)
                if hasattr(orm, "recurring_task_id") and orm.recurring_task_id
                else None
            ),
            milestone_id=UUID(orm.milestone_id) if orm.milestone_id else None,
            touchpoint_count=orm.touchpoint_count if hasattr(orm, "touchpoint_count") else None,
            touchpoint_minutes=orm.touchpoint_minutes if hasattr(orm, "touchpoint_minutes") else None,
            touchpoint_gap_days=(
                orm.touchpoint_gap_days
                if hasattr(orm, "touchpoint_gap_days") and orm.touchpoint_gap_days is not None
                else 0
            ),
            touchpoint_steps=orm.touchpoint_steps or [],
            completion_note=orm.completion_note if hasattr(orm, "completion_note") else None,
            completed_at=ensure_utc(orm.completed_at) if hasattr(orm, "completed_at") else None,
            completed_by=orm.completed_by if hasattr(orm, "completed_by") else None,
            auto_completed_by_parent_id=(
                UUID(orm.auto_completed_by_parent_id)
                if hasattr(orm, "auto_completed_by_parent_id") and orm.auto_completed_by_parent_id
                else None
            ),
            guide=orm.guide if hasattr(orm, "guide") else None,
            requires_all_completion=(
                bool(orm.requires_all_completion)
                if hasattr(orm, "requires_all_completion") and orm.requires_all_completion is not None
                else False
            ),
        )

    def _children_scope_clause(self, parent_id: str, project_id: str | None, user_id: str):
        """Build child query scope for personal/project task trees."""
        if project_id:
            return and_(TaskORM.parent_id == parent_id, TaskORM.project_id == project_id)
        return and_(
            TaskORM.parent_id == parent_id,
            TaskORM.user_id == user_id,
            TaskORM.project_id.is_(None),
        )

    async def _load_descendants(self, session, root: TaskORM) -> list[TaskORM]:
        """Load all descendants for a task within the same task scope."""
        descendants: list[TaskORM] = []
        visited: set[str] = set()
        frontier = [root.id]

        while frontier:
            query = select(TaskORM).where(TaskORM.parent_id.in_(frontier))
            if root.project_id:
                query = query.where(TaskORM.project_id == root.project_id)
            else:
                query = query.where(
                    and_(
                        TaskORM.user_id == root.user_id,
                        TaskORM.project_id.is_(None),
                    )
                )

            result = await session.execute(query)
            children = [child for child in result.scalars().all() if child.id not in visited]
            if not children:
                break

            descendants.extend(children)
            for child in children:
                visited.add(child.id)
            frontier = [child.id for child in children]

        return descendants

    async def _recalculate_parent_progress(self, session, parent_id: str) -> str | None:
        """Recalculate one parent's progress from direct children."""
        parent_result = await session.execute(select(TaskORM).where(TaskORM.id == parent_id))
        parent = parent_result.scalar_one_or_none()
        if not parent:
            return None

        child_query = select(TaskORM).where(
            self._children_scope_clause(parent.id, parent.project_id, parent.user_id)
        )
        children = (await session.execute(child_query)).scalars().all()
        if children:
            summary = summarize_progress(children)
            parent.progress = summary.progress
            parent.updated_at = now_utc()

        return parent.parent_id

    async def _recalculate_ancestor_progresses(
        self,
        session,
        start_parent_ids: list[str],
    ) -> None:
        """Recalculate progress for each parent chain from child to root."""
        for start_parent_id in start_parent_ids:
            current_parent_id = start_parent_id
            visited: set[str] = set()
            while current_parent_id and current_parent_id not in visited:
                visited.add(current_parent_id)
                current_parent_id = await self._recalculate_parent_progress(session, current_parent_id)

    def _set_done_state(
        self,
        orm: TaskORM,
        user_id: str,
        updated_at: datetime,
        auto_completed_by_parent_id: str | None = None,
    ) -> None:
        """Apply DONE state with completion metadata."""
        orm.status = TaskStatus.DONE.value
        orm.progress = 100
        orm.updated_at = updated_at
        if orm.completed_at is None:
            orm.completed_at = updated_at
        orm.completed_by = user_id
        if auto_completed_by_parent_id is not None:
            orm.auto_completed_by_parent_id = auto_completed_by_parent_id

    def _set_reopened_state(self, orm: TaskORM, updated_at: datetime) -> None:
        """Apply reopened state for tasks auto-completed by a parent."""
        orm.status = TaskStatus.TODO.value
        orm.progress = 0
        orm.updated_at = updated_at
        orm.completed_at = None
        orm.completed_by = None
        orm.auto_completed_by_parent_id = None

    async def create(self, user_id: str, task: TaskCreate) -> Task:
        """Create a new task."""
        async with self._session_factory() as session:
            parent_id_str = str(task.parent_id) if task.parent_id else None
            status_value = TaskStatus.TODO.value
            progress_value = task.progress
            completed_at = None
            completed_by = None
            auto_completed_by_parent_id = None

            if parent_id_str:
                parent_result = await session.execute(select(TaskORM).where(TaskORM.id == parent_id_str))
                parent = parent_result.scalar_one_or_none()
                if parent and parent.status == TaskStatus.DONE.value:
                    status_value = TaskStatus.DONE.value
                    progress_value = 100
                    completed_at = now_utc()
                    completed_by = user_id
                    auto_completed_by_parent_id = parent.auto_completed_by_parent_id or parent.id

            orm = TaskORM(
                id=str(uuid4()),
                user_id=user_id,
                project_id=str(task.project_id) if task.project_id else None,
                phase_id=str(task.phase_id) if task.phase_id else None,
                title=task.title,
                description=task.description,
                purpose=task.purpose,
                status=status_value,
                importance=task.importance.value,
                urgency=task.urgency.value,
                energy_level=task.energy_level.value,
                estimated_minutes=task.estimated_minutes,
                due_date=task.due_date,
                start_not_before=task.start_not_before,
                pinned_date=task.pinned_date,
                parent_id=parent_id_str,
                order_in_parent=task.order_in_parent,
                dependency_ids=[str(dep_id) for dep_id in task.dependency_ids],
                same_day_allowed=task.same_day_allowed,
                min_gap_days=task.min_gap_days,
                progress=progress_value,
                source_capture_id=str(task.source_capture_id) if task.source_capture_id else None,
                created_by=task.created_by.value,
                start_time=task.start_time,
                end_time=task.end_time,
                is_fixed_time=task.is_fixed_time,
                is_all_day=task.is_all_day,
                location=task.location,
                attendees=task.attendees,
                meeting_notes=task.meeting_notes,
                recurring_meeting_id=(
                    str(task.recurring_meeting_id)
                    if hasattr(task, "recurring_meeting_id") and task.recurring_meeting_id
                    else None
                ),
                recurring_task_id=(
                    str(task.recurring_task_id)
                    if hasattr(task, "recurring_task_id") and task.recurring_task_id
                    else None
                ),
                milestone_id=str(task.milestone_id) if task.milestone_id else None,
                touchpoint_count=task.touchpoint_count,
                touchpoint_minutes=task.touchpoint_minutes,
                touchpoint_gap_days=task.touchpoint_gap_days,
                touchpoint_steps=[step.model_dump(mode="json") for step in task.touchpoint_steps],
                completion_note=task.completion_note if hasattr(task, "completion_note") else None,
                completed_at=completed_at,
                completed_by=completed_by,
                auto_completed_by_parent_id=auto_completed_by_parent_id,
                guide=task.guide if hasattr(task, "guide") else None,
                requires_all_completion=task.requires_all_completion,
            )
            session.add(orm)

            if parent_id_str:
                await self._recalculate_ancestor_progresses(session, [parent_id_str])

            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, task_id: UUID, project_id: Optional[UUID] = None) -> Optional[Task]:
        """Get a task by ID. If project_id is given, uses project-based access (no user_id check)."""
        async with self._session_factory() as session:
            if project_id:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.project_id == str(project_id))
                    )
                )
            else:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                    )
                )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def get_by_id(self, user_id: str, task_id: UUID) -> Optional[Task]:
        """Get a task by ID. First tries user_id match, then any task by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id))
            )
            orm = result.scalar_one_or_none()
            if orm:
                return self._orm_to_model(orm)

            result = await session.execute(select(TaskORM).where(TaskORM.id == str(task_id)))
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
        """List tasks. If project_id specified, uses project-based access (no user_id filter)."""
        async with self._session_factory() as session:
            if project_id is not None:
                query = select(TaskORM).where(TaskORM.project_id == str(project_id))
            else:
                query = select(TaskORM).where(TaskORM.user_id == user_id)

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

    async def update(
        self,
        user_id: str,
        task_id: UUID,
        update: TaskUpdate,
        project_id: Optional[UUID] = None,
    ) -> Task:
        """Update an existing task. If project_id given, uses project-based access."""
        async with self._session_factory() as session:
            if project_id:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.project_id == str(project_id))
                    )
                )
            else:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                    )
                )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"Task {task_id} not found")

            original_status = orm.status
            old_parent_id = orm.parent_id
            update_data = update.model_dump(exclude_unset=True)
            normalized_data: dict[str, object] = {}
            nullable_fields = {
                "description",
                "purpose",
                "project_id",
                "phase_id",
                "estimated_minutes",
                "due_date",
                "start_not_before",
                "pinned_date",
                "parent_id",
                "source_capture_id",
                "start_time",
                "end_time",
                "location",
                "meeting_notes",
                "recurring_meeting_id",
                "recurring_task_id",
                "milestone_id",
                "touchpoint_count",
                "touchpoint_minutes",
                "completion_note",
                "guide",
            }
            for field, value in update_data.items():
                if value is None:
                    if field in nullable_fields:
                        normalized_data[field] = None
                    continue
                if field in {"project_id", "parent_id", "phase_id", "milestone_id"}:
                    normalized_data[field] = str(value)
                elif field == "dependency_ids":
                    normalized_data[field] = [str(dep_id) for dep_id in value]
                elif field == "touchpoint_steps":
                    normalized_data[field] = [
                        step.model_dump(mode="json") if hasattr(step, "model_dump") else step
                        for step in value
                    ]
                elif hasattr(value, "value"):
                    normalized_data[field] = value.value
                else:
                    normalized_data[field] = value

            forced_by_done_parent = False
            if orm.parent_id:
                parent_result = await session.execute(select(TaskORM).where(TaskORM.id == orm.parent_id))
                parent_task = parent_result.scalar_one_or_none()
                if parent_task and parent_task.status == TaskStatus.DONE.value:
                    requested_status = normalized_data.get("status")
                    if requested_status != TaskStatus.DONE.value:
                        normalized_data["status"] = TaskStatus.DONE.value
                        forced_by_done_parent = True
                    normalized_data["progress"] = 100

            for field, value in normalized_data.items():
                setattr(orm, field, value)

            status_value = orm.status
            status_changed = status_value != original_status
            became_done = status_changed and status_value == TaskStatus.DONE.value
            reopened_from_done = status_changed and original_status == TaskStatus.DONE.value
            updated_at = now_utc()
            orm.updated_at = updated_at

            if status_changed and not forced_by_done_parent:
                orm.auto_completed_by_parent_id = None

            if status_value == TaskStatus.DONE.value:
                orm.progress = 100
                if orm.completed_at is None:
                    orm.completed_at = updated_at
                orm.completed_by = user_id
            elif reopened_from_done:
                orm.progress = 0
                orm.completed_at = None
                orm.completed_by = None
            elif status_changed:
                orm.completed_at = None
                orm.completed_by = None

            changed_descendant_parent_ids: list[str] = []
            if became_done:
                descendants = await self._load_descendants(session, orm)
                for descendant in descendants:
                    if descendant.status == TaskStatus.DONE.value:
                        continue
                    self._set_done_state(
                        descendant,
                        user_id,
                        updated_at,
                        auto_completed_by_parent_id=orm.id,
                    )
                    if descendant.parent_id:
                        changed_descendant_parent_ids.append(descendant.parent_id)

            if reopened_from_done:
                descendants = await self._load_descendants(session, orm)
                for descendant in descendants:
                    if descendant.auto_completed_by_parent_id != orm.id:
                        continue
                    self._set_reopened_state(descendant, updated_at)
                    if descendant.parent_id:
                        changed_descendant_parent_ids.append(descendant.parent_id)

            parents_to_recalculate: list[str] = []
            if old_parent_id:
                parents_to_recalculate.append(old_parent_id)
            if orm.parent_id:
                parents_to_recalculate.append(orm.parent_id)
            if any(field in normalized_data for field in ("status", "progress", "estimated_minutes")):
                parents_to_recalculate.append(orm.id)
            parents_to_recalculate.extend(changed_descendant_parent_ids)

            if parents_to_recalculate:
                await self._recalculate_ancestor_progresses(session, parents_to_recalculate)

            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete(self, user_id: str, task_id: UUID, project_id: Optional[UUID] = None) -> bool:
        """Delete a task. If project_id given, uses project-based access."""
        async with self._session_factory() as session:
            if project_id:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.project_id == str(project_id))
                    )
                )
            else:
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                    )
                )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            parent_id = orm.parent_id
            await session.delete(orm)
            if parent_id:
                await self._recalculate_ancestor_progresses(session, [parent_id])
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
            if project_id is not None:
                conditions = [TaskORM.project_id == str(project_id)]
            else:
                conditions = [TaskORM.user_id == user_id, TaskORM.project_id.is_(None)]

            result = await session.execute(select(TaskORM).where(and_(*conditions)))
            tasks = result.scalars().all()

            similar = []
            for orm in tasks:
                score = SequenceMatcher(None, title.lower(), orm.title.lower()).ratio()
                if score >= threshold:
                    similar.append(
                        SimilarTask(
                            task=self._orm_to_model(orm),
                            similarity_score=score,
                        )
                    )

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

    async def get_subtasks(
        self,
        user_id: str,
        parent_id: UUID,
        project_id: Optional[UUID] = None,
    ) -> list[Task]:
        """Get all subtasks of a parent task."""
        return await self.list(
            user_id,
            project_id=project_id,
            parent_id=parent_id,
            include_done=True,
        )

    async def get_many(self, task_ids: list[UUID]) -> list[Task]:
        """Get multiple tasks by ID."""
        if not task_ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskORM).where(TaskORM.id.in_([str(tid) for tid in task_ids]))
            )
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def list_personal_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """List personal tasks (Inbox/Memo) - excluding project tasks."""
        async with self._session_factory() as session:
            query = select(TaskORM).where(
                and_(
                    TaskORM.user_id == user_id,
                    TaskORM.project_id.is_(None),
                )
            )

            if status:
                query = query.where(TaskORM.status == status)

            query = query.order_by(TaskORM.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def count(
        self,
        user_id: str,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count tasks matching filters."""
        async with self._session_factory() as session:
            if project_id is not None:
                query = select(func.count(TaskORM.id)).where(TaskORM.project_id == str(project_id))
            else:
                query = select(func.count(TaskORM.id)).where(TaskORM.user_id == user_id)

            if status:
                query = query.where(TaskORM.status == status)

            result = await session.execute(query)
            return result.scalar() or 0

    async def list_by_recurring_meeting(
        self,
        user_id: str,
        recurring_meeting_id: UUID,
        start_after: Optional[datetime] = None,
        end_before: Optional[datetime] = None,
    ) -> list["Task"]:
        """List tasks generated from a recurring meeting."""
        async with self._session_factory() as session:
            query = select(TaskORM).where(
                and_(
                    TaskORM.user_id == user_id,
                    TaskORM.recurring_meeting_id == str(recurring_meeting_id),
                )
            )

            if start_after:
                query = query.where(TaskORM.start_time >= start_after)
            if end_before:
                query = query.where(TaskORM.start_time < end_before)

            query = query.order_by(TaskORM.start_time.asc())

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def list_by_recurring_task(
        self,
        user_id: str,
        recurring_task_id: UUID,
        start_after: Optional[datetime] = None,
        end_before: Optional[datetime] = None,
    ) -> list["Task"]:
        """List tasks generated from a recurring task definition."""
        async with self._session_factory() as session:
            query = select(TaskORM).where(
                and_(
                    TaskORM.user_id == user_id,
                    TaskORM.recurring_task_id == str(recurring_task_id),
                )
            )

            if start_after:
                query = query.where(TaskORM.due_date >= start_after)
            if end_before:
                query = query.where(TaskORM.due_date < end_before)

            query = query.order_by(TaskORM.due_date.asc())

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def delete_by_recurring_task(
        self,
        user_id: str,
        recurring_task_id: UUID,
    ) -> int:
        """Delete all tasks generated from a recurring task definition."""
        async with self._session_factory() as session:
            stmt = sa_delete(TaskORM).where(
                and_(
                    TaskORM.user_id == user_id,
                    TaskORM.recurring_task_id == str(recurring_task_id),
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    async def list_completed_in_period(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
        project_id: Optional[UUID] = None,
    ) -> list[Task]:
        """
        List tasks completed within a specific period.

        Uses completed_at if available, falls back to updated_at for older data.

        Args:
            user_id: User ID
            period_start: Period start datetime (inclusive)
            period_end: Period end datetime (exclusive)
            project_id: Optional project ID filter

        Returns:
            List of completed tasks in the period
        """
        async with self._session_factory() as session:
            conditions = [
                TaskORM.user_id == user_id,
                TaskORM.status == TaskStatus.DONE.value,
            ]

            if project_id is not None:
                conditions.append(TaskORM.project_id == str(project_id))

            conditions.append(
                or_(
                    and_(
                        TaskORM.completed_at.isnot(None),
                        TaskORM.completed_at >= period_start,
                        TaskORM.completed_at < period_end,
                    ),
                    and_(
                        TaskORM.completed_at.is_(None),
                        TaskORM.updated_at >= period_start,
                        TaskORM.updated_at < period_end,
                    ),
                )
            )

            query = select(TaskORM).where(and_(*conditions))
            query = query.order_by(
                TaskORM.completed_at.desc().nullslast(),
                TaskORM.updated_at.desc(),
            )

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]
