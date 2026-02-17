"""
Notification model definitions.

Notifications inform users about events like achievement updates.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    """Types of notifications."""

    ACHIEVEMENT_PERSONAL = "achievement_personal"  # 個人達成項目の更新
    ACHIEVEMENT_PROJECT = "achievement_project"  # プロジェクト達成項目の更新
    TASK_ASSIGNED = "task_assigned"  # タスクが割り当てられた
    PROJECT_INVITED = "project_invited"  # プロジェクトに招待された
    MILESTONE_REACHED = "milestone_reached"  # マイルストーン達成
    CHECKIN_CREATED = "checkin_created"  # チェックインが作成された
    CHECKIN_UPDATED = "checkin_updated"  # チェックインが更新された
    ISSUE_NEW = "issue_new"  # 新しい要望が投稿された
    ISSUE_EDITED = "issue_edited"  # 要望が編集された
    ISSUE_LIKED = "issue_liked"  # 要望にいいねがついた
    ISSUE_COMMENTED = "issue_commented"  # 要望にコメントがついた
    ISSUE_STATUS_CHANGED = "issue_status_changed"  # 要望のステータスが変更された
    HEARTBEAT = "heartbeat"
    PROJECT_LINK_REQUEST = "project_link_request"  # 親プロジェクトへの紐付けリクエスト
    PROJECT_LINK_APPROVED = "project_link_approved"  # 紐付けリクエスト承認
    PROJECT_LINK_REJECTED = "project_link_rejected"  # 紐付けリクエスト却下


class Notification(BaseModel):
    """User notification model."""

    id: UUID
    user_id: str = Field(..., description="通知先ユーザーID")
    type: NotificationType = Field(..., description="通知タイプ")
    title: str = Field(..., max_length=200, description="通知タイトル")
    message: str = Field(..., max_length=500, description="通知メッセージ")

    # Navigation
    link_type: Optional[str] = Field(
        None,
        description="遷移先タイプ (achievement, project_achievement, task, project)",
    )
    link_id: Optional[str] = Field(
        None,
        description="遷移先のID",
    )

    # Context
    project_id: Optional[UUID] = Field(None, description="関連プロジェクトID")
    project_name: Optional[str] = Field(None, description="関連プロジェクト名")

    # Status
    is_read: bool = Field(False, description="既読フラグ")
    read_at: Optional[datetime] = Field(None, description="既読日時")

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    """Schema for creating a notification."""

    user_id: str
    type: NotificationType
    title: str
    message: str
    link_type: Optional[str] = None
    link_id: Optional[str] = None
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
