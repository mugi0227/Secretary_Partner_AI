"""
Unit tests for check-in agent tools.

Tests create_checkin and list_checkins tool functions.
"""

from datetime import date, datetime
from typing import Optional
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.collaboration import (
    CheckinCreateV2,
    CheckinItemResponse,
    CheckinV2,
)
from app.models.enums import (
    CheckinItemCategory,
    CheckinItemUrgency,
    CheckinMood,
    ProjectRole,
)
from app.services.project_permissions import ProjectAccess
from app.tools.checkin_tools import (
    CreateCheckinInput,
    ListCheckinsInput,
    create_checkin,
    list_checkins,
)

PROJECT_ID = uuid4()
USER_ID = "test_user"
OWNER_ID = "owner_user"


def _make_access() -> ProjectAccess:
    """Create a mock ProjectAccess for tests."""
    from app.models.project import Project

    project = Project(
        id=PROJECT_ID,
        user_id=OWNER_ID,
        name="Test Project",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return ProjectAccess(
        project=project,
        role=ProjectRole.MEMBER,
        owner_id=OWNER_ID,
    )


def _make_checkin_v2(
    checkin_id: Optional[UUID] = None,
    items: Optional[list[CheckinItemResponse]] = None,
    mood: Optional[CheckinMood] = None,
    free_comment: Optional[str] = None,
) -> CheckinV2:
    """Create a CheckinV2 for mock returns."""
    return CheckinV2(
        id=checkin_id or uuid4(),
        user_id=OWNER_ID,
        project_id=PROJECT_ID,
        member_user_id=USER_ID,
        checkin_date=date.today(),
        items=items or [],
        mood=mood,
        free_comment=free_comment,
        created_at=datetime.utcnow(),
    )


PATCH_TARGET = "app.tools.checkin_tools.require_project_action"


# ---------------------------------------------------------------------------
# create_checkin tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_checkin_basic():
    """Test creating a basic check-in with items."""
    checkin_repo = AsyncMock()
    project_repo = AsyncMock()
    member_repo = AsyncMock()

    expected = _make_checkin_v2(
        items=[
            CheckinItemResponse(
                id=uuid4(),
                category=CheckinItemCategory.BLOCKER,
                content="APIの認証が通らない",
                urgency=CheckinItemUrgency.HIGH,
            ),
            CheckinItemResponse(
                id=uuid4(),
                category=CheckinItemCategory.UPDATE,
                content="デザインレビュー完了",
                urgency=CheckinItemUrgency.MEDIUM,
            ),
        ],
        mood=CheckinMood.OKAY,
    )
    checkin_repo.create_v2.return_value = expected

    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
        items=[
            {"category": "blocker", "content": "APIの認証が通らない", "urgency": "high"},
            {"category": "update", "content": "デザインレビュー完了"},
        ],
        mood="okay",
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        result = await create_checkin(
            USER_ID, checkin_repo, project_repo, member_repo, input_data,
        )

    assert "error" not in result
    assert result["mood"] == "okay"
    checkin_repo.create_v2.assert_called_once()
    call_args = checkin_repo.create_v2.call_args
    assert call_args[0][0] == OWNER_ID  # owner_id
    assert call_args[0][1] == PROJECT_ID  # project_id
    checkin_data: CheckinCreateV2 = call_args[0][2]
    assert len(checkin_data.items) == 2
    assert checkin_data.items[0].category == CheckinItemCategory.BLOCKER
    assert checkin_data.items[1].category == CheckinItemCategory.UPDATE
    assert checkin_data.mood == CheckinMood.OKAY
    assert checkin_data.member_user_id == USER_ID


@pytest.mark.asyncio
async def test_create_checkin_defaults_date_to_today():
    """Test that checkin_date defaults to today."""
    checkin_repo = AsyncMock()
    checkin_repo.create_v2.return_value = _make_checkin_v2()

    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
        free_comment="特になし",
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        await create_checkin(
            USER_ID, checkin_repo, AsyncMock(), AsyncMock(), input_data,
        )

    checkin_data: CheckinCreateV2 = checkin_repo.create_v2.call_args[0][2]
    assert checkin_data.checkin_date == date.today()


@pytest.mark.asyncio
async def test_create_checkin_defaults_member_to_current_user():
    """Test that member_user_id defaults to the current user."""
    checkin_repo = AsyncMock()
    checkin_repo.create_v2.return_value = _make_checkin_v2()

    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        await create_checkin(
            USER_ID, checkin_repo, AsyncMock(), AsyncMock(), input_data,
        )

    checkin_data: CheckinCreateV2 = checkin_repo.create_v2.call_args[0][2]
    assert checkin_data.member_user_id == USER_ID


@pytest.mark.asyncio
async def test_create_checkin_invalid_category():
    """Test error on invalid category."""
    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
        items=[{"category": "invalid_cat", "content": "test"}],
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        result = await create_checkin(
            USER_ID, AsyncMock(), AsyncMock(), AsyncMock(), input_data,
        )

    assert "error" in result
    assert "invalid_cat" in result["error"]


@pytest.mark.asyncio
async def test_create_checkin_invalid_project_id():
    """Test error on invalid project ID."""
    input_data = CreateCheckinInput(
        project_id="not-a-uuid",
    )

    result = await create_checkin(
        USER_ID, AsyncMock(), AsyncMock(), AsyncMock(), input_data,
    )

    assert "error" in result
    assert "Invalid project ID" in result["error"]


@pytest.mark.asyncio
async def test_create_checkin_permission_denied():
    """Test error when user lacks CHECKIN_WRITE permission."""
    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
    )

    with patch(PATCH_TARGET, return_value={"error": "Permission denied"}):
        result = await create_checkin(
            USER_ID, AsyncMock(), AsyncMock(), AsyncMock(), input_data,
        )

    assert result == {"error": "Permission denied"}


@pytest.mark.asyncio
async def test_create_checkin_with_explicit_date():
    """Test creating a check-in with an explicit date."""
    checkin_repo = AsyncMock()
    checkin_repo.create_v2.return_value = _make_checkin_v2()

    input_data = CreateCheckinInput(
        project_id=str(PROJECT_ID),
        checkin_date="2025-06-15",
        free_comment="先週分",
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        await create_checkin(
            USER_ID, checkin_repo, AsyncMock(), AsyncMock(), input_data,
        )

    checkin_data: CheckinCreateV2 = checkin_repo.create_v2.call_args[0][2]
    assert checkin_data.checkin_date == date(2025, 6, 15)


# ---------------------------------------------------------------------------
# list_checkins tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_checkins_basic():
    """Test listing check-ins for a project."""
    checkin_repo = AsyncMock()
    checkins = [_make_checkin_v2(), _make_checkin_v2()]
    checkin_repo.list_v2.return_value = checkins

    input_data = ListCheckinsInput(
        project_id=str(PROJECT_ID),
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        result = await list_checkins(
            USER_ID, checkin_repo, AsyncMock(), AsyncMock(), input_data,
        )

    assert result["count"] == 2
    assert len(result["checkins"]) == 2
    checkin_repo.list_v2.assert_called_once()


@pytest.mark.asyncio
async def test_list_checkins_with_date_filter():
    """Test listing check-ins with date filter."""
    checkin_repo = AsyncMock()
    checkin_repo.list_v2.return_value = []

    input_data = ListCheckinsInput(
        project_id=str(PROJECT_ID),
        start_date="2025-01-01",
        end_date="2025-01-31",
    )

    with patch(PATCH_TARGET, return_value=_make_access()):
        result = await list_checkins(
            USER_ID, checkin_repo, AsyncMock(), AsyncMock(), input_data,
        )

    assert result["count"] == 0
    call_kwargs = checkin_repo.list_v2.call_args
    assert call_kwargs[1]["start_date"] == date(2025, 1, 1)
    assert call_kwargs[1]["end_date"] == date(2025, 1, 31)


@pytest.mark.asyncio
async def test_list_checkins_invalid_project_id():
    """Test error on invalid project ID."""
    input_data = ListCheckinsInput(
        project_id="not-a-uuid",
    )

    result = await list_checkins(
        USER_ID, AsyncMock(), AsyncMock(), AsyncMock(), input_data,
    )

    assert "error" in result
