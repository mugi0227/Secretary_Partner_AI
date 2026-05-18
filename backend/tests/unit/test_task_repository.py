"""
Unit tests for Task repository.
"""

from datetime import datetime, timezone

import pytest

from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus
from app.models.task import TaskCreate, TaskUpdate


@pytest.mark.asyncio
async def test_create_task(session_factory, test_user_id):
    """Test creating a task."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    task_data = TaskCreate(
        title="Test Task",
        description="Test description",
        importance=Priority.HIGH,
        urgency=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
        created_by=CreatedBy.USER,
    )

    task = await repo.create(test_user_id, task_data)

    assert task.id is not None
    assert task.title == "Test Task"
    assert task.user_id == test_user_id
    assert task.status == TaskStatus.TODO
    assert task.created_by == CreatedBy.USER


@pytest.mark.asyncio
async def test_get_task(session_factory, test_user_id):
    """Test getting a task by ID."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    task_data = TaskCreate(
        title="Test Task",
        created_by=CreatedBy.USER,
    )
    created = await repo.create(test_user_id, task_data)

    retrieved = await repo.get(test_user_id, created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.title == "Test Task"


@pytest.mark.asyncio
async def test_list_tasks(session_factory, test_user_id):
    """Test listing tasks."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    for i in range(3):
        task_data = TaskCreate(
            title=f"Task {i}",
            created_by=CreatedBy.USER,
        )
        await repo.create(test_user_id, task_data)

    tasks = await repo.list(test_user_id)

    assert len(tasks) == 3
    assert all(task.user_id == test_user_id for task in tasks)


@pytest.mark.asyncio
async def test_update_task(session_factory, test_user_id):
    """Test updating a task."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    created = await repo.create(
        test_user_id,
        TaskCreate(
            title="Original Title",
            created_by=CreatedBy.USER,
        ),
    )

    updated = await repo.update(
        test_user_id,
        created.id,
        TaskUpdate(title="Updated Title", status=TaskStatus.IN_PROGRESS),
    )

    assert updated.title == "Updated Title"
    assert updated.status == TaskStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_update_task_can_clear_pinned_date(session_factory, test_user_id):
    """Explicit None should clear nullable fields such as pinned_date."""
    repo = SqliteTaskRepository(session_factory=session_factory)
    pinned_date = datetime(2026, 1, 15, tzinfo=timezone.utc)

    created = await repo.create(
        test_user_id,
        TaskCreate(
            title="Pinned task",
            pinned_date=pinned_date,
            created_by=CreatedBy.USER,
        ),
    )

    assert created.pinned_date == pinned_date

    updated = await repo.update(test_user_id, created.id, TaskUpdate(pinned_date=None))

    assert updated.pinned_date is None


@pytest.mark.asyncio
async def test_status_done_sets_progress_and_completion_metadata(session_factory, test_user_id):
    """DONE transition should force progress to 100 and set completion metadata."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    created = await repo.create(
        test_user_id,
        TaskCreate(title="Task", progress=40, created_by=CreatedBy.USER),
    )

    updated = await repo.update(
        test_user_id,
        created.id,
        TaskUpdate(status=TaskStatus.DONE),
    )

    assert updated.status == TaskStatus.DONE
    assert updated.progress == 100
    assert updated.completed_at is not None
    assert updated.completed_by == test_user_id


@pytest.mark.asyncio
async def test_reopen_from_done_lowers_progress(session_factory, test_user_id):
    """DONE -> non-DONE should lower progress and clear completion metadata."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    task = await repo.create(
        test_user_id,
        TaskCreate(title="Task", created_by=CreatedBy.USER),
    )
    await repo.update(test_user_id, task.id, TaskUpdate(status=TaskStatus.DONE))

    reopened = await repo.update(test_user_id, task.id, TaskUpdate(status=TaskStatus.TODO))

    assert reopened.status == TaskStatus.TODO
    assert reopened.progress == 0
    assert reopened.completed_at is None
    assert reopened.completed_by is None


@pytest.mark.asyncio
async def test_parent_done_auto_completes_descendants(session_factory, test_user_id):
    """Parent DONE should auto-complete all descendants."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    parent = await repo.create(
        test_user_id,
        TaskCreate(title="Parent", created_by=CreatedBy.USER),
    )
    child = await repo.create(
        test_user_id,
        TaskCreate(title="Child", parent_id=parent.id, created_by=CreatedBy.USER),
    )
    grandchild = await repo.create(
        test_user_id,
        TaskCreate(title="Grandchild", parent_id=child.id, created_by=CreatedBy.USER),
    )

    await repo.update(test_user_id, parent.id, TaskUpdate(status=TaskStatus.DONE))

    updated_child = await repo.get(test_user_id, child.id)
    updated_grandchild = await repo.get(test_user_id, grandchild.id)

    assert updated_child is not None
    assert updated_grandchild is not None
    assert updated_child.status == TaskStatus.DONE
    assert updated_grandchild.status == TaskStatus.DONE
    assert updated_child.progress == 100
    assert updated_grandchild.progress == 100
    assert updated_child.auto_completed_by_parent_id == parent.id
    assert updated_grandchild.auto_completed_by_parent_id == parent.id


@pytest.mark.asyncio
async def test_parent_reopen_only_reopens_auto_completed_children(session_factory, test_user_id):
    """Parent reopen should only reopen children auto-completed by that parent."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    parent = await repo.create(
        test_user_id,
        TaskCreate(title="Parent", created_by=CreatedBy.USER),
    )
    auto_child = await repo.create(
        test_user_id,
        TaskCreate(title="Auto Child", parent_id=parent.id, created_by=CreatedBy.USER),
    )
    manual_done_child = await repo.create(
        test_user_id,
        TaskCreate(title="Manual Done Child", parent_id=parent.id, created_by=CreatedBy.USER),
    )

    await repo.update(test_user_id, manual_done_child.id, TaskUpdate(status=TaskStatus.DONE))
    await repo.update(test_user_id, parent.id, TaskUpdate(status=TaskStatus.DONE))
    await repo.update(test_user_id, parent.id, TaskUpdate(status=TaskStatus.IN_PROGRESS))

    updated_auto_child = await repo.get(test_user_id, auto_child.id)
    updated_manual_done_child = await repo.get(test_user_id, manual_done_child.id)

    assert updated_auto_child is not None
    assert updated_manual_done_child is not None
    assert updated_auto_child.status == TaskStatus.TODO
    assert updated_auto_child.progress == 0
    assert updated_auto_child.auto_completed_by_parent_id is None
    assert updated_manual_done_child.status == TaskStatus.DONE
    assert updated_manual_done_child.progress == 100


@pytest.mark.asyncio
async def test_parent_progress_is_weighted_average_of_children(session_factory, test_user_id):
    """Parent progress should be recalculated from child weighted progress."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    parent = await repo.create(
        test_user_id,
        TaskCreate(title="Parent", created_by=CreatedBy.USER),
    )
    child_a = await repo.create(
        test_user_id,
        TaskCreate(
            title="Child A",
            parent_id=parent.id,
            estimated_minutes=30,
            progress=0,
            created_by=CreatedBy.USER,
        ),
    )
    await repo.create(
        test_user_id,
        TaskCreate(
            title="Child B",
            parent_id=parent.id,
            estimated_minutes=90,
            progress=0,
            created_by=CreatedBy.USER,
        ),
    )

    await repo.update(test_user_id, child_a.id, TaskUpdate(progress=40))
    parent_after = await repo.get(test_user_id, parent.id)

    assert parent_after is not None
    assert parent_after.progress == 10


@pytest.mark.asyncio
async def test_delete_task(session_factory, test_user_id):
    """Test deleting a task."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    task_data = TaskCreate(
        title="Task to Delete",
        created_by=CreatedBy.USER,
    )
    created = await repo.create(test_user_id, task_data)

    deleted = await repo.delete(test_user_id, created.id)
    assert deleted is True

    retrieved = await repo.get(test_user_id, created.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_find_similar_tasks(session_factory, test_user_id):
    """Test finding similar tasks."""
    repo = SqliteTaskRepository(session_factory=session_factory)

    task_data = TaskCreate(
        title="Buy groceries",
        created_by=CreatedBy.USER,
    )
    await repo.create(test_user_id, task_data)

    similar = await repo.find_similar(
        test_user_id,
        title="Buy groceries",
        project_id=None,
        threshold=0.8,
    )

    assert len(similar) >= 1
    assert similar[0].similarity_score >= 0.8


@pytest.mark.asyncio
async def test_datetime_fields_are_restored_as_utc_aware(session_factory, test_user_id):
    """SQLite round-trips must preserve UTC semantics for task datetimes."""
    repo = SqliteTaskRepository(session_factory=session_factory)
    start_time = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
    end_time = datetime(2026, 3, 10, 1, 0, tzinfo=timezone.utc)

    created = await repo.create(
        test_user_id,
        TaskCreate(
            title="UTC Task",
            created_by=CreatedBy.USER,
            is_fixed_time=True,
            start_time=start_time,
            end_time=end_time,
        ),
    )
    completed = await repo.update(
        test_user_id,
        created.id,
        TaskUpdate(status=TaskStatus.DONE),
    )

    assert created.created_at.tzinfo == timezone.utc
    assert created.updated_at.tzinfo == timezone.utc
    assert created.start_time == start_time
    assert created.end_time == end_time
    assert completed.completed_at is not None
    assert completed.completed_at.tzinfo == timezone.utc
