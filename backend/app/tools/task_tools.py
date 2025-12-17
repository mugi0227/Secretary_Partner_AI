"""
Task-related agent tools.

Tools for creating, updating, deleting, and searching tasks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.task_repository import ITaskRepository
from app.models.enums import CreatedBy, EnergyLevel, Priority
from app.models.task import Task, TaskCreate, TaskUpdate
from app.services.planner_service import PlannerService


# ===========================================
# Tool Input Models
# ===========================================


class CreateTaskInput(BaseModel):
    """Input for create_task tool."""

    title: str = Field(
        ...,
        description="タスクのタイトル",
        validation_alias="task_title",
        json_schema_extra={"examples": ["買い物リストを作る", "圏論の勉強"]}
    )
    description: Optional[str] = Field(None, description="タスクの詳細説明")
    project_id: Optional[str] = Field(None, description="プロジェクトID（UUID文字列）")
    importance: Priority = Field(Priority.MEDIUM, description="重要度 (HIGH/MEDIUM/LOW)")
    urgency: Priority = Field(Priority.MEDIUM, description="緊急度 (HIGH/MEDIUM/LOW)")
    energy_level: EnergyLevel = Field(
        EnergyLevel.LOW, description="必要エネルギー (HIGH=重い, LOW=軽い)"
    )
    estimated_minutes: Optional[int] = Field(None, ge=1, le=480, description="見積もり時間（分）")
    due_date: Optional[str] = Field(None, description="期限（ISO形式: YYYY-MM-DDTHH:MM:SS）")

    model_config = {"populate_by_name": True}


class UpdateTaskInput(BaseModel):
    """Input for update_task tool."""

    task_id: str = Field(..., description="タスクID（UUID文字列）")
    title: Optional[str] = Field(None, description="タスクのタイトル")
    description: Optional[str] = Field(None, description="タスクの詳細説明")
    status: Optional[str] = Field(None, description="ステータス (TODO/IN_PROGRESS/WAITING/DONE)")
    importance: Optional[Priority] = Field(None, description="重要度")
    urgency: Optional[Priority] = Field(None, description="緊急度")
    energy_level: Optional[EnergyLevel] = Field(None, description="必要エネルギー")


class DeleteTaskInput(BaseModel):
    """Input for delete_task tool."""

    task_id: str = Field(..., description="タスクID（UUID文字列）")


class SearchSimilarTasksInput(BaseModel):
    """Input for search_similar_tasks tool."""

    task_title: str = Field(
        ...,
        description="検索するタスクタイトル",
        json_schema_extra={"examples": ["買い物リストを作る", "圏論の勉強"]}
    )
    project_id: Optional[str] = Field(
        None,
        description="プロジェクトID（指定時はそのプロジェクト内のみ検索）"
    )


class BreakdownTaskInput(BaseModel):
    """Input for breakdown_task tool."""

    task_id: str = Field(..., description="分解するタスクのID（UUID文字列、必須）")
    create_subtasks: bool = Field(
        True,
        description="サブタスクを自動作成するか（True: 作成する、False: ステップ案のみ返す）"
    )


# ===========================================
# Tool Functions
# ===========================================


async def create_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: CreateTaskInput,
) -> dict:
    """
    Create a new task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task creation data

    Returns:
        Created task as dict
    """
    # Parse project_id if provided
    project_id = UUID(input_data.project_id) if input_data.project_id else None

    # Parse due_date if provided
    due_date = None
    if input_data.due_date:
        try:
            due_date = datetime.fromisoformat(input_data.due_date.replace("Z", "+00:00"))
        except ValueError:
            pass  # Invalid date format, ignore

    task_data = TaskCreate(
        title=input_data.title,
        description=input_data.description,
        project_id=project_id,
        importance=input_data.importance,
        urgency=input_data.urgency,
        energy_level=input_data.energy_level,
        estimated_minutes=input_data.estimated_minutes,
        due_date=due_date,
        created_by=CreatedBy.AGENT,
    )

    task = await repo.create(user_id, task_data)
    return task.model_dump(mode="json")  # Serialize UUIDs to strings


async def update_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: UpdateTaskInput,
) -> dict:
    """
    Update an existing task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task update data

    Returns:
        Updated task as dict
    """
    task_id = UUID(input_data.task_id)

    update_data = TaskUpdate(
        title=input_data.title,
        description=input_data.description,
        status=input_data.status,
        importance=input_data.importance,
        urgency=input_data.urgency,
        energy_level=input_data.energy_level,
    )

    task = await repo.update(user_id, task_id, update_data)
    return task.model_dump(mode="json")  # Serialize UUIDs to strings


async def delete_task(
    user_id: str,
    repo: ITaskRepository,
    input_data: DeleteTaskInput,
) -> dict:
    """
    Delete a task.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Task deletion data

    Returns:
        Deletion result
    """
    task_id = UUID(input_data.task_id)
    deleted = await repo.delete(user_id, task_id)

    return {
        "success": deleted,
        "task_id": input_data.task_id,
        "message": "Task deleted successfully" if deleted else "Task not found",
    }


async def search_similar_tasks(
    user_id: str,
    repo: ITaskRepository,
    input_data: SearchSimilarTasksInput,
) -> dict:
    """
    Search for similar tasks to avoid duplicates.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: Search parameters

    Returns:
        List of similar tasks with similarity scores
    """
    settings = get_settings()

    # Parse project_id safely - only if it's a valid UUID string
    project_id = None
    if input_data.project_id and input_data.project_id.strip():
        try:
            project_id = UUID(input_data.project_id)
        except (ValueError, AttributeError):
            # Invalid UUID format, ignore and search all projects
            pass

    similar = await repo.find_similar(
        user_id,
        title=input_data.task_title,
        project_id=project_id,
        threshold=settings.SIMILARITY_THRESHOLD,
        limit=5,
    )

    return {
        "similar_tasks": [
            {
                "task": task.task.model_dump(mode="json"),
                "similarity_score": task.similarity_score,
            }
            for task in similar
        ],
        "count": len(similar),
    }


# ===========================================
# ADK Tool Definitions
# ===========================================


def create_task_tool(repo: ITaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for creating tasks."""
    async def _tool(input_data: dict) -> dict:
        """create_task: 新しいタスクを作成します。作成前にsearch_similar_tasksで重複チェック推奨。

        Parameters:
            title (str): タスクのタイトル（必須）※task_titleでも可
            description (str, optional): タスクの詳細説明
            project_id (str, optional): プロジェクトID
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            energy_level (str, optional): 必要エネルギー (HIGH/LOW)、デフォルト: LOW
            estimated_minutes (int, optional): 見積もり時間（分）
            due_date (str, optional): 期限（ISO形式）

        Returns:
            dict: 作成されたタスク情報
        """
        return await create_task(user_id, repo, CreateTaskInput(**input_data))

    _tool.__name__ = "create_task"
    return FunctionTool(func=_tool)


def update_task_tool(repo: ITaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for updating tasks."""
    async def _tool(input_data: dict) -> dict:
        """update_task: 既存のタスクを更新します（タイトル、説明、ステータス等）。

        Parameters:
            task_id (str): タスクID（UUID文字列、必須）
            title (str, optional): タスクのタイトル
            description (str, optional): タスクの詳細説明
            status (str, optional): ステータス (TODO/IN_PROGRESS/WAITING/DONE)
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)
            energy_level (str, optional): 必要エネルギー (HIGH/LOW)

        Returns:
            dict: 更新されたタスク情報
        """
        return await update_task(user_id, repo, UpdateTaskInput(**input_data))

    _tool.__name__ = "update_task"
    return FunctionTool(func=_tool)


def delete_task_tool(repo: ITaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for deleting tasks."""
    async def _tool(input_data: dict) -> dict:
        """delete_task: タスクを削除します。

        Parameters:
            task_id (str): 削除するタスクのID（UUID文字列、必須）

        Returns:
            dict: 削除結果 (success, task_id, message)
        """
        return await delete_task(user_id, repo, DeleteTaskInput(**input_data))

    _tool.__name__ = "delete_task"
    return FunctionTool(func=_tool)


def search_similar_tasks_tool(repo: ITaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for searching similar tasks."""
    async def _tool(input_data: dict) -> dict:
        """search_similar_tasks: 類似タスクを検索して重複をチェックします。

        Parameters:
            task_title (str): 検索するタスクのタイトル（必須）
            project_id (str, optional): プロジェクトID（指定時はそのプロジェクト内のみ検索）

        Returns:
            dict: 類似タスクのリストとスコア
        """
        return await search_similar_tasks(user_id, repo, SearchSimilarTasksInput(**input_data))

    _tool.__name__ = "search_similar_tasks"
    return FunctionTool(func=_tool)


async def breakdown_task(
    user_id: str,
    task_repo: ITaskRepository,
    memory_repo: IMemoryRepository,
    llm_provider: ILLMProvider,
    input_data: BreakdownTaskInput,
) -> dict:
    """
    Break down a task into subtasks using Planner Agent.

    Args:
        user_id: User ID
        task_repo: Task repository
        memory_repo: Memory repository
        llm_provider: LLM provider
        input_data: Breakdown parameters

    Returns:
        Breakdown result with steps and subtask IDs
    """
    task_id = UUID(input_data.task_id)

    service = PlannerService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        memory_repo=memory_repo,
    )

    result = await service.breakdown_task(
        user_id=user_id,
        task_id=task_id,
        create_subtasks=input_data.create_subtasks,
    )

    return result.model_dump(mode="json")


def breakdown_task_tool(
    repo: ITaskRepository,
    memory_repo: IMemoryRepository,
    llm_provider: ILLMProvider,
    user_id: str,
) -> FunctionTool:
    """Create ADK tool for breaking down tasks into subtasks."""
    async def _tool(input_data: dict) -> dict:
        """breakdown_task: タスクを3-5個のサブタスクに分解します（Planner Agentを使用）。

        Parameters:
            task_id (str): 分解するタスクのID（UUID文字列、必須）
            create_subtasks (bool, optional): サブタスクを自動作成するか（デフォルト: True）

        Returns:
            dict: 分解結果（steps: ステップリスト、subtasks_created: サブタスク作成有無、subtask_ids: 作成されたサブタスクIDリスト、markdown_guide: Markdownガイド）
        """
        return await breakdown_task(
            user_id, repo, memory_repo, llm_provider, BreakdownTaskInput(**input_data)
        )

    _tool.__name__ = "breakdown_task"
    return FunctionTool(func=_tool)

