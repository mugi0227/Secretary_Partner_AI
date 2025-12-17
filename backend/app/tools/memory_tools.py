"""
Memory-related agent tools.

Tools for searching and adding memories (user facts, work procedures, etc.).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from app.interfaces.memory_repository import IMemoryRepository
from app.models.enums import MemoryScope, MemoryType
from app.models.memory import MemoryCreate


# ===========================================
# Tool Input Models
# ===========================================


class SearchWorkMemoryInput(BaseModel):
    """Input for search_work_memory tool."""

    query: str = Field(..., description="検索クエリ（手順やルールを探す）")
    limit: int = Field(3, ge=1, le=10, description="最大結果数")


class AddToMemoryInput(BaseModel):
    """Input for add_to_memory tool."""

    content: str = Field(..., description="記憶する内容（ユーザーの名前、好み、事実など）")
    scope: MemoryScope = Field(
        MemoryScope.USER,
        description="記憶スコープ: USER(ユーザー個人), PROJECT(プロジェクト), WORK(仕事手順)"
    )
    memory_type: MemoryType = Field(
        MemoryType.FACT,
        description="記憶タイプ: FACT(事実), PREFERENCE(好み), PATTERN(傾向), RULE(ルール)"
    )
    project_id: Optional[str] = Field(None, description="プロジェクトID（PROJECT scopeの場合）")
    tags: list[str] = Field(default_factory=list, description="検索用タグ")


# ===========================================
# Tool Functions
# ===========================================


async def search_work_memory(
    user_id: str,
    repo: IMemoryRepository,
    input_data: SearchWorkMemoryInput,
) -> dict:
    """
    Search work memories (procedures, rules).

    Args:
        user_id: User ID
        repo: Memory repository
        input_data: Search parameters

    Returns:
        List of work memories with relevance scores
    """
    results = await repo.search_work_memory(
        user_id,
        query=input_data.query,
        limit=input_data.limit,
    )

    return {
        "memories": [
            {
                "memory": result.memory.model_dump(mode="json"),
                "relevance_score": result.relevance_score,
            }
            for result in results
        ],
        "count": len(results),
    }


async def add_to_memory(
    user_id: str,
    repo: IMemoryRepository,
    input_data: AddToMemoryInput,
) -> dict:
    """
    Add a new memory (user fact, preference, work procedure, etc.).

    Args:
        user_id: User ID
        repo: Memory repository
        input_data: Memory data

    Returns:
        Created memory as dict
    """
    project_id = UUID(input_data.project_id) if input_data.project_id else None

    memory_data = MemoryCreate(
        content=input_data.content,
        scope=input_data.scope,
        memory_type=input_data.memory_type,
        project_id=project_id,
        tags=input_data.tags,
        source="agent",
    )

    memory = await repo.create(user_id, memory_data)
    return memory.model_dump(mode="json")  # Serialize UUIDs to strings


# ===========================================
# ADK Tool Definitions
# ===========================================


def search_work_memory_tool(repo: IMemoryRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for searching work memories."""
    async def _tool(input_data: dict) -> dict:
        """search_work_memory: 仕事の手順やルール（WorkMemory）を検索します。

        Parameters:
            query (str): 検索クエリ（手順やルールを探す文字列、必須）
            limit (int, optional): 最大結果数（1〜10、デフォルト: 3）

        Returns:
            dict: 検索結果 (memories: リスト, count: 件数)
        """
        return await search_work_memory(user_id, repo, SearchWorkMemoryInput(**input_data))

    _tool.__name__ = "search_work_memory"
    return FunctionTool(func=_tool)


def add_to_memory_tool(repo: IMemoryRepository, user_id: str) -> FunctionTool:
    """Create ADK tool for adding memories."""
    async def _tool(input_data: dict) -> dict:
        """add_to_memory: 記憶（User/Project/Work）を追加します。

        Parameters:
            content (str): 記憶する内容（ユーザーの名前、好み、事実など、必須）
            scope (str, optional): 記憶スコープ (USER/PROJECT/WORK)、デフォルト: USER
            memory_type (str, optional): 記憶タイプ (FACT/PREFERENCE/PATTERN/RULE)、デフォルト: FACT
            project_id (str, optional): プロジェクトID（PROJECT scopeの場合に指定）
            tags (list[str], optional): 検索用タグのリスト

        Returns:
            dict: 作成された記憶情報
        """
        return await add_to_memory(user_id, repo, AddToMemoryInput(**input_data))

    _tool.__name__ = "add_to_memory"
    return FunctionTool(func=_tool)

