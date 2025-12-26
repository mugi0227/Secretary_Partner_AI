"""
Integration tests for Top3 API.
"""

import pytest
from datetime import datetime, timedelta

from app.infrastructure.local.database import get_session_factory, init_db
from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.models.task import TaskCreate
from app.models.enums import Priority, EnergyLevel
from app.services.top3_service import Top3Service


@pytest.fixture
async def task_repo():
    """Create in-memory task repository."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.infrastructure.local.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    repo = SqliteTaskRepository(session_factory)

    yield repo

    await engine.dispose()


@pytest.fixture
async def top3_service(task_repo):
    """Create Top3Service instance."""
    return Top3Service(task_repo=task_repo)


@pytest.mark.asyncio
async def test_top3_api_integration(task_repo, top3_service):
    """Test full Top3 flow with real repository."""
    user_id = "test_user"

    # Create diverse tasks
    tasks_data = [
        # High importance, high urgency, overdue - should be #1
        TaskCreate(
            title="Critical bug fix",
            importance=Priority.HIGH,
            urgency=Priority.HIGH,
            due_date=datetime.now() - timedelta(days=1),
        ),
        # Medium importance, medium urgency, due today - should be #2
        TaskCreate(
            title="Team meeting prep",
            importance=Priority.MEDIUM,
            urgency=Priority.MEDIUM,
            due_date=datetime.now(),
        ),
        # Low importance, low urgency, due next week - should be #3 or lower
        TaskCreate(
            title="Read article",
            importance=Priority.LOW,
            urgency=Priority.LOW,
            due_date=datetime.now() + timedelta(days=7),
        ),
        # High importance, low urgency, no due date
        TaskCreate(
            title="Strategic planning",
            importance=Priority.HIGH,
            urgency=Priority.LOW,
        ),
        # Low importance but due tomorrow with quick win bonus
        TaskCreate(
            title="Quick email response",
            importance=Priority.LOW,
            urgency=Priority.MEDIUM,
            due_date=datetime.now() + timedelta(days=1),
            energy_level=EnergyLevel.LOW,
        ),
    ]

    # Create all tasks
    for task_data in tasks_data:
        await task_repo.create(user_id, task_data)

    # Get top 3
    result = await top3_service.get_top3(user_id)
    top3 = result["tasks"]

    # Assertions
    assert len(top3) == 3

    # First should be critical bug (high importance + high urgency + overdue)
    # Score: 30 (importance) + 24 (urgency) + 30 (overdue) = 84
    assert top3[0].title == "Critical bug fix"

    # Second should be team meeting (medium importance + medium urgency + due today)
    # Score: 20 (importance) + 16 (urgency) + 25 (today) = 61
    assert top3[1].title == "Team meeting prep"

    # Third should be quick email (low importance + medium urgency + tomorrow + low energy)
    # Score: 10 (importance) + 16 (urgency) + 20 (tomorrow) + 2 (energy) = 48
    assert top3[2].title == "Quick email response"


@pytest.mark.asyncio
async def test_top3_api_with_completed_tasks(task_repo, top3_service):
    """Test that completed tasks are excluded from Top3."""
    user_id = "test_user"

    # Create tasks
    task1 = await task_repo.create(
        user_id,
        TaskCreate(
            title="Active task",
            importance=Priority.HIGH,
            urgency=Priority.HIGH,
        ),
    )

    task2 = await task_repo.create(
        user_id,
        TaskCreate(
            title="Completed task",
            importance=Priority.HIGH,
            urgency=Priority.HIGH,
        ),
    )

    # Mark second task as done
    from app.models.task import TaskUpdate
    from app.models.enums import TaskStatus

    await task_repo.update(user_id, task2.id, TaskUpdate(status=TaskStatus.DONE))

    # Get top 3
    result = await top3_service.get_top3(user_id)
    top3 = result["tasks"]

    # Should only return active task
    assert len(top3) == 1
    assert top3[0].title == "Active task"


@pytest.mark.asyncio
async def test_top3_api_empty_tasks(task_repo, top3_service):
    """Test Top3 with no tasks."""
    user_id = "test_user"

    # Get top 3 with no tasks
    result = await top3_service.get_top3(user_id)
    top3 = result["tasks"]

    assert len(top3) == 0


@pytest.mark.asyncio
async def test_top3_api_less_than_3_tasks(task_repo, top3_service):
    """Test Top3 with less than 3 tasks."""
    user_id = "test_user"

    # Create only 2 tasks
    await task_repo.create(
        user_id,
        TaskCreate(title="Task 1", importance=Priority.HIGH),
    )
    await task_repo.create(
        user_id,
        TaskCreate(title="Task 2", importance=Priority.MEDIUM),
    )

    # Get top 3
    result = await top3_service.get_top3(user_id)
    top3 = result["tasks"]

    # Should return only 2 tasks
    assert len(top3) == 2
