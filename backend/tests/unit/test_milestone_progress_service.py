"""
Unit tests for milestone progress service.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.enums import CreatedBy, EnergyLevel, MilestoneStatus, Priority, TaskStatus
from app.models.milestone import Milestone
from app.models.task import Task
from app.services.milestone_progress_service import MilestoneProgressService


def _make_task(
    *,
    task_id: UUID | None = None,
    project_id: UUID,
    milestone_id: UUID | None = None,
    parent_id: UUID | None = None,
    estimated_minutes: int | None = 60,
    progress: int = 0,
    status: TaskStatus = TaskStatus.TODO,
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
        due_date=None,
        start_not_before=None,
        pinned_date=None,
        parent_id=parent_id,
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
        milestone_id=milestone_id,
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


def _make_milestone(project_id: UUID, phase_id: UUID) -> Milestone:
    now = datetime.now(timezone.utc)
    return Milestone(
        id=uuid4(),
        user_id="user",
        project_id=project_id,
        phase_id=phase_id,
        title="milestone",
        description=None,
        status=MilestoneStatus.ACTIVE,
        order_in_phase=1,
        due_date=None,
        created_at=now,
        updated_at=now,
    )


class _StubTaskRepo:
    def __init__(self, tasks: list[Task]):
        self._tasks = tasks

    async def list(self, user_id, project_id=None, include_done=False, limit=100, offset=0, **kwargs):
        scoped = [task for task in self._tasks if task.project_id == project_id]
        return scoped[offset : offset + limit]


@pytest.mark.asyncio
async def test_milestone_progress_excludes_nested_children_from_double_count():
    project_id = uuid4()
    phase_id = uuid4()
    milestone = _make_milestone(project_id, phase_id)

    parent = _make_task(
        task_id=uuid4(),
        project_id=project_id,
        milestone_id=milestone.id,
        estimated_minutes=120,
        progress=80,
        status=TaskStatus.IN_PROGRESS,
    )
    child = _make_task(
        project_id=project_id,
        milestone_id=milestone.id,
        parent_id=parent.id,
        estimated_minutes=60,
        progress=20,
        status=TaskStatus.IN_PROGRESS,
    )
    sibling = _make_task(
        project_id=project_id,
        milestone_id=milestone.id,
        estimated_minutes=60,
        progress=50,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = _StubTaskRepo([parent, child, sibling])
    service = MilestoneProgressService(repo)

    result = await service.calculate_milestone_progress("user", milestone)

    assert result.progress == 70
    assert result.task_count == 2
    assert result.total_estimated_minutes == 180


@pytest.mark.asyncio
async def test_milestone_progress_for_empty_milestone():
    project_id = uuid4()
    phase_id = uuid4()
    milestone = _make_milestone(project_id, phase_id)
    repo = _StubTaskRepo([])
    service = MilestoneProgressService(repo)

    result = await service.calculate_milestone_progress("user", milestone)

    assert result.progress == 0
    assert result.task_count == 0
    assert result.completed_task_count == 0
    assert result.total_estimated_minutes == 0
    assert result.remaining_minutes == 0


@pytest.mark.asyncio
async def test_milestone_progress_counts_completed_and_remaining():
    project_id = uuid4()
    phase_id = uuid4()
    milestone = _make_milestone(project_id, phase_id)

    done_task = _make_task(
        project_id=project_id,
        milestone_id=milestone.id,
        estimated_minutes=60,
        progress=100,
        status=TaskStatus.DONE,
    )
    in_progress_task = _make_task(
        project_id=project_id,
        milestone_id=milestone.id,
        estimated_minutes=60,
        progress=50,
        status=TaskStatus.IN_PROGRESS,
    )
    repo = _StubTaskRepo([done_task, in_progress_task])
    service = MilestoneProgressService(repo)

    result = await service.calculate_milestone_progress("user", milestone)

    assert result.progress == 75
    assert result.completed_task_count == 1
    assert result.task_count == 2
    assert result.total_estimated_minutes == 120
    assert result.remaining_minutes == 30
