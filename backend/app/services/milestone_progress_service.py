"""
Milestone progress calculation service.
"""

from __future__ import annotations

from uuid import UUID

from app.interfaces.task_repository import ITaskRepository
from app.models.milestone import Milestone, MilestoneWithProgress
from app.models.task import Task
from app.services.progress_calculator import summarize_progress


class MilestoneProgressService:
    """Calculate milestone progress from related tasks."""

    def __init__(self, task_repo: ITaskRepository):
        self.task_repo = task_repo

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

    @staticmethod
    def _select_target_tasks(tasks: list[Task], milestone_id: UUID) -> list[Task]:
        milestone_tasks = [task for task in tasks if task.milestone_id == milestone_id]
        milestone_task_ids = {task.id for task in milestone_tasks}
        return [
            task
            for task in milestone_tasks
            if task.parent_id is None or task.parent_id not in milestone_task_ids
        ]

    async def calculate_milestone_progress(
        self,
        user_id: str,
        milestone: Milestone,
        project_tasks: list[Task] | None = None,
    ) -> MilestoneWithProgress:
        tasks = project_tasks
        if tasks is None:
            tasks = await self._list_project_tasks(user_id, milestone.project_id)
        target_tasks = self._select_target_tasks(tasks, milestone.id)
        summary = summarize_progress(target_tasks)
        return MilestoneWithProgress(
            **milestone.model_dump(),
            progress=summary.progress,
            total_estimated_minutes=summary.total_weight,
            remaining_minutes=summary.remaining_minutes,
            task_count=summary.task_count,
            completed_task_count=summary.completed_count,
        )

    async def enrich_milestones(
        self,
        user_id: str,
        milestones: list[Milestone],
    ) -> list[MilestoneWithProgress]:
        if not milestones:
            return []

        tasks_by_project: dict[UUID, list[Task]] = {}
        for milestone in milestones:
            if milestone.project_id not in tasks_by_project:
                tasks_by_project[milestone.project_id] = await self._list_project_tasks(
                    user_id,
                    milestone.project_id,
                )

        return [
            await self.calculate_milestone_progress(
                user_id,
                milestone,
                project_tasks=tasks_by_project[milestone.project_id],
            )
            for milestone in milestones
        ]
