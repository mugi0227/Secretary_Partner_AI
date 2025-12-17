"""
Heartbeat API endpoint.

Called periodically to trigger autonomous agent actions.
"""

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, AgentTaskRepo
from app.services.heartbeat_service import HeartbeatService

router = APIRouter()


def get_heartbeat_service(
    agent_task_repo: AgentTaskRepo,
) -> HeartbeatService:
    """Get HeartbeatService instance."""
    return HeartbeatService(agent_task_repo=agent_task_repo)


@router.post("", status_code=status.HTTP_200_OK)
async def heartbeat(
    user: CurrentUser,
    heartbeat_service: HeartbeatService = Depends(get_heartbeat_service),
):
    """
    Heartbeat endpoint for triggering autonomous agent actions.

    This endpoint is called periodically (via scheduler) to:
    - Check for pending agent tasks
    - Execute scheduled actions (reminders, reviews, etc.)
    - Respect quiet hours

    Returns:
        dict: Status, processed count, and failed count
    """
    result = await heartbeat_service.process_heartbeat(user.id)
    return result

