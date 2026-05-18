"""Service for user-selected daily plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.exceptions import NotFoundError
from app.core.logger import logger
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.enums import EnergyLevel, Priority, TaskStatus
from app.models.schedule import ScheduleResponse, TodayTasksResponse
from app.models.task import Task, TaskUpdate
from app.models.today_plan import (
    TodayPlanCapacity,
    TodayPlanReason,
    TodayPlanResponse,
    TodayPlanScoreComponent,
    TodayPlanTask,
)
from app.services.scheduler_service import SchedulerService
from app.services.task_utils import get_remaining_minutes
from app.utils.datetime_utils import (
    ensure_utc,
    get_user_today,
    normalize_timezone,
    user_date_to_utc,
)


@dataclass(frozen=True)
class TaskMutationScope:
    """Resolved persistence scope for a task mutation."""

    task: Task
    owner_user_id: str


class TodayPlanService:
    """Build and update daily plans where recommendations and selections are separate."""

    def __init__(
        self,
        task_repo: ITaskRepository,
        project_repo: IProjectRepository,
        assignment_repo: ITaskAssignmentRepository,
        user_repo: IUserRepository,
        scheduler_service: SchedulerService | None = None,
    ):
        self._task_repo = task_repo
        self._project_repo = project_repo
        self._assignment_repo = assignment_repo
        self._user_repo = user_repo
        self._scheduler_service = scheduler_service or SchedulerService()

    async def build_plan(
        self,
        user_id: str,
        *,
        target_date: date | None = None,
        capacity_hours: float | None = None,
        capacity_by_weekday: list[float] | None = None,
        recommendation_limit: int = 6,
    ) -> TodayPlanResponse:
        """Build today's plan without mutating user selections."""
        user_timezone = await self._resolve_user_timezone(user_id)
        today = target_date or get_user_today(user_timezone)
        tasks = await self._load_accessible_tasks(user_id)
        project_priorities = await self._load_project_priorities(user_id)
        assignments = await self._load_schedule_assignments(user_id)

        schedule = self._scheduler_service.build_schedule(
            tasks,
            project_priorities=project_priorities,
            start_date=today,
            capacity_hours=capacity_hours,
            capacity_by_weekday=capacity_by_weekday,
            max_days=30,
            current_user_id=user_id,
            assignments=assignments,
            filter_by_assignee=True,
            user_timezone=user_timezone,
        )
        today_result = self._scheduler_service.get_today_tasks(
            schedule,
            tasks,
            project_priorities=project_priorities,
            today=today,
            user_timezone=user_timezone,
        )
        plan = self._decorate_today_result(
            today_result=today_result,
            schedule=schedule,
            tasks=tasks,
            project_priorities=project_priorities,
            user_timezone=user_timezone,
            recommendation_limit=recommendation_limit,
        )
        logger.debug(
            "today_plan_built user_id=%s date=%s selected=%s recommendations=%s blocked=%s "
            "capacity_minutes=%s planned_minutes=%s",
            user_id,
            plan.today.isoformat(),
            len(plan.selected),
            len(plan.recommendations),
            len(plan.blocked),
            plan.capacity.capacity_minutes,
            plan.capacity.total_minutes,
        )
        return plan

    async def update_selection(
        self,
        user_id: str,
        task_ids: list[UUID],
        *,
        replace: bool = True,
        target_date: date | None = None,
        recommendation_limit: int = 6,
    ) -> TodayPlanResponse:
        """Persist the user's selected tasks for today and return the updated plan."""
        user_timezone = await self._resolve_user_timezone(user_id)
        today = target_date or get_user_today(user_timezone)
        selected_ids = list(dict.fromkeys(task_ids))
        selected_id_set = set(selected_ids)
        pin_datetime = user_date_to_utc(today, user_timezone)

        current_tasks = await self._load_accessible_tasks(user_id)
        current_selected_ids = {
            task.id
            for task in current_tasks
            if self._is_pinned_on(task, today, user_timezone) and not task.is_fixed_time
        }

        if replace:
            for task in current_tasks:
                if task.id in current_selected_ids and task.id not in selected_id_set:
                    scope = await self._resolve_task_for_update(user_id, task.id)
                    await self._task_repo.update(
                        scope.owner_user_id,
                        task.id,
                        TaskUpdate(pinned_date=None),
                        project_id=task.project_id,
                    )

        for task_id in selected_ids:
            scope = await self._resolve_task_for_update(user_id, task_id)
            await self._task_repo.update(
                scope.owner_user_id,
                task_id,
                TaskUpdate(pinned_date=pin_datetime),
                project_id=scope.task.project_id,
            )

        logger.info(
            "today_selection_updated user_id=%s date=%s selected=%s replace=%s",
            user_id,
            today.isoformat(),
            len(selected_ids),
            replace,
        )
        return await self.build_plan(
            user_id,
            target_date=today,
            recommendation_limit=recommendation_limit,
        )

    async def _resolve_user_timezone(self, user_id: str) -> str:
        try:
            user_account = await self._user_repo.get(UUID(user_id))
        except (TypeError, ValueError):
            user_account = None
        return normalize_timezone(user_account.timezone if user_account else None)

    async def _load_accessible_tasks(self, user_id: str) -> list[Task]:
        tasks_by_id = {
            task.id: task
            for task in await self._task_repo.list(user_id, include_done=True, limit=1000)
        }
        for assignment in await self._assignment_repo.list_for_assignee(user_id):
            task = await self._task_repo.get_by_id(user_id, assignment.task_id)
            if task:
                tasks_by_id[task.id] = task
        return list(tasks_by_id.values())

    async def _load_schedule_assignments(self, user_id: str):
        assignments_by_id = {
            assignment.id: assignment
            for assignment in await self._assignment_repo.list_all_for_user(user_id)
        }
        for assignment in await self._assignment_repo.list_for_assignee(user_id):
            assignments_by_id[assignment.id] = assignment
        return list(assignments_by_id.values())

    async def _load_project_priorities(self, user_id: str) -> dict[UUID, int]:
        return {project.id: project.priority for project in await self._project_repo.list(user_id, limit=1000)}

    async def _resolve_task_for_update(self, user_id: str, task_id: UUID) -> TaskMutationScope:
        task = await self._task_repo.get(user_id, task_id)
        if task and not task.project_id:
            return TaskMutationScope(task=task, owner_user_id=user_id)

        if task and task.project_id:
            project = await self._project_repo.get(user_id, task.project_id)
            if project:
                return TaskMutationScope(task=task, owner_user_id=project.user_id)

        task = await self._task_repo.get_by_id(user_id, task_id)
        if task and task.project_id:
            project = await self._project_repo.get(user_id, task.project_id)
            if project:
                return TaskMutationScope(task=task, owner_user_id=project.user_id)

        if task and task.user_id == user_id and not task.project_id:
            return TaskMutationScope(task=task, owner_user_id=user_id)

        raise NotFoundError(f"Task {task_id} not found")

    def _decorate_today_result(
        self,
        *,
        today_result: TodayTasksResponse,
        schedule: ScheduleResponse,
        tasks: list[Task],
        project_priorities: dict[UUID, int],
        user_timezone: str,
        recommendation_limit: int,
    ) -> TodayPlanResponse:
        task_map = {task.id: task for task in tasks}
        today = today_result.today
        selected_ids = {
            task.id
            for task in tasks
            if self._is_pinned_on(task, today, user_timezone) and not task.is_fixed_time
        }
        allocation_minutes = {
            allocation.task_id: allocation.allocated_minutes
            for allocation in today_result.today_allocations
        }
        scheduled_ids = [task.id for task in today_result.today_tasks]
        score_breakdowns = self._score_task_breakdowns(
            tasks=tasks,
            all_tasks=tasks,
            project_priorities=project_priorities,
            today=today,
            user_timezone=user_timezone,
        )
        scores = {
            task_id: self._score_from_breakdown(components)
            for task_id, components in score_breakdowns.items()
        }

        selected: list[TodayPlanTask] = []
        recommendations: list[TodayPlanTask] = []
        scheduled: list[TodayPlanTask] = []
        blocked: list[TodayPlanTask] = []

        for task_id in scheduled_ids:
            task = task_map.get(task_id)
            if not task or task.is_fixed_time:
                continue
            is_selected = task.id in selected_ids
            is_blocked = self._is_blocked(task, task_map)
            decorated = self._decorate_task(
                task=task,
                bucket="selected" if is_selected else "recommended",
                selected=is_selected,
                score=scores.get(task.id, 0.0),
                score_breakdown=score_breakdowns.get(task.id, []),
                allocated_minutes=allocation_minutes.get(task.id, 0),
                all_tasks=tasks,
                today=today,
                user_timezone=user_timezone,
                blocked=is_blocked,
            )
            if is_selected:
                selected.append(decorated)
            elif is_blocked:
                blocked.append(decorated.model_copy(update={"bucket": "blocked"}))
            elif len(recommendations) < recommendation_limit:
                recommendations.append(decorated)
            else:
                scheduled.append(decorated.model_copy(update={"bucket": "scheduled"}))

        scheduled_id_set = set(scheduled_ids)
        for task in tasks:
            if task.id not in selected_ids or task.id in scheduled_id_set or task.is_fixed_time:
                continue
            selected.append(
                self._decorate_task(
                    task=task,
                    bucket="selected",
                    selected=True,
                    score=scores.get(task.id, 0.0),
                    score_breakdown=score_breakdowns.get(task.id, []),
                    allocated_minutes=0,
                    all_tasks=tasks,
                    today=today,
                    user_timezone=user_timezone,
                    blocked=self._is_blocked(task, task_map),
                )
            )

        return TodayPlanResponse(
            today=today,
            selected=selected,
            recommendations=recommendations,
            scheduled=scheduled,
            blocked=blocked,
            capacity=self._build_capacity(today_result, selected),
        )

    def _score_task_breakdowns(
        self,
        *,
        tasks: list[Task],
        all_tasks: list[Task],
        project_priorities: dict[UUID, int],
        today: date,
        user_timezone: str,
    ) -> dict[UUID, list[TodayPlanScoreComponent]]:
        _, effective_due_by_task = self._scheduler_service._get_effective_constraints(
            all_tasks,
            reference_today=today,
            user_timezone=user_timezone,
        )
        return {
            task.id: self._build_score_breakdown(
                task=task,
                project_priorities=project_priorities,
                effective_due=effective_due_by_task.get(task.id),
                today=today,
            )
            for task in tasks
        }

    def _build_score_breakdown(
        self,
        *,
        task: Task,
        project_priorities: dict[UUID, int],
        effective_due: datetime | None,
        today: date,
    ) -> list[TodayPlanScoreComponent]:
        importance_weights = {
            Priority.HIGH: 3.0,
            Priority.MEDIUM: 2.0,
            Priority.LOW: 1.0,
        }
        urgency_weights = {
            Priority.HIGH: 3.0,
            Priority.MEDIUM: 2.0,
            Priority.LOW: 1.0,
        }

        importance_points = importance_weights.get(task.importance, 1.0) * 10
        urgency_points = urgency_weights.get(task.urgency, 1.0) * 8
        progress_points = 2.0 if task.status == TaskStatus.IN_PROGRESS else 0.0
        energy_points = 1.0 if task.energy_level == EnergyLevel.LOW else 0.0
        base_points = importance_points + urgency_points + progress_points + energy_points

        project_priority = 5
        if task.project_id and task.project_id in project_priorities:
            project_priority = project_priorities[task.project_id]
        project_points = base_points * (project_priority * self._scheduler_service.project_priority_weight)

        due_date = effective_due.date() if effective_due else None
        due_points = self._scheduler_service._calculate_due_bonus_for_date(due_date, today)

        components = [
            TodayPlanScoreComponent(
                code="importance",
                label="重要度",
                points=importance_points,
                detail=self._priority_label(task.importance),
            ),
            TodayPlanScoreComponent(
                code="urgency",
                label="緊急度",
                points=urgency_points,
                detail=self._priority_label(task.urgency),
            ),
        ]
        if due_date:
            components.append(
                TodayPlanScoreComponent(
                    code="due_date",
                    label="期限",
                    points=due_points,
                    detail=self._due_detail(due_date, today),
                )
            )
        if task.project_id:
            components.append(
                TodayPlanScoreComponent(
                    code="project_priority",
                    label="プロジェクト優先度",
                    points=project_points,
                    detail=f"{project_priority}/10",
                )
            )
        if progress_points:
            components.append(
                TodayPlanScoreComponent(
                    code="in_progress",
                    label="着手中",
                    points=progress_points,
                    detail="すでに進行中",
                )
            )
        if energy_points:
            components.append(
                TodayPlanScoreComponent(
                    code="low_energy",
                    label="軽め",
                    points=energy_points,
                    detail="低エネルギーでも進めやすい",
                )
            )
        components.append(
            TodayPlanScoreComponent(
                code="scope",
                label="範囲",
                points=0.0,
                detail="プロジェクトタスク" if task.project_id else "個人タスク",
            )
        )
        return components

    def _score_from_breakdown(self, components: list[TodayPlanScoreComponent]) -> float:
        return round(sum(component.points for component in components), 2)

    def _score_summary(self, components: list[TodayPlanScoreComponent]) -> str:
        positive_components = [
            component for component in components
            if component.points > 0 and component.code != "scope"
        ]
        if not positive_components:
            return "大きな偏りなし"
        ranked = sorted(positive_components, key=lambda component: component.points, reverse=True)
        return f"{'・'.join(component.label for component in ranked[:3])}で上位"

    def _decorate_task(
        self,
        *,
        task: Task,
        bucket: str,
        selected: bool,
        score: float,
        score_breakdown: list[TodayPlanScoreComponent],
        allocated_minutes: int,
        all_tasks: list[Task],
        today: date,
        user_timezone: str,
        blocked: bool,
    ) -> TodayPlanTask:
        return TodayPlanTask(
            task=task,
            bucket=bucket,
            selected=selected,
            score=score,
            score_summary=self._score_summary(score_breakdown),
            score_breakdown=score_breakdown,
            reasons=self._build_reasons(task, today, user_timezone, selected, blocked),
            allocated_minutes=allocated_minutes,
            remaining_minutes=max(0, get_remaining_minutes(task, all_tasks)),
        )

    def _build_reasons(
        self,
        task: Task,
        today: date,
        user_timezone: str,
        selected: bool,
        blocked: bool,
    ) -> list[TodayPlanReason]:
        reasons: list[TodayPlanReason] = []
        due_date = self._local_date(task.due_date, user_timezone) if task.due_date else None

        if selected:
            reasons.append(TodayPlanReason(code="selected_for_today", message="今日やるに選択済み"))
        if blocked:
            reasons.append(TodayPlanReason(code="blocked_by_dependency", message="依存タスクが未完了"))
        if due_date:
            days_until = (due_date - today).days
            if days_until < 0:
                reasons.append(TodayPlanReason(code="overdue", message="期限超過"))
            elif days_until == 0:
                reasons.append(TodayPlanReason(code="due_today", message="今日が期限"))
            elif days_until == 1:
                reasons.append(TodayPlanReason(code="due_tomorrow", message="明日が期限"))
            elif days_until <= 7:
                reasons.append(TodayPlanReason(code="due_this_week", message="今週が期限"))
        if task.importance == Priority.HIGH:
            reasons.append(TodayPlanReason(code="high_importance", message="重要度が高い"))
        if task.urgency == Priority.HIGH:
            reasons.append(TodayPlanReason(code="high_urgency", message="緊急度が高い"))
        if task.status == TaskStatus.IN_PROGRESS:
            reasons.append(TodayPlanReason(code="already_in_progress", message="すでに進行中"))
        if task.energy_level == EnergyLevel.LOW:
            reasons.append(TodayPlanReason(code="low_energy_quick_win", message="軽めに進めやすい"))

        return reasons

    def _priority_label(self, priority: Priority) -> str:
        return {
            Priority.HIGH: "高",
            Priority.MEDIUM: "中",
            Priority.LOW: "低",
        }.get(priority, priority.value)

    def _due_detail(self, due_date: date, today: date) -> str:
        days_until = (due_date - today).days
        if days_until < 0:
            return f"{abs(days_until)}日超過"
        if days_until == 0:
            return "今日"
        if days_until == 1:
            return "明日"
        return f"あと{days_until}日"

    def _build_capacity(
        self,
        today_result: TodayTasksResponse,
        selected: list[TodayPlanTask],
    ) -> TodayPlanCapacity:
        selected_minutes = sum(
            item.remaining_minutes if item.remaining_minutes > 0 else item.allocated_minutes
            for item in selected
        )
        total_minutes = selected_minutes + today_result.meeting_minutes
        capacity_usage_percent = 0
        if today_result.capacity_minutes > 0:
            capacity_usage_percent = min(
                100,
                int((total_minutes / today_result.capacity_minutes) * 100),
            )
        return TodayPlanCapacity(
            feasible=total_minutes <= today_result.capacity_minutes,
            total_minutes=selected_minutes,
            capacity_minutes=today_result.capacity_minutes,
            meeting_minutes=today_result.meeting_minutes,
            overflow_minutes=max(0, total_minutes - today_result.capacity_minutes),
            capacity_usage_percent=capacity_usage_percent,
        )

    def _is_blocked(self, task: Task, task_map: dict[UUID, Task]) -> bool:
        return any(
            not (dependency := task_map.get(dependency_id))
            or dependency.status != TaskStatus.DONE
            for dependency_id in task.dependency_ids
        )

    def _is_pinned_on(self, task: Task, target_date: date, user_timezone: str) -> bool:
        return (
            task.pinned_date is not None
            and self._local_date(task.pinned_date, user_timezone) == target_date
        )

    def _local_date(self, value: datetime, user_timezone: str) -> date:
        utc_value = ensure_utc(value)
        if utc_value is None:
            raise ValueError("datetime value is required")
        return utc_value.astimezone(ZoneInfo(normalize_timezone(user_timezone))).date()
