"""
Daily schedule plan generation service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.interfaces.project_repository import IProjectRepository
from app.interfaces.schedule_plan_repository import IDailySchedulePlanRepository
from app.interfaces.schedule_settings_repository import IScheduleSettingsRepository
from app.interfaces.schedule_snapshot_repository import IScheduleSnapshotRepository
from app.interfaces.task_assignment_repository import ITaskAssignmentRepository
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.user_repository import IUserRepository
from app.models.enums import ProjectVisibility, TaskStatus
from app.models.schedule import (
    ScheduleDay,
    ScheduleResponse,
    TaskAllocation,
    TaskScheduleInfo,
)
from app.models.schedule_plan import (
    DailySchedulePlanCreate,
    PendingChange,
    SchedulePlanResponse,
    ScheduleSettings,
    ScheduleTimeBlock,
    TaskPlanSnapshot,
    TimeBlockMoveRequest,
    WorkdayHours,
    default_weekly_work_hours,
)
from app.models.task import Task, TaskUpdate
from app.services.scheduler_service import SchedulerService, _pinned_local_date
from app.utils.datetime_utils import ensure_utc, get_user_today, normalize_timezone, now_utc

DEFAULT_PLAN_DAYS = 30


@dataclass
class TimeInterval:
    start_minutes: int
    end_minutes: int


def _parse_time_to_minutes(value: str) -> Optional[int]:
    parts = value.split(":")
    if len(parts) != 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        return None
    return hours * 60 + minutes


def _clone_intervals(intervals: list[TimeInterval]) -> list[TimeInterval]:
    return [TimeInterval(interval.start_minutes, interval.end_minutes) for interval in intervals]


def _subtract_intervals(base: list[TimeInterval], remove: list[TimeInterval]) -> list[TimeInterval]:
    if not remove:
        return base
    intervals = base
    for block in remove:
        next_intervals: list[TimeInterval] = []
        for interval in intervals:
            if block.end_minutes <= interval.start_minutes or block.start_minutes >= interval.end_minutes:
                next_intervals.append(interval)
                continue
            if block.start_minutes > interval.start_minutes:
                next_intervals.append(
                    TimeInterval(interval.start_minutes, min(block.start_minutes, interval.end_minutes))
                )
            if block.end_minutes < interval.end_minutes:
                next_intervals.append(
                    TimeInterval(max(block.end_minutes, interval.start_minutes), interval.end_minutes)
                )
        intervals = next_intervals
    return [interval for interval in intervals if interval.end_minutes > interval.start_minutes]


def _build_work_intervals(workday: WorkdayHours) -> list[TimeInterval]:
    if not workday.enabled:
        return []
    start = _parse_time_to_minutes(workday.start)
    end = _parse_time_to_minutes(workday.end)
    if start is None or end is None or end <= start:
        return []
    base = [TimeInterval(start, end)]
    breaks: list[TimeInterval] = []
    for entry in workday.breaks:
        b_start = _parse_time_to_minutes(entry.start)
        b_end = _parse_time_to_minutes(entry.end)
        if b_start is None or b_end is None or b_end <= b_start:
            continue
        overlap_start = max(start, b_start)
        overlap_end = min(end, b_end)
        if overlap_end <= overlap_start:
            continue
        breaks.append(TimeInterval(overlap_start, overlap_end))
    return _subtract_intervals(base, breaks)


def _clip_intervals(intervals: list[TimeInterval], start_minutes: int) -> list[TimeInterval]:
    clipped: list[TimeInterval] = []
    for interval in intervals:
        if interval.end_minutes <= start_minutes:
            continue
        clipped.append(
            TimeInterval(max(interval.start_minutes, start_minutes), interval.end_minutes)
        )
    return clipped


def _clip_intervals_end(intervals: list[TimeInterval], end_minutes: int) -> list[TimeInterval]:
    clipped: list[TimeInterval] = []
    for interval in intervals:
        if interval.start_minutes >= end_minutes:
            continue
        clipped.append(
            TimeInterval(interval.start_minutes, min(interval.end_minutes, end_minutes))
        )
    return [interval for interval in clipped if interval.end_minutes > interval.start_minutes]


def _to_local_datetime(value: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(normalize_timezone(timezone))
    utc_value = ensure_utc(value)
    if utc_value is None:
        raise ValueError("datetime value is required")
    return utc_value.astimezone(tz)


def _build_capacity_by_weekday(settings: ScheduleSettings) -> list[float]:
    weekly = settings.weekly_work_hours or default_weekly_work_hours()
    capacities: list[float] = []
    for day in weekly:
        intervals = _build_work_intervals(day)
        minutes = sum(interval.end_minutes - interval.start_minutes for interval in intervals)
        capacities.append(round(minutes / 60, 4))
    if len(capacities) != 7:
        capacities = [8.0] * 7
    return capacities


def _apply_capacity_buffer(
    capacity_by_weekday: list[float],
    buffer_hours: float,
) -> list[float]:
    return [max(0.0, hours - buffer_hours) for hours in capacity_by_weekday]


def _task_fingerprint(task: Task) -> str:
    payload = {
        "estimated_minutes": task.estimated_minutes,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "start_not_before": task.start_not_before.isoformat() if task.start_not_before else None,
        "pinned_date": task.pinned_date.isoformat() if task.pinned_date else None,
        "parent_id": str(task.parent_id) if task.parent_id else None,
        "dependency_ids": sorted([str(dep) for dep in task.dependency_ids or []]),
        "same_day_allowed": task.same_day_allowed,
        "min_gap_days": task.min_gap_days,
        "importance": task.importance.value if hasattr(task.importance, "value") else str(task.importance),
        "urgency": task.urgency.value if hasattr(task.urgency, "value") else str(task.urgency),
        "energy_level": task.energy_level.value if hasattr(task.energy_level, "value") else str(task.energy_level),
        "is_fixed_time": task.is_fixed_time,
        "is_all_day": task.is_all_day,
        "start_time": task.start_time.isoformat() if task.start_time else None,
        "end_time": task.end_time.isoformat() if task.end_time else None,
        "touchpoint_count": task.touchpoint_count,
        "touchpoint_minutes": task.touchpoint_minutes,
        "touchpoint_gap_days": task.touchpoint_gap_days,
        "touchpoint_steps": [
            {
                "title": step.title,
                "guide": step.guide,
                "estimated_minutes": step.estimated_minutes,
            }
            for step in (task.touchpoint_steps or [])
        ],
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _plan_params_fingerprint(params: dict) -> str:
    return json.dumps(params, ensure_ascii=True, sort_keys=True)


def _is_done_task(task: Optional[Task]) -> bool:
    if not task:
        return False
    status_value = task.status.value if hasattr(task.status, "value") else str(task.status)
    return status_value == TaskStatus.DONE.value or status_value == "DONE"


def _build_task_snapshots(tasks: list[Task]) -> list[TaskPlanSnapshot]:
    return [
        TaskPlanSnapshot(task_id=task.id, title=task.title, fingerprint=_task_fingerprint(task))
        for task in tasks
    ]


def _merge_task_info_lists(
    *lists: list[TaskScheduleInfo],
) -> list[TaskScheduleInfo]:
    """Merge multiple TaskScheduleInfo lists, deduplicating by task_id (last wins)."""
    seen: dict[UUID, TaskScheduleInfo] = {}
    for info_list in lists:
        for info in info_list:
            seen[info.task_id] = info
    return list(seen.values())


def _merge_task_infos_from_plans(plans: list) -> list[TaskScheduleInfo]:
    """Collect TaskScheduleInfo from all plans, deduplicating by task_id."""
    if not plans:
        return []
    return _merge_task_info_lists(*(plan.tasks for plan in plans))


def _compute_pending_changes(tasks: list[Task], snapshots: list[TaskPlanSnapshot]) -> list[PendingChange]:
    snapshot_map = {snapshot.task_id: snapshot for snapshot in snapshots}
    task_map = {task.id: task for task in tasks}
    pending: list[PendingChange] = []
    for task in tasks:
        snapshot = snapshot_map.get(task.id)
        if not snapshot:
            pending.append(PendingChange(task_id=task.id, title=task.title, change_type="new"))
            continue
        if snapshot.fingerprint != _task_fingerprint(task):
            pending.append(PendingChange(task_id=task.id, title=task.title, change_type="updated"))
    for snapshot_id, snapshot in snapshot_map.items():
        if snapshot_id not in task_map:
            pending.append(PendingChange(task_id=snapshot_id, title=snapshot.title, change_type="removed"))
    return pending


def _build_meeting_intervals(
    tasks: list[Task],
    target_date: date,
    timezone: str,
) -> list[TimeInterval]:
    intervals: list[TimeInterval] = []
    tz = ZoneInfo(timezone)
    for task in tasks:
        if not task.is_fixed_time:
            continue
        if task.is_all_day:
            all_day_date: Optional[date] = None
            if task.start_time:
                all_day_date = _to_local_datetime(task.start_time, timezone).date()
            elif task.start_not_before:
                all_day_date = _to_local_datetime(task.start_not_before, timezone).date()
            elif task.due_date:
                all_day_date = _to_local_datetime(task.due_date, timezone).date()
            if all_day_date != target_date:
                continue
            intervals.append(TimeInterval(0, 24 * 60))
            continue
        if not task.start_time or not task.end_time:
            continue
        start_dt = _to_local_datetime(task.start_time, timezone)
        if start_dt.date() != target_date:
            continue
        end_dt = _to_local_datetime(task.end_time, timezone)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=tz)
        start_mins = start_dt.hour * 60 + start_dt.minute
        end_mins = end_dt.hour * 60 + end_dt.minute
        if end_mins < start_mins:
            end_mins = 24 * 60
        intervals.append(TimeInterval(start_mins, end_mins))
    intervals.sort(key=lambda entry: entry.start_minutes)
    merged: list[TimeInterval] = []
    for interval in intervals:
        if merged and interval.start_minutes <= merged[-1].end_minutes:
            merged[-1].end_minutes = max(merged[-1].end_minutes, interval.end_minutes)
        else:
            merged.append(TimeInterval(interval.start_minutes, interval.end_minutes))
    return merged


def _meeting_minutes_before_now(
    tasks: list[Task],
    target_date: date,
    now_minutes: int,
    timezone: str,
) -> int:
    total = 0
    for interval in _build_meeting_intervals(tasks, target_date, timezone):
        if interval.start_minutes >= now_minutes:
            continue
        total += max(0, min(interval.end_minutes, now_minutes) - interval.start_minutes)
    return total


def _build_time_blocks(
    schedule: ScheduleResponse,
    tasks: list[Task],
    settings: ScheduleSettings,
    timezone: str,
    from_now: bool,
    start_date: date,
) -> tuple[list[ScheduleTimeBlock], dict[date, ScheduleDay], list[UUID]]:
    task_map = {task.id: task for task in tasks}
    work_hours = settings.weekly_work_hours or default_weekly_work_hours()
    break_after = settings.break_after_task_minutes
    tz = ZoneInfo(timezone)
    today = get_user_today(timezone)
    now_minutes = 0
    if from_now and start_date == today:
        now_dt = now_utc().astimezone(tz)
        now_minutes = now_dt.hour * 60 + now_dt.minute

    meeting_blocks_by_day: dict[date, list[ScheduleTimeBlock]] = {}
    meeting_intervals_by_day: dict[date, list[TimeInterval]] = {}
    for day in schedule.days:
        intervals = _build_meeting_intervals(tasks, day.date, timezone)
        meeting_intervals_by_day[day.date] = intervals
        blocks: list[ScheduleTimeBlock] = []
        for task in tasks:
            if not task.is_fixed_time or not task.start_time or not task.end_time:
                continue
            start_dt = _to_local_datetime(task.start_time, timezone)
            if start_dt.date() != day.date:
                continue
            end_dt = _to_local_datetime(task.end_time, timezone)
            blocks.append(
                ScheduleTimeBlock(
                    task_id=task.id,
                    start=start_dt,
                    end=end_dt,
                    kind="meeting",
                    status=task.status.value if hasattr(task.status, "value") else str(task.status),
                    pinned_date=_pinned_local_date(task.pinned_date, tz) if task.pinned_date else None,
                )
            )
        meeting_blocks_by_day[day.date] = blocks

    pinned_overflow: list[UUID] = []
    time_blocks: list[ScheduleTimeBlock] = []
    allocations_by_day: dict[date, list[TaskAllocation]] = {
        day.date: list(day.task_allocations) for day in schedule.days
    }
    remaining_by_task: dict[UUID, int] = {}
    for allocations in allocations_by_day.values():
        for allocation in allocations:
            task = task_map.get(allocation.task_id)
            if task and task.is_fixed_time:
                continue
            remaining_by_task[allocation.task_id] = (
                remaining_by_task.get(allocation.task_id, 0) + allocation.minutes
            )
    carryover: list[TaskAllocation] = []
    done_keep_by_day: dict[date, list[TaskAllocation]] = {}
    for day in schedule.days:
        weekday_index = (day.date.weekday() + 1) % 7
        day_work = work_hours[weekday_index] if weekday_index < len(work_hours) else WorkdayHours(
            enabled=True, start="09:00", end="18:00", breaks=[]
        )
        available_base = _build_work_intervals(day_work)
        available_base = _subtract_intervals(available_base, meeting_intervals_by_day.get(day.date, []))
        available_future = available_base
        if from_now and day.date == start_date:
            available_future = _clip_intervals(available_base, now_minutes)
        available_future = _clone_intervals(available_future)

        done_keep: list[TaskAllocation] = []
        done_ghost_queue: list[TaskAllocation] = []
        active_queue: list[TaskAllocation] = []
        if carryover:
            active_queue.extend(carryover)
            carryover = []

        for allocation in allocations_by_day.get(day.date, []):
            task = task_map.get(allocation.task_id)
            if task and task.is_fixed_time:
                continue
            if from_now and day.date == start_date and _is_done_task(task):
                # Keep done tasks at their original scheduled position as ghost blocks
                # (they don't consume available time so new tasks can overlap).
                done_keep.append(TaskAllocation(task_id=allocation.task_id, minutes=allocation.minutes))
                done_ghost_queue.append(TaskAllocation(task_id=allocation.task_id, minutes=allocation.minutes))
            else:
                active_queue.append(TaskAllocation(task_id=allocation.task_id, minutes=allocation.minutes))

        if done_keep:
            done_keep_by_day[day.date] = done_keep

        day_blocks: list[ScheduleTimeBlock] = []

        def allocate_blocks(
            allocations: list[TaskAllocation],
            available: list[TimeInterval],
            allow_carryover: bool,
        ) -> list[ScheduleTimeBlock]:
            blocks: list[ScheduleTimeBlock] = []
            for allocation in allocations:
                remaining_limit = remaining_by_task.get(allocation.task_id, 0)
                if remaining_limit <= 0:
                    continue
                remaining = min(allocation.minutes, remaining_limit)
                task = task_map.get(allocation.task_id)
                pinned_date = _pinned_local_date(task.pinned_date, tz) if task and task.pinned_date else None
                status_value = None
                if task:
                    status_value = (
                        task.status.value if hasattr(task.status, "value") else str(task.status)
                    )
                while remaining > 0 and available:
                    interval = available[0]
                    duration = min(remaining, interval.end_minutes - interval.start_minutes)
                    if duration <= 0:
                        available.pop(0)
                        continue
                    start_dt = datetime.combine(day.date, datetime.min.time(), tzinfo=tz) + timedelta(
                        minutes=interval.start_minutes
                    )
                    end_dt = start_dt + timedelta(minutes=duration)
                    blocks.append(
                        ScheduleTimeBlock(
                            task_id=allocation.task_id,
                            start=start_dt,
                            end=end_dt,
                            kind="auto",
                            status=status_value,
                            pinned_date=pinned_date,
                        )
                    )
                    remaining -= duration
                    remaining_by_task[allocation.task_id] = max(
                        0, remaining_by_task.get(allocation.task_id, 0) - duration
                    )
                    if remaining <= 0:
                        interval.start_minutes = min(
                            interval.end_minutes,
                            interval.start_minutes + duration + break_after,
                        )
                    else:
                        interval.start_minutes += duration
                    if interval.start_minutes >= interval.end_minutes:
                        available.pop(0)

                if remaining > 0:
                    if allow_carryover:
                        if pinned_date == day.date:
                            if allocation.task_id not in pinned_overflow:
                                pinned_overflow.append(allocation.task_id)
                            remaining_by_task[allocation.task_id] = 0
                        else:
                            carryover.append(TaskAllocation(task_id=allocation.task_id, minutes=remaining))
                    else:
                        remaining_by_task[allocation.task_id] = 0
            return blocks

        # Place done tasks as ghost blocks at their original scheduled positions.
        # These blocks do NOT consume available time, so new tasks can overlap (2-column).
        if done_ghost_queue:
            ghost_slots = _clone_intervals(available_base)
            for allocation in done_ghost_queue:
                task = task_map.get(allocation.task_id)
                pinned_date = _pinned_local_date(task.pinned_date, tz) if task and task.pinned_date else None
                status_value = None
                if task:
                    status_value = (
                        task.status.value if hasattr(task.status, "value") else str(task.status)
                    )
                remaining = allocation.minutes
                while remaining > 0 and ghost_slots:
                    interval = ghost_slots[0]
                    duration = min(remaining, interval.end_minutes - interval.start_minutes)
                    if duration <= 0:
                        ghost_slots.pop(0)
                        continue
                    start_dt = datetime.combine(day.date, datetime.min.time(), tzinfo=tz) + timedelta(
                        minutes=interval.start_minutes
                    )
                    end_dt = start_dt + timedelta(minutes=duration)
                    day_blocks.append(
                        ScheduleTimeBlock(
                            task_id=allocation.task_id,
                            start=start_dt,
                            end=end_dt,
                            kind="auto",
                            status=status_value,
                            pinned_date=pinned_date,
                        )
                    )
                    remaining -= duration
                    interval.start_minutes += duration + break_after
                    if interval.start_minutes >= interval.end_minutes:
                        ghost_slots.pop(0)

        if active_queue:
            day_blocks.extend(allocate_blocks(active_queue, available_future, True))

        time_blocks.extend(meeting_blocks_by_day.get(day.date, []))
        time_blocks.extend(day_blocks)

    auto_minutes_by_day: dict[date, dict[UUID, int]] = {}
    for block in time_blocks:
        if block.kind != "auto":
            continue
        day_key = block.start.astimezone(tz).date()
        per_day = auto_minutes_by_day.setdefault(day_key, {})
        per_day[block.task_id] = per_day.get(block.task_id, 0) + int(
            (block.end - block.start).total_seconds() / 60
        )

    updated_days: dict[date, ScheduleDay] = {}
    for day in schedule.days:
        meeting_allocations = [
            allocation
            for allocation in allocations_by_day.get(day.date, [])
            if task_map.get(allocation.task_id) and task_map[allocation.task_id].is_fixed_time
        ]
        auto_allocations = [
            TaskAllocation(task_id=task_id, minutes=minutes)
            for task_id, minutes in auto_minutes_by_day.get(day.date, {}).items()
        ]
        done_allocations: list[TaskAllocation] = done_keep_by_day.get(day.date, [])
        pinned_missing: list[TaskAllocation] = []
        for allocation in allocations_by_day.get(day.date, []):
            if allocation.task_id not in pinned_overflow:
                continue
            scheduled_minutes = auto_minutes_by_day.get(day.date, {}).get(allocation.task_id, 0)
            remaining_minutes = max(0, allocation.minutes - scheduled_minutes)
            if remaining_minutes > 0:
                pinned_missing.append(TaskAllocation(task_id=allocation.task_id, minutes=remaining_minutes))
        task_allocations = meeting_allocations + auto_allocations + done_allocations + pinned_missing
        allocated_minutes = sum(allocation.minutes for allocation in task_allocations)
        meeting_minutes = sum(allocation.minutes for allocation in meeting_allocations)
        overflow_minutes = max(0, allocated_minutes - day.capacity_minutes)
        available_minutes = max(0, day.capacity_minutes - allocated_minutes)
        updated_days[day.date] = ScheduleDay(
            date=day.date,
            capacity_minutes=day.capacity_minutes,
            allocated_minutes=allocated_minutes,
            overflow_minutes=overflow_minutes,
            task_allocations=task_allocations,
            meeting_minutes=meeting_minutes,
            available_minutes=available_minutes,
        )

    return time_blocks, updated_days, pinned_overflow


class DailySchedulePlanService:
    def __init__(
        self,
        task_repo: ITaskRepository,
        project_repo: IProjectRepository,
        assignment_repo: ITaskAssignmentRepository,
        snapshot_repo: IScheduleSnapshotRepository,
        user_repo: IUserRepository,
        settings_repo: IScheduleSettingsRepository,
        plan_repo: IDailySchedulePlanRepository,
        scheduler_service: Optional[SchedulerService] = None,
    ):
        self._task_repo = task_repo
        self._project_repo = project_repo
        self._assignment_repo = assignment_repo
        self._snapshot_repo = snapshot_repo
        self._user_repo = user_repo
        self._settings_repo = settings_repo
        self._plan_repo = plan_repo
        self._scheduler_service = scheduler_service or SchedulerService()

    def _filter_tasks_for_plan(
        self,
        tasks: list[Task],
        assignments: Optional[list],
        user_id: str,
        filter_by_assignee: bool,
        timezone: str,
        team_project_ids: Optional[set[UUID]] = None,
    ) -> list[Task]:
        if not filter_by_assignee or assignments is None:
            return tasks
        assignees_by_task: dict[UUID, set[str]] = {}
        for assignment in assignments:
            assignees_by_task.setdefault(assignment.task_id, set()).add(assignment.assignee_id)

        _team_ids = team_project_ids or set()

        def is_my_task(task: Task) -> bool:
            if not task.project_id:
                return True  # Personal task
            if task.project_id not in _team_ids:
                return True  # PRIVATE project task - always include
            # TEAM project: only if assigned to me
            assignees = assignees_by_task.get(task.id)
            if not assignees or user_id not in assignees:
                return False
            if task.requires_all_completion and task.status == TaskStatus.WAITING:
                my_assignment = next(
                    (
                        entry for entry in assignments
                        if entry.task_id == task.id and entry.assignee_id == user_id
                    ),
                    None,
                )
                if my_assignment and my_assignment.status == TaskStatus.DONE:
                    return False
            return True

        today = get_user_today(timezone)
        _tz = ZoneInfo(normalize_timezone(timezone))
        return [
            task
            for task in tasks
            if task.is_fixed_time
            or is_my_task(task)
            or (task.pinned_date and _pinned_local_date(task.pinned_date, _tz) >= today)
        ]

    async def _load_settings(self, user_id: str) -> ScheduleSettings:
        settings = await self._settings_repo.get(user_id)
        if settings:
            return settings
        now = now_utc()
        return ScheduleSettings(
            user_id=user_id,
            weekly_work_hours=default_weekly_work_hours(),
            buffer_hours=1.0,
            break_after_task_minutes=5,
            created_at=now,
            updated_at=now,
        )

    async def _load_user_timezone(self, user_id: str) -> str:
        try:
            user = await self._user_repo.get(UUID(user_id))
        except (TypeError, ValueError):
            user = None
        return normalize_timezone(user.timezone if user else None)

    async def _load_project_priorities(self, user_id: str) -> dict[UUID, int]:
        projects = await self._project_repo.list(user_id, limit=1000)
        return {project.id: project.priority for project in projects}

    async def _load_accessible_tasks(
        self,
        user_id: str,
        *,
        include_done: bool,
        projects: Optional[list] = None,
    ) -> list[Task]:
        accessible_projects = (
            projects if projects is not None else await self._project_repo.list(user_id, limit=1000)
        )
        task_map: dict[UUID, Task] = {}

        own_tasks = await self._task_repo.list(user_id, include_done=include_done, limit=1000)
        for task in own_tasks:
            task_map[task.id] = task

        for project in accessible_projects:
            if project.visibility != ProjectVisibility.TEAM:
                continue
            project_tasks = await self._task_repo.list(
                project.user_id,
                project_id=project.id,
                include_done=include_done,
                limit=1000,
            )
            for task in project_tasks:
                task_map[task.id] = task

        return list(task_map.values())

    async def _load_plan_windows(
        self,
        user_id: str,
        tasks: list[Task],
    ) -> dict[UUID, tuple[Optional[date], Optional[date]]]:
        if not tasks:
            return {}
        task_ids = {task.id for task in tasks}
        projects = await self._project_repo.list(user_id, limit=1000)
        planned_windows: dict[UUID, tuple[Optional[date], Optional[date]]] = {}
        for project in projects:
            snapshot = await self._snapshot_repo.get_active(user_id, project.id)
            if not snapshot:
                continue
            for snapshot_task in snapshot.tasks:
                if snapshot_task.task_id not in task_ids:
                    continue
                if snapshot_task.planned_start or snapshot_task.planned_end:
                    planned_windows[snapshot_task.task_id] = (
                        snapshot_task.planned_start,
                        snapshot_task.planned_end,
                    )
        return planned_windows

    async def build_plan(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        max_days: int = DEFAULT_PLAN_DAYS,
        from_now: bool = False,
        filter_by_assignee: bool = True,
        apply_plan_constraints: bool = True,
    ) -> SchedulePlanResponse:
        timezone = await self._load_user_timezone(user_id)
        resolved_start = start_date or get_user_today(timezone)
        settings = await self._load_settings(user_id)
        capacity_by_weekday = _build_capacity_by_weekday(settings)
        capacity_by_weekday = _apply_capacity_buffer(capacity_by_weekday, settings.buffer_hours)
        projects = await self._project_repo.list(user_id, limit=1000)

        if from_now and resolved_start == get_user_today(timezone):
            weekday_index = (resolved_start.weekday() + 1) % 7
            work_hours = settings.weekly_work_hours or default_weekly_work_hours()
            day_work = work_hours[weekday_index] if weekday_index < len(work_hours) else WorkdayHours(
                enabled=True, start="09:00", end="18:00", breaks=[]
            )
            intervals = _build_work_intervals(day_work)
            now_dt = now_utc().astimezone(ZoneInfo(timezone))
            now_minutes = now_dt.hour * 60 + now_dt.minute
            remaining_intervals = _clip_intervals(intervals, now_minutes)
            remaining_work_minutes = sum(
                interval.end_minutes - interval.start_minutes for interval in remaining_intervals
            )
            tasks_for_meetings = await self._load_accessible_tasks(
                user_id,
                include_done=True,
                projects=projects,
            )
            past_meeting_minutes = _meeting_minutes_before_now(
                tasks_for_meetings,
                resolved_start,
                now_minutes,
                timezone,
            )
            adjusted_capacity = max(0.0, (remaining_work_minutes + past_meeting_minutes) / 60)
            if len(capacity_by_weekday) == 7:
                capacity_by_weekday[weekday_index] = adjusted_capacity

        tasks = await self._load_accessible_tasks(
            user_id,
            include_done=True,
            projects=projects,
        )
        project_priorities = {project.id: project.priority for project in projects}
        assignments = None
        if filter_by_assignee:
            assignments = await self._assignment_repo.list_for_assignee(user_id)
        planned_windows = None
        if apply_plan_constraints:
            planned_windows = await self._load_plan_windows(user_id, tasks)

        team_project_ids = {
            p.id for p in projects
            if p.visibility == ProjectVisibility.TEAM
        }

        schedule = self._scheduler_service.build_schedule(
            tasks,
            project_priorities=project_priorities,
            start_date=resolved_start,
            capacity_by_weekday=capacity_by_weekday,
            max_days=max_days,
            current_user_id=user_id,
            assignments=assignments,
            filter_by_assignee=filter_by_assignee,
            planned_window_by_task=planned_windows,
            user_timezone=timezone,
            team_project_ids=team_project_ids,
        )

        filtered_tasks = self._filter_tasks_for_plan(
            tasks,
            assignments,
            user_id,
            filter_by_assignee,
            timezone,
            team_project_ids=team_project_ids,
        )

        time_blocks, updated_days, pinned_overflow = _build_time_blocks(
            schedule,
            filtered_tasks,
            settings,
            timezone,
            from_now,
            resolved_start,
        )

        updated_tasks = []
        for task in schedule.tasks:
            updated_tasks.append(task)

        updated_schedule = ScheduleResponse(
            start_date=schedule.start_date,
            days=[updated_days.get(day.date, day) for day in schedule.days],
            tasks=updated_tasks,
            unscheduled_task_ids=schedule.unscheduled_task_ids,
            excluded_tasks=schedule.excluded_tasks,
        )

        snapshots = _build_task_snapshots(filtered_tasks)
        pending_changes: list[PendingChange] = []
        plan_group_id = uuid4()
        generated_at = now_utc()
        plan_params = {
            "start_date": str(resolved_start),
            "max_days": max_days,
            "timezone": timezone,
            "filter_by_assignee": filter_by_assignee,
            "apply_plan_constraints": apply_plan_constraints,
            "capacity_by_weekday": capacity_by_weekday,
            "buffer_hours": settings.buffer_hours,
            "break_after_task_minutes": settings.break_after_task_minutes,
        }

        plans: list[DailySchedulePlanCreate] = []
        for day in updated_schedule.days:
            plans.append(
                DailySchedulePlanCreate(
                    user_id=user_id,
                    plan_date=day.date,
                    timezone=timezone,
                    plan_group_id=plan_group_id,
                    schedule_day=day,
                    tasks=updated_schedule.tasks,
                    unscheduled_task_ids=updated_schedule.unscheduled_task_ids,
                    excluded_tasks=updated_schedule.excluded_tasks,
                    time_blocks=[block for block in time_blocks if block.start.astimezone(ZoneInfo(timezone)).date() == day.date],
                    task_snapshots=snapshots,
                    pinned_overflow_task_ids=pinned_overflow,
                    plan_params=plan_params,
                    generated_at=generated_at,
                )
            )

        await self._plan_repo.upsert_many(user_id, plans)

        return SchedulePlanResponse(
            start_date=updated_schedule.start_date,
            days=updated_schedule.days,
            tasks=updated_schedule.tasks,
            unscheduled_task_ids=updated_schedule.unscheduled_task_ids,
            excluded_tasks=updated_schedule.excluded_tasks,
            plan_state="planned",
            plan_group_id=plan_group_id,
            plan_generated_at=generated_at,
            pending_changes=pending_changes,
            time_blocks=time_blocks,
            pinned_overflow_task_ids=pinned_overflow,
        )

    async def _get_past_days_from_plans(
        self,
        user_id: str,
        past_start: date,
        past_end: date,
        all_tasks: list[Task],
        timezone: str,
    ) -> tuple[list[ScheduleDay], list[ScheduleTimeBlock], list[TaskScheduleInfo]]:
        """Load saved plans for past days. Returns meeting-only data for days without plans."""
        plans = [
            plan
            for plan in await self._plan_repo.list_by_range(user_id, past_start, past_end)
            if plan.timezone == timezone
        ]
        plan_map = {plan.plan_date: plan for plan in plans}

        days: list[ScheduleDay] = []
        time_blocks: list[ScheduleTimeBlock] = []
        past_tasks = _merge_task_infos_from_plans(plans)
        cursor = past_start
        while cursor <= past_end:
            plan = plan_map.get(cursor)
            if plan:
                days.append(plan.schedule_day)
                time_blocks.extend(plan.time_blocks)
            else:
                meeting_blocks: list[ScheduleTimeBlock] = []
                meeting_allocations: list[TaskAllocation] = []
                for task in all_tasks:
                    if not task.is_fixed_time or not task.start_time or not task.end_time:
                        continue
                    start_dt = _to_local_datetime(task.start_time, timezone)
                    if start_dt.date() != cursor:
                        continue
                    end_dt = _to_local_datetime(task.end_time, timezone)
                    meeting_blocks.append(
                        ScheduleTimeBlock(
                            task_id=task.id,
                            start=start_dt,
                            end=end_dt,
                            kind="meeting",
                            status=task.status.value if hasattr(task.status, "value") else str(task.status),
                        )
                    )
                    duration = int((end_dt - start_dt).total_seconds() / 60)
                    meeting_allocations.append(TaskAllocation(task_id=task.id, minutes=max(0, duration)))
                    if task.id not in {t.task_id for t in past_tasks}:
                        past_tasks.append(TaskScheduleInfo(
                            task_id=task.id,
                            title=task.title,
                            project_id=task.project_id,
                            total_minutes=max(0, duration),
                            priority_score=0,
                            is_fixed_time=True,
                            start_time=task.start_time,
                            end_time=task.end_time,
                        ))
                time_blocks.extend(meeting_blocks)
                meeting_minutes = sum(a.minutes for a in meeting_allocations)
                days.append(ScheduleDay(
                    date=cursor,
                    capacity_minutes=0,
                    allocated_minutes=meeting_minutes,
                    overflow_minutes=0,
                    task_allocations=meeting_allocations,
                    meeting_minutes=meeting_minutes,
                    available_minutes=0,
                ))
            cursor += timedelta(days=1)

        return days, time_blocks, past_tasks

    async def get_plan_or_forecast(
        self,
        user_id: str,
        start_date: Optional[date],
        max_days: int,
        filter_by_assignee: bool,
        apply_plan_constraints: bool,
    ) -> SchedulePlanResponse:
        timezone = await self._load_user_timezone(user_id)
        resolved_start = start_date or get_user_today(timezone)
        user_today = get_user_today(timezone)

        # If the requested range includes past days, handle them separately
        # to avoid the scheduler re-allocating past tasks.
        if resolved_start < user_today:
            past_end = min(user_today - timedelta(days=1), resolved_start + timedelta(days=max_days - 1))
            past_days_count = (past_end - resolved_start).days + 1
            future_days_count = max(0, max_days - past_days_count)

            projects = await self._project_repo.list(user_id, limit=1000)
            all_tasks = await self._load_accessible_tasks(
                user_id,
                include_done=True,
                projects=projects,
            )
            past_days, past_time_blocks, past_task_infos = await self._get_past_days_from_plans(
                user_id, resolved_start, past_end, all_tasks, timezone,
            )

            if future_days_count > 0:
                future_result = await self._get_plan_or_forecast_from_date(
                    user_id, user_today, future_days_count,
                    filter_by_assignee, apply_plan_constraints, timezone,
                )
                merged_days = past_days + list(future_result.days)
                merged_time_blocks = past_time_blocks + list(future_result.time_blocks)
                merged_tasks = _merge_task_info_lists(past_task_infos, list(future_result.tasks))
                return SchedulePlanResponse(
                    start_date=resolved_start,
                    days=merged_days,
                    tasks=merged_tasks,
                    unscheduled_task_ids=future_result.unscheduled_task_ids,
                    excluded_tasks=future_result.excluded_tasks,
                    plan_state=future_result.plan_state,
                    plan_group_id=future_result.plan_group_id,
                    plan_generated_at=future_result.plan_generated_at,
                    pending_changes=future_result.pending_changes,
                    time_blocks=merged_time_blocks,
                    pinned_overflow_task_ids=future_result.pinned_overflow_task_ids,
                )
            else:
                return SchedulePlanResponse(
                    start_date=resolved_start,
                    days=past_days,
                    tasks=past_task_infos,
                    unscheduled_task_ids=[],
                    excluded_tasks=[],
                    plan_state="planned",
                    pending_changes=[],
                    time_blocks=past_time_blocks,
                    pinned_overflow_task_ids=[],
                )

        return await self._get_plan_or_forecast_from_date(
            user_id, resolved_start, max_days,
            filter_by_assignee, apply_plan_constraints, timezone,
        )

    async def _get_plan_or_forecast_from_date(
        self,
        user_id: str,
        resolved_start: date,
        max_days: int,
        filter_by_assignee: bool,
        apply_plan_constraints: bool,
        timezone: str,
    ) -> SchedulePlanResponse:
        """Original get_plan_or_forecast logic for today-or-future start dates."""
        end_date = resolved_start + timedelta(days=max_days - 1)
        plans = [
            plan
            for plan in await self._plan_repo.list_by_range(user_id, resolved_start, end_date)
            if plan.timezone == timezone
        ]
        if len(plans) == max_days:
            days = [plan.schedule_day for plan in plans]
            tasks = _merge_task_infos_from_plans(plans)
            unscheduled = plans[0].unscheduled_task_ids if plans else []
            excluded = plans[0].excluded_tasks if plans else []
            time_blocks: list[ScheduleTimeBlock] = []
            for plan in plans:
                time_blocks.extend(plan.time_blocks)
            projects = await self._project_repo.list(user_id, limit=1000)
            current_tasks = await self._load_accessible_tasks(
                user_id,
                include_done=True,
                projects=projects,
            )
            assignments = None
            if filter_by_assignee:
                assignments = await self._assignment_repo.list_for_assignee(user_id)
            team_project_ids = {
                p.id for p in projects
                if p.visibility == ProjectVisibility.TEAM
            }
            current_tasks = self._filter_tasks_for_plan(
                current_tasks,
                assignments,
                user_id,
                filter_by_assignee,
                timezone,
                team_project_ids=team_project_ids,
            )
            pending_changes = _compute_pending_changes(
                current_tasks,
                plans[0].task_snapshots if plans else [],
            )
            settings = await self._load_settings(user_id)
            capacity_by_weekday = _build_capacity_by_weekday(settings)
            capacity_by_weekday = _apply_capacity_buffer(capacity_by_weekday, settings.buffer_hours)
            current_params = {
                "start_date": str(resolved_start),
                "max_days": max_days,
                "timezone": timezone,
                "filter_by_assignee": filter_by_assignee,
                "apply_plan_constraints": apply_plan_constraints,
                "capacity_by_weekday": capacity_by_weekday,
                "buffer_hours": settings.buffer_hours,
                "break_after_task_minutes": settings.break_after_task_minutes,
            }
            plan_params = plans[0].plan_params if plans else {}
            params_changed = _plan_params_fingerprint(current_params) != _plan_params_fingerprint(plan_params)
            plan_state = "stale" if pending_changes or params_changed else "planned"
            pinned_overflow = []
            for plan in plans:
                for task_id in plan.pinned_overflow_task_ids:
                    if task_id not in pinned_overflow:
                        pinned_overflow.append(task_id)
            return SchedulePlanResponse(
                start_date=resolved_start,
                days=days,
                tasks=tasks,
                unscheduled_task_ids=unscheduled,
                excluded_tasks=excluded,
                plan_state=plan_state,
                plan_group_id=plans[0].plan_group_id if plans else None,
                plan_generated_at=plans[0].generated_at if plans else None,
                pending_changes=pending_changes,
                time_blocks=time_blocks,
                pinned_overflow_task_ids=pinned_overflow,
            )

        settings = await self._load_settings(user_id)
        capacity_by_weekday = _build_capacity_by_weekday(settings)
        capacity_by_weekday = _apply_capacity_buffer(capacity_by_weekday, settings.buffer_hours)
        projects = await self._project_repo.list(user_id, limit=1000)
        tasks = await self._load_accessible_tasks(
            user_id,
            include_done=True,
            projects=projects,
        )
        project_priorities = {project.id: project.priority for project in projects}
        assignments = None
        if filter_by_assignee:
            assignments = await self._assignment_repo.list_for_assignee(user_id)
        planned_windows = None
        if apply_plan_constraints:
            planned_windows = await self._load_plan_windows(user_id, tasks)
        team_project_ids = {
            p.id for p in projects
            if p.visibility == ProjectVisibility.TEAM
        }
        schedule = self._scheduler_service.build_schedule(
            tasks,
            project_priorities=project_priorities,
            start_date=resolved_start,
            capacity_by_weekday=capacity_by_weekday,
            max_days=max_days,
            current_user_id=user_id,
            assignments=assignments,
            filter_by_assignee=filter_by_assignee,
            planned_window_by_task=planned_windows,
            user_timezone=timezone,
            team_project_ids=team_project_ids,
        )

        return SchedulePlanResponse(
            start_date=schedule.start_date,
            days=schedule.days,
            tasks=schedule.tasks,
            unscheduled_task_ids=schedule.unscheduled_task_ids,
            excluded_tasks=schedule.excluded_tasks,
            plan_state="forecast",
            pending_changes=[],
            time_blocks=[],
            pinned_overflow_task_ids=[],
        )

    async def move_time_block(
        self,
        user_id: str,
        request: TimeBlockMoveRequest,
    ) -> Optional[ScheduleTimeBlock]:
        """Move or resize a time block within the stored schedule plan.

        For meeting blocks, also updates the underlying task's start_time/end_time.
        If duration changed (resize), also updates estimated_minutes.
        """
        timezone = await self._load_user_timezone(user_id)
        new_start_local = _to_local_datetime(request.new_start, timezone)
        new_end_local = _to_local_datetime(request.new_end, timezone)
        target_date = new_start_local.date()
        is_cross_day = request.original_date != target_date

        if is_cross_day:
            result = await self._plan_repo.move_time_block_across_days(
                user_id=user_id,
                source_date=request.original_date,
                target_date=target_date,
                task_id=request.task_id,
                new_start=new_start_local,
                new_end=new_end_local,
            )
        else:
            result = await self._plan_repo.update_time_block(
                user_id=user_id,
                plan_date=request.original_date,
                task_id=request.task_id,
                new_start=new_start_local,
                new_end=new_end_local,
            )

        if not result:
            return None

        # Sync underlying task data
        task = await self._task_repo.get(user_id, request.task_id)
        if not task:
            task = await self._task_repo.get_by_id(user_id, request.task_id)
        if task:
            updates: dict[str, Any] = {}
            if task.is_fixed_time:
                updates["start_time"] = new_start_local
                updates["end_time"] = new_end_local
            old_duration = (
                int((task.end_time - task.start_time).total_seconds() / 60)
                if task.start_time and task.end_time
                else task.estimated_minutes or 0
            )
            new_duration = int((new_end_local - new_start_local).total_seconds() / 60)
            if old_duration != new_duration and new_duration > 0:
                updates["estimated_minutes"] = new_duration
            updated_task = task
            if updates:
                updated_task = await self._task_repo.update(
                    user_id=user_id,
                    task_id=request.task_id,
                    update=TaskUpdate(**updates),
                    project_id=task.project_id,
                )
            source_plan = await self._plan_repo.get_by_date(user_id, request.original_date)
            if source_plan:
                await self._plan_repo.update_task_snapshot_for_group(
                    user_id=user_id,
                    plan_group_id=source_plan.plan_group_id,
                    snapshot=TaskPlanSnapshot(
                        task_id=updated_task.id,
                        title=updated_task.title,
                        fingerprint=_task_fingerprint(updated_task),
                    ),
                )

        return result
