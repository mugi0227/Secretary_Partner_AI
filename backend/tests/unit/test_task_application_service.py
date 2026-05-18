from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import BusinessLogicError
from app.models.enums import CreatedBy, TaskStatus
from app.models.postpone import DoTodayRequest, PostponeRequest
from app.models.task import Task, TaskUpdate
from app.services.task_application_service import TaskApplicationService
from app.utils.datetime_utils import get_user_today, user_date_to_utc


def _task(
    user_id: str,
    *,
    status: TaskStatus = TaskStatus.TODO,
    start_not_before: datetime | None = None,
    pinned_date: datetime | None = None,
    requires_all_completion: bool = False,
) -> Task:
    now = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    return Task(
        id=uuid4(),
        user_id=user_id,
        title="Task",
        status=status,
        start_not_before=start_not_before,
        pinned_date=pinned_date,
        requires_all_completion=requires_all_completion,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_postpone_task_clears_pin_as_explicit_update() -> None:
    user_id = str(uuid4())
    existing = _task(
        user_id,
        pinned_date=datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    task_repo = AsyncMock()
    project_repo = AsyncMock()
    postpone_repo = AsyncMock()
    user_repo = AsyncMock()

    task_repo.get.return_value = existing
    task_repo.update.return_value = existing
    user_repo.get.return_value = SimpleNamespace(timezone="Asia/Tokyo")

    service = TaskApplicationService(
        task_repo=task_repo,
        project_repo=project_repo,
        postpone_repo=postpone_repo,
        user_repo=user_repo,
    )

    await service.postpone_task(
        user_id,
        existing.id,
        PostponeRequest(to_date=get_user_today("Asia/Tokyo") + timedelta(days=1)),
    )

    update = task_repo.update.await_args.args[2]
    assert isinstance(update, TaskUpdate)
    assert update.pinned_date is None
    assert "pinned_date" in update.model_fields_set


@pytest.mark.asyncio
async def test_do_today_uses_user_timezone_to_clear_future_start_gate() -> None:
    user_id = str(uuid4())
    timezone_name = "Asia/Tokyo"
    today = get_user_today(timezone_name)
    tomorrow_start = user_date_to_utc(today + timedelta(days=1), timezone_name)
    today_start = user_date_to_utc(today, timezone_name)
    existing = _task(user_id, start_not_before=tomorrow_start)
    task_repo = AsyncMock()
    project_repo = AsyncMock()
    user_repo = AsyncMock()

    task_repo.get.return_value = existing
    task_repo.update.return_value = existing
    user_repo.get.return_value = SimpleNamespace(timezone=timezone_name)

    service = TaskApplicationService(
        task_repo=task_repo,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    await service.do_today(user_id, existing.id, DoTodayRequest(pin=True))

    update = task_repo.update.await_args.args[2]
    assert update.start_not_before == today_start
    assert update.pinned_date == today_start


@pytest.mark.asyncio
async def test_update_task_requires_all_assignees_done_before_task_done() -> None:
    user_id = str(uuid4())
    existing = _task(user_id, requires_all_completion=True)
    task_repo = AsyncMock()
    project_repo = AsyncMock()
    assignment_repo = AsyncMock()

    task_repo.get.return_value = existing
    assignment_repo.list_by_task.return_value = [
        SimpleNamespace(status=TaskStatus.DONE),
        SimpleNamespace(status=TaskStatus.TODO),
    ]

    service = TaskApplicationService(
        task_repo=task_repo,
        project_repo=project_repo,
        assignment_repo=assignment_repo,
    )

    with pytest.raises(BusinessLogicError):
        await service.update_task(user_id, existing.id, TaskUpdate(status=TaskStatus.DONE))

    task_repo.update.assert_not_called()
