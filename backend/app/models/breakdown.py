"""
Task breakdown model definitions.

Models for Planner Agent output validation.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import EnergyLevel


class BreakdownStep(BaseModel):
    """A single step in a task breakdown (3-5 steps total)."""

    step_number: int = Field(..., ge=1, le=10, description="ステップ番号")
    title: str = Field(..., min_length=1, max_length=200, description="ステップのタイトル")
    description: Optional[str] = Field(None, max_length=500, description="このステップで達成すること")
    estimated_minutes: int = Field(30, ge=15, le=120, description="見積もり時間（分）")
    energy_level: EnergyLevel = Field(EnergyLevel.LOW, description="必要エネルギー")
    guide: str = Field(
        "",
        max_length=2000,
        description="詳細な進め方ガイド（Markdown形式、サブステップの代わり）",
    )
    dependency_step_numbers: list[int] = Field(
        default_factory=list,
        description="このステップが依存する先行ステップの番号リスト（DAG形成）",
    )


class TaskBreakdown(BaseModel):
    """Complete task breakdown result."""

    original_task_id: UUID = Field(..., description="元タスクのID")
    original_task_title: str = Field(..., description="元タスクのタイトル")
    steps: list[BreakdownStep] = Field(
        ..., min_length=3, max_length=5, description="分解されたステップリスト（3-5個）"
    )
    total_estimated_minutes: int = Field(..., ge=1, description="合計見積もり時間（分）")
    work_memory_used: list[str] = Field(
        default_factory=list, description="参照したWorkMemoryの内容"
    )


class BreakdownRequest(BaseModel):
    """Request model for task breakdown endpoint."""

    create_subtasks: bool = Field(
        False, description="分解結果をサブタスクとして作成するか（デフォルト: False）"
    )


class BreakdownResponse(BaseModel):
    """Response model for task breakdown endpoint."""

    breakdown: TaskBreakdown = Field(..., description="分解結果")
    subtasks_created: bool = Field(False, description="サブタスクが作成されたか")
    subtask_ids: list[UUID] = Field(
        default_factory=list, description="作成されたサブタスクのID"
    )
    markdown_guide: str = Field("", description="Markdown形式の実行ガイド")

