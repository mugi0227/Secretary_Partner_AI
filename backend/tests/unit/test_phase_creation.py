"""
Unit tests for Phase creation.

These tests verify:
1. Basic phase creation with name only
2. Phase creation with description
3. Phase ordering (order_in_project auto-increment)
4. Multiple phases in a project
"""

import pytest

from app.infrastructure.local.phase_repository import SqlitePhaseRepository
from app.infrastructure.local.project_repository import SqliteProjectRepository
from app.models.phase import PhaseCreate
from app.models.project import ProjectCreate


@pytest.mark.asyncio
async def test_create_phase_basic(session_factory, test_user_id):
    """Test basic phase creation with name only."""
    project_repo = SqliteProjectRepository(session_factory=session_factory)
    phase_repo = SqlitePhaseRepository(session_factory=session_factory)

    project = await project_repo.create(
        test_user_id,
        ProjectCreate(name="Test Project"),
    )

    phase = await phase_repo.create(
        test_user_id,
        PhaseCreate(project_id=project.id, name="設計", order_in_project=1),
    )

    assert phase.name == "設計"
    assert phase.project_id == project.id
    assert phase.order_in_project == 1
    assert phase.status == "ACTIVE"
    assert phase.description is None


@pytest.mark.asyncio
async def test_create_phase_with_description(session_factory, test_user_id):
    """Test phase creation with description."""
    project_repo = SqliteProjectRepository(session_factory=session_factory)
    phase_repo = SqlitePhaseRepository(session_factory=session_factory)

    project = await project_repo.create(
        test_user_id,
        ProjectCreate(name="Test Project"),
    )

    phase = await phase_repo.create(
        test_user_id,
        PhaseCreate(
            project_id=project.id,
            name="実装",
            description="メイン機能の実装フェーズ",
            order_in_project=1,
        ),
    )

    assert phase.name == "実装"
    assert phase.description == "メイン機能の実装フェーズ"


@pytest.mark.asyncio
async def test_create_multiple_phases_ordering(session_factory, test_user_id):
    """Test creating multiple phases with correct ordering."""
    project_repo = SqliteProjectRepository(session_factory=session_factory)
    phase_repo = SqlitePhaseRepository(session_factory=session_factory)

    project = await project_repo.create(
        test_user_id,
        ProjectCreate(name="Test Project"),
    )

    names = ["設計", "実装", "テスト", "リリース"]
    for i, name in enumerate(names, start=1):
        await phase_repo.create(
            test_user_id,
            PhaseCreate(project_id=project.id, name=name, order_in_project=i),
        )

    phases = await phase_repo.list_by_project(test_user_id, project.id)
    assert len(phases) == 4
    assert [p.name for p in phases] == names
    assert [p.order_in_project for p in phases] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_create_phase_appears_in_list(session_factory, test_user_id):
    """Test that a newly created phase appears in project phase list."""
    project_repo = SqliteProjectRepository(session_factory=session_factory)
    phase_repo = SqlitePhaseRepository(session_factory=session_factory)

    project = await project_repo.create(
        test_user_id,
        ProjectCreate(name="Test Project"),
    )

    # Initially no phases
    phases = await phase_repo.list_by_project(test_user_id, project.id)
    assert len(phases) == 0

    # Create one phase
    await phase_repo.create(
        test_user_id,
        PhaseCreate(project_id=project.id, name="Phase 1", order_in_project=1),
    )

    # Should appear in list
    phases = await phase_repo.list_by_project(test_user_id, project.id)
    assert len(phases) == 1
    assert phases[0].name == "Phase 1"
    assert phases[0].total_tasks == 0
    assert phases[0].completed_tasks == 0
