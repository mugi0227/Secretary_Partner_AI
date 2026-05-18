from uuid import uuid4

import pytest

from app.infrastructure.local.heartbeat_event_repository import SqliteHeartbeatEventRepository
from app.models.heartbeat import HeartbeatEventCreate, HeartbeatSeverity


@pytest.fixture
def repository(db_session):
    def factory():
        class SessionCtx:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return SessionCtx()

    return SqliteHeartbeatEventRepository(session_factory=factory)


def _make_event(
    *,
    user_id: str = "user-1",
    session_id: str = "heartbeat-20260518",
    is_read: bool = False,
) -> HeartbeatEventCreate:
    return HeartbeatEventCreate(
        user_id=user_id,
        task_id=uuid4(),
        severity=HeartbeatSeverity.HIGH,
        risk_score=42,
        metadata={"chat_session_id": session_id},
        is_read=is_read,
    )


@pytest.mark.asyncio
async def test_list_unread_returns_only_unread_events_for_user(repository) -> None:
    unread = await repository.create(_make_event(session_id="heartbeat-unread"))
    await repository.create(_make_event(session_id="heartbeat-read", is_read=True))
    await repository.create(_make_event(user_id="other-user", session_id="heartbeat-other"))

    results = await repository.list_unread("user-1")

    assert [event.id for event in results] == [unread.id]
    assert results[0].metadata["chat_session_id"] == "heartbeat-unread"
