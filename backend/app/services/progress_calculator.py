"""
Shared progress calculation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from app.models.enums import TaskStatus

DEFAULT_ESTIMATED_MINUTES = 60


class SupportsProgress(Protocol):
    status: TaskStatus | str
    progress: int | None
    estimated_minutes: int | None


@dataclass(slots=True)
class ProgressSummary:
    progress: int
    total_weight: int
    remaining_minutes: int
    completed_count: int
    task_count: int


def normalized_progress(status: TaskStatus | str, progress: int | None) -> int:
    status_value = status.value if isinstance(status, TaskStatus) else str(status)
    if status_value == TaskStatus.DONE.value:
        return 100
    value = progress if progress is not None else 0
    return max(0, min(value, 100))


def effective_weight(estimated_minutes: int | None) -> int:
    if estimated_minutes is None or estimated_minutes <= 0:
        return DEFAULT_ESTIMATED_MINUTES
    return estimated_minutes


def summarize_progress(items: Iterable[SupportsProgress]) -> ProgressSummary:
    total_weight = 0
    weighted_progress = 0
    remaining_minutes = 0
    completed_count = 0
    task_count = 0

    for item in items:
        task_count += 1
        weight = effective_weight(item.estimated_minutes)
        progress = normalized_progress(item.status, item.progress)
        weighted_progress += progress * weight
        total_weight += weight
        remaining_minutes += weight * (100 - progress) // 100
        if progress == 100:
            completed_count += 1

    progress = round(weighted_progress / total_weight) if total_weight > 0 else 0
    return ProgressSummary(
        progress=progress,
        total_weight=total_weight,
        remaining_minutes=remaining_minutes,
        completed_count=completed_count,
        task_count=task_count,
    )
