"""
Unit tests for Top3Service.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.top3_service import Top3Service
from app.models.task import Task
from app.models.enums import TaskStatus, Priority, EnergyLevel, CreatedBy


@pytest.fixture
def mock_task_repo():
    """Create mock task repository."""
    repo = AsyncMock()
    return repo


@pytest.fixture
def top3_service(mock_task_repo):
    """Create Top3Service with mocked dependencies."""
    return Top3Service(task_repo=mock_task_repo)


def create_test_task(
    title: str,
    importance: Priority = Priority.MEDIUM,
    urgency: Priority = Priority.MEDIUM,
    energy_level: EnergyLevel = EnergyLevel.LOW,
    due_date: datetime | None = None,
) -> Task:
    """Helper to create test task."""
    return Task(
        id=uuid4(),
        user_id="test_user",
        title=title,
        status=TaskStatus.TODO,
        importance=importance,
        urgency=urgency,
        energy_level=energy_level,
        due_date=due_date,
        created_by=CreatedBy.USER,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_get_top3_no_tasks(top3_service, mock_task_repo):
    """Test getting top3 when there are no tasks."""
    mock_task_repo.list.return_value = []

    result = await top3_service.get_top3("test_user")

    assert result["tasks"] == []


@pytest.mark.asyncio
async def test_get_top3_less_than_3_tasks(top3_service, mock_task_repo):
    """Test getting top3 when there are less than 3 tasks."""
    tasks = [
        create_test_task("Task 1", importance=Priority.HIGH),
        create_test_task("Task 2", importance=Priority.MEDIUM),
    ]
    mock_task_repo.list.return_value = tasks

    result = await top3_service.get_top3("test_user")
    tasks = result["tasks"]

    assert len(tasks) == 2
    assert tasks[0].title == "Task 1"  # Higher importance first


@pytest.mark.asyncio
async def test_get_top3_importance_scoring(top3_service, mock_task_repo):
    """Test that importance is scored correctly."""
    tasks = [
        create_test_task("Low importance", importance=Priority.LOW),
        create_test_task("Medium importance", importance=Priority.MEDIUM),
        create_test_task("High importance", importance=Priority.HIGH),
    ]
    mock_task_repo.list.return_value = tasks

    result = await top3_service.get_top3("test_user")
    tasks = result["tasks"]

    # Should prioritize HIGH importance
    assert tasks[0].title == "High importance"
    assert tasks[1].title == "Medium importance"
    assert tasks[2].title == "Low importance"


@pytest.mark.asyncio
async def test_get_top3_urgency_scoring(top3_service, mock_task_repo):
    """Test that urgency is scored correctly."""
    tasks = [
        create_test_task("Low urgency", urgency=Priority.LOW),
        create_test_task("Medium urgency", urgency=Priority.MEDIUM),
        create_test_task("High urgency", urgency=Priority.HIGH),
    ]
    mock_task_repo.list.return_value = tasks

    result = await top3_service.get_top3("test_user")
    tasks = result["tasks"]

    # Should prioritize HIGH urgency
    assert tasks[0].title == "High urgency"


@pytest.mark.asyncio
async def test_get_top3_due_date_scoring(top3_service, mock_task_repo):
    """Test that due dates are scored correctly."""
    now = datetime.now()

    tasks = [
        create_test_task("Due next week", due_date=now + timedelta(days=7)),
        create_test_task("Due tomorrow", due_date=now + timedelta(days=1)),
        create_test_task("Overdue", due_date=now - timedelta(days=1)),
    ]
    mock_task_repo.list.return_value = tasks

    result = await top3_service.get_top3("test_user")
    tasks = result["tasks"]

    # Overdue tasks should be highest priority
    assert tasks[0].title == "Overdue"
    assert tasks[1].title == "Due tomorrow"


@pytest.mark.asyncio
async def test_get_top3_combined_scoring(top3_service, mock_task_repo):
    """Test combined importance + urgency + due date scoring."""
    now = datetime.now()

    tasks = [
        create_test_task(
            "Task A",
            importance=Priority.LOW,
            urgency=Priority.LOW,
        ),
        create_test_task(
            "Task B",
            importance=Priority.HIGH,
            urgency=Priority.HIGH,
            due_date=now + timedelta(days=1),
        ),
        create_test_task(
            "Task C",
            importance=Priority.MEDIUM,
            urgency=Priority.MEDIUM,
        ),
        create_test_task(
            "Task D",
            importance=Priority.HIGH,
            urgency=Priority.LOW,
            due_date=now - timedelta(days=1),  # Overdue
        ),
    ]
    mock_task_repo.list.return_value = tasks

    result = await top3_service.get_top3("test_user")
    tasks = result["tasks"]

    assert len(tasks) == 3
    # Task D should be first (HIGH importance + overdue)
    # Task B should be second (HIGH importance + urgency + due tomorrow)
    # Task C should be third (MEDIUM importance/urgency)


@pytest.mark.asyncio
async def test_calculate_base_score_importance():
    """Test base score calculation for importance."""
    service = Top3Service(task_repo=AsyncMock())

    task_high = create_test_task("High", importance=Priority.HIGH)
    task_med = create_test_task("Med", importance=Priority.MEDIUM)
    task_low = create_test_task("Low", importance=Priority.LOW)

    score_high = service._calculate_base_score(task_high)
    score_med = service._calculate_base_score(task_med)
    score_low = service._calculate_base_score(task_low)

    assert score_high > score_med > score_low


@pytest.mark.asyncio
async def test_calculate_base_score_urgency():
    """Test base score calculation for urgency."""
    service = Top3Service(task_repo=AsyncMock())

    task_high = create_test_task("High", urgency=Priority.HIGH)
    task_med = create_test_task("Med", urgency=Priority.MEDIUM)
    task_low = create_test_task("Low", urgency=Priority.LOW)

    score_high = service._calculate_base_score(task_high)
    score_med = service._calculate_base_score(task_med)
    score_low = service._calculate_base_score(task_low)

    assert score_high > score_med > score_low


@pytest.mark.asyncio
async def test_calculate_base_score_due_date():
    """Test base score calculation for due dates."""
    service = Top3Service(task_repo=AsyncMock())
    now = datetime.now()

    task_overdue = create_test_task("Overdue", due_date=now - timedelta(days=1))
    task_today = create_test_task("Today", due_date=now + timedelta(hours=1))
    task_week = create_test_task("This week", due_date=now + timedelta(days=5))

    score_overdue = service._calculate_base_score(task_overdue)
    score_today = service._calculate_base_score(task_today)
    score_week = service._calculate_base_score(task_week)

    assert score_overdue > score_today > score_week


@pytest.mark.asyncio
async def test_get_top3_energy_level_bonus():
    """Test that low energy tasks get a slight bonus."""
    service = Top3Service(task_repo=AsyncMock())

    task_low_energy = create_test_task(
        "Low energy",
        importance=Priority.MEDIUM,
        energy_level=EnergyLevel.LOW,
    )
    task_high_energy = create_test_task(
        "High energy",
        importance=Priority.MEDIUM,
        energy_level=EnergyLevel.HIGH,
    )

    score_low = service._calculate_base_score(task_low_energy)
    score_high = service._calculate_base_score(task_high_energy)

    # Low energy should get a small bonus
    assert score_low > score_high
