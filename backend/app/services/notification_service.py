"""
Notification helper functions for creating notifications across the app.

Each function creates notifications for specific events and handles
recipient filtering (exclude actor, developer checks, etc.).
"""

from uuid import UUID

from app.core.config import get_settings
from app.interfaces.notification_repository import INotificationRepository
from app.models.notification import NotificationCreate, NotificationType


def _get_developer_id() -> str:
    """Get developer user ID from settings. Returns empty string if not set."""
    return get_settings().DEVELOPER_USER_ID


async def notify_checkin_change(
    notification_repo: INotificationRepository,
    project_id: UUID,
    project_name: str,
    actor_user_id: str,
    actor_display_name: str,
    member_user_ids: set[str],
    is_update: bool = False,
):
    """Notify project members about a check-in creation or update."""
    notification_type = (
        NotificationType.CHECKIN_UPDATED if is_update
        else NotificationType.CHECKIN_CREATED
    )
    action = "更新" if is_update else "提出"
    recipients = member_user_ids - {actor_user_id}
    if not recipients:
        return

    notifications = [
        NotificationCreate(
            user_id=uid,
            type=notification_type,
            title=f"チェックインが{action}されました",
            message=f"{actor_display_name or '匿名'}さんが「{project_name}」のチェックインを{action}しました",
            link_type="checkin",
            link_id=str(project_id),
            project_id=project_id,
            project_name=project_name,
        )
        for uid in recipients
    ]
    await notification_repo.create_bulk(notifications)


async def notify_issue_new(
    notification_repo: INotificationRepository,
    issue_id: UUID,
    issue_title: str,
    actor_user_id: str,
):
    """Notify developer about a new issue."""
    dev_id = _get_developer_id()
    if not dev_id or dev_id == actor_user_id:
        return

    await notification_repo.create(NotificationCreate(
        user_id=dev_id,
        type=NotificationType.ISSUE_NEW,
        title="新しい要望が投稿されました",
        message=f"「{issue_title}」",
        link_type="issue",
        link_id=str(issue_id),
    ))


async def notify_issue_edited(
    notification_repo: INotificationRepository,
    issue_id: UUID,
    issue_title: str,
    actor_user_id: str,
):
    """Notify developer about an issue edit."""
    dev_id = _get_developer_id()
    if not dev_id or dev_id == actor_user_id:
        return

    await notification_repo.create(NotificationCreate(
        user_id=dev_id,
        type=NotificationType.ISSUE_EDITED,
        title="要望が編集されました",
        message=f"「{issue_title}」が編集されました",
        link_type="issue",
        link_id=str(issue_id),
    ))


async def notify_issue_status_changed(
    notification_repo: INotificationRepository,
    issue_id: UUID,
    issue_title: str,
    issue_poster_user_id: str,
    actor_user_id: str,
    new_status_label: str,
):
    """Notify issue poster and developer about status change."""
    dev_id = _get_developer_id()
    recipients: set[str] = set()

    if actor_user_id != issue_poster_user_id:
        recipients.add(issue_poster_user_id)
    if dev_id and actor_user_id != dev_id:
        recipients.add(dev_id)

    if not recipients:
        return

    notifications = [
        NotificationCreate(
            user_id=uid,
            type=NotificationType.ISSUE_STATUS_CHANGED,
            title="要望のステータスが変更されました",
            message=f"「{issue_title}」のステータスが「{new_status_label}」に変更されました",
            link_type="issue",
            link_id=str(issue_id),
        )
        for uid in recipients
    ]
    await notification_repo.create_bulk(notifications)


async def notify_issue_liked(
    notification_repo: INotificationRepository,
    issue_id: UUID,
    issue_title: str,
    issue_poster_user_id: str,
    liker_user_id: str,
    liker_display_name: str,
):
    """Notify issue poster and developer about a like."""
    dev_id = _get_developer_id()
    recipients: set[str] = set()

    if liker_user_id != issue_poster_user_id:
        recipients.add(issue_poster_user_id)
    if dev_id and liker_user_id != dev_id:
        recipients.add(dev_id)

    if not recipients:
        return

    notifications = [
        NotificationCreate(
            user_id=uid,
            type=NotificationType.ISSUE_LIKED,
            title="要望にいいねがつきました",
            message=f"{liker_display_name or '匿名'}さんが「{issue_title}」にいいねしました",
            link_type="issue",
            link_id=str(issue_id),
        )
        for uid in recipients
    ]
    await notification_repo.create_bulk(notifications)


async def notify_project_link_request(
    notification_repo: INotificationRepository,
    parent_project_id: UUID,
    parent_project_name: str,
    child_project_name: str,
    requester_display_name: str,
    owner_user_id: str,
):
    """Notify parent project owner about a link request."""
    await notification_repo.create(NotificationCreate(
        user_id=owner_user_id,
        type=NotificationType.PROJECT_LINK_REQUEST,
        title="プロジェクト紐付けリクエスト",
        message=f"{requester_display_name or '匿名'}さんが「{child_project_name}」を「{parent_project_name}」に紐付けたいとリクエストしました",
        link_type="project",
        link_id=str(parent_project_id),
        project_id=parent_project_id,
        project_name=parent_project_name,
    ))


async def notify_project_link_approved(
    notification_repo: INotificationRepository,
    child_project_id: UUID,
    parent_project_name: str,
    child_project_name: str,
    requester_user_id: str,
):
    """Notify requester that their link request was approved."""
    await notification_repo.create(NotificationCreate(
        user_id=requester_user_id,
        type=NotificationType.PROJECT_LINK_APPROVED,
        title="紐付けリクエストが承認されました",
        message=f"「{child_project_name}」の「{parent_project_name}」への紐付けが承認されました",
        link_type="project",
        link_id=str(child_project_id),
        project_id=child_project_id,
        project_name=child_project_name,
    ))


async def notify_child_project_link_request(
    notification_repo: INotificationRepository,
    child_project_id: UUID,
    child_project_name: str,
    parent_project_name: str,
    requester_display_name: str,
    child_owner_user_id: str,
):
    """Notify child project owner about a link request."""
    await notification_repo.create(NotificationCreate(
        user_id=child_owner_user_id,
        type=NotificationType.PROJECT_LINK_REQUEST,
        title="プロジェクト紐付けリクエスト",
        message=f"{requester_display_name or '匿名'}さんが「{child_project_name}」を「{parent_project_name}」の子プロジェクトにしたいとリクエストしました",
        link_type="project",
        link_id=str(child_project_id),
        project_id=child_project_id,
        project_name=child_project_name,
    ))


async def notify_project_link_rejected(
    notification_repo: INotificationRepository,
    child_project_id: UUID,
    parent_project_name: str,
    child_project_name: str,
    requester_user_id: str,
):
    """Notify requester that their link request was rejected."""
    await notification_repo.create(NotificationCreate(
        user_id=requester_user_id,
        type=NotificationType.PROJECT_LINK_REJECTED,
        title="紐付けリクエストが却下されました",
        message=f"「{child_project_name}」の「{parent_project_name}」への紐付けが却下されました",
        link_type="project",
        link_id=str(child_project_id),
        project_id=child_project_id,
        project_name=child_project_name,
    ))


async def notify_issue_commented(
    notification_repo: INotificationRepository,
    issue_id: UUID,
    issue_title: str,
    issue_poster_user_id: str,
    commenter_user_id: str,
    commenter_display_name: str,
):
    """Notify issue poster and developer about a new comment."""
    dev_id = _get_developer_id()
    recipients: set[str] = set()

    if commenter_user_id != issue_poster_user_id:
        recipients.add(issue_poster_user_id)
    if dev_id and commenter_user_id != dev_id:
        recipients.add(dev_id)

    if not recipients:
        return

    notifications = [
        NotificationCreate(
            user_id=uid,
            type=NotificationType.ISSUE_COMMENTED,
            title="要望にコメントがつきました",
            message=f"{commenter_display_name or '匿名'}さんが「{issue_title}」にコメントしました",
            link_type="issue",
            link_id=str(issue_id),
        )
        for uid in recipients
    ]
    await notification_repo.create_bulk(notifications)
