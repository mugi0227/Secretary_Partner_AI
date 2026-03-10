"""
Notification helper functions for creating notifications across the app.

Each function creates notifications for specific events and handles
recipient filtering (exclude actor, developer checks, etc.).
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence, Union
from uuid import UUID

from app.core.config import get_settings
from app.interfaces.email_provider import IEmailProvider
from app.interfaces.notification_repository import INotificationRepository
from app.interfaces.user_repository import IUserRepository
from app.models.collaboration import (
    CheckinCreateV2,
    CheckinItem,
    CheckinV2,
    ProjectMember,
)
from app.models.enums import CheckinItemCategory, CheckinMood, ProjectRole
from app.models.notification import NotificationCreate, NotificationType

logger = logging.getLogger(__name__)


def _get_developer_id() -> str:
    """Get developer user ID from settings. Returns empty string if not set."""
    return get_settings().DEVELOPER_USER_ID


# =============================================================================
# Checkin email helpers
# =============================================================================

_MOOD_LABELS = {
    CheckinMood.GOOD: "順調 😊",
    CheckinMood.OKAY: "まあまあ 😐",
    CheckinMood.STRUGGLING: "厳しい 😣",
}

_CATEGORY_LABELS = {
    CheckinItemCategory.BLOCKER: "ブロッカー",
    CheckinItemCategory.DISCUSSION: "相談事項",
    CheckinItemCategory.REQUEST: "依頼",
    CheckinItemCategory.UPDATE: "進捗報告",
}

_URGENCY_LABELS = {"high": "🔴高", "medium": "🟡中", "low": "🟢低"}


def _build_checkin_email(
    project_name: str,
    actor_display_name: str,
    is_update: bool,
    items: Sequence[CheckinItem],
    mood: Optional[CheckinMood],
    must_discuss: Optional[str],
    free_comment: Optional[str],
) -> tuple[str, str, str]:
    """Build subject, text body, and HTML body for a checkin email."""
    action = "更新" if is_update else "提出"
    actor = actor_display_name or "匿名"
    subject = f"[{project_name}] チェックインが{action}されました - {actor}"

    lines: list[str] = [
        f"{actor}さんが「{project_name}」のチェックインを{action}しました。",
        "",
    ]

    if mood:
        lines.append(f"■ 気分: {_MOOD_LABELS.get(mood, mood)}")
        lines.append("")

    for cat in (
        CheckinItemCategory.BLOCKER,
        CheckinItemCategory.DISCUSSION,
        CheckinItemCategory.REQUEST,
        CheckinItemCategory.UPDATE,
    ):
        cat_items = [i for i in items if i.category == cat]
        if cat_items:
            lines.append(f"■ {_CATEGORY_LABELS[cat]}:")
            for item in cat_items:
                urg = _URGENCY_LABELS.get(item.urgency, "")
                lines.append(f"  - {item.content} ({urg})")
            lines.append("")

    if must_discuss:
        lines.append("■ 次回ミーティングで必ず話し合いたいこと:")
        lines.append(f"  {must_discuss}")
        lines.append("")

    if free_comment:
        lines.append("■ 自由コメント:")
        lines.append(f"  {free_comment}")
        lines.append("")

    body_text = "\n".join(lines)

    # Simple HTML version
    body_html = body_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body_html = f"<pre style='font-family: sans-serif; white-space: pre-wrap;'>{body_html}</pre>"

    return subject, body_text, body_html


async def _send_checkin_email(
    email_provider: IEmailProvider,
    user_repo: IUserRepository,
    members: list[ProjectMember],
    actor_user_id: str,
    project_name: str,
    actor_display_name: str,
    is_update: bool,
    checkin: Union[CheckinCreateV2, CheckinV2],
) -> None:
    """Send checkin email to ADMIN+ members (excluding the actor)."""
    admin_members = [
        m for m in members
        if m.role in (ProjectRole.OWNER, ProjectRole.ADMIN)
        and m.member_user_id != actor_user_id
    ]
    if not admin_members:
        return

    # Gather email addresses
    emails: list[str] = []
    for m in admin_members:
        try:
            uid = UUID(m.member_user_id)
        except ValueError:
            continue
        user = await user_repo.get(uid)
        if user and user.email:
            emails.append(user.email)

    if not emails:
        return

    items = checkin.items if checkin.items else []
    subject, body_text, body_html = _build_checkin_email(
        project_name=project_name,
        actor_display_name=actor_display_name,
        is_update=is_update,
        items=items,
        mood=checkin.mood,
        must_discuss=checkin.must_discuss_in_next_meeting,
        free_comment=checkin.free_comment,
    )

    try:
        await email_provider.send_email(emails, subject, body_text, body_html)
    except Exception:
        logger.exception("Failed to send checkin email notification")


# =============================================================================
# In-app notification helpers
# =============================================================================


async def notify_checkin_change(
    notification_repo: INotificationRepository,
    project_id: UUID,
    project_name: str,
    actor_user_id: str,
    actor_display_name: str,
    member_user_ids: set[str],
    is_update: bool = False,
    *,
    email_provider: Optional[IEmailProvider] = None,
    user_repo: Optional[IUserRepository] = None,
    members: Optional[list[ProjectMember]] = None,
    checkin: Optional[Union[CheckinCreateV2, CheckinV2]] = None,
):
    """Notify project members about a check-in creation or update.

    In-app notifications are always sent.
    If email_provider / user_repo / members / checkin are provided,
    an email is also sent to ADMIN+ members.
    """
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

    # Send email notification to ADMIN+ members
    if email_provider and user_repo and members and checkin:
        await _send_checkin_email(
            email_provider=email_provider,
            user_repo=user_repo,
            members=members,
            actor_user_id=actor_user_id,
            project_name=project_name,
            actor_display_name=actor_display_name,
            is_update=is_update,
            checkin=checkin,
        )


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
