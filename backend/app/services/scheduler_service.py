"""
Scheduler service for capacity-aware task scheduling.

Handles task scheduling with capacity constraints and dependency resolution.
"""

from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from app.core.logger import setup_logger
from app.models.enums import EnergyLevel, Priority, TaskStatus
from app.models.schedule import (
    ScheduleDay,
    TaskAllocation,
    TaskScheduleInfo,
    ScheduleResponse,
    TodayTasksResponse,
    TodayTaskAllocation,
    UnscheduledTask,
    ExcludedTask,
)
from app.models.task import Task
from app.services.task_utils import get_effective_estimated_minutes, is_parent_task

logger = setup_logger(__name__)


class SchedulerService:
    """
    Service for capacity-aware task scheduling.

    Provides:
    - Capacity calculation (daily work hour limits)
    - Overflow detection and suggestions
    - Dependency-aware scheduling
    """

    def __init__(
        self,
        default_capacity_hours: float = 8.0,
        default_task_minutes: int = 60,
        project_priority_weight: float = 0.05,
        energy_high_ratio: float = 0.4,
        energy_low_ratio: float = 0.6,
    ):
        """
        Initialize scheduler service.

        Args:
            default_capacity_hours: Default daily capacity in hours
        """
        self.default_capacity_hours = default_capacity_hours
        self.default_task_minutes = default_task_minutes
        self.project_priority_weight = project_priority_weight
        self.energy_high_ratio = energy_high_ratio
        self.energy_low_ratio = energy_low_ratio

    def check_schedule_feasibility(
        self,
        tasks: list[Task],
        capacity_hours: Optional[float] = None,
    ) -> dict:
        """
        Check if tasks fit within daily capacity.

        Args:
            tasks: List of tasks to schedule
            capacity_hours: Daily capacity in hours (None = use default)

        Returns:
            Dictionary with:
                - feasible: bool
                - total_minutes: int
                - capacity_minutes: int
                - overflow_minutes: int
                - tasks_that_fit: list[Task]
                - overflow_tasks: list[Task]
        """
        capacity = capacity_hours or self.default_capacity_hours
        capacity_minutes = int(capacity * 60)

        # Calculate total estimated time
        total_minutes = 0
        tasks_with_time = []
        tasks_without_time = []

        for task in tasks:
            # Use effective estimated minutes (considers subtasks)
            effective_minutes = get_effective_estimated_minutes(task, tasks)
            if effective_minutes > 0:
                total_minutes += effective_minutes
                tasks_with_time.append(task)
            else:
                tasks_without_time.append(task)

        # Assume 15 minutes for tasks without estimates
        total_minutes += len(tasks_without_time) * self.default_task_minutes

        # Check feasibility
        feasible = total_minutes <= capacity_minutes
        overflow_minutes = max(0, total_minutes - capacity_minutes)

        # Determine which tasks fit
        tasks_that_fit = []
        overflow_tasks = []
        accumulated_minutes = 0

        # Prioritize tasks with estimates first (already scored by caller)
        for task in tasks_with_time:
            # Use effective estimated minutes (considers subtasks)
            task_minutes = get_effective_estimated_minutes(task, tasks)
            if accumulated_minutes + task_minutes <= capacity_minutes:
                tasks_that_fit.append(task)
                accumulated_minutes += task_minutes
            else:
                overflow_tasks.append(task)

        # Add tasks without estimates if space remains
        for task in tasks_without_time:
            if accumulated_minutes + self.default_task_minutes <= capacity_minutes:
                tasks_that_fit.append(task)
                accumulated_minutes += self.default_task_minutes
            else:
                overflow_tasks.append(task)

        result = {
            "feasible": feasible,
            "total_minutes": total_minutes,
            "capacity_minutes": capacity_minutes,
            "overflow_minutes": overflow_minutes,
            "tasks_that_fit": tasks_that_fit,
            "overflow_tasks": overflow_tasks,
            "capacity_usage_percent": (
                min(100, int((total_minutes / capacity_minutes) * 100))
                if capacity_minutes > 0
                else 0
            ),
        }

        logger.info(
            f"Capacity check: {len(tasks_that_fit)}/{len(tasks)} tasks fit "
            f"({total_minutes}/{capacity_minutes} min, "
            f"{result['capacity_usage_percent']}% capacity)"
        )

        return result

    def suggest_overflow_actions(self, overflow_tasks: list[Task]) -> str:
        """
        Generate human-friendly suggestion for overflow tasks.

        Args:
            overflow_tasks: Tasks that don't fit in today's capacity

        Returns:
            Suggestion message
        """
        if not overflow_tasks:
            return ""

        task_count = len(overflow_tasks)
        task_titles = [task.title for task in overflow_tasks[:3]]

        if task_count == 1:
            message = (
                f"タスク「{task_titles[0]}」は今日の時間内に収まりません。"
                f"明日に回しますか？"
            )
        elif task_count <= 3:
            titles = "、".join(task_titles)
            message = (
                f"{task_count}件のタスク（{titles}）が今日の時間内に収まりません。"
                f"明日に回しますか？"
            )
        else:
            titles = "、".join(task_titles)
            remaining = task_count - 3
            message = (
                f"{task_count}件のタスク（{titles}、他{remaining}件）が"
                f"今日の時間内に収まりません。明日に回しますか？"
            )

        return message

    def build_schedule(
        self,
        tasks: list[Task],
        project_priorities: dict[UUID, int] | None = None,
        start_date: Optional[date] = None,
        capacity_hours: Optional[float] = None,
        max_days: int = 60,
    ) -> ScheduleResponse:
        """
        Build a capacity-aware schedule across multiple days.

        - Tasks can span multiple days.
        - Dependencies are respected.
        """
        if not tasks:
            start = start_date or date.today()
            return ScheduleResponse(
                start_date=start,
                days=[],
                tasks=[],
                unscheduled_task_ids=[],
                excluded_tasks=[],
            )

        start = start_date or date.today()
        capacity_minutes_default = int((capacity_hours or self.default_capacity_hours) * 60)
        project_priorities = project_priorities or {}

        all_task_map = {task.id: task for task in tasks}

        def get_parent_info(task: Task) -> tuple[Optional[UUID], Optional[str]]:
            if not task.parent_id:
                return None, None
            parent = all_task_map.get(task.parent_id)
            return task.parent_id, parent.title if parent else None

        excluded_tasks: list[ExcludedTask] = []
        for task in tasks:
            reason: Optional[str] = None
            if task.status == TaskStatus.WAITING:
                reason = "waiting"
            elif is_parent_task(task, tasks):
                reason = "parent_task"
            if reason:
                parent_id, parent_title = get_parent_info(task)
                excluded_tasks.append(
                    ExcludedTask(
                        task_id=task.id,
                        title=task.title,
                        reason=reason,
                        parent_id=parent_id,
                        parent_title=parent_title,
                    )
                )

        # Filter tasks to schedule (exclude DONE and WAITING, skip parent tasks)
        candidate_tasks = [
            task
            for task in tasks
            if task.status != TaskStatus.DONE
            and task.status != TaskStatus.WAITING
            and not is_parent_task(task, tasks)
        ]
        candidate_ids = {task.id for task in candidate_tasks}

        blocked_task_ids: set[UUID] = set()
        unscheduled_reasons: dict[UUID, str] = {}
        for task in candidate_tasks:
            if not task.dependency_ids:
                continue
            reason: Optional[str] = None
            for dep_id in task.dependency_ids:
                dep_task = all_task_map.get(dep_id)
                if dep_task is None:
                    reason = "dependency_missing"
                    break
                if dep_task.status != TaskStatus.DONE and dep_id not in candidate_ids:
                    reason = "dependency_unresolved"
                    break
            if reason:
                blocked_task_ids.add(task.id)
                unscheduled_reasons[task.id] = reason

        scheduled_tasks = [task for task in candidate_tasks if task.id not in blocked_task_ids]

        if not scheduled_tasks:
            tasks_info = [
                TaskScheduleInfo(
                    task_id=task.id,
                    title=task.title,
                    project_id=task.project_id,
                    parent_id=get_parent_info(task)[0],
                    parent_title=get_parent_info(task)[1],
                    due_date=task.due_date,
                    planned_start=None,
                    planned_end=None,
                    total_minutes=get_effective_estimated_minutes(task, tasks) or self.default_task_minutes,
                    priority_score=self._calculate_task_score(task, project_priorities, start),
                )
                for task in candidate_tasks
            ]
            unscheduled_items = [
                UnscheduledTask(task_id=task_id, reason=unscheduled_reasons.get(task_id, "dependency_unresolved"))
                for task_id in blocked_task_ids
            ]
            return ScheduleResponse(
                start_date=start,
                days=[],
                tasks=tasks_info,
                unscheduled_task_ids=unscheduled_items,
                excluded_tasks=excluded_tasks,
            )

        task_map = {task.id: task for task in scheduled_tasks}
        remaining_minutes: dict[UUID, int] = {}
        base_scores: dict[UUID, float] = {}

        for task in candidate_tasks:
            base_scores[task.id] = self._calculate_base_score(task, project_priorities)

        for task in scheduled_tasks:
            minutes = get_effective_estimated_minutes(task, tasks)
            remaining_minutes[task.id] = minutes if minutes > 0 else self.default_task_minutes

        # Build dependency graph within scheduled tasks
        task_ids = set(task_map.keys())
        dependents: dict[UUID, list[UUID]] = {task_id: [] for task_id in task_ids}
        indegree: dict[UUID, int] = {task_id: 0 for task_id in task_ids}

        for task in scheduled_tasks:
            relevant_deps = [dep_id for dep_id in task.dependency_ids if dep_id in task_ids]
            for dep_id in relevant_deps:
                dependents[dep_id].append(task.id)
                indegree[task.id] += 1

        ready = [task_id for task_id, count in indegree.items() if count == 0]
        in_progress: list[UUID] = []

        task_start: dict[UUID, date] = {}
        task_end: dict[UUID, date] = {}

        days: list[ScheduleDay] = []
        day_cursor = start
        remaining_task_ids = set(task_ids)
        safety_limit = max_days

        ended_due_to_limit = False
        ended_due_to_cycle = False

        while remaining_task_ids and safety_limit > 0:
            capacity_remaining = capacity_minutes_default
            allocations: list[TaskAllocation] = []
            allocated_minutes = 0
            overflow_minutes = 0
            energy_minutes = {EnergyLevel.HIGH: 0, EnergyLevel.LOW: 0}
            day_scores = {
                task_id: base_scores[task_id] + self._calculate_due_bonus(task_map[task_id], day_cursor)
                for task_id in task_map
            }

            forced_today = [
                task_id
                for task_id in ready + in_progress
                if task_map[task_id].due_date
                and task_map[task_id].due_date.date() <= day_cursor
            ]

            if forced_today:
                for task_id in self._sort_task_ids(forced_today, day_scores, task_map):
                    minutes = remaining_minutes.get(task_id, 0)
                    if minutes <= 0:
                        continue
                    if task_id not in task_start:
                        task_start[task_id] = day_cursor
                    allocations.append(TaskAllocation(task_id=task_id, minutes=minutes))
                    allocated_minutes += minutes
                    capacity_remaining -= minutes
                    remaining_minutes[task_id] = 0
                    task_end[task_id] = day_cursor
                    energy_minutes[task_map[task_id].energy_level] += minutes
                    if task_id in in_progress:
                        in_progress.remove(task_id)
                    if task_id in ready:
                        ready.remove(task_id)
                    remaining_task_ids.discard(task_id)
                    self._release_dependents(task_id, indegree, dependents, ready)

                if capacity_remaining < 0:
                    overflow_minutes = abs(capacity_remaining)
                if capacity_remaining <= 0:
                    days.append(
                        ScheduleDay(
                            date=day_cursor,
                            capacity_minutes=capacity_minutes_default,
                            allocated_minutes=allocated_minutes,
                            overflow_minutes=overflow_minutes,
                            task_allocations=allocations,
                        )
                    )
                    day_cursor += timedelta(days=1)
                    safety_limit -= 1
                    continue

            # Normal scheduling within remaining capacity
            while capacity_remaining > 0 and (ready or in_progress):
                candidate_pool = in_progress if in_progress else ready
                next_id = self._pick_next_task(candidate_pool, day_scores, task_map, energy_minutes)
                minutes_left = remaining_minutes.get(next_id, 0)
                if minutes_left <= 0:
                    if next_id in in_progress:
                        in_progress.remove(next_id)
                    if next_id in ready:
                        ready.remove(next_id)
                    continue

                allocation = min(capacity_remaining, minutes_left)
                if next_id not in task_start:
                    task_start[next_id] = day_cursor

                allocations.append(TaskAllocation(task_id=next_id, minutes=allocation))
                allocated_minutes += allocation
                remaining_minutes[next_id] = minutes_left - allocation
                capacity_remaining -= allocation
                energy_minutes[task_map[next_id].energy_level] += allocation

                if remaining_minutes[next_id] == 0:
                    task_end[next_id] = day_cursor
                    remaining_task_ids.discard(next_id)
                    if next_id in in_progress:
                        in_progress.remove(next_id)
                    if next_id in ready:
                        ready.remove(next_id)
                    self._release_dependents(next_id, indegree, dependents, ready)
                else:
                    if next_id in ready:
                        ready.remove(next_id)
                    if next_id not in in_progress:
                        in_progress.append(next_id)

            days.append(
                ScheduleDay(
                    date=day_cursor,
                    capacity_minutes=capacity_minutes_default,
                    allocated_minutes=allocated_minutes,
                    overflow_minutes=overflow_minutes,
                    task_allocations=allocations,
                )
            )
            day_cursor += timedelta(days=1)
            safety_limit -= 1

            if not ready and not in_progress and remaining_task_ids:
                ended_due_to_cycle = True
                break

        if remaining_task_ids and safety_limit <= 0:
            ended_due_to_limit = True

        tasks_info: list[TaskScheduleInfo] = []
        tasks_for_info = scheduled_tasks + [task for task in candidate_tasks if task.id in blocked_task_ids]
        for task in tasks_for_info:
            total_minutes = get_effective_estimated_minutes(task, tasks) or self.default_task_minutes
            if task.id in remaining_task_ids:
                total_minutes = remaining_minutes.get(task.id, total_minutes)
            tasks_info.append(
                TaskScheduleInfo(
                    task_id=task.id,
                    title=task.title,
                    project_id=task.project_id,
                    parent_id=get_parent_info(task)[0],
                    parent_title=get_parent_info(task)[1],
                    due_date=task.due_date,
                    planned_start=task_start.get(task.id),
                    planned_end=task_end.get(task.id),
                    total_minutes=total_minutes,
                    priority_score=self._calculate_task_score(
                        task,
                        project_priorities,
                        task_start.get(task.id, start),
                    ),
                )
            )

        for task_id in remaining_task_ids:
            if task_id in unscheduled_reasons:
                continue
            if ended_due_to_limit:
                unscheduled_reasons[task_id] = "max_days_exceeded"
            elif ended_due_to_cycle:
                unscheduled_reasons[task_id] = "dependency_cycle"
            else:
                unscheduled_reasons[task_id] = "unscheduled"

        unscheduled_task_ids = [
            UnscheduledTask(task_id=task_id, reason=unscheduled_reasons.get(task_id, "unscheduled"))
            for task_id in sorted(unscheduled_reasons.keys())
        ]
        return ScheduleResponse(
            start_date=start,
            days=days,
            tasks=tasks_info,
            unscheduled_task_ids=unscheduled_task_ids,
            excluded_tasks=excluded_tasks,
        )

    def get_today_tasks(
        self,
        schedule: ScheduleResponse,
        tasks: list[Task],
        project_priorities: dict[UUID, int] | None = None,
        today: Optional[date] = None,
    ) -> TodayTasksResponse:
        """Extract today's tasks and top3 from schedule."""
        today_date = today or date.today()
        task_map = {task.id: task for task in tasks}
        project_priorities = project_priorities or {}

        today_day = next((day for day in schedule.days if day.date == today_date), None)
        today_task_ids: list[UUID] = []
        allocated_minutes = 0
        overflow_minutes = 0
        capacity_minutes = 0
        allocation_minutes_by_task: dict[UUID, int] = {}

        if today_day:
            seen: set[UUID] = set()
            for alloc in today_day.task_allocations:
                allocation_minutes_by_task[alloc.task_id] = (
                    allocation_minutes_by_task.get(alloc.task_id, 0) + alloc.minutes
                )
                if alloc.task_id in seen:
                    continue
                seen.add(alloc.task_id)
                today_task_ids.append(alloc.task_id)
            allocated_minutes = today_day.allocated_minutes
            overflow_minutes = today_day.overflow_minutes
            capacity_minutes = today_day.capacity_minutes

        today_tasks = [task_map[task_id] for task_id in today_task_ids if task_id in task_map]
        today_allocations: list[TodayTaskAllocation] = []
        for task_id in today_task_ids:
            task = task_map.get(task_id)
            if not task:
                continue
            total_minutes = get_effective_estimated_minutes(task, tasks)
            if total_minutes <= 0:
                total_minutes = self.default_task_minutes
            allocated_for_day = allocation_minutes_by_task.get(task_id, 0)
            ratio = allocated_for_day / total_minutes if total_minutes > 0 else 0.0
            today_allocations.append(
                TodayTaskAllocation(
                    task_id=task_id,
                    allocated_minutes=allocated_for_day,
                    total_minutes=total_minutes,
                    ratio=min(1.0, max(0.0, ratio)),
                )
            )
        today_tasks_sorted = today_tasks
        top3_ids = [task.id for task in today_tasks_sorted[:3]]

        return TodayTasksResponse(
            today=today_date,
            today_tasks=today_tasks_sorted,
            today_allocations=today_allocations,
            top3_ids=top3_ids,
            total_estimated_minutes=allocated_minutes,
            capacity_minutes=capacity_minutes,
            overflow_minutes=overflow_minutes,
            overflow=overflow_minutes > 0,
        )

    def _calculate_task_score(
        self,
        task: Task,
        project_priorities: dict[UUID, int],
        reference_date: date,
    ) -> float:
        """Calculate a scheduling score for a task at a given date."""
        base_score = self._calculate_base_score(task, project_priorities)
        return base_score + self._calculate_due_bonus(task, reference_date)

    def _calculate_base_score(self, task: Task, project_priorities: dict[UUID, int]) -> float:
        """Calculate stable base score for a task (no due-date contribution)."""
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

        score = 0.0
        score += importance_weights.get(task.importance, 1.0) * 10
        score += urgency_weights.get(task.urgency, 1.0) * 8

        if task.status == TaskStatus.IN_PROGRESS:
            score += 2

        if task.energy_level == EnergyLevel.LOW:
            score += 1

        project_priority = 5
        if task.project_id and task.project_id in project_priorities:
            project_priority = project_priorities[task.project_id]
        score *= 1 + (project_priority * self.project_priority_weight)
        return score

    @staticmethod
    def _calculate_due_bonus(task: Task, reference_date: date) -> float:
        """Calculate due-date bonus that increases toward the due date."""
        if not task.due_date:
            return 0.0

        due_date = task.due_date.date()
        days_until = (due_date - reference_date).days
        max_bonus = 30.0
        horizon_days = 14

        if days_until <= 0:
            return max_bonus
        if days_until >= horizon_days:
            return 0.0

        step = max_bonus / horizon_days
        return max(0.0, max_bonus - (days_until * step))

    @staticmethod
    def _sort_task_ids(
        task_ids: list[UUID],
        scores: dict[UUID, float],
        task_map: dict[UUID, Task],
    ) -> list[UUID]:
        return sorted(
            task_ids,
            key=lambda task_id: (
                -scores.get(task_id, 0.0),
                task_map[task_id].due_date or datetime.max,
                task_map[task_id].created_at,
            ),
        )

    def _pick_next_task(
        self,
        task_ids: list[UUID],
        scores: dict[UUID, float],
        task_map: dict[UUID, Task],
        energy_minutes: dict[EnergyLevel, int],
    ) -> UUID:
        if not task_ids:
            raise ValueError("No task IDs available for scheduling")

        total_minutes = energy_minutes[EnergyLevel.HIGH] + energy_minutes[EnergyLevel.LOW]
        preferred_energy: Optional[EnergyLevel] = None

        if total_minutes > 0:
            high_ratio = energy_minutes[EnergyLevel.HIGH] / total_minutes
            low_ratio = energy_minutes[EnergyLevel.LOW] / total_minutes
            if high_ratio > self.energy_high_ratio:
                preferred_energy = EnergyLevel.LOW
            elif low_ratio > self.energy_low_ratio:
                preferred_energy = EnergyLevel.HIGH

        if preferred_energy:
            preferred_ids = [
                task_id
                for task_id in task_ids
                if task_map[task_id].energy_level == preferred_energy
            ]
            if preferred_ids:
                task_ids = preferred_ids

        return self._sort_task_ids(task_ids, scores, task_map)[0]

    @staticmethod
    def _release_dependents(
        task_id: UUID,
        indegree: dict[UUID, int],
        dependents: dict[UUID, list[UUID]],
        ready: list[UUID],
    ) -> None:
        for dependent_id in dependents.get(task_id, []):
            indegree[dependent_id] -= 1
            if indegree[dependent_id] <= 0 and dependent_id not in ready:
                ready.append(dependent_id)
