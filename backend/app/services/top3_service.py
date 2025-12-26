"""
Top 3 service for intelligent task prioritization.

Provides rule-based scoring with optional AI enhancement.
"""

from datetime import datetime, date
from uuid import UUID
from typing import Optional

from app.core.logger import setup_logger
from app.interfaces.task_repository import ITaskRepository
from app.models.task import Task
from app.models.enums import Priority, EnergyLevel, TaskStatus
from app.services.scheduler_service import SchedulerService

logger = setup_logger(__name__)


class Top3Service:
    """
    Service for calculating today's top 3 priority tasks.

    Uses a hybrid approach:
    1. Rule-based scoring (importance, urgency, due date)
    2. Optional AI enhancement (context-aware adjustments)
    """

    def __init__(self, task_repo: ITaskRepository, scheduler_service: Optional[SchedulerService] = None):
        self.task_repo = task_repo
        self.scheduler_service = scheduler_service or SchedulerService()

        # Scoring weights
        self.importance_weights = {
            Priority.HIGH: 3.0,
            Priority.MEDIUM: 2.0,
            Priority.LOW: 1.0,
        }

        self.urgency_weights = {
            Priority.HIGH: 3.0,
            Priority.MEDIUM: 2.0,
            Priority.LOW: 1.0,
        }

    async def get_top3(
        self,
        user_id: str,
        capacity_hours: Optional[float] = None,
        check_capacity: bool = True,
    ) -> dict:
        """
        Get today's top 3 priority tasks with capacity awareness.

        Args:
            user_id: User ID
            capacity_hours: Daily capacity in hours (None = use default 8h)
            check_capacity: Whether to check capacity constraints

        Returns:
            Dictionary with:
                - tasks: list[Task] - Top 3 tasks
                - capacity_info: dict - Capacity check results (if check_capacity=True)
                - overflow_suggestion: str - Suggestion for overflow tasks
        """
        # Get all incomplete tasks
        tasks = await self.task_repo.list(
            user_id=user_id,
            include_done=False,
            limit=100,
        )

        if not tasks:
            logger.info(f"No tasks found for user {user_id}")
            return {"tasks": [], "capacity_info": None, "overflow_suggestion": ""}

        # Filter out tasks with unmet dependencies
        actionable_tasks = await self._filter_actionable_tasks(user_id, tasks)

        if not actionable_tasks:
            logger.info(f"No actionable tasks found for user {user_id}")
            return {"tasks": [], "capacity_info": None, "overflow_suggestion": ""}

        # Calculate scores
        scored_tasks = []
        for task in actionable_tasks:
            score = self._calculate_base_score(task)
            scored_tasks.append((task, score))

        # Sort by score (highest first)
        scored_tasks.sort(key=lambda x: x[1], reverse=True)

        # Get top tasks (more than 3 for capacity check)
        top_tasks = [task for task, score in scored_tasks]

        # Check capacity if requested
        capacity_info = None
        overflow_suggestion = ""
        final_tasks = top_tasks[:3]

        if check_capacity:
            # Check capacity for all top tasks
            capacity_result = self.scheduler_service.check_schedule_feasibility(
                top_tasks,
                capacity_hours=capacity_hours,
            )
            capacity_info = capacity_result

            # If capacity exceeded, suggest moving overflow tasks
            if not capacity_result["feasible"]:
                overflow_tasks = capacity_result["overflow_tasks"]
                overflow_suggestion = self.scheduler_service.suggest_overflow_actions(
                    overflow_tasks
                )
                # Return only tasks that fit
                final_tasks = capacity_result["tasks_that_fit"][:3]

        logger.info(
            f"Top 3 tasks for {user_id}: "
            f"{[task.title for task in final_tasks]}"
        )

        return {
            "tasks": final_tasks,
            "capacity_info": capacity_info,
            "overflow_suggestion": overflow_suggestion,
        }

    async def _filter_actionable_tasks(self, user_id: str, tasks: list[Task]) -> list[Task]:
        """
        Filter tasks to only include those with all dependencies completed.

        Args:
            user_id: User ID
            tasks: List of tasks to filter

        Returns:
            List of actionable tasks (dependencies met)
        """
        if not tasks:
            return []

        # Get all task IDs and their statuses
        task_status_map = {task.id: task.status for task in tasks}

        # Also fetch dependency tasks that might not be in the current list
        all_dependency_ids = set()
        for task in tasks:
            all_dependency_ids.update(task.dependency_ids)

        # Fetch missing dependency tasks
        missing_dep_ids = all_dependency_ids - set(task_status_map.keys())
        if missing_dep_ids:
            for dep_id in missing_dep_ids:
                try:
                    dep_task = await self.task_repo.get(user_id, dep_id)
                    if dep_task:
                        task_status_map[dep_task.id] = dep_task.status
                except Exception as e:
                    logger.warning(f"Failed to fetch dependency task {dep_id}: {e}")

        # Filter actionable tasks
        actionable = []
        for task in tasks:
            if not task.dependency_ids:
                # No dependencies, always actionable
                actionable.append(task)
                continue

            # Check if all dependencies are completed
            all_deps_met = True
            for dep_id in task.dependency_ids:
                dep_status = task_status_map.get(dep_id)
                if dep_status != TaskStatus.DONE:
                    all_deps_met = False
                    logger.debug(
                        f"Task {task.title} blocked by dependency {dep_id} "
                        f"(status: {dep_status})"
                    )
                    break

            if all_deps_met:
                actionable.append(task)

        logger.info(
            f"Filtered {len(tasks)} tasks to {len(actionable)} actionable tasks "
            f"(blocked: {len(tasks) - len(actionable)})"
        )

        return actionable

    def _calculate_base_score(self, task: Task) -> float:
        """
        Calculate base priority score for a task.

        Scoring factors:
        - Importance (30 points max): 10 * weight
        - Urgency (24 points max): 8 * weight
        - Due date proximity (30 points max):
          - Overdue: +30
          - Due today/tomorrow: +20
          - Due this week: +10
        - Energy level (2 points max):
          - LOW energy: +2 (quick wins)

        Args:
            task: Task to score

        Returns:
            Priority score (higher = more important)
        """
        score = 0.0

        # Importance weight (30 points max)
        importance_weight = self.importance_weights.get(task.importance, 1.0)
        score += importance_weight * 10

        # Urgency weight (24 points max)
        urgency_weight = self.urgency_weights.get(task.urgency, 1.0)
        score += urgency_weight * 8

        # Due date proximity (30 points max)
        if task.due_date:
            today = date.today()
            due_date = task.due_date.date()
            days_until = (due_date - today).days

            if days_until < 0:
                # Overdue
                score += 30
            elif days_until == 0:
                # Due today
                score += 25
            elif days_until == 1:
                # Due tomorrow
                score += 20
            elif days_until <= 7:
                # Due this week
                score += 10
            elif days_until <= 14:
                # Due in 2 weeks
                score += 5

        # Energy level bonus for low-energy tasks (quick wins)
        if task.energy_level == EnergyLevel.LOW:
            score += 2

        return score
