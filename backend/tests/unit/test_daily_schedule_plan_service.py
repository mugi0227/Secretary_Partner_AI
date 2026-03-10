from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.models.enums import CreatedBy, TaskStatus
from app.models.schedule_plan import ScheduleTimeBlock, TimeBlockMoveRequest
from app.models.task import Task, TaskUpdate
from app.services.daily_schedule_plan_service import (
    DailySchedulePlanService,
    _build_meeting_intervals,
)


def _build_task(
    task_id: UUID,
    *,
    project_id: UUID | None = None,
    start_time: datetime,
    end_time: datetime,
    is_all_day: bool = False,
    is_fixed_time: bool = True,
) -> Task:
    now = datetime.now(timezone.utc)
    return Task(
        id=task_id,
        user_id="owner-user",
        project_id=project_id,
        title="Meeting",
        status=TaskStatus.TODO,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
        is_fixed_time=is_fixed_time,
        start_time=start_time,
        end_time=end_time,
        is_all_day=is_all_day,
    )


def _build_service(task_repo: AsyncMock, plan_repo: AsyncMock) -> DailySchedulePlanService:
    user_repo = AsyncMock()
    user_repo.get.return_value = None
    return DailySchedulePlanService(
        task_repo=task_repo,
        project_repo=AsyncMock(),
        assignment_repo=AsyncMock(),
        snapshot_repo=AsyncMock(),
        user_repo=user_repo,
        settings_repo=AsyncMock(),
        plan_repo=plan_repo,
    )


@pytest.mark.asyncio
async def test_move_time_block_uses_repository_signature_for_personal_task() -> None:
    user_id = str(uuid4())
    task_id = uuid4()
    original_start = datetime(2026, 2, 8, 9, 0, tzinfo=timezone.utc)
    original_end = datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc)
    moved_start = datetime(2026, 2, 8, 11, 0, tzinfo=timezone.utc)
    moved_end = datetime(2026, 2, 8, 12, 0, tzinfo=timezone.utc)

    task_repo = AsyncMock()
    task_repo.get.return_value = _build_task(
        task_id,
        start_time=original_start,
        end_time=original_end,
    )
    task_repo.update.return_value = _build_task(
        task_id,
        start_time=moved_start,
        end_time=moved_end,
    )
    plan_repo = AsyncMock()
    plan_repo.update_time_block.return_value = ScheduleTimeBlock(
        task_id=task_id,
        start=moved_start,
        end=moved_end,
        kind="meeting",
        status="TODO",
    )
    group_id = uuid4()
    plan_repo.get_by_date.return_value = SimpleNamespace(plan_group_id=group_id)
    service = _build_service(task_repo, plan_repo)

    request = TimeBlockMoveRequest(
        task_id=task_id,
        original_date=date(2026, 2, 8),
        new_start=moved_start,
        new_end=moved_end,
    )

    result = await service.move_time_block(user_id=user_id, request=request)

    assert result is not None
    task_repo.get.assert_awaited_once_with(user_id, task_id)
    task_repo.update.assert_awaited_once()
    kwargs = task_repo.update.await_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["task_id"] == task_id
    assert kwargs["project_id"] is None
    assert isinstance(kwargs["update"], TaskUpdate)
    plan_repo.update_task_snapshot_for_group.assert_awaited_once()
    snapshot_call = plan_repo.update_task_snapshot_for_group.await_args.kwargs
    assert snapshot_call["user_id"] == user_id
    assert snapshot_call["plan_group_id"] == group_id
    assert snapshot_call["snapshot"].task_id == task_id


@pytest.mark.asyncio
async def test_move_time_block_falls_back_to_get_by_id_for_project_task() -> None:
    user_id = str(uuid4())
    task_id = uuid4()
    project_id = uuid4()
    original_start = datetime(2026, 2, 8, 9, 0, tzinfo=timezone.utc)
    original_end = datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc)
    moved_start = datetime(2026, 2, 8, 13, 0, tzinfo=timezone.utc)
    moved_end = datetime(2026, 2, 8, 14, 0, tzinfo=timezone.utc)

    task_repo = AsyncMock()
    task_repo.get.return_value = None
    task_repo.get_by_id.return_value = _build_task(
        task_id,
        project_id=project_id,
        start_time=original_start,
        end_time=original_end,
    )
    task_repo.update.return_value = _build_task(
        task_id,
        project_id=project_id,
        start_time=moved_start,
        end_time=moved_end,
    )
    plan_repo = AsyncMock()
    plan_repo.update_time_block.return_value = ScheduleTimeBlock(
        task_id=task_id,
        start=moved_start,
        end=moved_end,
        kind="meeting",
        status="TODO",
    )
    group_id = uuid4()
    plan_repo.get_by_date.return_value = SimpleNamespace(plan_group_id=group_id)
    service = _build_service(task_repo, plan_repo)

    request = TimeBlockMoveRequest(
        task_id=task_id,
        original_date=date(2026, 2, 8),
        new_start=moved_start,
        new_end=moved_end,
    )

    result = await service.move_time_block(user_id=user_id, request=request)

    assert result is not None
    task_repo.get.assert_awaited_once_with(user_id, task_id)
    task_repo.get_by_id.assert_awaited_once_with(user_id, task_id)
    task_repo.update.assert_awaited_once()
    kwargs = task_repo.update.await_args.kwargs
    assert kwargs["project_id"] == project_id
    assert isinstance(kwargs["update"], TaskUpdate)
    plan_repo.update_task_snapshot_for_group.assert_awaited_once()
    snapshot_call = plan_repo.update_task_snapshot_for_group.await_args.kwargs
    assert snapshot_call["plan_group_id"] == group_id
    assert snapshot_call["snapshot"].task_id == task_id


def test_build_meeting_intervals_all_day_respects_target_date() -> None:
    task_id = uuid4()
    all_day_date = date(2026, 2, 8)
    task = _build_task(
        task_id,
        start_time=datetime(2026, 2, 8, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 2, 8, 23, 59, tzinfo=timezone.utc),
        is_all_day=True,
    )

    same_day = _build_meeting_intervals([task], all_day_date, "UTC")
    other_day = _build_meeting_intervals([task], all_day_date + timedelta(days=1), "UTC")

    assert len(same_day) == 1
    assert same_day[0].start_minutes == 0
    assert same_day[0].end_minutes == 24 * 60
    assert other_day == []


def test_filter_tasks_for_plan_always_includes_fixed_time_meetings() -> None:
    """Fixed-time meetings must always be included so that _build_time_blocks
    can correctly classify them as meeting blocks instead of auto blocks."""
    team_project_id = uuid4()
    private_project_id = uuid4()
    user_id = "member-user"
    start = datetime(2026, 2, 8, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 8, 10, 0, tzinfo=timezone.utc)

    assigned_team_task = _build_task(
        uuid4(),
        project_id=team_project_id,
        start_time=start,
        end_time=end,
        is_fixed_time=False,
    )
    unassigned_team_meeting = _build_task(
        uuid4(),
        project_id=team_project_id,
        start_time=start,
        end_time=end,
        is_fixed_time=True,
    )
    private_meeting = _build_task(
        uuid4(),
        project_id=private_project_id,
        start_time=start,
        end_time=end,
        is_fixed_time=True,
    )

    assignments = [
        SimpleNamespace(task_id=assigned_team_task.id, assignee_id=user_id, status=None),
    ]
    service = _build_service(AsyncMock(), AsyncMock())

    filtered = service._filter_tasks_for_plan(
        [assigned_team_task, unassigned_team_meeting, private_meeting],
        assignments,
        user_id,
        True,
        "UTC",
        team_project_ids={team_project_id},
    )
    filtered_ids = {task.id for task in filtered}

    assert assigned_team_task.id in filtered_ids
    assert private_meeting.id in filtered_ids
    # Fixed-time meetings are always included regardless of assignment
    # to prevent them from being auto-scheduled like regular tasks
    assert unassigned_team_meeting.id in filtered_ids


def test_build_meeting_intervals_treats_naive_values_as_utc() -> None:
    task_id = uuid4()
    task = _build_task(
        task_id,
        start_time=datetime(2026, 2, 8, 0, 0),
        end_time=datetime(2026, 2, 8, 1, 0),
    )

    intervals = _build_meeting_intervals([task], date(2026, 2, 8), "Asia/Tokyo")

    assert len(intervals) == 1
    assert intervals[0].start_minutes == 9 * 60
    assert intervals[0].end_minutes == 10 * 60