from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.chat_session import ChatMessage
from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus
from app.models.heartbeat import HeartbeatEvent, HeartbeatSettings
from app.models.task import Task
from app.models.user import UserAccount
from app.services.task_heartbeat_service import TaskHeartbeatService
from app.utils.datetime_utils import UTC


def make_task(**overrides) -> Task:
    now = overrides.pop("now", datetime(2024, 1, 10, 12, 0, tzinfo=UTC))
    data = {
        "id": uuid4(),
        "user_id": "user",
        "title": "Test Task",
        "description": None,
        "purpose": None,
        "project_id": None,
        "phase_id": None,
        "importance": Priority.MEDIUM,
        "urgency": Priority.MEDIUM,
        "energy_level": EnergyLevel.LOW,
        "estimated_minutes": 60,
        "due_date": None,
        "start_not_before": None,
        "pinned_date": None,
        "parent_id": None,
        "order_in_parent": None,
        "dependency_ids": [],
        "same_day_allowed": True,
        "min_gap_days": 0,
        "progress": 0,
        "start_time": None,
        "end_time": None,
        "is_fixed_time": False,
        "is_all_day": False,
        "location": None,
        "attendees": [],
        "meeting_notes": None,
        "recurring_meeting_id": None,
        "recurring_task_id": None,
        "milestone_id": None,
        "touchpoint_count": None,
        "touchpoint_minutes": None,
        "touchpoint_gap_days": 0,
        "touchpoint_steps": [],
        "completion_note": None,
        "guide": None,
        "requires_all_completion": False,
        "status": TaskStatus.TODO,
        "source_capture_id": None,
        "created_by": CreatedBy.USER,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "completed_by": None,
    }
    data.update(overrides)
    return Task(**data)


def make_settings(now: datetime) -> HeartbeatSettings:
    return HeartbeatSettings(
        user_id="user",
        enabled=True,
        notification_limit_per_day=3,
        notification_window_start="00:00",
        notification_window_end="23:59",
        heartbeat_intensity="standard",
        daily_capacity_per_task_minutes=60,
        cooldown_hours_per_task=24,
        created_at=now,
        updated_at=now,
    )


def make_chat_message(
    user_id: str,
    now: datetime,
    session_id: str = "heartbeat-test",
) -> ChatMessage:
    return ChatMessage(
        id=uuid4(),
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content="message",
        created_at=now,
    )


@pytest.mark.asyncio
async def test_run_creates_chat_message_for_critical_task():
    now = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
    user_id = str(uuid4())
    task = make_task(
        title="Critical Task",
        estimated_minutes=180,
        due_date=now,
        now=now,
    )
    settings = make_settings(now)

    task_repo = AsyncMock()
    task_repo.list.return_value = [task]

    chat_repo = AsyncMock()
    chat_repo.add_message.return_value = make_chat_message(user_id, now)

    settings_repo = AsyncMock()
    settings_repo.get.return_value = settings

    event_repo = AsyncMock()
    event_repo.list_by_user_since.return_value = []
    event_repo.count_by_user_since.return_value = 0
    event_repo.create.return_value = HeartbeatEvent(
        id=uuid4(),
        user_id=user_id,
        task_id=task.id,
        severity="critical",
        risk_score=80,
        notification_id=None,
        metadata={},
        created_at=now,
    )

    user_repo = AsyncMock()
    user_repo.get.return_value = UserAccount(
        id=UUID(user_id),
        provider_issuer="issuer",
        provider_sub="sub",
        email=None,
        display_name=None,
        first_name=None,
        last_name=None,
        username=None,
        password_hash=None,
        timezone="UTC",
        enable_weekly_meeting_reminder=False,
        created_at=now,
        updated_at=now,
    )

    service = TaskHeartbeatService(
        task_repo=task_repo,
        chat_repo=chat_repo,
        settings_repo=settings_repo,
        event_repo=event_repo,
        user_repo=user_repo,
        task_assignment_repo=None,
    )

    result = await service.run(user_id, now=now)

    assert result["status"] == "success"
    assert result["notified"] == 1
    call_kwargs = chat_repo.add_message.call_args.kwargs
    assert call_kwargs["session_id"].startswith("heartbeat-")
    assert call_kwargs["title"].startswith("Heartbeat")
    chat_repo.add_message.assert_called_once()
    event_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_run_notifies_high_risk_task_without_deadline():
    now = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
    user_id = str(uuid4())
    task = make_task(
        title="Stale Important Task",
        importance=Priority.HIGH,
        estimated_minutes=60,
        due_date=None,
        updated_at=now - timedelta(days=20),
        now=now,
    )
    settings = make_settings(now)

    task_repo = AsyncMock()
    task_repo.list.return_value = [task]

    chat_repo = AsyncMock()
    chat_repo.add_message.return_value = make_chat_message(user_id, now)

    settings_repo = AsyncMock()
    settings_repo.get.return_value = settings

    event_repo = AsyncMock()
    event_repo.list_by_user_since.return_value = []
    event_repo.count_by_user_since.return_value = 0
    event_repo.create.return_value = HeartbeatEvent(
        id=uuid4(),
        user_id=user_id,
        task_id=task.id,
        severity="high",
        risk_score=60,
        notification_id=None,
        metadata={},
        created_at=now,
    )

    user_repo = AsyncMock()
    user_repo.get.return_value = UserAccount(
        id=UUID(user_id),
        provider_issuer="issuer",
        provider_sub="sub",
        email=None,
        display_name=None,
        first_name=None,
        last_name=None,
        username=None,
        password_hash=None,
        timezone="UTC",
        enable_weekly_meeting_reminder=False,
        created_at=now,
        updated_at=now,
    )

    service = TaskHeartbeatService(
        task_repo=task_repo,
        chat_repo=chat_repo,
        settings_repo=settings_repo,
        event_repo=event_repo,
        user_repo=user_repo,
        task_assignment_repo=None,
    )

    result = await service.run(user_id, now=now)

    assert result["status"] == "success"
    assert result["notified"] == 1
    chat_repo.add_message.assert_called_once()
    event_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_run_respects_daily_limit():
    now = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
    user_id = str(uuid4())
    task = make_task(
        title="Limited Task",
        estimated_minutes=60,
        due_date=now,
        now=now,
    )
    settings = make_settings(now)
    settings.notification_limit_per_day = 1

    task_repo = AsyncMock()
    task_repo.list.return_value = [task]

    chat_repo = AsyncMock()
    settings_repo = AsyncMock()
    settings_repo.get.return_value = settings

    event_repo = AsyncMock()
    event_repo.list_by_user_since.return_value = []
    event_repo.count_by_user_since.return_value = 1

    user_repo = AsyncMock()
    user_repo.get.return_value = UserAccount(
        id=UUID(user_id),
        provider_issuer="issuer",
        provider_sub="sub",
        email=None,
        display_name=None,
        first_name=None,
        last_name=None,
        username=None,
        password_hash=None,
        timezone="UTC",
        enable_weekly_meeting_reminder=False,
        created_at=now,
        updated_at=now,
    )

    service = TaskHeartbeatService(
        task_repo=task_repo,
        chat_repo=chat_repo,
        settings_repo=settings_repo,
        event_repo=event_repo,
        user_repo=user_repo,
        task_assignment_repo=None,
    )

    result = await service.run(user_id, now=now)

    assert result["status"] == "limit_reached"
    chat_repo.add_message.assert_not_called()


@pytest.mark.asyncio
async def test_get_status_reports_high_risk_level():
    now = datetime(2024, 1, 10, 12, 0, tzinfo=UTC)
    user_id = str(uuid4())
    task = make_task(
        title="Risk Task",
        estimated_minutes=180,
        due_date=now,
        now=now,
    )
    settings = make_settings(now)

    task_repo = AsyncMock()
    task_repo.list.return_value = [task]

    chat_repo = AsyncMock()
    settings_repo = AsyncMock()
    settings_repo.get.return_value = settings

    event_repo = AsyncMock()
    event_repo.count_by_user_since.return_value = 0

    user_repo = AsyncMock()
    user_repo.get.return_value = UserAccount(
        id=UUID(user_id),
        provider_issuer="issuer",
        provider_sub="sub",
        email=None,
        display_name=None,
        first_name=None,
        last_name=None,
        username=None,
        password_hash=None,
        timezone="UTC",
        enable_weekly_meeting_reminder=False,
        created_at=now,
        updated_at=now,
    )

    service = TaskHeartbeatService(
        task_repo=task_repo,
        chat_repo=chat_repo,
        settings_repo=settings_repo,
        event_repo=event_repo,
        user_repo=user_repo,
        task_assignment_repo=None,
    )

    result = await service.get_status(user_id, now=now)

    assert result["evaluated"] == 1
    assert result["risk_level"] == "high"
    assert len(result["top_risks"]) == 1
