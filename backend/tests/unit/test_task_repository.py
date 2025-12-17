"""
Unit tests for Task repository.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.infrastructure.local.database import get_session_factory
from app.models.task import TaskCreate
from app.models.enums import Priority, EnergyLevel, CreatedBy, TaskStatus


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

    # Create multiple tasks
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

    task_data = TaskCreate(
        title="Original Title",
        created_by=CreatedBy.USER,
    )
    created = await repo.create(test_user_id, task_data)

    from app.models.task import TaskUpdate
    update = TaskUpdate(title="Updated Title", status=TaskStatus.IN_PROGRESS)

    updated = await repo.update(test_user_id, created.id, update)

    assert updated.title == "Updated Title"
    assert updated.status == TaskStatus.IN_PROGRESS


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

    # Create a task
    task_data = TaskCreate(
        title="Buy groceries",
        created_by=CreatedBy.USER,
    )
    await repo.create(test_user_id, task_data)

    # Find similar (in Inbox, i.e., project_id=None)
    similar = await repo.find_similar(
        test_user_id,
        title="Buy groceries",
        project_id=None,  # Search in Inbox
        threshold=0.8,
    )

    assert len(similar) >= 1
    assert similar[0].similarity_score >= 0.8

