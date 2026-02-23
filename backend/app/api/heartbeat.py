"""
Heartbeat API endpoint.

Called periodically to trigger autonomous agent actions.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps import (
    AgentTaskRepo,
    ChatRepo,
    CheckinRepo,
    CurrentUser,
    HeartbeatEventRepo,
    HeartbeatSettingsRepo,
    LLMProvider,
    ProjectRepo,
    RecurringMeetingRepo,
    RecurringTaskRepo,
    TaskAssignmentRepo,
    TaskRepo,
    UserRepo,
)
from app.models.heartbeat import HeartbeatSettingsUpdate
from app.services.heartbeat_service import HeartbeatService
from app.services.recurring_meeting_service import RecurringMeetingService
from app.services.recurring_task_service import RecurringTaskService
from app.services.task_heartbeat_service import TaskHeartbeatService

router = APIRouter()


class HeartbeatSettingsResponse(BaseModel):
    user_id: str
    enabled: bool
    notification_limit_per_day: int
    notification_window_start: str
    notification_window_end: str
    heartbeat_intensity: str
    daily_capacity_per_task_minutes: int
    cooldown_hours_per_task: int
    created_at: datetime
    updated_at: datetime


class HeartbeatRiskTaskResponse(BaseModel):
    task_id: str
    title: str
    severity: str
    risk_score: float
    days_remaining: int | None
    required_days: int | None
    slack_ratio: float | None
    due_date: datetime | None


class HeartbeatStatusResponse(BaseModel):
    evaluated: int
    risk_level: str
    top_risks: list[HeartbeatRiskTaskResponse]
    evaluated_at: datetime
    sent_today: int
    limit: int


class HeartbeatUnreadCountResponse(BaseModel):
    count: int


def get_task_heartbeat_service(
    task_repo: TaskRepo,
    task_assignment_repo: TaskAssignmentRepo,
    chat_repo: ChatRepo,
    heartbeat_settings_repo: HeartbeatSettingsRepo,
    heartbeat_event_repo: HeartbeatEventRepo,
    user_repo: UserRepo,
    project_repo: ProjectRepo,
    llm_provider: LLMProvider,
) -> TaskHeartbeatService:
    return TaskHeartbeatService(
        task_repo=task_repo,
        task_assignment_repo=task_assignment_repo,
        chat_repo=chat_repo,
        settings_repo=heartbeat_settings_repo,
        event_repo=heartbeat_event_repo,
        user_repo=user_repo,
        project_repo=project_repo,
        llm_provider=llm_provider,
    )


def get_heartbeat_service(
    agent_task_repo: AgentTaskRepo,
    recurring_meeting_repo: RecurringMeetingRepo,
    recurring_task_repo: RecurringTaskRepo,
    task_repo: TaskRepo,
    checkin_repo: CheckinRepo,
    user_repo: UserRepo,
    task_heartbeat_service: TaskHeartbeatService = Depends(get_task_heartbeat_service),
) -> HeartbeatService:
    """Get HeartbeatService instance."""
    recurring_service = RecurringMeetingService(
        recurring_repo=recurring_meeting_repo,
        task_repo=task_repo,
        checkin_repo=checkin_repo,
        user_repo=user_repo,
    )
    recurring_task_service = RecurringTaskService(
        recurring_repo=recurring_task_repo,
        task_repo=task_repo,
        user_repo=user_repo,
    )
    return HeartbeatService(
        agent_task_repo=agent_task_repo,
        recurring_meeting_service=recurring_service,
        recurring_task_service=recurring_task_service,
        task_heartbeat_service=task_heartbeat_service,
        user_repo=user_repo,
    )


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


@router.get("/status", response_model=HeartbeatStatusResponse, status_code=status.HTTP_200_OK)
async def heartbeat_status(
    user: CurrentUser,
    task_heartbeat_service: TaskHeartbeatService = Depends(get_task_heartbeat_service),
):
    status_data = await task_heartbeat_service.get_status(user.id)
    top_risks = [
        HeartbeatRiskTaskResponse(
            task_id=str(item.task.id),
            title=item.task.title,
            severity=item.severity.value,
            risk_score=item.risk_score,
            days_remaining=item.days_remaining,
            required_days=item.required_days,
            slack_ratio=item.slack_ratio,
            due_date=item.task.due_date,
        )
        for item in status_data["top_risks"]
    ]
    return HeartbeatStatusResponse(
        evaluated=status_data["evaluated"],
        risk_level=status_data["risk_level"],
        top_risks=top_risks,
        evaluated_at=status_data["evaluated_at"],
        sent_today=status_data["sent_today"],
        limit=status_data["limit"],
    )


@router.get("/settings", response_model=HeartbeatSettingsResponse, status_code=status.HTTP_200_OK)
async def get_heartbeat_settings(
    user: CurrentUser,
    settings_repo: HeartbeatSettingsRepo,
):
    settings = await settings_repo.get(user.id)
    if not settings:
        settings = await settings_repo.upsert(user.id, HeartbeatSettingsUpdate())
    return HeartbeatSettingsResponse(
        user_id=settings.user_id,
        enabled=settings.enabled,
        notification_limit_per_day=settings.notification_limit_per_day,
        notification_window_start=settings.notification_window_start,
        notification_window_end=settings.notification_window_end,
        heartbeat_intensity=settings.heartbeat_intensity.value,
        daily_capacity_per_task_minutes=settings.daily_capacity_per_task_minutes,
        cooldown_hours_per_task=settings.cooldown_hours_per_task,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.put("/settings", response_model=HeartbeatSettingsResponse, status_code=status.HTTP_200_OK)
async def update_heartbeat_settings(
    payload: HeartbeatSettingsUpdate,
    user: CurrentUser,
    settings_repo: HeartbeatSettingsRepo,
):
    settings = await settings_repo.upsert(user.id, payload)
    return HeartbeatSettingsResponse(
        user_id=settings.user_id,
        enabled=settings.enabled,
        notification_limit_per_day=settings.notification_limit_per_day,
        notification_window_start=settings.notification_window_start,
        notification_window_end=settings.notification_window_end,
        heartbeat_intensity=settings.heartbeat_intensity.value,
        daily_capacity_per_task_minutes=settings.daily_capacity_per_task_minutes,
        cooldown_hours_per_task=settings.cooldown_hours_per_task,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get(
    "/unread-count",
    response_model=HeartbeatUnreadCountResponse,
    status_code=status.HTTP_200_OK,
)
async def get_heartbeat_unread_count(
    user: CurrentUser,
    event_repo: HeartbeatEventRepo,
):
    count = await event_repo.count_unread(user.id)
    return HeartbeatUnreadCountResponse(count=count)


@router.post(
    "/mark-read",
    response_model=HeartbeatUnreadCountResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_heartbeat_as_read(
    user: CurrentUser,
    event_repo: HeartbeatEventRepo,
):
    await event_repo.mark_all_read(user.id)
    count = await event_repo.count_unread(user.id)
    return HeartbeatUnreadCountResponse(count=count)

