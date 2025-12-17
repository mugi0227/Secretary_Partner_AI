"""
Today API endpoints.

Smart daily features like Top 3 tasks.
"""

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, TaskRepo
from app.models.task import Task
from app.services.top3_service import Top3Service

router = APIRouter()


def get_top3_service(task_repo: TaskRepo) -> Top3Service:
    """Get Top3Service instance."""
    return Top3Service(task_repo=task_repo)


@router.get("/top3", response_model=list[Task], status_code=status.HTTP_200_OK)
async def get_top3_tasks(
    user: CurrentUser,
    top3_service: Top3Service = Depends(get_top3_service),
):
    """
    Get today's top 3 priority tasks.

    Uses intelligent scoring based on:
    - Importance level (HIGH/MEDIUM/LOW)
    - Urgency level (HIGH/MEDIUM/LOW)
    - Due date proximity (overdue, today, tomorrow, this week)
    - Energy level (quick wins for low-energy tasks)

    Returns:
        list[Task]: Top 3 tasks ordered by priority (or fewer if less than 3 exist)
    """
    return await top3_service.get_top3(user.id)
