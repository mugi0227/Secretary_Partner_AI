"""Application service for task mutations.

This module is the shared mutation boundary for API routes and agent tools.
Repositories remain persistence-focused; actor access, owner scope, validation,
assignment side effects, and date-specific task commands live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.interfaces.postpone_repository import IPostponeRepository
from app.interfaces.project_member_repository import IProjectMemberRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.collaboration import (
    TaskAssignment,
    TaskAssignmentCreate,
    TaskAssignmentsCreate,
    TaskAssignmentUpdate,
)
from app.models.enums import ProjectVisibility, TaskStatus
from app.models.postpone import DoTodayRequest, PostponeRequest
from app.models.project import Project
from app.models.task import Task, TaskCreate, TaskUpdate
from app.services.assignee_utils import is_invitation_assignee
from app.services.task_utils import renumber_siblings
from app.utils.datetime_utils import (
    all_day_bounds_to_utc,
    ensure_utc,
    get_user_today,
    normalize_timezone,
    user_date_to_utc,
)
from app.utils.dependency_validator import DependencyValidator


@dataclass(frozen=True)
class TaskMutationScope:
    """Resolved task scope for a user-initiated mutation."""

    task: Task
    owner_user_id: str
    project_id: UUID | None


@dataclass
class TaskCreationResult:
    """Task creation result with optional assignment side effects."""

    task: Task
    assignments: list[TaskAssignment] = field(default_factory=list)


class TaskApplicationService:
    """Single application boundary for task mutations."""

    def __init__(
        self,
        task_repo: ITaskRepository,
        project_repo: IProjectRepository | None,
        assignment_repo: ITaskAssignmentRepository | None = None,
        member_repo: IProjectMemberRepository | None = None,
        user_repo: IUserRepository | None = None,
        postpone_repo: IPostponeRepository | None = None,
    ):
        self._task_repo = task_repo
        self._project_repo = project_repo
        self._assignment_repo = assignment_repo
        self._member_repo = member_repo
        self._user_repo = user_repo
        self._postpone_repo = postpone_repo

    async def resolve_task_scope(self, actor_user_id: str, task_id: UUID) -> TaskMutationScope:
        """Resolve a task and its persistence owner for the acting user."""
        task = await self._task_repo.get(actor_user_id, task_id)
        if task and not task.project_id:
            return TaskMutationScope(task=task, owner_user_id=actor_user_id, project_id=None)

        if task and task.project_id:
            project = await self._get_project_or_none(actor_user_id, task.project_id)
            if project:
                return TaskMutationScope(
                    task=task,
                    owner_user_id=project.user_id,
                    project_id=task.project_id,
                )

        task = await self._task_repo.get_by_id(actor_user_id, task_id)
        if task and task.project_id:
            project = await self._get_project_or_none(actor_user_id, task.project_id)
            if project:
                return TaskMutationScope(
                    task=task,
                    owner_user_id=project.user_id,
                    project_id=task.project_id,
                )

        if task and task.user_id == actor_user_id and not task.project_id:
            return TaskMutationScope(task=task, owner_user_id=actor_user_id, project_id=None)

        raise NotFoundError(f"Task {task_id} not found")

    async def create_task(
        self,
        actor_user_id: str,
        task: TaskCreate,
        *,
        assignee_ids: list[str] | None = None,
        inherit_parent_assignments: bool = False,
        auto_assign_requester: bool = False,
        dedupe_fixed_time: bool = False,
        shift_siblings: bool = True,
    ) -> TaskCreationResult:
        """Create a task after resolving owner scope and validating relationships."""
        project = None
        owner_user_id = actor_user_id
        if task.project_id:
            project = await self._get_project_or_none(actor_user_id, task.project_id)
            if not project:
                raise NotFoundError(f"Project {task.project_id} not found")
            owner_user_id = project.user_id

        if task.parent_id:
            parent_scope = await self.resolve_task_scope(actor_user_id, task.parent_id)
            owner_user_id = parent_scope.owner_user_id
            if task.project_id is None:
                task.project_id = parent_scope.project_id
            elif task.project_id != parent_scope.project_id:
                raise BusinessLogicError("parent_id and project_id mismatch")

        await self._validate_task_relationships(
            owner_user_id=owner_user_id,
            task_id=uuid4(),
            dependency_ids=task.dependency_ids,
            parent_id=task.parent_id,
            project_id=task.project_id,
            validate_parent=task.parent_id is not None,
        )
        if shift_siblings:
            await self._shift_siblings_for_insert(owner_user_id, task)
        await self._normalize_all_day_task(owner_user_id, task)

        if dedupe_fixed_time and task.is_fixed_time and task.start_time and task.end_time:
            existing = await self._find_existing_meeting(
                owner_user_id,
                task.start_time,
                task.end_time,
                task.title,
                task.project_id,
            )
            if existing:
                return TaskCreationResult(task=existing)

        created_task = await self._task_repo.create(owner_user_id, task)
        assignments = await self._assign_created_task(
            actor_user_id=actor_user_id,
            owner_user_id=owner_user_id,
            task=created_task,
            project_visibility=project.visibility if project else None,
            assignee_ids=assignee_ids or [],
            inherit_parent_assignments=inherit_parent_assignments,
            auto_assign_requester=auto_assign_requester,
        )
        return TaskCreationResult(task=created_task, assignments=assignments)

    async def update_task(self, actor_user_id: str, task_id: UUID, update: TaskUpdate) -> Task:
        """Update a task through the shared mutation boundary."""
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        await self._normalize_all_day_update(scope.owner_user_id, scope.task, update)
        await self._validate_completion_guard(scope, update)
        await self._validate_update_relationships(scope, task_id, update)

        try:
            return await self._task_repo.update(
                scope.owner_user_id,
                task_id,
                update,
                project_id=scope.project_id,
            )
        except NotFoundError:
            raise

    async def delete_task(self, actor_user_id: str, task_id: UUID) -> bool:
        """Delete a task and renumber siblings through the shared boundary."""
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        parent_id = scope.task.parent_id
        deleted = await self._task_repo.delete(
            scope.owner_user_id,
            task_id,
            project_id=scope.project_id,
        )
        if deleted and parent_id:
            await renumber_siblings(
                self._task_repo,
                scope.owner_user_id,
                parent_id,
                scope.project_id,
            )
        return deleted

    async def assign_task(
        self,
        actor_user_id: str,
        task_id: UUID,
        assignment: TaskAssignmentCreate,
    ) -> TaskAssignment:
        """Assign one user to a task after resolving task access."""
        if not self._assignment_repo:
            raise BusinessLogicError("Task assignment repository is unavailable")
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        await self._validate_assignees_are_project_members(
            actor_user_id,
            scope.task,
            [assignment.assignee_id],
        )
        return await self._assignment_repo.assign(scope.owner_user_id, task_id, assignment)

    async def assign_task_multiple(
        self,
        actor_user_id: str,
        task_id: UUID,
        assignments: TaskAssignmentsCreate,
    ) -> list[TaskAssignment]:
        """Replace task assignees after resolving task access."""
        if not self._assignment_repo:
            raise BusinessLogicError("Task assignment repository is unavailable")
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        await self._validate_assignees_are_project_members(
            actor_user_id,
            scope.task,
            assignments.assignee_ids,
        )
        return await self._assignment_repo.assign_multiple(
            scope.owner_user_id,
            task_id,
            assignments,
        )

    async def update_assignment(
        self,
        actor_user_id: str,
        assignment_id: UUID,
        update: TaskAssignmentUpdate,
    ) -> TaskAssignment:
        """Update assignment fields after resolving the underlying task access."""
        if not self._assignment_repo:
            raise BusinessLogicError("Task assignment repository is unavailable")
        assignment = await self._assignment_repo.get_by_id(assignment_id)
        if not assignment:
            raise NotFoundError(f"Assignment {assignment_id} not found")
        scope = await self.resolve_task_scope(actor_user_id, assignment.task_id)
        return await self._assignment_repo.update(scope.owner_user_id, assignment_id, update)

    async def unassign_task(self, actor_user_id: str, task_id: UUID) -> bool:
        """Remove all task assignees after resolving task access."""
        if not self._assignment_repo:
            raise BusinessLogicError("Task assignment repository is unavailable")
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        return await self._assignment_repo.delete_by_task(scope.owner_user_id, task_id)

    async def postpone_task(
        self,
        actor_user_id: str,
        task_id: UUID,
        request: PostponeRequest,
    ) -> Task:
        """Postpone a task and record the postpone event."""
        if not self._postpone_repo:
            raise BusinessLogicError("Postpone repository is unavailable")
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        user_timezone = await self._resolve_user_timezone(actor_user_id)
        from_date = get_user_today(user_timezone)
        await self._postpone_repo.create(
            user_id=scope.owner_user_id,
            task_id=task_id,
            from_date=from_date,
            to_date=request.to_date,
            reason=request.reason,
            pinned=request.pin,
        )

        target_datetime = user_date_to_utc(request.to_date, user_timezone)
        update_data = TaskUpdate(start_not_before=target_datetime)
        if request.pin:
            update_data.pinned_date = target_datetime
        else:
            update_data.pinned_date = None

        return await self._task_repo.update(
            scope.owner_user_id,
            task_id,
            update_data,
            project_id=scope.project_id,
        )

    async def do_today(
        self,
        actor_user_id: str,
        task_id: UUID,
        request: DoTodayRequest,
    ) -> Task:
        """Pull a task into today's schedule."""
        scope = await self.resolve_task_scope(actor_user_id, task_id)
        user_timezone = await self._resolve_user_timezone(actor_user_id)
        today = get_user_today(user_timezone)
        today_datetime = user_date_to_utc(today, user_timezone)

        update_data = TaskUpdate()
        if scope.task.start_not_before:
            start_not_before = ensure_utc(scope.task.start_not_before)
            if (
                start_not_before
                and start_not_before.astimezone(ZoneInfo(user_timezone)).date() > today
            ):
                update_data.start_not_before = today_datetime
        if request.pin:
            update_data.pinned_date = today_datetime

        return await self._task_repo.update(
            scope.owner_user_id,
            task_id,
            update_data,
            project_id=scope.project_id,
        )

    async def _resolve_user_timezone(self, user_id: str) -> str:
        if self._user_repo is None:
            return normalize_timezone(None)
        try:
            user = await self._user_repo.get(UUID(user_id))
        except (TypeError, ValueError):
            user = None
        return normalize_timezone(user.timezone if user else None)

    async def _get_project_or_none(
        self,
        actor_user_id: str,
        project_id: UUID,
    ) -> Project | None:
        if self._project_repo is None:
            return None
        return await self._project_repo.get(actor_user_id, project_id)

    async def _validate_task_relationships(
        self,
        *,
        owner_user_id: str,
        task_id: UUID,
        dependency_ids: list[UUID],
        parent_id: UUID | None,
        project_id: UUID | None,
        validate_parent: bool,
    ) -> None:
        if not dependency_ids and not validate_parent:
            return
        validator = DependencyValidator(self._task_repo)
        try:
            if dependency_ids:
                await validator.validate_dependencies(
                    task_id,
                    dependency_ids,
                    owner_user_id,
                    parent_id,
                    project_id=project_id,
                )
            if validate_parent and parent_id:
                await validator.validate_parent_child_consistency(
                    task_id,
                    parent_id,
                    owner_user_id,
                )
        except BusinessLogicError:
            raise

    async def _validate_update_relationships(
        self,
        scope: TaskMutationScope,
        task_id: UUID,
        update: TaskUpdate,
    ) -> None:
        if update.dependency_ids is None and update.parent_id is None:
            return
        dependency_ids = (
            update.dependency_ids
            if update.dependency_ids is not None
            else scope.task.dependency_ids
        )
        parent_id = update.parent_id if update.parent_id is not None else scope.task.parent_id
        await self._validate_task_relationships(
            owner_user_id=scope.owner_user_id,
            task_id=task_id,
            dependency_ids=dependency_ids or [],
            parent_id=parent_id,
            project_id=scope.project_id,
            validate_parent=update.parent_id is not None,
        )

    async def _shift_siblings_for_insert(self, owner_user_id: str, task: TaskCreate) -> None:
        if not task.parent_id or task.order_in_parent is None:
            return
        existing_siblings = await self._task_repo.get_subtasks(
            owner_user_id,
            task.parent_id,
            project_id=task.project_id,
        )
        for sibling in existing_siblings:
            if (
                sibling.order_in_parent is not None
                and sibling.order_in_parent >= task.order_in_parent
            ):
                await self._task_repo.update(
                    owner_user_id,
                    sibling.id,
                    TaskUpdate(order_in_parent=sibling.order_in_parent + 1),
                    project_id=task.project_id,
                )

    async def _normalize_all_day_task(self, owner_user_id: str, task: TaskCreate) -> None:
        if not task.is_all_day:
            return
        timezone_name = await self._resolve_user_timezone(owner_user_id)
        reference = task.start_time or task.due_date or task.start_not_before
        start_utc, end_utc = all_day_bounds_to_utc(timezone_name, reference=reference)
        task.start_time = start_utc
        task.end_time = end_utc
        task.is_fixed_time = True

    async def _normalize_all_day_update(
        self,
        owner_user_id: str,
        current_task: Task,
        update: TaskUpdate,
    ) -> None:
        if update.is_all_day is not True:
            return
        timezone_name = await self._resolve_user_timezone(owner_user_id)
        reference = (
            update.start_time
            or update.due_date
            or update.start_not_before
            or current_task.start_time
            or current_task.due_date
            or current_task.start_not_before
        )
        start_utc, end_utc = all_day_bounds_to_utc(timezone_name, reference=reference)
        update.start_time = start_utc
        update.end_time = end_utc
        update.is_fixed_time = True

    async def _validate_completion_guard(
        self,
        scope: TaskMutationScope,
        update: TaskUpdate,
    ) -> None:
        if (
            update.status != TaskStatus.DONE
            or not scope.task.requires_all_completion
            or not self._assignment_repo
        ):
            return
        assignments = await self._assignment_repo.list_by_task(
            scope.owner_user_id,
            scope.task.id,
        )
        if len(assignments) <= 1:
            return
        if not all(assignment.status == TaskStatus.DONE for assignment in assignments):
            raise BusinessLogicError(
                "All assignees must complete the task before it can be marked done"
            )

    async def _assign_created_task(
        self,
        *,
        actor_user_id: str,
        owner_user_id: str,
        task: Task,
        project_visibility: ProjectVisibility | None,
        assignee_ids: list[str],
        inherit_parent_assignments: bool,
        auto_assign_requester: bool,
    ) -> list[TaskAssignment]:
        if not self._assignment_repo:
            return []

        assignments: list[TaskAssignment] = []
        resolved_ids = await self._resolve_assignee_ids(task.project_id, assignee_ids)
        for assignee_id in resolved_ids:
            assignments.append(
                await self._assignment_repo.assign(
                    owner_user_id,
                    task.id,
                    TaskAssignmentCreate(assignee_id=assignee_id),
                )
            )

        if assignments:
            return assignments

        if inherit_parent_assignments and task.parent_id:
            parent_assignments = await self._assignment_repo.list_by_task(
                owner_user_id,
                task.parent_id,
            )
            for assignment in parent_assignments:
                if assignment.assignee_id:
                    assignments.append(
                        await self._assignment_repo.assign(
                            owner_user_id,
                            task.id,
                            TaskAssignmentCreate(assignee_id=assignment.assignee_id),
                        )
                    )

        if assignments:
            return assignments

        if project_visibility == ProjectVisibility.PRIVATE:
            assignments.extend(
                await self._assignment_repo.assign_multiple(
                    owner_user_id,
                    task.id,
                    TaskAssignmentsCreate(assignee_ids=[actor_user_id]),
                )
            )
            return assignments

        if auto_assign_requester and task.project_id and self._member_repo:
            members = await self._member_repo.list_by_project(task.project_id)
            member_ids = {member.member_user_id for member in members}
            if actor_user_id in member_ids:
                assignments.append(
                    await self._assignment_repo.assign(
                        owner_user_id,
                        task.id,
                        TaskAssignmentCreate(assignee_id=actor_user_id),
                    )
                )
            elif len(members) == 1:
                assignments.append(
                    await self._assignment_repo.assign(
                        owner_user_id,
                        task.id,
                        TaskAssignmentCreate(assignee_id=members[0].member_user_id),
                    )
                )

        return assignments

    async def _resolve_assignee_ids(
        self,
        project_id: UUID | None,
        assignee_ids: list[str],
    ) -> list[str]:
        values = [value.strip() for value in assignee_ids if value and value.strip()]
        if not values or not project_id or not self._member_repo:
            return list(dict.fromkeys(values))

        members = await self._member_repo.list_by_project(project_id)
        user_id_set = {member.member_user_id for member in members}
        record_to_user = {str(member.id): member.member_user_id for member in members}
        resolved: list[str] = []
        for assignee_id in values:
            if is_invitation_assignee(assignee_id):
                resolved.append(assignee_id)
            elif assignee_id in user_id_set:
                resolved.append(assignee_id)
            elif assignee_id in record_to_user:
                resolved.append(record_to_user[assignee_id])
        return list(dict.fromkeys(resolved))

    async def _validate_assignees_are_project_members(
        self,
        actor_user_id: str,
        task: Task,
        assignee_ids: list[str],
    ) -> None:
        if not task.project_id or not self._member_repo:
            return
        project = await self._get_project_or_none(actor_user_id, task.project_id)
        if not project:
            raise NotFoundError(f"Project {task.project_id} not found")
        members = await self._member_repo.list_by_project(task.project_id)
        valid_ids = {member.member_user_id for member in members}
        invalid = [
            assignee_id
            for assignee_id in assignee_ids
            if not is_invitation_assignee(assignee_id) and assignee_id not in valid_ids
        ]
        if invalid:
            raise BusinessLogicError(
                f"Assignees are not project members: {', '.join(invalid)}"
            )

    async def _find_existing_meeting(
        self,
        owner_user_id: str,
        start_time: datetime,
        end_time: datetime,
        title: str,
        project_id: UUID | None,
    ) -> Task | None:
        normalized_title = _normalize_meeting_title(title)
        tasks = await self._task_repo.list(
            owner_user_id,
            project_id=project_id,
            include_done=True,
            limit=1000,
        )
        for task in tasks:
            if not task.is_fixed_time or not task.start_time or not task.end_time:
                continue
            if not _within_minutes(task.start_time, start_time, 30):
                continue
            if not _within_minutes(task.end_time, end_time, 30):
                continue
            if _normalize_meeting_title(task.title) == normalized_title:
                return task
        return None


def _normalize_meeting_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def _within_minutes(left: datetime, right: datetime, minutes: int) -> bool:
    left_utc = ensure_utc(left) or left
    right_utc = ensure_utc(right) or right
    delta_seconds = abs((left_utc - right_utc).total_seconds())
    return delta_seconds <= minutes * 60
