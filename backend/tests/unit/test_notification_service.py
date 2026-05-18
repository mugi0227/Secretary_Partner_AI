"""
Unit tests for notification_service.

Tests notification creation logic for issue (要望) and check-in events.
Uses a mock repository to verify correct notifications are created.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.notification import NotificationType
from app.services import notification_service as notify


@pytest.fixture
def mock_repo():
    """Mock notification repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.create_bulk = AsyncMock(return_value=[])
    return repo


# ============================================
# Check-in notifications
# ============================================


class TestNotifyCheckinChange:
    """Tests for notify_checkin_change."""

    @pytest.mark.asyncio
    async def test_created_notification_sent_to_other_members(self, mock_repo):
        """チェックイン作成時、アクター以外のメンバーに通知される。"""
        project_id = uuid4()
        await notify.notify_checkin_change(
            mock_repo,
            project_id=project_id,
            project_name="テストPJ",
            actor_user_id="user_A",
            actor_display_name="Aさん",
            member_user_ids={"user_A", "user_B", "user_C"},
            is_update=False,
        )

        mock_repo.create_bulk.assert_called_once()
        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 2
        recipient_ids = {n.user_id for n in notifications}
        assert recipient_ids == {"user_B", "user_C"}
        for n in notifications:
            assert n.type == NotificationType.CHECKIN_CREATED
            assert "提出" in n.title
            assert "Aさん" in n.message
            assert "テストPJ" in n.message
            assert n.link_type == "checkin"
            assert n.link_id == str(project_id)
            assert n.project_id == project_id
            assert n.project_name == "テストPJ"

    @pytest.mark.asyncio
    async def test_updated_notification(self, mock_repo):
        """チェックイン更新時、CHECKIN_UPDATED タイプで「更新」が含まれる。"""
        project_id = uuid4()
        await notify.notify_checkin_change(
            mock_repo,
            project_id=project_id,
            project_name="PJ2",
            actor_user_id="user_A",
            actor_display_name="太郎",
            member_user_ids={"user_A", "user_B"},
            is_update=True,
        )

        mock_repo.create_bulk.assert_called_once()
        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        n = notifications[0]
        assert n.type == NotificationType.CHECKIN_UPDATED
        assert "更新" in n.title
        assert "更新" in n.message

    @pytest.mark.asyncio
    async def test_actor_excluded_from_recipients(self, mock_repo):
        """アクター自身には通知されない。"""
        await notify.notify_checkin_change(
            mock_repo,
            project_id=uuid4(),
            project_name="PJ",
            actor_user_id="user_A",
            actor_display_name="Aさん",
            member_user_ids={"user_A"},
        )

        mock_repo.create_bulk.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_members_no_notification(self, mock_repo):
        """メンバーが空の場合、通知されない。"""
        await notify.notify_checkin_change(
            mock_repo,
            project_id=uuid4(),
            project_name="PJ",
            actor_user_id="user_A",
            actor_display_name="Aさん",
            member_user_ids=set(),
        )

        mock_repo.create_bulk.assert_not_called()

    @pytest.mark.asyncio
    async def test_anonymous_display_name(self, mock_repo):
        """display_name が空の場合「匿名」が使われる。"""
        await notify.notify_checkin_change(
            mock_repo,
            project_id=uuid4(),
            project_name="PJ",
            actor_user_id="user_A",
            actor_display_name="",
            member_user_ids={"user_A", "user_B"},
        )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert "匿名" in notifications[0].message


# ============================================
# Issue (要望) notifications
# ============================================


DEVELOPER_ID = "dev_user_001"


def _patch_dev_id(dev_id=DEVELOPER_ID):
    return patch.object(notify, "_get_developer_id", return_value=dev_id)


class TestNotifyIssueNew:
    """Tests for notify_issue_new (新しい要望)."""

    @pytest.mark.asyncio
    async def test_notifies_developer(self, mock_repo):
        """新しい要望投稿時、開発者に通知される。"""
        issue_id = uuid4()
        with _patch_dev_id():
            await notify.notify_issue_new(
                mock_repo, issue_id, "機能要望タイトル", "poster_user",
            )

        mock_repo.create.assert_called_once()
        n = mock_repo.create.call_args[0][0]
        assert n.user_id == DEVELOPER_ID
        assert n.type == NotificationType.ISSUE_NEW
        assert "新しい要望" in n.title
        assert "機能要望タイトル" in n.message
        assert n.link_type == "issue"
        assert n.link_id == str(issue_id)

    @pytest.mark.asyncio
    async def test_developer_posts_own_issue_no_notification(self, mock_repo):
        """開発者自身が投稿した場合、通知されない。"""
        with _patch_dev_id():
            await notify.notify_issue_new(
                mock_repo, uuid4(), "タイトル", DEVELOPER_ID,
            )

        mock_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_developer_configured(self, mock_repo):
        """DEVELOPER_USER_ID が未設定の場合、通知されない。"""
        with _patch_dev_id(""):
            await notify.notify_issue_new(
                mock_repo, uuid4(), "タイトル", "poster_user",
            )

        mock_repo.create.assert_not_called()


class TestNotifyIssueEdited:
    """Tests for notify_issue_edited (要望編集)."""

    @pytest.mark.asyncio
    async def test_notifies_developer(self, mock_repo):
        """要望編集時、開発者に通知される。"""
        issue_id = uuid4()
        with _patch_dev_id():
            await notify.notify_issue_edited(
                mock_repo, issue_id, "編集された要望", "editor_user",
            )

        n = mock_repo.create.call_args[0][0]
        assert n.user_id == DEVELOPER_ID
        assert n.type == NotificationType.ISSUE_EDITED
        assert "編集" in n.title
        assert "編集された要望" in n.message

    @pytest.mark.asyncio
    async def test_developer_edits_own_no_notification(self, mock_repo):
        """開発者自身が編集した場合、通知されない。"""
        with _patch_dev_id():
            await notify.notify_issue_edited(
                mock_repo, uuid4(), "タイトル", DEVELOPER_ID,
            )

        mock_repo.create.assert_not_called()


class TestNotifyIssueStatusChanged:
    """Tests for notify_issue_status_changed (ステータス変更)."""

    @pytest.mark.asyncio
    async def test_notifies_poster_and_developer(self, mock_repo):
        """ステータス変更時、投稿者と開発者の両方に通知される。"""
        issue_id = uuid4()
        with _patch_dev_id():
            await notify.notify_issue_status_changed(
                mock_repo, issue_id, "要望タイトル",
                issue_poster_user_id="poster_user",
                actor_user_id="admin_user",
                new_status_label="対応予定",
            )

        mock_repo.create_bulk.assert_called_once()
        notifications = mock_repo.create_bulk.call_args[0][0]
        recipient_ids = {n.user_id for n in notifications}
        assert "poster_user" in recipient_ids
        assert DEVELOPER_ID in recipient_ids
        for n in notifications:
            assert n.type == NotificationType.ISSUE_STATUS_CHANGED
            assert "ステータス" in n.title
            assert "対応予定" in n.message

    @pytest.mark.asyncio
    async def test_developer_changes_own_issue_notifies_poster_only(self, mock_repo):
        """開発者がステータス変更した場合、投稿者のみ通知される。"""
        with _patch_dev_id():
            await notify.notify_issue_status_changed(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                actor_user_id=DEVELOPER_ID,
                new_status_label="完了",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        assert notifications[0].user_id == "poster_user"

    @pytest.mark.asyncio
    async def test_poster_is_actor_notifies_developer_only(self, mock_repo):
        """投稿者がアクターの場合、開発者のみ通知される。"""
        with _patch_dev_id():
            await notify.notify_issue_status_changed(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                actor_user_id="poster_user",
                new_status_label="検討中",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        assert notifications[0].user_id == DEVELOPER_ID

    @pytest.mark.asyncio
    async def test_poster_is_developer_no_duplicate(self, mock_repo):
        """投稿者が開発者の場合、アクターでなければ1通だけ送られる。"""
        with _patch_dev_id():
            await notify.notify_issue_status_changed(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id=DEVELOPER_ID,
                actor_user_id="other_admin",
                new_status_label="対応中",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        # set で重複排除されるため1通
        assert len(notifications) == 1
        assert notifications[0].user_id == DEVELOPER_ID

    @pytest.mark.asyncio
    async def test_no_recipients(self, mock_repo):
        """全員がアクターの場合、通知されない。"""
        with _patch_dev_id(DEVELOPER_ID):
            await notify.notify_issue_status_changed(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id=DEVELOPER_ID,
                actor_user_id=DEVELOPER_ID,
                new_status_label="完了",
            )

        mock_repo.create_bulk.assert_not_called()


class TestNotifyIssueLiked:
    """Tests for notify_issue_liked (いいね)."""

    @pytest.mark.asyncio
    async def test_notifies_poster_and_developer(self, mock_repo):
        """いいね時、投稿者と開発者に通知される。"""
        issue_id = uuid4()
        with _patch_dev_id():
            await notify.notify_issue_liked(
                mock_repo, issue_id, "要望タイトル",
                issue_poster_user_id="poster_user",
                liker_user_id="liker_user",
                liker_display_name="いいね太郎",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        recipient_ids = {n.user_id for n in notifications}
        assert "poster_user" in recipient_ids
        assert DEVELOPER_ID in recipient_ids
        for n in notifications:
            assert n.type == NotificationType.ISSUE_LIKED
            assert "いいね" in n.title
            assert "いいね太郎" in n.message
            assert "要望タイトル" in n.message

    @pytest.mark.asyncio
    async def test_poster_likes_own_issue(self, mock_repo):
        """投稿者が自分の要望にいいねした場合、開発者のみ通知される。"""
        with _patch_dev_id():
            await notify.notify_issue_liked(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                liker_user_id="poster_user",
                liker_display_name="Poster",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        assert notifications[0].user_id == DEVELOPER_ID

    @pytest.mark.asyncio
    async def test_anonymous_liker(self, mock_repo):
        """display_name が空の場合「匿名」が使われる。"""
        with _patch_dev_id():
            await notify.notify_issue_liked(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                liker_user_id="liker_user",
                liker_display_name="",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert "匿名" in notifications[0].message


class TestNotifyIssueCommented:
    """Tests for notify_issue_commented (コメント)."""

    @pytest.mark.asyncio
    async def test_notifies_poster_and_developer(self, mock_repo):
        """コメント時、投稿者と開発者に通知される。"""
        issue_id = uuid4()
        with _patch_dev_id():
            await notify.notify_issue_commented(
                mock_repo, issue_id, "要望タイトル",
                issue_poster_user_id="poster_user",
                commenter_user_id="commenter_user",
                commenter_display_name="コメント太郎",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        recipient_ids = {n.user_id for n in notifications}
        assert "poster_user" in recipient_ids
        assert DEVELOPER_ID in recipient_ids
        for n in notifications:
            assert n.type == NotificationType.ISSUE_COMMENTED
            assert "コメント" in n.title
            assert "コメント太郎" in n.message
            assert "要望タイトル" in n.message

    @pytest.mark.asyncio
    async def test_poster_comments_own_issue(self, mock_repo):
        """投稿者が自分の要望にコメントした場合、開発者のみ通知される。"""
        with _patch_dev_id():
            await notify.notify_issue_commented(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                commenter_user_id="poster_user",
                commenter_display_name="Poster",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        assert notifications[0].user_id == DEVELOPER_ID

    @pytest.mark.asyncio
    async def test_developer_comments_notifies_poster_only(self, mock_repo):
        """開発者がコメントした場合、投稿者のみ通知される。"""
        with _patch_dev_id():
            await notify.notify_issue_commented(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                commenter_user_id=DEVELOPER_ID,
                commenter_display_name="Dev",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert len(notifications) == 1
        assert notifications[0].user_id == "poster_user"

    @pytest.mark.asyncio
    async def test_anonymous_commenter(self, mock_repo):
        """display_name が空の場合「匿名」が使われる。"""
        with _patch_dev_id():
            await notify.notify_issue_commented(
                mock_repo, uuid4(), "タイトル",
                issue_poster_user_id="poster_user",
                commenter_user_id="commenter_user",
                commenter_display_name="",
            )

        notifications = mock_repo.create_bulk.call_args[0][0]
        assert "匿名" in notifications[0].message
