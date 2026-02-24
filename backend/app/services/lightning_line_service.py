"""
Lightning line calculation service.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from app.interfaces.task_repository import ITaskRepository
from app.models.enums import TaskStatus
from app.models.lightning_line import (
    LightningLinePoint,
    LightningLineResponse,
)
from app.models.task import Task
from app.services.progress_calculator import effective_weight, normalized_progress
from app.utils.datetime_utils import now_utc


class LightningLineService:
    """Build lightning line points for project tasks."""

    def __init__(self, task_repo: ITaskRepository):
        self.task_repo = task_repo

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _reference_datetime(reference_date: date) -> datetime:
        return datetime.combine(reference_date, time.min, tzinfo=timezone.utc)

    @staticmethod
    def _estimated_duration_days(task: Task) -> int:
        minutes = effective_weight(task.estimated_minutes)
        return max(1, math.ceil(minutes / (8 * 60)))

    @classmethod
    def _plan_window(cls, task: Task) -> tuple[datetime, datetime] | None:
        if not task.due_date:
            return None

        due_date = cls._to_utc(task.due_date)
        if task.start_not_before:
            start_date = cls._to_utc(task.start_not_before)
        else:
            duration_days = cls._estimated_duration_days(task)
            start_date = due_date - timedelta(days=duration_days)

        if start_date > due_date:
            start_date = due_date
        return start_date, due_date

    @staticmethod
    def _planned_progress(reference_dt: datetime, start_dt: datetime, end_dt: datetime) -> float:
        duration_days = max((end_dt - start_dt).total_seconds() / 86400, 1.0)
        elapsed_days = (reference_dt - start_dt).total_seconds() / 86400
        planned = (elapsed_days / duration_days) * 100
        return max(0.0, min(planned, 100.0))

    async def _list_project_tasks(self, user_id: str, project_id: UUID) -> list[Task]:
        tasks: list[Task] = []
        offset = 0
        limit = 200
        while True:
            batch = await self.task_repo.list(
                user_id=user_id,
                project_id=project_id,
                include_done=True,
                limit=limit,
                offset=offset,
            )
            if not batch:
                break
            tasks.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return tasks

    async def calculate(
        self,
        user_id: str,
        project_id: UUID,
        reference_date: date | None = None,
    ) -> LightningLineResponse:
        target_date = reference_date or now_utc().date()
        reference_dt = self._reference_datetime(target_date)
        tasks = await self._list_project_tasks(user_id, project_id)

        points: list[LightningLinePoint] = []
        for task in tasks:
            if not task.due_date:
                continue

            plan_window = self._plan_window(task)
            if not plan_window:
                continue
            start_dt, end_dt = plan_window

            planned_progress = self._planned_progress(reference_dt, start_dt, end_dt)
            actual_progress = float(normalized_progress(task.status, task.progress))
            duration_days = max((end_dt - start_dt).total_seconds() / 86400, 1.0)
            deviation_days = ((actual_progress - planned_progress) / 100.0) * duration_days

            if task.status == TaskStatus.DONE:
                target_point_dt = end_dt if reference_dt < end_dt else reference_dt
                deviation_days = (target_point_dt - reference_dt).total_seconds() / 86400

            points.append(
                LightningLinePoint(
                    task_id=task.id,
                    row_key=str(task.id),
                    planned_progress=round(planned_progress, 2),
                    actual_progress=round(actual_progress, 2),
                    deviation_days=round(deviation_days, 2),
                )
            )

        points.sort(key=lambda point: (point.row_key, str(point.task_id)))
        return LightningLineResponse(reference_date=target_date, points=points)
