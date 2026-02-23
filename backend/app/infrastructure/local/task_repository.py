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
from app.utils.datetime_utils import now_utc


class SqliteTaskRepository(ITaskRepository):
    """SQLite implementation of task repository."""

    def __init__(self, session_factory=None):
        """
        Initialize repository.

        Args:
            session_factory: Optional session factory (for testing)
        """
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _normalized_progress(status: str, progress: int | None) -> int:
        if status == TaskStatus.DONE.value:
            return 100
        value = progress if progress is not None else 0
        return max(0, min(value, 100))

    @staticmethod
    def _effective_weight(task: TaskORM) -> int:
        return task.estimated_minutes if task.estimated_minutes and task.estimated_minutes > 0 else 60

    @staticmethod
    def _set_done_state(task: TaskORM, user_id: str, timestamp: datetime) -> None:
        task.status = TaskStatus.DONE.value
        task.progress = 100
        if task.completed_at is None:
            task.completed_at = timestamp
        task.completed_by = user_id
        task.updated_at = timestamp

    @staticmethod
    def _set_reopened_state(task: TaskORM, timestamp: datetime, status: str = TaskStatus.TODO.value) -> None:
        task.status = status
        task.progress = 0
        task.completed_at = None
        task.completed_by = None
        task.updated_at = timestamp

    async def _load_descendants(
        self,
        session,
        user_id: str,
        project_id: str | None,
        root_ids: list[str],
    ) -> list[TaskORM]:
        """Load all descendants for the given root task IDs."""
        descendants: list[TaskORM] = []
        seen: set[str] = set()
        frontier = set(root_ids)

        while frontier:
            conditions = [TaskORM.parent_id.in_(list(frontier))]
            if project_id:
                conditions.append(TaskORM.project_id == project_id)
            else:
                conditions.append(TaskORM.user_id == user_id)
            result = await session.execute(select(TaskORM).where(and_(*conditions)))
            batch = [task for task in result.scalars().all() if task.id not in seen]
            if not batch:
                break

            descendants.extend(batch)
            seen.update(task.id for task in batch)
            frontier = {task.id for task in batch}

        return descendants

    async def _recalculate_parent_progress(
        self,
        session,
        parent: TaskORM,
        user_id: str,
    ) -> None:
        conditions = [TaskORM.parent_id == parent.id]
        if parent.project_id:
            conditions.append(TaskORM.project_id == parent.project_id)
        else:
            conditions.append(TaskORM.user_id == user_id)
        result = await session.execute(select(TaskORM).where(and_(*conditions)))
        children = result.scalars().all()
        if not children:
            return

        total_weight = 0
        weighted_progress = 0
        for child in children:
            weight = self._effective_weight(child)
            progress = self._normalized_progress(child.status, child.progress)
            total_weight += weight
            weighted_progress += progress * weight
        if total_weight <= 0:
            return

        if parent.status == TaskStatus.DONE.value:
            parent.progress = 100
        else:
            parent.progress = round(weighted_progress / total_weight)
        parent.updated_at = now_utc()

    async def _recalculate_ancestor_progresses(
        self,
        session,
        user_id: str,
        parent_id: str | None,
        project_id: str | None,
    ) -> None:
        """Recalculate progress from the immediate parent up to the root."""
        current_parent_id = parent_id
        seen: set[str] = set()
        while current_parent_id and current_parent_id not in seen:
            seen.add(current_parent_id)
            conditions = [TaskORM.id == current_parent_id]
            if project_id:
                conditions.append(TaskORM.project_id == project_id)
            else:
                conditions.append(TaskORM.user_id == user_id)
            result = await session.execute(select(TaskORM).where(and_(*conditions)))
            parent = result.scalar_one_or_none()
            if not parent:
                break
            await self._recalculate_parent_progress(session, parent, user_id)
            current_parent_id = parent.parent_id

    def _orm_to_model(self, orm: TaskORM) -> Task:
        """Convert ORM object to Pydantic model."""
        return Task(
            id=UUID(orm.id),
            user_id=orm.user_id,
            project_id=UUID(orm.project_id) if orm.project_id else None,
            phase_id=UUID(orm.phase_id) if orm.phase_id else None,
            title=orm.title,
            description=orm.description,
            purpose=orm.purpose if hasattr(orm, 'purpose') else None,
            status=TaskStatus(orm.status),
            importance=orm.importance,
            urgency=orm.urgency,
            energy_level=orm.energy_level,
            estimated_minutes=orm.estimated_minutes,
            due_date=orm.due_date,
            start_not_before=orm.start_not_before,
            parent_id=UUID(orm.parent_id) if orm.parent_id else None,
            order_in_parent=orm.order_in_parent,
            dependency_ids=[UUID(dep_id) for dep_id in (orm.dependency_ids or [])],
            same_day_allowed=(
                bool(orm.same_day_allowed)
                if hasattr(orm, 'same_day_allowed') and orm.same_day_allowed is not None
                else True
            ),
            min_gap_days=orm.min_gap_days if hasattr(orm, 'min_gap_days') and orm.min_gap_days is not None else 0,
            progress=orm.progress if hasattr(orm, 'progress') and orm.progress is not None else 0,
            source_capture_id=UUID(orm.source_capture_id) if orm.source_capture_id else None,
            created_by=orm.created_by,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            start_time=orm.start_time,
            end_time=orm.end_time,
            is_fixed_time=bool(orm.is_fixed_time),
            is_all_day=bool(orm.is_all_day) if hasattr(orm, 'is_all_day') and orm.is_all_day is not None else False,
            location=orm.location,
            attendees=orm.attendees or [],
            meeting_notes=orm.meeting_notes,
            recurring_meeting_id=UUID(orm.recurring_meeting_id) if orm.recurring_meeting_id else None,
            recurring_task_id=UUID(orm.recurring_task_id) if hasattr(orm, 'recurring_task_id') and orm.recurring_task_id else None,
            milestone_id=UUID(orm.milestone_id) if orm.milestone_id else None,
            touchpoint_count=orm.touchpoint_count if hasattr(orm, 'touchpoint_count') else None,
            touchpoint_minutes=orm.touchpoint_minutes if hasattr(orm, 'touchpoint_minutes') else None,
            touchpoint_gap_days=orm.touchpoint_gap_days if hasattr(orm, 'touchpoint_gap_days') and orm.touchpoint_gap_days is not None else 0,
            touchpoint_steps=orm.touchpoint_steps or [],
            completion_note=orm.completion_note if hasattr(orm, 'completion_note') else None,
            completed_at=orm.completed_at if hasattr(orm, 'completed_at') else None,
            completed_by=orm.completed_by if hasattr(orm, 'completed_by') else None,
            auto_completed_by_parent_id=(
                UUID(orm.auto_completed_by_parent_id)
                if hasattr(orm, "auto_completed_by_parent_id") and orm.auto_completed_by_parent_id
                else None
            ),
            guide=orm.guide if hasattr(orm, 'guide') else None,
            requires_all_completion=bool(orm.requires_all_completion) if hasattr(orm, 'requires_all_completion') and orm.requires_all_completion is not None else False,
        )

    async def create(self, user_id: str, task: TaskCreate) -> Task:
        """Create a new task."""
        async with self._session_factory() as session:
            parent: TaskORM | None = None
            orm = TaskORM(
                id=str(uuid4()),
                user_id=user_id,
                project_id=str(task.project_id) if task.project_id else None,
                phase_id=str(task.phase_id) if task.phase_id else None,
                title=task.title,
                description=task.description,
                purpose=task.purpose,
                importance=task.importance.value,
                urgency=task.urgency.value,
                energy_level=task.energy_level.value,
                estimated_minutes=task.estimated_minutes,
                due_date=task.due_date,
                start_not_before=task.start_not_before,
                parent_id=str(task.parent_id) if task.parent_id else None,
                order_in_parent=task.order_in_parent,
                dependency_ids=[str(dep_id) for dep_id in task.dependency_ids],
                same_day_allowed=task.same_day_allowed,
                min_gap_days=task.min_gap_days,
                progress=task.progress,
                source_capture_id=str(task.source_capture_id) if task.source_capture_id else None,
                created_by=task.created_by.value,
                start_time=task.start_time,
                end_time=task.end_time,
                is_fixed_time=task.is_fixed_time,
                is_all_day=task.is_all_day,
                location=task.location,
                attendees=task.attendees,
                meeting_notes=task.meeting_notes,
                recurring_task_id=str(task.recurring_task_id) if hasattr(task, 'recurring_task_id') and task.recurring_task_id else None,
                milestone_id=str(task.milestone_id) if task.milestone_id else None,
                touchpoint_count=task.touchpoint_count,
                touchpoint_minutes=task.touchpoint_minutes,
                touchpoint_gap_days=task.touchpoint_gap_days,
                touchpoint_steps=[step.model_dump(mode="json") for step in task.touchpoint_steps],
                completion_note=task.completion_note if hasattr(task, 'completion_note') else None,
                guide=task.guide if hasattr(task, 'guide') else None,
                requires_all_completion=task.requires_all_completion,
            )
            if orm.parent_id:
                parent_conditions = [TaskORM.id == orm.parent_id]
                if orm.project_id:
                    parent_conditions.append(TaskORM.project_id == orm.project_id)
                else:
                    parent_conditions.append(TaskORM.user_id == user_id)
                parent_result = await session.execute(select(TaskORM).where(and_(*parent_conditions)))
                parent = parent_result.scalar_one_or_none()
                if parent and parent.status == TaskStatus.DONE.value:
                    timestamp = now_utc()
                    self._set_done_state(orm, user_id, timestamp)
                    orm.auto_completed_by_parent_id = parent.id

            session.add(orm)
            await session.flush()
            if orm.parent_id:
                await self._recalculate_ancestor_progresses(
                    session=session,
                    user_id=user_id,
                    parent_id=orm.parent_id,
                    project_id=orm.project_id,
                )
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, task_id: UUID, project_id: Optional[UUID] = None) -> Optional[Task]:
        """Get a task by ID. If project_id is given, uses project-based access (no user_id check)."""
        async with self._session_factory() as session:
            if project_id:
                # Project-based access: filter by project_id only
                result = await session.execute(
                    select(TaskORM).where(
                        and_(TaskORM.id == str(task_id), TaskORM.project_id == str(project_id))
                    )
                )
            else:
                # Personal access: require user_id match
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
            # First try personal access (user_id match)
            result = await session.execute(
                select(TaskORM).where(
                    and_(TaskORM.id == str(task_id), TaskORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()
            if orm:
                return self._orm_to_model(orm)

            # Fallback: find by task_id only (for project tasks where user_id differs)
            result = await session.execute(
                select(TaskORM).where(TaskORM.id == str(task_id))
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
        """List tasks. If project_id specified, uses project-based access (no user_id filter)."""
        async with self._session_factory() as session:
            if project_id is not None:
                # Project-based access: filter by project_id only
                query = select(TaskORM).where(TaskORM.project_id == str(project_id))
            else:
                # Personal access (Inbox/schedule): filter by user_id
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

    async def update(self, user_id: str, task_id: UUID, update: TaskUpdate, project_id: Optional[UUID] = None) -> Task:
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
            old_project_id = orm.project_id

            # Check if parent task is DONE - if so, force this subtask to stay DONE
            if orm.parent_id:
                parent_result = await session.execute(
                    select(TaskORM).where(TaskORM.id == orm.parent_id)
                )
                parent_task = parent_result.scalar_one_or_none()
                if parent_task and parent_task.status == TaskStatus.DONE.value:
                    # Parent is completed, force subtask to be DONE
                    update.status = TaskStatus.DONE

            update_data = update.model_dump(exclude_unset=True)
            status_value = None
            for field, value in update_data.items():
                if value is not None:
                    if field in ("project_id", "parent_id", "phase_id", "milestone_id"):
                        value = str(value) if value else None
                    elif field == "dependency_ids":
                        value = [str(dep_id) for dep_id in value]
                    elif field == "touchpoint_steps":
                        value = [
                            step.model_dump(mode="json") if hasattr(step, "model_dump") else step
                            for step in value
                        ]
                    elif hasattr(value, "value"):  # Enum
                        value = value.value
                    if field == "status":
                        status_value = value
                    setattr(orm, field, value)

            timestamp = now_utc()
            orm.updated_at = timestamp
            new_status = status_value if status_value is not None else orm.status
            status_changed_to_done = (
                original_status != TaskStatus.DONE.value and new_status == TaskStatus.DONE.value
            )
            status_changed_from_done = (
                original_status == TaskStatus.DONE.value
                and status_value is not None
                and status_value != TaskStatus.DONE.value
            )

            if status_changed_to_done:
                self._set_done_state(orm, user_id, timestamp)
                orm.auto_completed_by_parent_id = None
            elif status_changed_from_done:
                self._set_reopened_state(orm, timestamp, status=new_status)
                orm.auto_completed_by_parent_id = None
            elif status_value is not None and new_status != TaskStatus.DONE.value:
                orm.completed_at = None
                orm.completed_by = None
                orm.progress = 0
            elif new_status == TaskStatus.DONE.value:
                orm.progress = 100

            # Cascade status changes to descendants.
            if status_changed_to_done:
                descendants = await self._load_descendants(
                    session=session,
                    user_id=user_id,
                    project_id=orm.project_id,
                    root_ids=[orm.id],
                )
                for subtask in descendants:
                    if subtask.status != TaskStatus.DONE.value:
                        self._set_done_state(subtask, user_id, timestamp)
                        subtask.auto_completed_by_parent_id = orm.id
            elif status_changed_from_done:
                descendants = await self._load_descendants(
                    session=session,
                    user_id=user_id,
                    project_id=orm.project_id,
                    root_ids=[orm.id],
                )
                for subtask in descendants:
                    if subtask.auto_completed_by_parent_id == orm.id:
                        self._set_reopened_state(subtask, timestamp, status=TaskStatus.TODO.value)
                        subtask.auto_completed_by_parent_id = None
            elif status_value is not None:
                conditions = [TaskORM.parent_id == str(task_id)]
                if orm.project_id:
                    conditions.append(TaskORM.project_id == orm.project_id)
                else:
                    conditions.append(TaskORM.user_id == user_id)
                subtask_result = await session.execute(select(TaskORM).where(and_(*conditions)))
                for subtask in subtask_result.scalars().all():
                    if status_value == TaskStatus.DONE.value:
                        if subtask.status != TaskStatus.DONE.value:
                            self._set_done_state(subtask, user_id, timestamp)
                            subtask.auto_completed_by_parent_id = orm.id
                    else:
                        subtask.status = status_value
                        subtask.completed_at = None
                        subtask.completed_by = None
                        subtask.progress = 0
                        subtask.updated_at = timestamp

            affected_fields = {"status", "progress", "estimated_minutes", "parent_id"}
            should_recalculate = bool(affected_fields & set(update_data.keys()))
            if should_recalculate or status_changed_to_done or status_changed_from_done:
                if old_parent_id:
                    await self._recalculate_ancestor_progresses(
                        session=session,
                        user_id=user_id,
                        parent_id=old_parent_id,
                        project_id=old_project_id,
                    )
                if orm.parent_id and orm.parent_id != old_parent_id:
                    await self._recalculate_ancestor_progresses(
                        session=session,
                        user_id=user_id,
                        parent_id=orm.parent_id,
                        project_id=orm.project_id,
                    )
                elif orm.parent_id and not old_parent_id:
                    await self._recalculate_ancestor_progresses(
                        session=session,
                        user_id=user_id,
                        parent_id=orm.parent_id,
                        project_id=orm.project_id,
                    )

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
            if project_id is not None:
                # Project-based access
                conditions = [TaskORM.project_id == str(project_id)]
            else:
                # Personal Inbox access
                conditions = [TaskORM.user_id == user_id, TaskORM.project_id.is_(None)]

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

    async def get_subtasks(self, user_id: str, parent_id: UUID, project_id: Optional[UUID] = None) -> list[Task]:
        """Get all subtasks of a parent task."""
        return await self.list(user_id, project_id=project_id, parent_id=parent_id, include_done=True)

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
                    TaskORM.project_id.is_(None)
                )
            )

            if status:
                query = query.where(TaskORM.status == status)
            else:
                # Default behavior: exclude DONE unless specified?
                # Replicating list() default behavior logic or just basic filtering?
                # list() implementation: if not include_done: query = query.where(status != DONE)
                # But here we stick to the args. If status is None, we return all statuses unless caller filters.
                # Actually, list() has include_done.
                # Let's add include_done to signature to match list().
                pass

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
            # Filter by user and DONE status
            conditions = [
                TaskORM.user_id == user_id,
                TaskORM.status == TaskStatus.DONE.value,
            ]

            if project_id is not None:
                conditions.append(TaskORM.project_id == str(project_id))

            # Use completed_at if available, otherwise fall back to updated_at
            # This handles both new tasks (with completed_at) and legacy tasks
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
            query = query.order_by(TaskORM.completed_at.desc().nullslast(), TaskORM.updated_at.desc())

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]
