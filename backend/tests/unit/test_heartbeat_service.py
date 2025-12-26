"""
Unit tests for HeartbeatService.
"""

import pytest
from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.heartbeat_service import HeartbeatService
from app.models.agent_task import AgentTask, AgentTaskPayload
from app.models.enums import AgentTaskStatus, ActionType


@pytest.fixture
def mock_agent_task_repo():
    """Create mock agent task repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def heartbeat_service(mock_agent_task_repo):
    """Create HeartbeatService with mocked dependencies."""
    return HeartbeatService(agent_task_repo=mock_agent_task_repo)


@pytest.mark.asyncio
async def test_is_quiet_hours():
    """Test quiet hours detection."""
    service = HeartbeatService(agent_task_repo=AsyncMock())

    # During quiet hours (2:00 AM - 6:00 AM)
    assert service._is_quiet_hours(time(2, 0)) is True
    assert service._is_quiet_hours(time(3, 30)) is True
    assert service._is_quiet_hours(time(5, 59)) is True

    # Outside quiet hours
    assert service._is_quiet_hours(time(1, 59)) is False
    assert service._is_quiet_hours(time(6, 0)) is False
    assert service._is_quiet_hours(time(12, 0)) is False
    assert service._is_quiet_hours(time(23, 0)) is False


@pytest.mark.asyncio
async def test_process_heartbeat_quiet_hours(heartbeat_service, mock_agent_task_repo):
    """Test heartbeat during quiet hours - should skip."""
    user_id = "test_user"

    # Mock current time to be during quiet hours
    import app.services.heartbeat_service
    original_datetime = app.services.heartbeat_service.datetime

    class MockDateTime:
        @staticmethod
        def now():
            mock_now = datetime.now().replace(hour=3, minute=0)  # 3:00 AM
            return mock_now

    app.services.heartbeat_service.datetime = MockDateTime

    try:
        result = await heartbeat_service.process_heartbeat(user_id)

        assert result["status"] == "quiet_hours"
        assert result["processed"] == 0
        # Should not call repository
        mock_agent_task_repo.get_pending.assert_not_called()
    finally:
        app.services.heartbeat_service.datetime = original_datetime


@pytest.mark.asyncio
async def test_process_heartbeat_no_pending_tasks(heartbeat_service, mock_agent_task_repo):
    """Test heartbeat with no pending tasks."""
    user_id = "test_user"

    # No pending tasks
    mock_agent_task_repo.get_pending.return_value = []

    import app.services.heartbeat_service
    original_datetime = app.services.heartbeat_service.datetime

    class MockDateTime:
        @staticmethod
        def now():
            mock_now = datetime.now().replace(hour=12, minute=0)
            return mock_now

    app.services.heartbeat_service.datetime = MockDateTime

    try:
        result = await heartbeat_service.process_heartbeat(user_id)
    finally:
        app.services.heartbeat_service.datetime = original_datetime

    assert result["status"] == "success"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_process_heartbeat_with_pending_tasks(heartbeat_service, mock_agent_task_repo):
    """Test heartbeat with pending tasks."""
    user_id = "test_user"

    # Create mock pending tasks
    task1 = AgentTask(
        id=uuid4(),
        user_id=user_id,
        trigger_time=datetime.now() - timedelta(minutes=5),
        action_type=ActionType.CHECK_PROGRESS,
        status=AgentTaskStatus.PENDING,
        payload=AgentTaskPayload(message_tone="gentle"),
        retry_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    task2 = AgentTask(
        id=uuid4(),
        user_id=user_id,
        trigger_time=datetime.now() - timedelta(minutes=10),
        action_type=ActionType.ENCOURAGE,
        status=AgentTaskStatus.PENDING,
        payload=AgentTaskPayload(message_tone="neutral"),
        retry_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    mock_agent_task_repo.get_pending.return_value = [task1, task2]
    mock_agent_task_repo.mark_completed.return_value = task1

    import app.services.heartbeat_service
    original_datetime = app.services.heartbeat_service.datetime

    class MockDateTime:
        @staticmethod
        def now():
            mock_now = datetime.now().replace(hour=12, minute=0)
            return mock_now

    app.services.heartbeat_service.datetime = MockDateTime

    try:
        result = await heartbeat_service.process_heartbeat(user_id)
    finally:
        app.services.heartbeat_service.datetime = original_datetime

    assert result["status"] == "success"
    assert result["processed"] == 2
    assert mock_agent_task_repo.mark_completed.call_count == 2


@pytest.mark.asyncio
async def test_process_heartbeat_task_failure(heartbeat_service, mock_agent_task_repo):
    """Test heartbeat when a task execution fails."""
    user_id = "test_user"

    # Create mock pending task
    task = AgentTask(
        id=uuid4(),
        user_id=user_id,
        trigger_time=datetime.now() - timedelta(minutes=5),
        action_type=ActionType.CHECK_PROGRESS,
        status=AgentTaskStatus.PENDING,
        payload=AgentTaskPayload(message_tone="gentle"),
        retry_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    mock_agent_task_repo.get_pending.return_value = [task]

    # Simulate execution failure
    mock_agent_task_repo.mark_completed.side_effect = Exception("Execution failed")
    mock_agent_task_repo.mark_failed.return_value = task

    import app.services.heartbeat_service
    original_datetime = app.services.heartbeat_service.datetime

    class MockDateTime:
        @staticmethod
        def now():
            mock_now = datetime.now().replace(hour=12, minute=0)
            return mock_now

    app.services.heartbeat_service.datetime = MockDateTime

    try:
        result = await heartbeat_service.process_heartbeat(user_id)
    finally:
        app.services.heartbeat_service.datetime = original_datetime

    # Should still return success even if tasks fail
    assert result["status"] == "success"
    assert result["processed"] == 0
    assert result["failed"] == 1

    # Should call mark_failed
    mock_agent_task_repo.mark_failed.assert_called_once()


@pytest.mark.asyncio
async def test_execute_agent_task_check_progress():
    """Test executing CHECK_PROGRESS action."""
    service = HeartbeatService(agent_task_repo=AsyncMock())

    task = AgentTask(
        id=uuid4(),
        user_id="test_user",
        trigger_time=datetime.now(),
        action_type=ActionType.CHECK_PROGRESS,
        status=AgentTaskStatus.PENDING,
        payload=AgentTaskPayload(
            target_task_id=uuid4(),
            message_tone="gentle",
        ),
        retry_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    # Should not raise exception
    result = await service._execute_agent_task("test_user", task)
    assert result is not None


@pytest.mark.asyncio
async def test_execute_agent_task_encourage():
    """Test executing ENCOURAGE action."""
    service = HeartbeatService(agent_task_repo=AsyncMock())

    task = AgentTask(
        id=uuid4(),
        user_id="test_user",
        trigger_time=datetime.now(),
        action_type=ActionType.ENCOURAGE,
        status=AgentTaskStatus.PENDING,
        payload=AgentTaskPayload(message_tone="neutral"),
        retry_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    result = await service._execute_agent_task("test_user", task)
    assert result is not None
