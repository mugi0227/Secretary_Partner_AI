"""
Unit tests for lightning line service.
"""

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus
from app.models.task import Task
from app.services.lightning_line_service import LightningLineService


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _make_task(
    *,
    task_id: UUID | None = None,
    project_id: UUID,
    status: TaskStatus,
    progress: int,
    due_date: datetime | None,
    start_not_before: datetime | None = None,
    estimated_minutes: int | None = 60,
) -> Task:
    now = datetime.now(timezone.utc)
    return Task(
        id=task_id or uuid4(),
        user_id="user",
        project_id=project_id,
        phase_id=None,
        title="task",
        description=None,
        purpose=None,
        status=status,
        importance=Priority.MEDIUM,
        urgency=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
        estimated_minutes=estimated_minutes,
        due_date=due_date,
        start_not_before=start_not_before,
        pinned_date=None,
        parent_id=None,
        order_in_parent=None,
        dependency_ids=[],
        same_day_allowed=True,
        min_gap_days=0,
        progress=progress,
        start_time=None,
        end_time=None,
        is_fixed_time=False,
        is_all_day=False,
        location=None,
        attendees=[],
        meeting_notes=None,
        recurring_meeting_id=None,
        recurring_task_id=None,
        milestone_id=None,
        touchpoint_count=None,
        touchpoint_minutes=None,
        touchpoint_gap_days=0,
        touchpoint_steps=[],
        guide=None,
        completion_note=None,
        source_capture_id=None,
        created_by=CreatedBy.USER,
        created_at=now,
        updated_at=now,
        completed_at=None,
        completed_by=None,
        auto_completed_by_parent_id=None,
        requires_all_completion=False,
    )


class _StubTaskRepo:
    def __init__(self, tasks: list[Task]):
        self._tasks = tasks

    async def list(self, user_id, project_id=None, include_done=False, limit=100, offset=0, **kwargs):
        scoped = [task for task in self._tasks if task.project_id == project_id]
        return scoped[offset : offset + limit]


@pytest.mark.asyncio
async def test_lightning_line_deviation_signs_for_progress():
    project_id = uuid4()
    reference_date = date(2026, 2, 24)

    delayed = _make_task(
        project_id=project_id,
        status=TaskStatus.IN_PROGRESS,
        progress=20,
        start_not_before=_dt("2026-02-20T00:00:00"),
        due_date=_dt("2026-02-28T00:00:00"),
    )
    ahead = _make_task(
        project_id=project_id,
        status=TaskStatus.IN_PROGRESS,
        progress=80,
        start_not_before=_dt("2026-02-20T00:00:00"),
        due_date=_dt("2026-02-28T00:00:00"),
    )
    service = LightningLineService(_StubTaskRepo([delayed, ahead]))

    result = await service.calculate("user", project_id, reference_date=reference_date)
    by_id = {point.task_id: point for point in result.points}

    assert by_id[delayed.id].deviation_days < 0
    assert by_id[ahead.id].deviation_days > 0


@pytest.mark.asyncio
async def test_lightning_line_done_task_before_due_is_pinned_to_due():
    project_id = uuid4()
    reference_date = date(2026, 2, 24)
    done_future = _make_task(
        project_id=project_id,
        status=TaskStatus.DONE,
        progress=100,
        due_date=_dt("2026-03-01T00:00:00"),
    )
    service = LightningLineService(_StubTaskRepo([done_future]))

    result = await service.calculate("user", project_id, reference_date=reference_date)

    assert len(result.points) == 1
    assert result.points[0].deviation_days == 5.0


@pytest.mark.asyncio
async def test_lightning_line_done_task_after_due_is_pinned_to_now():
    project_id = uuid4()
    reference_date = date(2026, 2, 24)
    done_past = _make_task(
        project_id=project_id,
        status=TaskStatus.DONE,
        progress=100,
        due_date=_dt("2026-02-10T00:00:00"),
    )
    service = LightningLineService(_StubTaskRepo([done_past]))

    result = await service.calculate("user", project_id, reference_date=reference_date)

    assert len(result.points) == 1
    assert result.points[0].deviation_days == 0.0


@pytest.mark.asyncio
async def test_lightning_line_skips_tasks_without_due_date():
    project_id = uuid4()
    reference_date = date(2026, 2, 24)
    undated = _make_task(
        project_id=project_id,
        status=TaskStatus.IN_PROGRESS,
        progress=50,
        due_date=None,
    )
    service = LightningLineService(_StubTaskRepo([undated]))

    result = await service.calculate("user", project_id, reference_date=reference_date)

    assert result.points == []
