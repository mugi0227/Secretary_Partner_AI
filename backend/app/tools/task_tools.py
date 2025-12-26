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
from app.interfaces.project_repository import IProjectRepository
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
    dependency_ids: list[str] = Field(
        default_factory=list,
        description="このタスクが依存する他のタスクのIDリスト（UUID文字列のリスト）"
    )

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


class ListTasksInput(BaseModel):
    """Input for list_tasks tool."""

    project_id: Optional[str] = Field(
        None,
        description="プロジェクトID（指定時はそのプロジェクト内のみ取得）"
    )
    status_filter: Optional[list[str]] = Field(
        None,
        description="ステータスフィルタ（例: ['TODO', 'IN_PROGRESS']）。指定なしで全ステータス取得"
    )
    limit: int = Field(
        50,
        ge=1,
        le=100,
        description="取得件数上限（デフォルト: 50、最大: 100）"
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

    # Parse dependency_ids if provided
    dependency_ids = []
    for dep_id_str in input_data.dependency_ids:
        try:
            dependency_ids.append(UUID(dep_id_str))
        except (ValueError, AttributeError):
            # Invalid UUID format, skip this dependency
            pass

    task_data = TaskCreate(
        title=input_data.title,
        description=input_data.description,
        project_id=project_id,
        importance=input_data.importance,
        urgency=input_data.urgency,
        energy_level=input_data.energy_level,
        estimated_minutes=input_data.estimated_minutes,
        due_date=due_date,
        dependency_ids=dependency_ids,
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


async def list_tasks(
    user_id: str,
    repo: ITaskRepository,
    input_data: ListTasksInput,
) -> dict:
    """
    List tasks with optional filters.

    Args:
        user_id: User ID
        repo: Task repository
        input_data: List parameters

    Returns:
        List of tasks matching the filters
    """
    # Parse project_id if provided
    project_id = None
    if input_data.project_id and input_data.project_id.strip():
        try:
            project_id = UUID(input_data.project_id)
        except (ValueError, AttributeError):
            # Invalid UUID format, ignore
            pass

    # Get tasks - we'll filter by status in Python since repo.list doesn't support multiple statuses
    all_tasks = await repo.list(
        user_id,
        project_id=project_id,
        parent_id=None,  # Only root tasks (not subtasks)
    )

    # Filter by status if specified
    if input_data.status_filter:
        status_set = set(s.upper() for s in input_data.status_filter)
        filtered_tasks = [t for t in all_tasks if t.status.value in status_set]
    else:
        filtered_tasks = all_tasks

    # Apply limit
    limited_tasks = filtered_tasks[:input_data.limit]

    return {
        "tasks": [task.model_dump(mode="json") for task in limited_tasks],
        "count": len(limited_tasks),
        "total_matching": len(filtered_tasks),
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

        **⚠️ 依存関係の設定（重要）**:
        タスク作成時には、以下の手順で依存関係を判断してください：
        1. list_tasks で同じプロジェクト内の未完了タスク（TODO/IN_PROGRESS）を取得
        2. 新しいタスクが既存タスクの完了を前提とする場合、dependency_ids に設定
        3. 例: 「確定申告書を提出する」を作る場合 → 「領収書を整理する」が未完了なら依存関係を設定
        4. 並行実行可能なタスク（関係ないタスク）には依存関係を設定しない

        Parameters:
            title (str): タスクのタイトル（必須）※task_titleでも可
            description (str, optional): タスクの詳細説明
            project_id (str, optional): プロジェクトID
            importance (str, optional): 重要度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            urgency (str, optional): 緊急度 (HIGH/MEDIUM/LOW)、デフォルト: MEDIUM
            energy_level (str, optional): 必要エネルギー (HIGH/LOW)、デフォルト: LOW
            estimated_minutes (int, optional): 見積もり時間（分）
            due_date (str, optional): 期限（ISO形式）
            dependency_ids (list[str], optional): このタスクが依存する他のタスクのIDリスト（UUID文字列）

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


def list_tasks_tool(repo: ITaskRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for listing tasks."""
    async def _tool(input_data: dict) -> dict:
        """list_tasks: タスク一覧を取得します（依存関係判断に利用）。

        Parameters:
            project_id (str, optional): プロジェクトID（指定時はそのプロジェクト内のみ取得）
            status_filter (list[str], optional): ステータスフィルタ（例: ["TODO", "IN_PROGRESS"]）
            limit (int, optional): 取得件数上限（デフォルト: 50、最大: 100）

        Returns:
            dict: タスク一覧（各タスクにはid, title, description, status, dependency_ids等を含む）
        """
        return await list_tasks(user_id, repo, ListTasksInput(**input_data))

    _tool.__name__ = "list_tasks"
    return FunctionTool(func=_tool)


async def breakdown_task(
    user_id: str,
    task_repo: ITaskRepository,
    memory_repo: IMemoryRepository,
    llm_provider: ILLMProvider,
    project_repo: Optional[IProjectRepository],
    input_data: BreakdownTaskInput,
) -> dict:
    """
    Break down a task into subtasks using Planner Agent.

    Args:
        user_id: User ID
        task_repo: Task repository
        memory_repo: Memory repository
        llm_provider: LLM provider
        project_repo: Project repository (optional)
        input_data: Breakdown parameters

    Returns:
        Breakdown result with steps and subtask IDs
    """
    task_id = UUID(input_data.task_id)

    service = PlannerService(
        llm_provider=llm_provider,
        task_repo=task_repo,
        memory_repo=memory_repo,
        project_repo=project_repo,
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
    project_repo: Optional[IProjectRepository] = None,
) -> FunctionTool:
    """Create ADK tool for breaking down tasks into subtasks."""
    async def _tool(input_data: dict) -> dict:
        """breakdown_task: タスクを3-5個のサブタスクに分解します（Planner Agentを使用）。

        タスクがプロジェクトに属している場合、プロジェクトの目標・重要ポイント・READMEを考慮して分解します。

        Parameters:
            task_id (str): 分解するタスクのID（UUID文字列、必須）
            create_subtasks (bool, optional): サブタスクを自動作成するか（デフォルト: True）

        Returns:
            dict: 分解結果（steps: ステップリスト、subtasks_created: サブタスク作成有無、subtask_ids: 作成されたサブタスクIDリスト、markdown_guide: Markdownガイド）
        """
        return await breakdown_task(
            user_id, repo, memory_repo, llm_provider, project_repo, BreakdownTaskInput(**input_data)
        )

    _tool.__name__ = "breakdown_task"
    return FunctionTool(func=_tool)

