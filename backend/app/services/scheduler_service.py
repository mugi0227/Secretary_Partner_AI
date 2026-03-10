"""
Scheduler service for capacity-aware task scheduling.

Handles task scheduling with capacity constraints and dependency resolution.
"""

import math
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.logger import setup_logger
from app.models.collaboration import ProjectMember, TaskAssignment
from app.models.enums import EnergyLevel, Priority, TaskStatus
from app.models.schedule import (
    ExcludedTask,
    ScheduleDay,
    ScheduleResponse,
    TaskAllocation,
    TaskScheduleInfo,
    TodayTaskAllocation,
    TodayTasksResponse,
    UnscheduledTask,
)
from app.models.task import Task
from app.services.slack_engine import compute_all_slack
from app.services.task_utils import (
    get_effective_estimated_minutes,
    get_remaining_minutes,
    is_parent_task,
)
from app.utils.datetime_utils import ensure_utc, normalize_timezone

logger = setup_logger(__name__)

_UTC = ZoneInfo("UTC")


def _pinned_local_date(pinned_date: datetime, tz: ZoneInfo) -> date:
    """Extract the local date from a UTC pinned_date.

    Naive datetimes are assumed UTC (backend convention).
    """
    if pinned_date.tzinfo is None:
        pinned_date = pinned_date.replace(tzinfo=_UTC)
    return pinned_date.astimezone(tz).date()


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

    @staticmethod
    def _to_local_datetime(value: datetime, timezone: str) -> datetime:
        """Convert a datetime to the user's local timezone."""
        tz = ZoneInfo(normalize_timezone(timezone))
        utc_value = ensure_utc(value)
        if utc_value is None:
            raise ValueError("datetime value is required")
        return utc_value.astimezone(tz)

    def _get_meetings_for_day(
        self,
        tasks: list[Task],
        target_date: date,
        user_timezone: str = "UTC",
    ) -> tuple[list[Task], int]:
        """
        Get meetings scheduled for a specific day and calculate total duration.

        Handles overlapping meetings by merging time intervals to avoid
        double-counting overlapping periods.

        Args:
            tasks: All tasks
            target_date: Date to check
            user_timezone: User's timezone for date comparison

        Returns:
            (list of meeting tasks, total meeting minutes accounting for overlaps)
        """
        meetings = [
            task for task in tasks
            if task.is_fixed_time
            and task.start_time
            and self._to_local_datetime(task.start_time, user_timezone).date() == target_date
        ]

        if not meetings:
            return meetings, 0

        # Create list of time intervals (start_minutes, end_minutes from midnight)
        intervals = []
        for meeting in meetings:
            if meeting.end_time and meeting.start_time:
                # Convert to local timezone for correct hour/minute extraction
                local_start = self._to_local_datetime(meeting.start_time, user_timezone)
                local_end = self._to_local_datetime(meeting.end_time, user_timezone)

                start_mins = local_start.hour * 60 + local_start.minute
                end_mins = local_end.hour * 60 + local_end.minute

                # Handle meetings that span midnight (rare but possible)
                if end_mins < start_mins:
                    end_mins = 24 * 60  # Cap at end of day

                intervals.append((start_mins, end_mins))

        # Sort intervals by start time
        intervals.sort()

        # Merge overlapping intervals
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                # Overlaps with previous interval, merge them
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                # No overlap, add as new interval
                merged.append((start, end))

        # Calculate total minutes from merged intervals
        total_minutes = sum(end - start for start, end in merged)

        return meetings, total_minutes

    def _calculate_meeting_minutes_per_user(
        self,
        meetings: list[Task],
        user_timezone: str = "UTC",
    ) -> dict[str, int]:
        """
        Calculate meeting minutes per user, handling overlapping meetings.

        Groups meetings by user_id and merges overlapping intervals for each user
        to avoid double-counting when the same user has multiple overlapping meetings.

        Args:
            meetings: List of meeting tasks for a specific day
            user_timezone: User's timezone for correct time extraction

        Returns:
            Dictionary mapping user_id to total meeting minutes (with overlaps merged)
        """
        from collections import defaultdict

        # Group meetings by user_id
        user_intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)

        for meeting in meetings:
            if not meeting.end_time or not meeting.start_time:
                continue

            user_id = meeting.user_id
            if not user_id:
                continue

            # Convert to local timezone for correct hour/minute extraction
            local_start = self._to_local_datetime(meeting.start_time, user_timezone)
            local_end = self._to_local_datetime(meeting.end_time, user_timezone)

            start_mins = local_start.hour * 60 + local_start.minute
            end_mins = local_end.hour * 60 + local_end.minute

            # Handle meetings that span midnight
            if end_mins < start_mins:
                end_mins = 24 * 60

            user_intervals[user_id].append((start_mins, end_mins))

        # Calculate merged duration for each user
        result: dict[str, int] = {}

        for user_id, intervals in user_intervals.items():
            if not intervals:
                result[user_id] = 0
                continue

            # Sort and merge overlapping intervals
            intervals.sort()
            merged = []
            for start, end in intervals:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))

            result[user_id] = sum(end - start for start, end in merged)

        return result

    def build_schedule(
        self,
        tasks: list[Task],
        project_priorities: dict[UUID, int] | None = None,
        start_date: Optional[date] = None,
        capacity_hours: Optional[float] = None,
        capacity_by_weekday: Optional[list[float]] = None,
        capacity_ratio: Optional[float] = None,
        max_days: int = 60,
        current_user_id: Optional[str] = None,
        assignments: Optional[list[TaskAssignment]] = None,
        members: Optional[list[ProjectMember]] = None,
        filter_by_assignee: bool = False,
        planned_window_by_task: Optional[dict[UUID, tuple[Optional[date], Optional[date]]]] = None,
        user_timezone: str = "UTC",
        team_project_ids: Optional[set[UUID]] = None,
    ) -> ScheduleResponse:
        """
        Build a capacity-aware schedule across multiple days.

        - Tasks can span multiple days.
        - Dependencies are respected.
        - Supports multi-user capacity if members and assignments are provided.
        """
        user_timezone = normalize_timezone(user_timezone)
        tz = ZoneInfo(user_timezone)
        local_today = datetime.now(tz).date()
        if not tasks:
            start = start_date or local_today
            return ScheduleResponse(
                start_date=start,
                days=[],
                tasks=[],
                unscheduled_task_ids=[],
                excluded_tasks=[],
            )

        start = start_date or local_today
        project_priorities = project_priorities or {}
        capacity_by_weekday = capacity_by_weekday if capacity_by_weekday and len(capacity_by_weekday) == 7 else None
        capacity_ratio = 1.0 if capacity_ratio is None else capacity_ratio

        # --- 1. Setup Member Capacities ---
        # Map user_id -> capacity_hours (default)
        user_capacity_map: dict[str, float] = {}
        if members:
            for m in members:
                user_capacity_map[m.member_user_id] = m.capacity_hours or self.default_capacity_hours

        # Fallback for unassigned or unknown users
        default_cap = capacity_hours or self.default_capacity_hours

        def get_user_capacity_minutes(user_id: str | None, day: date) -> int:
            if capacity_by_weekday:
                # If global weekday pattern is set, applying it to base hours?
                # Or overriding? Let's assume global weekday override for simplicity,
                # or perhaps scale individual capacity?
                # For now, simplistic approach: use capacity_by_weekday if set globally, ignoring individual diffs
                # unless we want complex logic.
                # Let's prioritize individual capacity if set, else global pattern.
                if user_id and user_id in user_capacity_map:
                    base = user_capacity_map[user_id]
                    # Maybe scale by weekday factor?
                    # detailed implementation omitted for brevity, using base for now
                    return max(0, int(base * capacity_ratio * 60))

                weekday_index = (day.weekday() + 1) % 7
                hours = capacity_by_weekday[weekday_index]
                return max(0, int(hours * capacity_ratio * 60))

            if user_id and user_id in user_capacity_map:
                return max(0, int(user_capacity_map[user_id] * capacity_ratio * 60))
            return max(0, int(default_cap * capacity_ratio * 60))

        # Build Assignment Map
        assignment_map: dict[UUID, str] = {}
        if assignments:
            for a in assignments:
                assignment_map[a.task_id] = a.assignee_id

        # Determine "Project Owner" or Default Resource for unassigned tasks
        # If current_user_id is passed, use that?
        default_assignee = current_user_id or "unassigned"

        all_task_map = {task.id: task for task in tasks}
        subtasks_by_parent: dict[UUID, set[UUID]] = {}
        for task in tasks:
            if task.parent_id:
                subtasks_by_parent.setdefault(task.parent_id, set()).add(task.id)
        effective_start_by_task, effective_due_by_task = self._get_effective_constraints(
            tasks,
            planned_window_by_task=planned_window_by_task,
            reference_today=local_today,
            user_timezone=user_timezone,
        )
        effective_due_date_by_task: dict[UUID, date] = {
            task_id: due.date() for task_id, due in effective_due_by_task.items()
        }

        def get_parent_info(task: Task) -> tuple[Optional[UUID], Optional[str]]:
            if not task.parent_id:
                return None, None
            parent = all_task_map.get(task.parent_id)
            return task.parent_id, parent.title if parent else None

        def is_touchpoint_task(task: Task) -> bool:
            return bool(
                task.touchpoint_count
                or task.touchpoint_minutes
                or task.touchpoint_gap_days
                or task.touchpoint_steps
            )

        def get_touchpoint_limit(task: Task, total_minutes: int) -> Optional[int]:
            if task.touchpoint_minutes:
                return task.touchpoint_minutes
            count = task.touchpoint_count or (len(task.touchpoint_steps) if task.touchpoint_steps else None)
            if count:
                return max(1, math.ceil(total_minutes / count))
            if task.touchpoint_gap_days:
                return min(total_minutes, self.default_task_minutes)
            return None

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

        # Filter tasks to schedule
        candidate_tasks = [
            task
            for task in tasks
            if task.status != TaskStatus.DONE
            and (task.status != TaskStatus.WAITING or task.requires_all_completion)
            and not is_parent_task(task, tasks)
            and not task.is_fixed_time
        ]

        # Filter by assignee if requested
        if filter_by_assignee and current_user_id and assignments is not None:
            # Build set of assignees per task (supports multiple assignees)
            assignees_by_task: dict[UUID, set[str]] = {}
            for a in assignments:
                if a.task_id not in assignees_by_task:
                    assignees_by_task[a.task_id] = set()
                assignees_by_task[a.task_id].add(a.assignee_id)

            _team_ids = team_project_ids or set()

            def is_my_task(task: Task) -> bool:
                if not task.project_id:
                    return True  # Personal tasks (Inbox/Memo) always included
                if task.project_id not in _team_ids:
                    return True  # PRIVATE project task - always include
                # TEAM project: only if assigned to me
                assignees = assignees_by_task.get(task.id)
                if not assignees:
                    return False  # Unassigned TEAM project tasks excluded
                if current_user_id not in assignees:
                    return False
                # Exclude requires_all_completion tasks where I already checked
                if task.requires_all_completion and task.status == TaskStatus.WAITING:
                    my_assignment = next(
                        (a for a in assignments if a.task_id == task.id and a.assignee_id == current_user_id),
                        None,
                    )
                    if my_assignment and my_assignment.status == TaskStatus.DONE:
                        return False
                return True

            # Pinned tasks bypass assignee filter — the user explicitly chose
            # to pin this task to a date, so it must appear in the schedule.
            candidate_tasks = [
                t for t in candidate_tasks
                if is_my_task(t)
                or (t.pinned_date and _pinned_local_date(t.pinned_date, tz) >= local_today)
            ]

        candidate_ids = {task.id for task in candidate_tasks}

        # Check dependencies
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
                    order_in_parent=task.order_in_parent,
                    due_date=effective_due_by_task.get(task.id, task.due_date),
                    planned_start=None,
                    planned_end=None,
                    total_minutes=get_effective_estimated_minutes(task, tasks) or self.default_task_minutes,
                    priority_score=self._calculate_task_score(task, project_priorities, start),
                    pinned_date=_pinned_local_date(task.pinned_date, tz) if task.pinned_date else None,
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

        def is_available(task_id: UUID, day: date) -> bool:
            not_before = effective_start_by_task.get(task_id)
            return not_before is None or not_before <= day

        remaining_minutes: dict[UUID, int] = {}
        total_minutes_by_task: dict[UUID, int] = {}
        last_scheduled_day_by_task: dict[UUID, date] = {}
        base_scores: dict[UUID, float] = {}

        for task in candidate_tasks:
            base_scores[task.id] = self._calculate_base_score(task, project_priorities)

        # Compute slack for two-tier priority sort
        # 将来日起点の場合、slack計算もその日を基準にする（利用可能日数を過大評価しない）
        tz = ZoneInfo(user_timezone)
        actual_now = datetime.now(tz)
        slack_reference = max(actual_now, datetime.combine(start, actual_now.time(), tzinfo=tz))
        effective_daily_cap_minutes = int(default_cap * capacity_ratio * 60)
        slack_summary = compute_all_slack(
            tasks=tasks,
            daily_capacity_minutes=effective_daily_cap_minutes,
            user_timezone=user_timezone,
            now=slack_reference,
        )

        for task in scheduled_tasks:
            total_minutes = get_effective_estimated_minutes(task, tasks)
            if total_minutes <= 0:
                total_minutes = self.default_task_minutes
            total_minutes_by_task[task.id] = total_minutes
            minutes = get_remaining_minutes(task, tasks)
            if minutes <= 0:
                minutes = total_minutes
            remaining_minutes[task.id] = minutes if minutes > 0 else self.default_task_minutes

        # Build dependency graph
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
            # --- Per-Day scheduling ---

            # 1. Identify active users for this day (all members + default)
            active_users = set(user_capacity_map.keys()) | {default_assignee}
            # Add anyone who has assigned tasks
            for task_id in remaining_task_ids:
                uid = assignment_map.get(task_id, default_assignee)
                active_users.add(uid)

            # Initialize capacity for each user for today
            user_capacities: dict[str, int] = {}
            for uid in active_users:
                user_capacities[uid] = get_user_capacity_minutes(uid if uid != "unassigned" else None, day_cursor)

            # Reduce capacity by fixed meetings
            day_meetings, meeting_minutes = self._get_meetings_for_day(tasks, day_cursor, user_timezone)

            # Check for all-day tasks and zero out capacity for affected users
            all_day_user_ids: set[str] = set()
            for meeting in day_meetings:
                if meeting.is_all_day:
                    meeting_user_id = assignment_map.get(meeting.id, meeting.user_id)
                    all_day_user_ids.add(meeting_user_id)

            for user_id in all_day_user_ids:
                if user_id in user_capacities:
                    user_capacities[user_id] = 0

            # Calculate meeting minutes per user with overlap handling
            # This prevents double-counting when the same user has multiple overlapping meetings
            meeting_minutes_per_user = self._calculate_meeting_minutes_per_user(day_meetings, user_timezone)

            # Subtract meeting time from each user's capacity (with overlaps already merged)
            # Skip users who already have capacity=0 due to all-day tasks
            for user_id, minutes in meeting_minutes_per_user.items():
                if user_id in user_capacities and user_id not in all_day_user_ids:
                    user_capacities[user_id] = max(0, user_capacities[user_id] - minutes)

            # Map meeting ID to allocations for reporting
            energy_minutes = {
                EnergyLevel.HIGH: meeting_minutes,
                EnergyLevel.MEDIUM: 0,
                EnergyLevel.LOW: 0,
            }
            warmup_pending = True
            cooldown_for_high = False
            scheduled_today_by_parent: dict[UUID, set[UUID]] = {}
            touchpoint_allocated_today: set[UUID] = set()
            allocations: list[TaskAllocation] = []

            for meeting in day_meetings:
                duration = int((meeting.end_time - meeting.start_time).total_seconds() / 60)
                allocations.append(TaskAllocation(task_id=meeting.id, minutes=duration))

                task_start[meeting.id] = day_cursor
                task_end[meeting.id] = day_cursor
                if meeting.id in remaining_task_ids:
                    remaining_task_ids.discard(meeting.id)
                    remaining_minutes[meeting.id] = 0

            # Calculate total capacity for reporting (sum of all users)
            original_capacities = {uid: get_user_capacity_minutes(uid if uid != "unassigned" else None, day_cursor) for uid in active_users}
            capacity_minutes_today = sum(original_capacities.values())

            # Force-schedule pinned tasks for this day (bypass capacity AND
            # start_not_before — pinned_date is the strongest user signal)
            pinned_for_day = [
                tid for tid in list(ready) + list(in_progress)
                if tid in remaining_task_ids
                and task_map[tid].pinned_date
                and _pinned_local_date(task_map[tid].pinned_date, tz) == day_cursor
                and remaining_minutes.get(tid, 0) > 0
            ]
            pinned_allocated_minutes = 0
            for tid in pinned_for_day:
                if tid not in task_start:
                    task_start[tid] = day_cursor
                task = task_map.get(tid)
                total_minutes = total_minutes_by_task.get(tid, self.default_task_minutes)
                limit = get_touchpoint_limit(task, total_minutes) if task else None
                force_mins = remaining_minutes[tid]
                if limit:
                    force_mins = min(force_mins, limit)
                allocations.append(TaskAllocation(task_id=tid, minutes=force_mins))
                assignee = assignment_map.get(tid, default_assignee)
                user_capacities[assignee] = max(0, user_capacities.get(assignee, 0) - force_mins)
                pinned_allocated_minutes += force_mins
                if task and task.energy_level in energy_minutes:
                    energy_minutes[task.energy_level] += force_mins
                if task and task.parent_id:
                    scheduled_today_by_parent.setdefault(task.parent_id, set()).add(tid)
                if task and is_touchpoint_task(task):
                    touchpoint_allocated_today.add(tid)
                last_scheduled_day_by_task[tid] = day_cursor
                remaining_minutes[tid] = max(0, remaining_minutes[tid] - force_mins)
                if remaining_minutes[tid] <= 0:
                    task_end[tid] = day_cursor
                    remaining_task_ids.discard(tid)
                    if tid in in_progress:
                        in_progress.remove(tid)
                    if tid in ready:
                        ready.remove(tid)
                    self._release_dependents(tid, indegree, dependents, ready)
                else:
                    task_end[tid] = day_cursor
                    if tid in ready:
                        ready.remove(tid)
                    if tid not in in_progress:
                        in_progress.append(tid)
                if warmup_pending:
                    warmup_pending = False
                if task and task.energy_level == EnergyLevel.HIGH:
                    cooldown_for_high = True
                elif task and task.energy_level == EnergyLevel.LOW:
                    cooldown_for_high = False

            # 2. Schedule Ready Tasks
            # We loop until no more tasks can be scheduled today for ANY user

            day_scores = {
                task_id: base_scores[task_id]
                + self._calculate_due_bonus_for_date(
                    effective_due_date_by_task.get(task_id),
                    day_cursor,
                )
                for task_id in task_map
            }

            allocated_minutes_total = 0

            def can_schedule_today(task_id: UUID) -> bool:
                task = task_map.get(task_id)
                if not task:
                    return False
                if task.parent_id:
                    siblings_today = scheduled_today_by_parent.get(task.parent_id, set()) - {task_id}
                    if not task.same_day_allowed and siblings_today:
                        return False
                    gap_days = task.min_gap_days or 0
                    if gap_days > 0:
                        sibling_days = [
                            last_scheduled_day_by_task.get(sid)
                            for sid in subtasks_by_parent.get(task.parent_id, set())
                            if sid != task_id and last_scheduled_day_by_task.get(sid)
                        ]
                        if sibling_days and (day_cursor - max(sibling_days)).days < gap_days:
                            return False
                if is_touchpoint_task(task):
                    if task_id in touchpoint_allocated_today:
                        return False
                    gap_days = task.touchpoint_gap_days or 0
                    if gap_days > 0:
                        last_day = last_scheduled_day_by_task.get(task_id)
                        if last_day and (day_cursor - last_day).days < gap_days:
                            return False
                return True

            while True:
                # Find available tasks
                available_in_progress = [tid for tid in in_progress if is_available(tid, day_cursor)]
                available_ready = [tid for tid in ready if is_available(tid, day_cursor)]

                # Filter by capacity availability
                # A task is candidate ONLY if its assignee has capacity > 0
                def has_capacity(tid: UUID) -> bool:
                    assignee = assignment_map.get(tid, default_assignee)
                    return user_capacities.get(assignee, 0) > 0

                candidates_ip = [
                    t for t in available_in_progress if has_capacity(t) and can_schedule_today(t)
                ]
                candidates_rd = [
                    t for t in available_ready if has_capacity(t) and can_schedule_today(t)
                ]

                if not candidates_ip and not candidates_rd:
                    break

                # Pick best task
                candidate_pool = candidates_ip if candidates_ip else candidates_rd
                if warmup_pending:
                    low_candidates = [
                        tid for tid in candidate_pool
                        if task_map[tid].energy_level == EnergyLevel.LOW
                    ]
                    if low_candidates:
                        candidate_pool = low_candidates
                if cooldown_for_high:
                    low_candidates = [
                        tid for tid in candidate_pool
                        if task_map[tid].energy_level == EnergyLevel.LOW
                    ]
                    if low_candidates:
                        candidate_pool = low_candidates
                next_id = self._pick_next_task(
                    candidate_pool, day_scores, task_map, energy_minutes,
                    slack_results_by_id=slack_summary.results_by_id,
                )

                minutes_left = remaining_minutes.get(next_id, 0)
                if minutes_left <= 0:
                    # Cleanup zero duration tasks
                    remaining_minutes[next_id] = 0
                    remaining_task_ids.discard(next_id)
                    if next_id in in_progress:
                        in_progress.remove(next_id)
                    if next_id in ready:
                        ready.remove(next_id)
                    self._release_dependents(next_id, indegree, dependents, ready)
                    continue

                assignee = assignment_map.get(next_id, default_assignee)
                cap = user_capacities.get(assignee, 0)

                task = task_map[next_id]
                total_minutes = total_minutes_by_task.get(next_id, self.default_task_minutes)
                limit = get_touchpoint_limit(task, total_minutes)
                allocation = min(cap, minutes_left)
                if limit:
                    allocation = min(allocation, limit)

                if next_id not in task_start:
                    task_start[next_id] = day_cursor

                allocations.append(TaskAllocation(task_id=next_id, minutes=allocation))

                user_capacities[assignee] -= allocation
                remaining_minutes[next_id] -= allocation
                allocated_minutes_total += allocation
                if task.energy_level in energy_minutes:
                    energy_minutes[task.energy_level] += allocation
                if task.parent_id:
                    scheduled_today_by_parent.setdefault(task.parent_id, set()).add(next_id)
                if is_touchpoint_task(task):
                    touchpoint_allocated_today.add(next_id)
                last_scheduled_day_by_task[next_id] = day_cursor
                if warmup_pending:
                    warmup_pending = False
                if task.energy_level == EnergyLevel.HIGH:
                    cooldown_for_high = True
                elif task.energy_level == EnergyLevel.LOW:
                    cooldown_for_high = False

                if remaining_minutes[next_id] <= 0:
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

            # Force-schedule tasks that would exceed their due date if pushed to tomorrow
            # These tasks get scheduled even if over capacity, BUT respect
            # start_not_before so that explicit "明日やる" postpones are honoured.
            forced_overflow_minutes = 0
            for tid in list(in_progress) + list(ready):
                due_dt = effective_due_date_by_task.get(tid)
                if due_dt is None:
                    continue
                # If due date is today or earlier, and task is not yet fully scheduled,
                # AND the task is actually available today (respects start_not_before)
                if due_dt <= day_cursor and tid in remaining_task_ids and remaining_minutes.get(tid, 0) > 0 and is_available(tid, day_cursor):
                    # Force allocate this task today regardless of capacity
                    if tid not in task_start:
                        task_start[tid] = day_cursor

                    force_mins = remaining_minutes[tid]
                    allocations.append(TaskAllocation(task_id=tid, minutes=force_mins))
                    forced_overflow_minutes += force_mins
                    task = task_map.get(tid)
                    if task and task.energy_level in energy_minutes:
                        energy_minutes[task.energy_level] += force_mins
                    if task and task.parent_id:
                        scheduled_today_by_parent.setdefault(task.parent_id, set()).add(tid)
                    if task and is_touchpoint_task(task):
                        touchpoint_allocated_today.add(tid)
                    last_scheduled_day_by_task[tid] = day_cursor
                    if warmup_pending:
                        warmup_pending = False
                    if task and task.energy_level == EnergyLevel.HIGH:
                        cooldown_for_high = True
                    elif task and task.energy_level == EnergyLevel.LOW:
                        cooldown_for_high = False

                    task_end[tid] = day_cursor
                    remaining_minutes[tid] = 0
                    remaining_task_ids.discard(tid)
                    if tid in in_progress:
                        in_progress.remove(tid)
                    if tid in ready:
                        ready.remove(tid)
                    self._release_dependents(tid, indegree, dependents, ready)

            # End of Day Processing
            # Calculate overflow including forced allocations
            overflow_minutes = forced_overflow_minutes

            days.append(
                ScheduleDay(
                    date=day_cursor,
                    capacity_minutes=capacity_minutes_today,
                    allocated_minutes=allocated_minutes_total + meeting_minutes + forced_overflow_minutes + pinned_allocated_minutes,
                    overflow_minutes=overflow_minutes,
                    task_allocations=allocations,
                    meeting_minutes=meeting_minutes,
                    available_minutes=sum(user_capacities.values()),
                )
            )

            day_cursor += timedelta(days=1)
            safety_limit -= 1

            if not ready and not in_progress and remaining_task_ids:
                ended_due_to_cycle = True
                break

        if remaining_task_ids and safety_limit <= 0:
            ended_due_to_limit = True

        # Collect all meeting tasks that were scheduled
        all_meetings = [task for task in tasks if task.is_fixed_time and task.id in task_start]

        tasks_info: list[TaskScheduleInfo] = []
        tasks_for_info = scheduled_tasks + [task for task in candidate_tasks if task.id in blocked_task_ids] + all_meetings
        for task in tasks_for_info:
            if task.is_fixed_time and task.start_time and task.end_time:
                total_minutes = int((task.end_time - task.start_time).total_seconds() / 60)
                total_minutes = max(0, total_minutes)
            else:
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
                    order_in_parent=task.order_in_parent,
                    due_date=effective_due_by_task.get(task.id, task.due_date),
                    planned_start=task_start.get(task.id),
                    planned_end=task_end.get(task.id),
                    total_minutes=total_minutes,
                    priority_score=self._calculate_task_score(
                        task,
                        project_priorities,
                        task_start.get(task.id, start),
                    ),
                    status=task.status.value if hasattr(task.status, 'value') else str(task.status),
                    pinned_date=_pinned_local_date(task.pinned_date, tz) if task.pinned_date else None,
                    is_fixed_time=task.is_fixed_time,
                    start_time=task.start_time if task.is_fixed_time else None,
                    end_time=task.end_time if task.is_fixed_time else None,
                )
            )

        # Include tasks completed on each scheduled day so they remain
        # visible in the calendar (same pattern as get_today_tasks).
        scheduled_task_ids = {ti.task_id for ti in tasks_info}
        tz = ZoneInfo(user_timezone)
        day_map = {day.date: day for day in days}
        for task in tasks:
            if (
                task.status != TaskStatus.DONE
                or not task.completed_at
                or task.id in scheduled_task_ids
                or task.is_fixed_time
                or is_parent_task(task, tasks)
            ):
                continue
            completed_dt = task.completed_at
            if completed_dt.tzinfo is None:
                completed_dt = completed_dt.replace(tzinfo=ZoneInfo("UTC"))
            completed_date = completed_dt.astimezone(tz).date()
            day = day_map.get(completed_date)
            if day is None:
                continue
            task_mins = get_effective_estimated_minutes(task, tasks)
            if task_mins <= 0:
                task_mins = self.default_task_minutes
            day.task_allocations.append(TaskAllocation(task_id=task.id, minutes=task_mins))
            tasks_info.append(
                TaskScheduleInfo(
                    task_id=task.id,
                    title=task.title,
                    project_id=task.project_id,
                    parent_id=get_parent_info(task)[0],
                    parent_title=get_parent_info(task)[1],
                    order_in_parent=task.order_in_parent,
                    due_date=effective_due_by_task.get(task.id, task.due_date),
                    planned_start=completed_date,
                    planned_end=completed_date,
                    total_minutes=task_mins,
                    priority_score=0.0,
                    status="done",
                    pinned_date=_pinned_local_date(task.pinned_date, tz) if task.pinned_date else None,
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
        user_timezone: str = "UTC",
    ) -> TodayTasksResponse:
        """Extract today's tasks and top3 from schedule."""
        user_timezone = normalize_timezone(user_timezone)
        tz = ZoneInfo(user_timezone)
        today_date = today or datetime.now(tz).date()
        task_map = {task.id: task for task in tasks}
        project_priorities = project_priorities or {}
        _, effective_due_by_task = self._get_effective_constraints(
            tasks,
            reference_today=today_date,
            user_timezone=user_timezone,
        )
        effective_due_date_by_task: dict[UUID, date] = {
            task_id: due.date() for task_id, due in effective_due_by_task.items()
        }

        today_day = next((day for day in schedule.days if day.date == today_date), None)
        today_task_ids: list[UUID] = []
        allocated_minutes = 0
        overflow_minutes = 0
        capacity_minutes = 0
        meeting_minutes = 0
        allocation_minutes_by_task: dict[UUID, int] = {}

        if today_day:
            seen: set[UUID] = set()
            for alloc in today_day.task_allocations:
                task = task_map.get(alloc.task_id)
                if task and task.is_fixed_time:
                    continue
                allocation_minutes_by_task[alloc.task_id] = (
                    allocation_minutes_by_task.get(alloc.task_id, 0) + alloc.minutes
                )
                if alloc.task_id in seen:
                    continue
                seen.add(alloc.task_id)
                today_task_ids.append(alloc.task_id)
            allocated_minutes = sum(allocation_minutes_by_task.values())
            overflow_minutes = today_day.overflow_minutes
            capacity_minutes = today_day.capacity_minutes
            meeting_minutes = today_day.meeting_minutes

        # Ensure pinned_date == today tasks are included even if not in schedule
        for task in tasks:
            if (
                task.pinned_date
                and _pinned_local_date(task.pinned_date, tz) == today_date
                and task.id not in set(today_task_ids)
                and task.id in task_map
                and task.status != TaskStatus.DONE
                and not task.is_fixed_time
            ):
                today_task_ids.append(task.id)

        # Include tasks completed today so they remain visible after unlock
        today_task_id_set = set(today_task_ids)
        for task in tasks:
            if (
                task.status == TaskStatus.DONE
                and task.completed_at
                and task.id not in today_task_id_set
                and not task.is_fixed_time
                and not is_parent_task(task, tasks)
            ):
                completed_dt = task.completed_at
                if completed_dt.tzinfo is None:
                    completed_dt = completed_dt.replace(tzinfo=ZoneInfo("UTC"))
                if completed_dt.astimezone(tz).date() == today_date:
                    today_task_ids.append(task.id)
                    today_task_id_set.add(task.id)
                    task_minutes = get_effective_estimated_minutes(task, tasks)
                    if task_minutes <= 0:
                        task_minutes = self.default_task_minutes
                    allocation_minutes_by_task[task.id] = task_minutes
                    allocated_minutes += task_minutes

        today_tasks = [task_map[task_id] for task_id in today_task_ids if task_id in task_map]
        today_allocations: list[TodayTaskAllocation] = []
        for task_id in today_task_ids:
            task = task_map.get(task_id)
            if not task:
                continue
            # Use remaining minutes (considering progress) for allocation calculation
            remaining_mins = get_remaining_minutes(task, tasks)
            total_minutes = get_effective_estimated_minutes(task, tasks)
            if total_minutes <= 0:
                total_minutes = self.default_task_minutes
            if remaining_mins <= 0:
                remaining_mins = total_minutes

            allocated_for_day = allocation_minutes_by_task.get(task_id, 0)
            # ratio is based on remaining work, not total
            ratio = allocated_for_day / remaining_mins if remaining_mins > 0 else 0.0
            today_allocations.append(
                TodayTaskAllocation(
                    task_id=task_id,
                    allocated_minutes=allocated_for_day,
                    total_minutes=remaining_mins,  # Use remaining as "total" for today's planning
                    ratio=min(1.0, max(0.0, ratio)),
                )
            )
        # Calculate scores for all today's tasks
        task_scores = {
            task.id: self._calculate_base_score(task, project_priorities)
            + self._calculate_due_bonus_for_date(
                effective_due_date_by_task.get(task.id),
                today_date,
            )
            for task in today_tasks
        }

        # Sort by score (descending), then by due date, then by creation time
        today_tasks_sorted = sorted(
            today_tasks,
            key=lambda t: (
                -task_scores[t.id],
                t.due_date or datetime.max,
                t.created_at
            )
        )

        # Filter out tasks blocked by dependencies for Top3 selection
        # A task is blocked if any of its dependencies are not DONE
        unblocked_tasks = []
        for task in today_tasks_sorted:
            if not task.dependency_ids:
                unblocked_tasks.append(task)
                continue
            # Check if all dependencies are completed
            all_deps_done = True
            for dep_id in task.dependency_ids:
                dep_task = task_map.get(dep_id)
                if dep_task is None or dep_task.status != TaskStatus.DONE:
                    all_deps_done = False
                    break
            if all_deps_done:
                unblocked_tasks.append(task)

        # Top 3 are the most important UNBLOCKED tasks based on score
        top3_ids = [task.id for task in unblocked_tasks[:3]]

        return TodayTasksResponse(
            today=today_date,
            today_tasks=today_tasks_sorted,
            today_allocations=today_allocations,
            top3_ids=top3_ids,
            total_estimated_minutes=allocated_minutes,
            capacity_minutes=capacity_minutes,
            meeting_minutes=meeting_minutes,
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
    def _get_effective_constraints(
        tasks: list[Task],
        planned_window_by_task: Optional[dict[UUID, tuple[Optional[date], Optional[date]]]] = None,
        reference_today: Optional[date] = None,
        user_timezone: str = "UTC",
    ) -> tuple[dict[UUID, date], dict[UUID, datetime]]:
        task_map = {task.id: task for task in tasks}
        planned_window_by_task = planned_window_by_task or {}
        effective_start_by_task: dict[UUID, date] = {}
        effective_due_by_task: dict[UUID, datetime] = {}
        today = reference_today or date.today()
        _tz = ZoneInfo(normalize_timezone(user_timezone))

        def get_parent_bounds(task: Task) -> tuple[Optional[datetime], Optional[datetime]]:
            parent_start_candidates: list[datetime] = []
            parent_due_candidates: list[datetime] = []
            parent_id = task.parent_id
            seen: set[UUID] = set()
            while parent_id and parent_id not in seen:
                seen.add(parent_id)
                parent = task_map.get(parent_id)
                if not parent:
                    break
                if parent.start_not_before:
                    parent_start_candidates.append(parent.start_not_before)
                if parent.due_date:
                    parent_due_candidates.append(parent.due_date)
                parent_id = parent.parent_id
            parent_start = max(parent_start_candidates) if parent_start_candidates else None
            parent_due = min(parent_due_candidates) if parent_due_candidates else None
            return parent_start, parent_due

        for task in tasks:
            parent_start, parent_due = get_parent_bounds(task)
            start_dt = task.start_not_before
            if parent_start and (start_dt is None or start_dt < parent_start):
                start_dt = parent_start

            # Pinned date is the strongest signal — unconditionally override
            # start_not_before / parent constraints.  Past pins are ignored
            # so that "今日やる" only lasts for one day.
            if task.pinned_date and _pinned_local_date(task.pinned_date, _tz) >= today:
                # Use local-date midnight so that .date() yields the user's
                # local date, not the UTC date of the stored pinned_date.
                start_dt = datetime.combine(
                    _pinned_local_date(task.pinned_date, _tz), datetime.min.time(),
                )

            planned_start, planned_end = planned_window_by_task.get(task.id, (None, None))
            if planned_start:
                planned_start_dt = datetime.combine(planned_start, datetime.min.time())
                if start_dt is None or start_dt < planned_start_dt:
                    start_dt = planned_start_dt

            due_dt = task.due_date
            if due_dt is None:
                due_dt = parent_due
            elif parent_due and due_dt > parent_due:
                due_dt = parent_due

            if planned_end:
                planned_end_dt = datetime.combine(planned_end, datetime.max.time())
                if due_dt is None or due_dt > planned_end_dt:
                    due_dt = planned_end_dt

            if start_dt and due_dt and due_dt < start_dt:
                if parent_due and parent_due >= start_dt:
                    due_dt = parent_due
                elif parent_due:
                    due_dt = parent_due
                else:
                    due_dt = start_dt

            if start_dt:
                effective_start_by_task[task.id] = start_dt.date()
            if due_dt:
                effective_due_by_task[task.id] = due_dt

        return effective_start_by_task, effective_due_by_task

    @staticmethod
    def _calculate_due_bonus_for_date(due_date: Optional[date], reference_date: date) -> float:
        """Calculate due-date bonus that increases toward the due date."""
        if not due_date:
            return 0.0

        days_until = (due_date - reference_date).days
        max_bonus = 30.0
        horizon_days = 14

        if days_until <= 0:
            return max_bonus
        if days_until >= horizon_days:
            return 0.0

        step = max_bonus / horizon_days
        return max(0.0, max_bonus - (days_until * step))

    def _calculate_due_bonus(self, task: Task, reference_date: date) -> float:
        """Calculate due-date bonus that increases toward the due date."""
        return self._calculate_due_bonus_for_date(
            task.due_date.date() if task.due_date else None,
            reference_date,
        )

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
        slack_results_by_id: Optional[dict] = None,
    ) -> UUID:
        if not task_ids:
            raise ValueError("No task IDs available for scheduling")

        # Energy balancing: prefer under-represented energy level
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

        # Two-tier slack-based sort when slack results are available
        if slack_results_by_id:
            return self._sort_by_slack(task_ids, task_map, slack_results_by_id, scores)

        return self._sort_task_ids(task_ids, scores, task_map)[0]

    @staticmethod
    def _sort_by_slack(
        task_ids: list[UUID],
        task_map: dict[UUID, Task],
        slack_results_by_id: dict,
        scores: dict[UUID, float],
    ) -> UUID:
        """Two-tier sort: danger zone by ratio asc, safe zone by importance desc."""
        from app.services.slack_engine import RATIO_DANGER_ZONE

        importance_weight = {Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}
        inf = float("inf")

        danger: list[UUID] = []
        safe: list[UUID] = []

        for tid in task_ids:
            slack = slack_results_by_id.get(tid)
            if slack and slack.slack_ratio is not None and slack.slack_ratio < RATIO_DANGER_ZONE:
                danger.append(tid)
            else:
                safe.append(tid)

        # Danger zone: ratio ascending (most urgent first)
        danger.sort(
            key=lambda tid: (
                slack_results_by_id[tid].slack_ratio
                if tid in slack_results_by_id and slack_results_by_id[tid].slack_ratio is not None
                else inf,
            )
        )

        # Safe zone: importance descending, then ratio ascending
        safe.sort(
            key=lambda tid: (
                -importance_weight.get(task_map[tid].importance, 1),
                slack_results_by_id[tid].slack_ratio
                if tid in slack_results_by_id and slack_results_by_id[tid].slack_ratio is not None
                else inf,
                -scores.get(tid, 0.0),
            )
        )

        combined = danger + safe
        return combined[0]

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
