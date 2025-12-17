"""
AgentTask model definitions.

AgentTasks represent the secretary agent's autonomous scheduled actions.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ActionType, AgentTaskStatus


class AgentTaskPayload(BaseModel):
    """Payload for agent task execution."""

    target_task_id: Optional[UUID] = Field(None, description="対象タスクID")
    message_tone: str = Field("neutral", description="メッセージのトーン (gentle/neutral/firm)")
    custom_message: Optional[str] = Field(None, description="カスタムメッセージ")
    metadata: dict[str, Any] = Field(default_factory=dict, description="追加メタデータ")


class AgentTaskBase(BaseModel):
    """Base agent task fields."""

    trigger_time: datetime = Field(..., description="実行予定時刻")
    action_type: ActionType = Field(..., description="アクションタイプ")
    payload: AgentTaskPayload = Field(
        default_factory=AgentTaskPayload, description="実行時のペイロード"
    )


class AgentTaskCreate(AgentTaskBase):
    """Schema for creating a new agent task."""

    pass


class AgentTaskUpdate(BaseModel):
    """Schema for updating an agent task."""

    trigger_time: Optional[datetime] = None
    status: Optional[AgentTaskStatus] = None
    payload: Optional[AgentTaskPayload] = None


class AgentTask(AgentTaskBase):
    """Complete agent task model."""

    id: UUID
    user_id: str = Field(..., description="対象ユーザーID")
    status: AgentTaskStatus = Field(AgentTaskStatus.PENDING)
    retry_count: int = Field(0, ge=0, description="リトライ回数")
    last_error: Optional[str] = Field(None, description="最後のエラーメッセージ")
    executed_at: Optional[datetime] = Field(None, description="実行完了時刻")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
