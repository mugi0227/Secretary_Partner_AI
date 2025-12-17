"""
Top 3 service for intelligent task prioritization.

Provides rule-based scoring with optional AI enhancement.
"""

from datetime import datetime, date

from app.core.logger import setup_logger
from app.interfaces.task_repository import ITaskRepository
from app.models.task import Task
from app.models.enums import Priority, EnergyLevel

logger = setup_logger(__name__)


class Top3Service:
    """
    Service for calculating today's top 3 priority tasks.

    Uses a hybrid approach:
    1. Rule-based scoring (importance, urgency, due date)
    2. Optional AI enhancement (context-aware adjustments)
    """

    def __init__(self, task_repo: ITaskRepository):
        self.task_repo = task_repo

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

    async def get_top3(self, user_id: str) -> list[Task]:
        """
        Get today's top 3 priority tasks.

        Args:
            user_id: User ID

        Returns:
            List of top 3 tasks (or fewer if less than 3 exist)
        """
        # Get all incomplete tasks
        tasks = await self.task_repo.list(
            user_id=user_id,
            include_done=False,
            limit=100,
        )

        if not tasks:
            logger.info(f"No tasks found for user {user_id}")
            return []

        # Calculate scores
        scored_tasks = []
        for task in tasks:
            score = self._calculate_base_score(task)
            scored_tasks.append((task, score))

        # Sort by score (highest first)
        scored_tasks.sort(key=lambda x: x[1], reverse=True)

        # Return top 3
        top3 = [task for task, score in scored_tasks[:3]]

        logger.info(
            f"Top 3 tasks for {user_id}: "
            f"{[task.title for task in top3]}"
        )

        return top3

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
