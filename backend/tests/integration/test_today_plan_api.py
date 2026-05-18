"""Integration tests for today's plan API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.infrastructure.local.database import Base
from app.infrastructure.local.project_repository import SqliteProjectRepository
from app.infrastructure.local.task_assignment_repository import SqliteTaskAssignmentRepository
from app.infrastructure.local.task_repository import SqliteTaskRepository
from app.infrastructure.local.user_repository import SqliteUserRepository
from app.interfaces.auth_provider import User
from app.models.enums import Priority
from app.models.user import UserCreate
from main import app


@dataclass(frozen=True)
class TodayApiHarness:
    client: AsyncClient
    user_id: str


@pytest.fixture
async def today_api_harness() -> AsyncIterator[TodayApiHarness]:
    """Run the FastAPI app against an isolated in-memory SQLite database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    task_repo = SqliteTaskRepository(session_factory)
    project_repo = SqliteProjectRepository(session_factory)
    assignment_repo = SqliteTaskAssignmentRepository(session_factory)
    user_repo = SqliteUserRepository(session_factory)
    user = await user_repo.create(
        UserCreate(
            provider_issuer="test",
            provider_sub="today-plan-api",
            email="today-plan-api@example.com",
            username="today_plan_api",
            timezone="Asia/Tokyo",
        )
    )

    async def current_user() -> User:
        return User(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
        )

    previous_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.update(
        {
            deps.get_current_user: current_user,
            deps.get_task_repository: lambda: task_repo,
            deps.get_project_repository: lambda: project_repo,
            deps.get_task_assignment_repository: lambda: assignment_repo,
            deps.get_user_repository: lambda: user_repo,
        }
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield TodayApiHarness(client=client, user_id=str(user.id))

    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)
    await engine.dispose()


async def _create_task(
    harness: TodayApiHarness,
    title: str,
    *,
    importance: str = Priority.MEDIUM.value,
    urgency: str = Priority.MEDIUM.value,
    estimated_minutes: int = 30,
    due_date: datetime | None = None,
    start_not_before: datetime | None = None,
) -> dict:
    response = await harness.client.post(
        "/api/tasks",
        json={
            "title": title,
            "importance": importance,
            "urgency": urgency,
            "estimated_minutes": estimated_minutes,
            "due_date": due_date.isoformat() if due_date else None,
            "start_not_before": start_not_before.isoformat() if start_not_before else None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_today_selection_replaces_existing_user_choice(
    today_api_harness: TodayApiHarness,
) -> None:
    now = datetime.now(timezone.utc)
    urgent = await _create_task(
        today_api_harness,
        "Critical customer follow-up",
        importance=Priority.HIGH.value,
        urgency=Priority.HIGH.value,
        estimated_minutes=90,
        due_date=now,
    )
    manual_focus = await _create_task(
        today_api_harness,
        "Draft launch plan",
        importance=Priority.MEDIUM.value,
        urgency=Priority.MEDIUM.value,
        estimated_minutes=45,
    )

    initial = await today_api_harness.client.get("/api/today/plan?recommendation_limit=5")
    assert initial.status_code == 200, initial.text
    initial_data = initial.json()
    assert initial_data["selected"] == []
    assert urgent["id"] in {item["task"]["id"] for item in initial_data["recommendations"]}
    urgent_item = next(
        item for item in initial_data["recommendations"] if item["task"]["id"] == urgent["id"]
    )
    assert urgent_item["score"] > 0
    assert urgent_item["score_summary"]
    assert {"importance", "urgency", "due_date"}.issubset(
        {component["code"] for component in urgent_item["score_breakdown"]}
    )

    first_selection = await today_api_harness.client.put(
        "/api/today/selection",
        json={"task_ids": [manual_focus["id"]], "replace": True},
    )
    assert first_selection.status_code == 200, first_selection.text
    first_data = first_selection.json()
    assert [item["task"]["id"] for item in first_data["selected"]] == [manual_focus["id"]]
    assert manual_focus["id"] not in {
        item["task"]["id"] for item in first_data["recommendations"]
    }

    replacement = await today_api_harness.client.put(
        "/api/today/selection",
        json={"task_ids": [urgent["id"]], "replace": True},
    )
    assert replacement.status_code == 200, replacement.text
    replacement_data = replacement.json()
    assert [item["task"]["id"] for item in replacement_data["selected"]] == [urgent["id"]]
    assert manual_focus["id"] not in {
        item["task"]["id"] for item in replacement_data["selected"]
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_do_today_clears_future_start_gate_and_adds_selection(
    today_api_harness: TodayApiHarness,
) -> None:
    future_start = datetime.now(timezone.utc) + timedelta(days=5)
    task = await _create_task(
        today_api_harness,
        "Pull blocked future task into today",
        importance=Priority.HIGH.value,
        urgency=Priority.MEDIUM.value,
        estimated_minutes=40,
        start_not_before=future_start,
    )

    response = await today_api_harness.client.post(
        f"/api/tasks/{task['id']}/do-today",
        json={"pin": True},
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["pinned_date"] is not None
    assert updated["start_not_before"] != future_start.isoformat()

    plan = await today_api_harness.client.get("/api/today/plan")
    assert plan.status_code == 200, plan.text
    plan_data = plan.json()
    assert task["id"] in {item["task"]["id"] for item in plan_data["selected"]}
