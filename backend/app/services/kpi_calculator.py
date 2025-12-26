"""
KPI calculation utilities.

Compute project KPI current values based on task data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, TypeVar
from uuid import UUID

from app.interfaces.task_repository import ITaskRepository
from app.models.enums import TaskStatus
from app.models.project import Project, ProjectWithTaskCount
from app.models.project_kpi import ProjectKpiConfig, ProjectKpiMetric
from app.models.task import Task
from app.services.task_utils import get_effective_estimated_minutes


TProject = TypeVar("TProject", Project, ProjectWithTaskCount)


def _normalize_dt(value: datetime) -> datetime:
    """Normalize datetime to naive UTC for comparisons."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _round(value: float) -> float:
    return round(value, 2)


def _compute_task_kpis(tasks: Iterable[Task]) -> dict[str, float | int]:
    task_list = list(tasks)
    total_tasks = len(task_list)
    done_tasks = [task for task in task_list if task.status == TaskStatus.DONE]
    done_count = len(done_tasks)

    now = datetime.utcnow()
    week_cutoff = now - timedelta(days=7)

    overdue_count = 0
    remaining_minutes = 0
    weekly_throughput = 0
    wip_count = 0
    backlog_count = 0

    task_by_id = {task.id: task for task in task_list}
    done_ids = {task.id for task in task_list if task.status == TaskStatus.DONE}

    for task in task_list:
        if task.status == TaskStatus.IN_PROGRESS:
            wip_count += 1

        if task.status != TaskStatus.DONE:
            backlog_count += 1
            # Use effective estimated minutes (considers subtasks)
            effective_minutes = get_effective_estimated_minutes(task, task_list)
            remaining_minutes += effective_minutes

        if task.due_date and task.status != TaskStatus.DONE:
            due = _normalize_dt(task.due_date)
            if due < now:
                overdue_count += 1

        if task.status == TaskStatus.DONE and task.updated_at:
            updated = _normalize_dt(task.updated_at)
            if updated >= week_cutoff:
                weekly_throughput += 1

    blocked_tasks = 0
    for task in task_list:
        if task.status == TaskStatus.DONE:
            continue
        if task.status == TaskStatus.WAITING:
            blocked_tasks += 1
            continue
        if task.dependency_ids:
            for dep_id in task.dependency_ids:
                dep_task = task_by_id.get(dep_id)
                if dep_task is None or dep_task.id not in done_ids:
                    blocked_tasks += 1
                    break

    completion_rate = _round((done_count / total_tasks) * 100) if total_tasks else 0.0
    remaining_hours = _round(remaining_minutes / 60) if remaining_minutes else 0.0

    return {
        "completion_rate": completion_rate,
        "overdue_tasks": overdue_count,
        "remaining_hours": remaining_hours,
        "weekly_throughput": weekly_throughput,
        "wip_count": wip_count,
        "blocked_tasks": blocked_tasks,
        "backlog_count": backlog_count,
    }


def _apply_kpi_results(
    config: ProjectKpiConfig,
    computed: dict[str, float | int],
) -> ProjectKpiConfig:
    updated_metrics: list[ProjectKpiMetric] = []
    for metric in config.metrics:
        use_auto = metric.source == "tasks" or metric.source is None
        if use_auto and metric.key in computed:
            updated_metrics.append(metric.model_copy(update={"current": computed[metric.key]}))
        else:
            updated_metrics.append(metric.model_copy())

    return config.model_copy(update={"metrics": updated_metrics})


async def _fetch_all_tasks(
    task_repo: ITaskRepository,
    user_id: str,
    project_id: UUID,
    limit: int = 200,
) -> list[Task]:
    tasks: list[Task] = []
    offset = 0
    while True:
        batch = await task_repo.list(
            user_id,
            project_id=project_id,
            include_done=True,
            limit=limit,
            offset=offset,
        )
        tasks.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return tasks


async def apply_project_kpis(
    user_id: str,
    project: TProject,
    task_repo: ITaskRepository,
) -> TProject:
    if not project.kpi_config or not project.kpi_config.metrics:
        return project

    tasks = await _fetch_all_tasks(task_repo, user_id, project.id)
    computed = _compute_task_kpis(tasks)
    updated_config = _apply_kpi_results(project.kpi_config, computed)
    return project.model_copy(update={"kpi_config": updated_config})
