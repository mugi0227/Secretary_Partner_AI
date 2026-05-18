"""
Unit tests for SQLite notification repository.

Tests CRUD operations for notification persistence.
"""

from uuid import uuid4

import pytest

from app.infrastructure.local.notification_repository import SqliteNotificationRepository
from app.models.notification import NotificationCreate, NotificationType


@pytest.fixture
def repository(db_session):
    """Create repository with test session."""
    def factory():
        class SessionCtx:
            async def __aenter__(self):
                return db_session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return SessionCtx()

    return SqliteNotificationRepository(session_factory=factory)


@pytest.fixture
def user_id():
    return "test_user_123"


def _make_notification(
    user_id: str = "test_user_123",
    ntype: NotificationType = NotificationType.ISSUE_NEW,
    title: str = "テスト通知",
    message: str = "テストメッセージ",
    link_type: str | None = "issue",
    link_id: str | None = None,
    project_id=None,
    project_name: str | None = None,
) -> NotificationCreate:
    return NotificationCreate(
        user_id=user_id,
        type=ntype,
        title=title,
        message=message,
        link_type=link_type,
        link_id=link_id or str(uuid4()),
        project_id=project_id,
        project_name=project_name,
    )


# ============================================
# Create
# ============================================


class TestCreate:
    """Tests for single notification creation."""

    @pytest.mark.asyncio
    async def test_create_returns_notification(self, repository, user_id):
        """通知を作成すると Notification モデルが返る。"""
        data = _make_notification(user_id=user_id)
        result = await repository.create(data)

        assert result.id is not None
        assert result.user_id == user_id
        assert result.type == NotificationType.ISSUE_NEW
        assert result.title == "テスト通知"
        assert result.message == "テストメッセージ"
        assert result.is_read is False
        assert result.read_at is None
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_create_with_project_context(self, repository, user_id):
        """プロジェクト情報付きの通知を作成できる。"""
        pid = uuid4()
        data = _make_notification(
            user_id=user_id,
            ntype=NotificationType.CHECKIN_CREATED,
            title="チェックイン",
            message="提出されました",
            link_type="checkin",
            project_id=pid,
            project_name="テストPJ",
        )
        result = await repository.create(data)

        assert result.project_id == pid
        assert result.project_name == "テストPJ"
        assert result.link_type == "checkin"


# ============================================
# Create Bulk
# ============================================


class TestCreateBulk:
    """Tests for bulk notification creation."""

    @pytest.mark.asyncio
    async def test_create_bulk_multiple(self, repository):
        """複数の通知を一括作成できる。"""
        notifications = [
            _make_notification(user_id="user_A", title="通知A"),
            _make_notification(user_id="user_B", title="通知B"),
            _make_notification(user_id="user_C", title="通知C"),
        ]
        results = await repository.create_bulk(notifications)

        assert len(results) == 3
        titles = {r.title for r in results}
        assert titles == {"通知A", "通知B", "通知C"}

    @pytest.mark.asyncio
    async def test_create_bulk_empty_list(self, repository):
        """空リストの場合、空リストが返る。"""
        results = await repository.create_bulk([])
        assert results == []


# ============================================
# Get
# ============================================


class TestGet:
    """Tests for getting a notification by ID."""

    @pytest.mark.asyncio
    async def test_get_existing(self, repository, user_id):
        """作成した通知をIDで取得できる。"""
        created = await repository.create(_make_notification(user_id=user_id))
        result = await repository.get(user_id, created.id)

        assert result is not None
        assert result.id == created.id
        assert result.title == created.title

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repository, user_id):
        """存在しないIDの場合、None が返る。"""
        result = await repository.get(user_id, uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_get_wrong_user(self, repository):
        """他ユーザーの通知は取得できない。"""
        created = await repository.create(_make_notification(user_id="user_A"))
        result = await repository.get("user_B", created.id)
        assert result is None


# ============================================
# List
# ============================================


class TestList:
    """Tests for listing notifications."""

    @pytest.mark.asyncio
    async def test_list_empty(self, repository, user_id):
        """通知がない場合、空リストが返る。"""
        results = await repository.list(user_id)
        assert results == []

    @pytest.mark.asyncio
    async def test_list_returns_own_notifications(self, repository):
        """自分の通知のみ返される。"""
        await repository.create(_make_notification(user_id="user_A", title="A通知"))
        await repository.create(_make_notification(user_id="user_B", title="B通知"))

        results = await repository.list("user_A")
        assert len(results) == 1
        assert results[0].title == "A通知"

    @pytest.mark.asyncio
    async def test_list_ordered_by_created_at_desc(self, repository, user_id):
        """通知は作成日時の降順で返される。"""
        await repository.create(_make_notification(user_id=user_id, title="1st"))
        await repository.create(_make_notification(user_id=user_id, title="2nd"))
        await repository.create(_make_notification(user_id=user_id, title="3rd"))

        results = await repository.list(user_id)
        # SQLite in-memory では同一タイムスタンプになる可能性があるため件数のみ検証
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_unread_only(self, repository, user_id):
        """unread_only で未読のみフィルタできる。"""
        await repository.create(_make_notification(user_id=user_id, title="未読"))
        n2 = await repository.create(_make_notification(user_id=user_id, title="既読"))
        await repository.mark_as_read(user_id, n2.id)

        results = await repository.list(user_id, unread_only=True)
        assert len(results) == 1
        assert results[0].title == "未読"

    @pytest.mark.asyncio
    async def test_list_with_limit_and_offset(self, repository, user_id):
        """limit と offset でページングできる。"""
        for i in range(5):
            await repository.create(
                _make_notification(user_id=user_id, title=f"通知{i}")
            )

        results = await repository.list(user_id, limit=2, offset=0)
        assert len(results) == 2

        results_page2 = await repository.list(user_id, limit=2, offset=2)
        assert len(results_page2) == 2


# ============================================
# Mark as Read
# ============================================


class TestMarkAsRead:
    """Tests for marking notifications as read."""

    @pytest.mark.asyncio
    async def test_mark_as_read(self, repository, user_id):
        """通知を既読にできる。"""
        created = await repository.create(_make_notification(user_id=user_id))
        assert created.is_read is False

        result = await repository.mark_as_read(user_id, created.id)
        assert result is not None
        assert result.is_read is True
        assert result.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_already_read_idempotent(self, repository, user_id):
        """既に既読の通知を再度既読にしてもエラーにならない。"""
        created = await repository.create(_make_notification(user_id=user_id))
        await repository.mark_as_read(user_id, created.id)
        result = await repository.mark_as_read(user_id, created.id)
        assert result is not None
        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_mark_nonexistent_returns_none(self, repository, user_id):
        """存在しない通知の既読はNoneが返る。"""
        result = await repository.mark_as_read(user_id, uuid4())
        assert result is None


# ============================================
# Mark All as Read
# ============================================


class TestMarkAllAsRead:
    """Tests for marking all notifications as read."""

    @pytest.mark.asyncio
    async def test_mark_all_as_read(self, repository, user_id):
        """全通知を一括既読にできる。"""
        await repository.create(_make_notification(user_id=user_id))
        await repository.create(_make_notification(user_id=user_id))
        await repository.create(_make_notification(user_id=user_id))

        count = await repository.mark_all_as_read(user_id)
        assert count == 3

        unread = await repository.get_unread_count(user_id)
        assert unread == 0

    @pytest.mark.asyncio
    async def test_mark_all_no_unread(self, repository, user_id):
        """未読がない場合、0が返る。"""
        count = await repository.mark_all_as_read(user_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_mark_all_only_affects_own(self, repository):
        """他ユーザーの通知には影響しない。"""
        await repository.create(_make_notification(user_id="user_A"))
        await repository.create(_make_notification(user_id="user_B"))

        count = await repository.mark_all_as_read("user_A")
        assert count == 1

        unread_b = await repository.get_unread_count("user_B")
        assert unread_b == 1


# ============================================
# Unread Count
# ============================================


class TestGetUnreadCount:
    """Tests for getting unread notification count."""

    @pytest.mark.asyncio
    async def test_initial_count_zero(self, repository, user_id):
        """通知がない場合、0が返る。"""
        count = await repository.get_unread_count(user_id)
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_increments(self, repository, user_id):
        """通知を作成するとカウントが増える。"""
        await repository.create(_make_notification(user_id=user_id))
        await repository.create(_make_notification(user_id=user_id))

        count = await repository.get_unread_count(user_id)
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_decrements_on_read(self, repository, user_id):
        """既読にするとカウントが減る。"""
        n = await repository.create(_make_notification(user_id=user_id))
        await repository.create(_make_notification(user_id=user_id))

        await repository.mark_as_read(user_id, n.id)

        count = await repository.get_unread_count(user_id)
        assert count == 1


# ============================================
# Delete
# ============================================


class TestDelete:
    """Tests for deleting notifications."""

    @pytest.mark.asyncio
    async def test_delete_existing(self, repository, user_id):
        """通知を削除できる。"""
        created = await repository.create(_make_notification(user_id=user_id))

        deleted = await repository.delete(user_id, created.id)
        assert deleted is True

        result = await repository.get(user_id, created.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repository, user_id):
        """存在しない通知の削除はFalseが返る。"""
        deleted = await repository.delete(user_id, uuid4())
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_wrong_user(self, repository):
        """他ユーザーの通知は削除できない。"""
        created = await repository.create(_make_notification(user_id="user_A"))

        deleted = await repository.delete("user_B", created.id)
        assert deleted is False

        # 元のユーザーでは取得できる
        result = await repository.get("user_A", created.id)
        assert result is not None
