"""
Recurring task tools for the agent.

These tools allow the agent to create, list, update, and delete recurring task definitions.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.recurring_task_repository import IRecurringTaskRepository
from app.interfaces.task_repository import ITaskRepository
from app.models.enums import EnergyLevel, Priority, RecurringTaskFrequency
from app.models.recurring_task import RecurringTaskCreate, RecurringTaskUpdate
from app.services.recurring_task_service import RecurringTaskService
from app.utils.datetime_utils import now_utc

WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


class CreateRecurringTaskInput(BaseModel):
    """Input for create_recurring_task tool."""

    title: str = Field(..., description="定期タスクのタイトル")
    description: Optional[str] = Field(None, description="タスクの詳細説明")
    purpose: Optional[str] = Field(None, description="なぜやるか（目的）")
    project_id: Optional[str] = Field(None, description="プロジェクトID")
    phase_id: Optional[str] = Field(None, description="フェーズID")
    frequency: str = Field(
        ..., description="頻度 (daily/weekly/biweekly/monthly/bimonthly/custom)"
    )
    weekday: Optional[int] = Field(
        None, description="曜日 (0=月曜...6=日曜), weekly/biweeklyの場合必須"
    )
    day_of_month: Optional[int] = Field(
        None, description="日付 (1-31), monthly/bimonthlyの場合必須"
    )
    custom_interval_days: Optional[int] = Field(
        None, description="間隔日数 (1-365), customの場合必須"
    )
    estimated_minutes: Optional[int] = Field(None, description="見積もり時間（分）")
    importance: Optional[str] = Field("MEDIUM", description="重要度 (HIGH/MEDIUM/LOW)")
    urgency: Optional[str] = Field("MEDIUM", description="緊急度 (HIGH/MEDIUM/LOW)")
    energy_level: Optional[str] = Field("LOW", description="必要エネルギー (HIGH/MEDIUM/LOW)")


class ListRecurringTasksInput(BaseModel):
    """Input for list_recurring_tasks tool."""

    project_id: Optional[str] = Field(None, description="プロジェクトID")
    include_inactive: bool = Field(False, description="無効化された定義も含める")


class UpdateRecurringTaskInput(BaseModel):
    """Input for update_recurring_task tool."""

    recurring_task_id: str = Field(..., description="定期タスク定義ID")
    title: Optional[str] = Field(None, description="新しいタイトル")
    is_active: Optional[bool] = Field(None, description="有効/無効")
    frequency: Optional[str] = Field(None, description="新しい頻度")
    weekday: Optional[int] = Field(None, description="新しい曜日")
    day_of_month: Optional[int] = Field(None, description="新しい日付")
    custom_interval_days: Optional[int] = Field(None, description="新しい間隔日数")
    estimated_minutes: Optional[int] = Field(None, description="新しい見積もり時間")
    importance: Optional[str] = Field(None, description="新しい重要度")
    urgency: Optional[str] = Field(None, description="新しい緊急度")
    energy_level: Optional[str] = Field(None, description="新しいエネルギーレベル")


class DeleteRecurringTaskInput(BaseModel):
    """Input for delete_recurring_task tool."""

    recurring_task_id: str = Field(..., description="定期タスク定義ID")


def _frequency_label(freq: str, weekday: int | None, day_of_month: int | None, interval: int | None) -> str:
    """Human-readable frequency label."""
    if freq == "daily":
        return "毎日"
    if freq == "weekly" and weekday is not None:
        return f"毎週{WEEKDAY_NAMES[weekday]}曜日"
    if freq == "biweekly" and weekday is not None:
        return f"隔週{WEEKDAY_NAMES[weekday]}曜日"
    if freq == "monthly" and day_of_month is not None:
        return f"毎月{day_of_month}日"
    if freq == "bimonthly" and day_of_month is not None:
        return f"隔月{day_of_month}日"
    if freq == "custom" and interval is not None:
        return f"{interval}日ごと"
    return freq


def _compute_anchor(frequency: str, weekday: int | None, day_of_month: int | None) -> date:
    """Auto-compute anchor date from frequency."""
    today = now_utc().date()
    if frequency in ("weekly", "biweekly") and weekday is not None:
        delta = (weekday - today.weekday()) % 7
        return today + timedelta(days=delta)
    if frequency in ("monthly", "bimonthly") and day_of_month is not None:
        if today.day <= day_of_month:
            try:
                return today.replace(day=day_of_month)
            except ValueError:
                return today
    return today


async def create_recurring_task(
    user_id: str,
    recurring_repo: IRecurringTaskRepository,
    task_repo: ITaskRepository,
    input_data: CreateRecurringTaskInput,
) -> dict:
    """Create a recurring task definition and generate upcoming instances."""
    try:
        freq = RecurringTaskFrequency(input_data.frequency)
    except ValueError:
        return {"error": f"Invalid frequency: {input_data.frequency}. Use: daily/weekly/biweekly/monthly/bimonthly/custom"}

    anchor = _compute_anchor(input_data.frequency, input_data.weekday, input_data.day_of_month)

    data = RecurringTaskCreate(
        title=input_data.title,
        description=input_data.description,
        purpose=input_data.purpose,
        project_id=UUID(input_data.project_id) if input_data.project_id else None,
        phase_id=UUID(input_data.phase_id) if input_data.phase_id else None,
        frequency=freq,
        weekday=input_data.weekday,
        day_of_month=input_data.day_of_month,
        custom_interval_days=input_data.custom_interval_days,
        estimated_minutes=input_data.estimated_minutes,
        importance=Priority(input_data.importance) if input_data.importance else Priority.MEDIUM,
        urgency=Priority(input_data.urgency) if input_data.urgency else Priority.MEDIUM,
        energy_level=EnergyLevel(input_data.energy_level) if input_data.energy_level else EnergyLevel.LOW,
        anchor_date=anchor,
    )
    created = await recurring_repo.create(user_id, data)

    service = RecurringTaskService(recurring_repo=recurring_repo, task_repo=task_repo)
    gen_result = await service.ensure_upcoming_tasks(user_id)

    freq_label = _frequency_label(
        input_data.frequency, input_data.weekday, input_data.day_of_month, input_data.custom_interval_days
    )
    return {
        "recurring_task_id": str(created.id),
        "title": created.title,
        "frequency": freq_label,
        "generated_tasks": gen_result["created_count"],
        "message": f"定期タスク「{created.title}」（{freq_label}）を作成しました。{gen_result['created_count']}件のタスクを生成しました。",
    }


async def list_recurring_tasks(
    user_id: str,
    recurring_repo: IRecurringTaskRepository,
    input_data: ListRecurringTasksInput,
) -> dict:
    """List recurring task definitions."""
    project_id = UUID(input_data.project_id) if input_data.project_id else None
    items = await recurring_repo.list(
        user_id, project_id=project_id, include_inactive=input_data.include_inactive
    )
    result = []
    for item in items:
        freq_label = _frequency_label(
            item.frequency.value, item.weekday, item.day_of_month, item.custom_interval_days
        )
        result.append({
            "id": str(item.id),
            "title": item.title,
            "frequency": freq_label,
            "is_active": item.is_active,
            "project_id": str(item.project_id) if item.project_id else None,
            "estimated_minutes": item.estimated_minutes,
            "last_generated_date": item.last_generated_date.isoformat() if item.last_generated_date else None,
        })
    return {"recurring_tasks": result, "count": len(result)}


async def update_recurring_task(
    user_id: str,
    recurring_repo: IRecurringTaskRepository,
    input_data: UpdateRecurringTaskInput,
) -> dict:
    """Update a recurring task definition."""
    try:
        rid = UUID(input_data.recurring_task_id)
    except ValueError:
        return {"error": f"Invalid recurring task ID: {input_data.recurring_task_id}"}

    update_fields: dict = {}
    if input_data.title is not None:
        update_fields["title"] = input_data.title
    if input_data.is_active is not None:
        update_fields["is_active"] = input_data.is_active
    if input_data.frequency is not None:
        update_fields["frequency"] = RecurringTaskFrequency(input_data.frequency)
    if input_data.weekday is not None:
        update_fields["weekday"] = input_data.weekday
    if input_data.day_of_month is not None:
        update_fields["day_of_month"] = input_data.day_of_month
    if input_data.custom_interval_days is not None:
        update_fields["custom_interval_days"] = input_data.custom_interval_days
    if input_data.estimated_minutes is not None:
        update_fields["estimated_minutes"] = input_data.estimated_minutes
    if input_data.importance is not None:
        update_fields["importance"] = Priority(input_data.importance)
    if input_data.urgency is not None:
        update_fields["urgency"] = Priority(input_data.urgency)
    if input_data.energy_level is not None:
        update_fields["energy_level"] = EnergyLevel(input_data.energy_level)

    update = RecurringTaskUpdate(**update_fields)
    try:
        updated = await recurring_repo.update(user_id, rid, update)
    except Exception as e:
        return {"error": str(e)}

    return {
        "recurring_task_id": str(updated.id),
        "title": updated.title,
        "is_active": updated.is_active,
        "message": f"定期タスク「{updated.title}」を更新しました。",
    }


async def delete_recurring_task(
    user_id: str,
    recurring_repo: IRecurringTaskRepository,
    input_data: DeleteRecurringTaskInput,
) -> dict:
    """Delete a recurring task definition."""
    try:
        rid = UUID(input_data.recurring_task_id)
    except ValueError:
        return {"error": f"Invalid recurring task ID: {input_data.recurring_task_id}"}

    deleted = await recurring_repo.delete(user_id, rid)
    if not deleted:
        return {"error": f"定期タスク {input_data.recurring_task_id} が見つかりません。"}
    return {"message": "定期タスクを削除しました。"}


# ============================================================================
# FunctionTool factories
# ============================================================================


def create_recurring_task_tool(
    recurring_repo: IRecurringTaskRepository,
    task_repo: ITaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for creating a recurring task definition."""

    async def _tool(input_data: dict) -> dict:
        """create_recurring_task: 定期タスク（繰り返しタスク）の定義を作成します。毎日/毎週/隔週/毎月/隔月/カスタム間隔で自動的にタスクを生成します。

        Parameters:
            title (str): タスクのタイトル（必須）
            description (str, optional): 詳細説明
            purpose (str, optional): 目的
            project_id (str, optional): プロジェクトID
            frequency (str): 頻度 - daily(毎日)/weekly(毎週)/biweekly(隔週)/monthly(毎月)/bimonthly(隔月)/custom(カスタム)
            weekday (int, optional): 曜日 (0=月曜...6=日曜) - weekly/biweekly時に必須
            day_of_month (int, optional): 日付 (1-31) - monthly/bimonthly時に必須
            custom_interval_days (int, optional): 間隔日数 - custom時に必須
            estimated_minutes (int, optional): 見積もり時間（分）
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)
            energy_level (str, optional): 必要エネルギー (HIGH/MEDIUM/LOW)

        Returns:
            dict: recurring_task_id, title, frequency, generated_tasks, message
        """
        return await create_recurring_task(
            user_id, recurring_repo, task_repo, CreateRecurringTaskInput(**input_data)
        )

    _tool.__name__ = "create_recurring_task"
    return FunctionTool(func=_tool)


def list_recurring_tasks_tool(
    recurring_repo: IRecurringTaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for listing recurring task definitions."""

    async def _tool(input_data: dict) -> dict:
        """list_recurring_tasks: 定期タスクの定義一覧を取得します。

        Parameters:
            project_id (str, optional): プロジェクトIDでフィルタ
            include_inactive (bool, optional): 無効化された定義も含める（デフォルト: false）

        Returns:
            dict: recurring_tasks (list), count (int)
        """
        return await list_recurring_tasks(
            user_id, recurring_repo, ListRecurringTasksInput(**input_data)
        )

    _tool.__name__ = "list_recurring_tasks"
    return FunctionTool(func=_tool)


def update_recurring_task_tool(
    recurring_repo: IRecurringTaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for updating a recurring task definition."""

    async def _tool(input_data: dict) -> dict:
        """update_recurring_task: 定期タスクの定義を更新します（タイトル変更、無効化など）。

        Parameters:
            recurring_task_id (str): 定期タスク定義ID（必須）
            title (str, optional): 新しいタイトル
            is_active (bool, optional): 有効/無効
            frequency (str, optional): 新しい頻度
            weekday (int, optional): 新しい曜日
            day_of_month (int, optional): 新しい日付
            custom_interval_days (int, optional): 新しい間隔日数
            estimated_minutes (int, optional): 新しい見積もり時間
            importance (str, optional): 新しい重要度
            urgency (str, optional): 新しい緊急度
            energy_level (str, optional): 新しいエネルギーレベル

        Returns:
            dict: recurring_task_id, title, is_active, message
        """
        return await update_recurring_task(
            user_id, recurring_repo, UpdateRecurringTaskInput(**input_data)
        )

    _tool.__name__ = "update_recurring_task"
    return FunctionTool(func=_tool)


def delete_recurring_task_tool(
    recurring_repo: IRecurringTaskRepository,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for deleting a recurring task definition."""

    async def _tool(input_data: dict) -> dict:
        """delete_recurring_task: 定期タスクの定義を削除します。既に生成されたタスクは残ります。

        Parameters:
            recurring_task_id (str): 定期タスク定義ID（必須）

        Returns:
            dict: message
        """
        return await delete_recurring_task(
            user_id, recurring_repo, DeleteRecurringTaskInput(**input_data)
        )

    _tool.__name__ = "delete_recurring_task"
    return FunctionTool(func=_tool)
