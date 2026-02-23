"""
Slack Calculation Engine.

Single source of truth for task urgency calculation.
Computes slack ratio (available capacity / required work) for all active tasks,
considering dependency chains. Used by both Heartbeat (danger detection) and
Scheduler (daily task recommendation).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from app.models.enums import Priority, TaskStatus
from app.models.heartbeat import HeartbeatSeverity
from app.models.task import Task
from app.services.task_utils import (
    get_effective_estimated_minutes,
    get_remaining_minutes,
    is_parent_task,
)
from app.utils.datetime_utils import ensure_utc

# ---------------------------------------------------------------------------
# Ratio thresholds
# ---------------------------------------------------------------------------
RATIO_CRITICAL = 1.0  # 物理的に間に合わない
RATIO_HIGH = 1.5  # やばい
RATIO_MEDIUM = 2.0  # 注意
RATIO_DANGER_ZONE = RATIO_HIGH  # 危険ゾーン境界 (sort用)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaskSlackResult:
    """Slack computation result for a single task."""

    task_id: UUID
    remaining_minutes: int  # このタスク自体の残り工数
    chain_remaining_minutes: int  # このタスク＋下流依存の未完了残り工数合計（期限まで必要な実作業）
    effective_deadline: Optional[date]  # チェーン内の最も近い期限（下流から逆伝播）
    available_minutes: Optional[int]  # effective_deadlineまでの残りキャパ（分）
    slack_ratio: Optional[float]  # available / chain_remaining (None = 期限なし)
    severity: HeartbeatSeverity  # ratioから算出
    is_actionable: bool  # 直接の依存がすべてDONE


@dataclass(frozen=True)
class SlackSummary:
    """Summary of slack computation across all tasks."""

    results: list[TaskSlackResult]
    total_demand_minutes: int  # 全アクティブタスクの残り工数合計
    total_capacity_minutes: int  # ホライズン期間のキャパ合計
    is_overloaded: bool  # demand > capacity
    results_by_id: dict[UUID, TaskSlackResult] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Severity from ratio
# ---------------------------------------------------------------------------
def severity_from_ratio(ratio: Optional[float]) -> HeartbeatSeverity:
    """Map slack_ratio to severity level."""
    if ratio is None:
        return HeartbeatSeverity.LOW
    if ratio < RATIO_CRITICAL:
        return HeartbeatSeverity.CRITICAL
    if ratio < RATIO_HIGH:
        return HeartbeatSeverity.HIGH
    if ratio < RATIO_MEDIUM:
        return HeartbeatSeverity.MEDIUM
    return HeartbeatSeverity.LOW


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------
def compute_all_slack(
    tasks: list[Task],
    daily_capacity_minutes: int,
    user_timezone: str,
    now: datetime,
    horizon_days: int = 60,
    default_task_minutes: int = 0,
) -> SlackSummary:
    """
    Compute slack for every active task considering dependency chains.

    Args:
        tasks: All tasks (including DONE, needed for chain resolution).
        daily_capacity_minutes: Average productive minutes per day.
        user_timezone: IANA timezone string.
        now: Current datetime (UTC or aware).
        horizon_days: Days to look ahead for capacity check.
        default_task_minutes: Fallback estimate for tasks without one.
            If 0, uses daily_capacity_minutes.
    """
    if not tasks:
        return SlackSummary(
            results=[],
            total_demand_minutes=0,
            total_capacity_minutes=horizon_days * daily_capacity_minutes,
            is_overloaded=False,
            results_by_id={},
        )

    default_minutes = default_task_minutes or daily_capacity_minutes
    all_tasks_list = list(tasks)
    task_map: dict[UUID, Task] = {t.id: t for t in all_tasks_list}
    today = now.astimezone(ZoneInfo(user_timezone)).date()

    # 1. Identify active leaf tasks
    active_ids: set[UUID] = set()
    for task in all_tasks_list:
        if task.status in {TaskStatus.DONE, TaskStatus.WAITING}:
            continue
        if task.is_fixed_time:
            continue
        if is_parent_task(task, all_tasks_list):
            continue
        active_ids.add(task.id)

    # 2. Build bidirectional dependency graph (over ALL tasks)
    upstream: dict[UUID, set[UUID]] = defaultdict(set)  # task → its prerequisites
    downstream: dict[UUID, set[UUID]] = defaultdict(set)  # task → tasks depending on it
    for task in all_tasks_list:
        for dep_id in task.dependency_ids:
            if dep_id in task_map:
                upstream[task.id].add(dep_id)
                downstream[dep_id].add(task.id)

    # 3. For each active task compute chain info
    results: list[TaskSlackResult] = []

    for task_id in active_ids:
        task = task_map[task_id]

        # 3a. Remaining minutes for this task
        remaining = get_remaining_minutes(task, all_tasks_list)
        if remaining <= 0:
            estimated = get_effective_estimated_minutes(task, all_tasks_list)
            remaining = estimated if estimated > 0 else default_minutes

        # 3b. Chain remaining: this task + downstream unfinished tasks
        #     A->B->C(期限) の場合、A の chain = A+B+C（先頭が最も危険）
        chain_remaining = remaining
        visited_down: set[UUID] = set()
        queue = list(downstream.get(task_id, set()))
        while queue:
            did = queue.pop()
            if did in visited_down or did not in task_map:
                continue
            visited_down.add(did)
            dn_task = task_map[did]
            if dn_task.status != TaskStatus.DONE:
                dn_remaining = get_remaining_minutes(dn_task, all_tasks_list)
                if dn_remaining <= 0:
                    dn_est = get_effective_estimated_minutes(dn_task, all_tasks_list)
                    dn_remaining = dn_est if dn_est > 0 else default_minutes
                chain_remaining += dn_remaining
            queue.extend(downstream.get(did, set()) - visited_down)

        # 3c. Effective deadline: own due_date or earliest downstream due_date
        effective_deadline = _find_effective_deadline(
            task_id, task_map, downstream, user_timezone, today,
        )

        # 3d. Compute ratio
        available: Optional[int] = None
        ratio: Optional[float] = None
        if effective_deadline is not None:
            days_until = max(0, (effective_deadline - today).days + 1)
            available = days_until * daily_capacity_minutes
            if chain_remaining > 0:
                ratio = available / chain_remaining
            else:
                ratio = float("inf")

        sev = severity_from_ratio(ratio)

        # 3e. Actionable check
        is_actionable = True
        for dep_id in task.dependency_ids:
            dep = task_map.get(dep_id)
            if dep and dep.status != TaskStatus.DONE:
                is_actionable = False
                break

        results.append(
            TaskSlackResult(
                task_id=task_id,
                remaining_minutes=remaining,
                chain_remaining_minutes=chain_remaining,
                effective_deadline=effective_deadline,
                available_minutes=available,
                slack_ratio=ratio,
                severity=sev,
                is_actionable=is_actionable,
            )
        )

    # 4. Global capacity check
    total_demand = sum(r.remaining_minutes for r in results)
    total_capacity = horizon_days * daily_capacity_minutes
    is_overloaded = total_demand > total_capacity

    results_by_id = {r.task_id: r for r in results}
    return SlackSummary(
        results=results,
        total_demand_minutes=total_demand,
        total_capacity_minutes=total_capacity,
        is_overloaded=is_overloaded,
        results_by_id=results_by_id,
    )


# ---------------------------------------------------------------------------
# Two-tier priority sort
# ---------------------------------------------------------------------------
def sort_by_slack_priority(
    results: list[TaskSlackResult],
    tasks_by_id: dict[UUID, Task],
) -> list[TaskSlackResult]:
    """
    Two-tier sort implementing Eisenhower matrix:
    - Danger zone (ratio < RATIO_DANGER_ZONE): ratio ascending (most urgent first)
    - Safe zone (ratio >= RATIO_DANGER_ZONE or None): importance desc, ratio asc
    """
    importance_weight = {Priority.HIGH: 3, Priority.MEDIUM: 2, Priority.LOW: 1}

    danger: list[TaskSlackResult] = []
    safe: list[TaskSlackResult] = []

    for r in results:
        if r.slack_ratio is not None and r.slack_ratio < RATIO_DANGER_ZONE:
            danger.append(r)
        else:
            safe.append(r)

    danger.sort(key=lambda r: (r.slack_ratio if r.slack_ratio is not None else float("inf"),))

    safe.sort(
        key=lambda r: (
            -importance_weight.get(tasks_by_id[r.task_id].importance, 1),
            r.slack_ratio if r.slack_ratio is not None else float("inf"),
        )
    )

    return danger + safe


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _find_effective_deadline(
    task_id: UUID,
    task_map: dict[UUID, Task],
    downstream: dict[UUID, set[UUID]],
    user_timezone: str,
    today: date,
) -> Optional[date]:
    """Find the tightest deadline by looking at own and downstream due_dates."""
    candidates: list[date] = []
    task = task_map[task_id]

    # Own due_date
    if task.due_date:
        due_utc = ensure_utc(task.due_date)
        if due_utc:
            candidates.append(due_utc.astimezone(ZoneInfo(user_timezone)).date())

    # BFS through downstream dependents
    visited: set[UUID] = set()
    queue = list(downstream.get(task_id, set()))
    while queue:
        current = queue.pop()
        if current in visited or current not in task_map:
            continue
        visited.add(current)
        dep_task = task_map[current]
        if dep_task.due_date:
            due_utc = ensure_utc(dep_task.due_date)
            if due_utc:
                candidates.append(due_utc.astimezone(ZoneInfo(user_timezone)).date())
        queue.extend(downstream.get(current, set()) - visited)

    return min(candidates) if candidates else None
