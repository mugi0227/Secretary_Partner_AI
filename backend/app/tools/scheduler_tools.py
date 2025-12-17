"""
Scheduler-related agent tools.

Tools for scheduling autonomous agent actions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.models.agent_task import AgentTaskCreate, AgentTaskPayload
from app.models.enums import ActionType


# ===========================================
# Tool Input Models
# ===========================================


class ScheduleAgentTaskInput(BaseModel):
    """Input for schedule_agent_task tool."""

    action_type: ActionType = Field(..., description="アクションタイプ")
    execute_at: str = Field(..., description="実行時刻（ISO形式: YYYY-MM-DDTHH:MM:SS）")
    target_task_id: Optional[str] = Field(None, description="対象タスクID（UUID文字列）")
    message_tone: str = Field("neutral", description="メッセージのトーン (gentle/neutral/firm)")
    custom_message: Optional[str] = Field(None, description="カスタムメッセージ")
    metadata: dict[str, Any] = Field(default_factory=dict, description="追加メタデータ")


# ===========================================
# Tool Functions
# ===========================================


def get_current_datetime() -> dict:
    """
    Get current date and time.

    Returns:
        Current datetime information in various formats
    """
    now = datetime.now()
    return {
        "current_datetime": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "weekday_ja": ["月", "火", "水", "木", "金", "土", "日"][now.weekday()],
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute,
        "timestamp": now.timestamp(),
    }


async def schedule_agent_task(
    user_id: str,
    repo: IAgentTaskRepository,
    input_data: ScheduleAgentTaskInput,
) -> dict:
    """
    Schedule an autonomous agent action.

    Args:
        user_id: User ID
        repo: Agent task repository
        input_data: Schedule parameters

    Returns:
        Created agent task as dict
    """
    # Parse execute_at
    try:
        trigger_time = datetime.fromisoformat(
            input_data.execute_at.replace("Z", "+00:00")
        )
    except ValueError:
        raise ValueError(f"Invalid date format: {input_data.execute_at}")

    # Parse target_task_id if provided
    target_task_id = UUID(input_data.target_task_id) if input_data.target_task_id else None

    payload = AgentTaskPayload(
        target_task_id=target_task_id,
        message_tone=input_data.message_tone,
        custom_message=input_data.custom_message,
        metadata=input_data.metadata,
    )

    task_data = AgentTaskCreate(
        trigger_time=trigger_time,
        action_type=input_data.action_type,
        payload=payload,
    )

    task = await repo.create(user_id, task_data)
    return task.model_dump(mode="json")  # Serialize UUIDs to strings


# ===========================================
# ADK Tool Definitions
# ===========================================


def get_current_datetime_tool() -> FunctionTool:
    """Create ADK tool for getting current datetime."""
    def _tool() -> dict:
        """get_current_datetime: 現在の日時を取得します。

        Parameters:
            なし

        Returns:
            dict: 現在の日時情報（ISO形式、日付、時刻、曜日、年月日時分など）
        """
        return get_current_datetime()

    _tool.__name__ = "get_current_datetime"
    return FunctionTool(func=_tool)


def schedule_agent_task_tool(repo: IAgentTaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for scheduling agent tasks."""
    async def _tool(input_data: dict) -> dict:
        """schedule_agent_task: 自律行動（リマインド等）をスケジュールします。

        Parameters:
            action_type (str): アクションタイプ（REMINDER/FOLLOWUP/MOTIVATE等、必須）
            execute_at (str): 実行時刻（ISO形式: YYYY-MM-DDTHH:MM:SS、必須）
            target_task_id (str, optional): 対象タスクID（UUID文字列）
            message_tone (str, optional): メッセージのトーン (gentle/neutral/firm)、デフォルト: neutral
            custom_message (str, optional): カスタムメッセージ
            metadata (dict, optional): 追加メタデータ

        Returns:
            dict: 作成されたエージェントタスク情報
        """
        return await schedule_agent_task(user_id, repo, ScheduleAgentTaskInput(**input_data))

    _tool.__name__ = "schedule_agent_task"
    return FunctionTool(func=_tool)

