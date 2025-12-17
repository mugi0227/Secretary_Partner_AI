"""
End-to-end tests for task breakdown endpoint.

Tests POST /api/tasks/{task_id}/breakdown with real API calls.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.config import get_settings
from app.infrastructure.local.database import init_db, get_session_factory, TaskORM
from app.models.enums import CreatedBy
from app.models.task import TaskCreate
from app.infrastructure.local.task_repository import SqliteTaskRepository
from main import app


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_breakdown_endpoint():
    """Test task breakdown endpoint functionality."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    await init_db()

    # First, create a task to break down
    session_factory = get_session_factory()
    task_repo = SqliteTaskRepository(session_factory=session_factory)
    task = await task_repo.create(
        "dev_user",
        TaskCreate(
            title="引っ越しの準備をする",
            description="来月の引っ越しに向けて準備を進める",
            created_by=CreatedBy.USER,
        ),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/tasks/{task.id}/breakdown",
            json={"create_subtasks": False},
            headers={"Authorization": "Bearer dev_user"},
        )

        assert response.status_code == 200, response.text
        data = response.json()

        # Verify breakdown structure
        assert "breakdown" in data
        breakdown = data["breakdown"]
        assert breakdown["original_task_id"] == str(task.id)
        assert len(breakdown["steps"]) >= 2
        assert breakdown["total_estimated_minutes"] > 0

        # Verify each step
        for step in breakdown["steps"]:
            assert "step_number" in step
            assert "title" in step
            assert "estimated_minutes" in step
            assert "energy_level" in step

        # Verify markdown guide
        assert "markdown_guide" in data
        assert len(data["markdown_guide"]) > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_breakdown_creates_subtasks():
    """Test breakdown endpoint creates subtasks when requested."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    await init_db()

    # Create a task
    session_factory = get_session_factory()
    task_repo = SqliteTaskRepository(session_factory=session_factory)
    task = await task_repo.create(
        "dev_user",
        TaskCreate(
            title="プレゼン資料を作成する",
            description="来週の会議用のプレゼン資料を作る",
            created_by=CreatedBy.USER,
        ),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/tasks/{task.id}/breakdown",
            json={"create_subtasks": True},
            headers={"Authorization": "Bearer dev_user"},
        )

        assert response.status_code == 200, response.text
        data = response.json()

        # Verify subtasks were created
        assert data["subtasks_created"] is True
        assert len(data["subtask_ids"]) > 0
        assert len(data["subtask_ids"]) == len(data["breakdown"]["steps"])

    # Verify subtasks exist in DB
    subtasks = await task_repo.get_subtasks("dev_user", task.id)
    assert len(subtasks) == len(data["breakdown"]["steps"])

    for subtask in subtasks:
        assert subtask.parent_id == task.id
        assert subtask.created_by == CreatedBy.AGENT


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_breakdown_not_found():
    """Test breakdown endpoint returns 404 for non-existent task."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    await init_db()

    from uuid import uuid4
    fake_task_id = uuid4()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/tasks/{fake_task_id}/breakdown",
            json={"create_subtasks": False},
            headers={"Authorization": "Bearer dev_user"},
        )

        assert response.status_code == 404


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_get_subtasks_endpoint():
    """Test GET /api/tasks/{task_id}/subtasks endpoint."""
    settings = get_settings()

    if not settings.GOOGLE_API_KEY:
        pytest.skip("GOOGLE_API_KEY not configured")

    await init_db()

    # Create parent and child tasks
    session_factory = get_session_factory()
    task_repo = SqliteTaskRepository(session_factory=session_factory)

    parent = await task_repo.create(
        "dev_user",
        TaskCreate(title="親タスク", created_by=CreatedBy.USER),
    )

    child1 = await task_repo.create(
        "dev_user",
        TaskCreate(title="子タスク1", parent_id=parent.id, created_by=CreatedBy.AGENT),
    )
    child2 = await task_repo.create(
        "dev_user",
        TaskCreate(title="子タスク2", parent_id=parent.id, created_by=CreatedBy.AGENT),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/tasks/{parent.id}/subtasks",
            headers={"Authorization": "Bearer dev_user"},
        )

        assert response.status_code == 200, response.text
        subtasks = response.json()
        assert len(subtasks) == 2
        subtask_ids = [s["id"] for s in subtasks]
        assert str(child1.id) in subtask_ids
        assert str(child2.id) in subtask_ids

