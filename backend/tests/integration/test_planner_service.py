"""
Integration tests for PlannerService.

Tests task breakdown with real LLM API calls.
"""

import pytest
from uuid import uuid4

from app.core.config import get_settings
from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.infrastructure.local.memory_repository import SqliteMemoryRepository
from app.infrastructure.local.gemini_api_provider import GeminiAPIProvider
from app.models.enums import CreatedBy, Priority, EnergyLevel
from app.models.task import TaskCreate
from app.services.planner_service import PlannerService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_planner_service_breakdown(session_factory, test_user_id):
    """Test PlannerService can break down a task."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    task_repo = SqliteTaskRepository(session_factory=session_factory)
    memory_repo = SqliteMemoryRepository(session_factory=session_factory)
    llm_provider = GeminiAPIProvider(settings.GEMINI_MODEL)

    # Create a task to break down
    task_data = TaskCreate(
        title="確定申告を完了する",
        description="今年の確定申告書類を準備して提出する",
        importance=Priority.HIGH,
        urgency=Priority.MEDIUM,
        created_by=CreatedBy.USER,
    )
    task = await task_repo.create(test_user_id, task_data)

    # Run breakdown
    service = PlannerService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        memory_repo=memory_repo,
    )

    response = await service.breakdown_task(
        user_id=test_user_id,
        task_id=task.id,
        create_subtasks=False,  # Don't create subtasks for this test
    )

    # Verify breakdown
    assert response.breakdown is not None
    assert response.breakdown.original_task_id == task.id
    # Should be 3-5 steps
    assert 3 <= len(response.breakdown.steps) <= 5, f"Expected 3-5 steps, got {len(response.breakdown.steps)}"
    assert response.breakdown.total_estimated_minutes > 0

    # Verify each step has required fields
    for step in response.breakdown.steps:
        assert step.step_number >= 1
        assert len(step.title) > 0
        assert 15 <= step.estimated_minutes <= 120, f"Step {step.step_number} estimated_minutes should be 15-120, got {step.estimated_minutes}"
        assert step.energy_level in [EnergyLevel.HIGH, EnergyLevel.LOW]
        # Guide should be provided (may be empty but field exists)
        assert hasattr(step, "guide")

    # Verify markdown guide
    assert len(response.markdown_guide) > 0
    assert "確定申告" in response.markdown_guide


@pytest.mark.integration
@pytest.mark.asyncio
async def test_planner_service_creates_subtasks(session_factory, test_user_id):
    """Test PlannerService can create subtasks from breakdown."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    task_repo = SqliteTaskRepository(session_factory=session_factory)
    memory_repo = SqliteMemoryRepository(session_factory=session_factory)
    llm_provider = GeminiAPIProvider(settings.GEMINI_MODEL)

    # Create a task to break down
    task_data = TaskCreate(
        title="部屋の大掃除をする",
        description="部屋全体を掃除して整理整頓する",
        importance=Priority.MEDIUM,
        urgency=Priority.LOW,
        created_by=CreatedBy.USER,
    )
    task = await task_repo.create(test_user_id, task_data)

    # Run breakdown with subtask creation
    service = PlannerService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        memory_repo=memory_repo,
    )

    response = await service.breakdown_task(
        user_id=test_user_id,
        task_id=task.id,
        create_subtasks=True,
    )

    # Verify subtasks were created
    assert response.subtasks_created is True
    assert len(response.subtask_ids) == len(response.breakdown.steps)

    # Verify subtasks exist in DB
    subtasks = await task_repo.get_subtasks(test_user_id, task.id)
    assert len(subtasks) == len(response.breakdown.steps)

    # Verify subtask properties
    for subtask in subtasks:
        assert subtask.parent_id == task.id
        assert subtask.project_id == task.project_id
        assert subtask.created_by == CreatedBy.AGENT

