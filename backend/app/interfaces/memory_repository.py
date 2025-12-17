"""
Memory repository interface.

Defines the contract for memory (AI's knowledge) persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from app.models.memory import Memory, MemoryCreate, MemorySearchResult
from app.models.enums import MemoryScope, MemoryType


class IMemoryRepository(ABC):
    """Abstract interface for memory persistence."""

    @abstractmethod
    async def create(self, user_id: str, memory: MemoryCreate) -> Memory:
        """
        Create a new memory.

        Args:
            user_id: Owner user ID
            memory: Memory creation data

        Returns:
            Created memory
        """
        pass

    @abstractmethod
    async def get(self, user_id: str, memory_id: UUID) -> Optional[Memory]:
        """
        Get a memory by ID.

        Args:
            user_id: Owner user ID
            memory_id: Memory ID

        Returns:
            Memory if found, None otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        user_id: str,
        scope: Optional[MemoryScope] = None,
        memory_type: Optional[MemoryType] = None,
        project_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """
        List memories with optional filters.

        Args:
            user_id: Owner user ID
            scope: Filter by scope (USER/PROJECT/WORK)
            memory_type: Filter by type
            project_id: Filter by project
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of memories
        """
        pass

    @abstractmethod
    async def search(
        self,
        user_id: str,
        query: str,
        scope: Optional[MemoryScope] = None,
        project_id: Optional[UUID] = None,
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        """
        Search memories by content.

        For simple implementations, uses keyword matching.
        For advanced implementations, uses vector similarity.

        Args:
            user_id: Owner user ID
            query: Search query
            scope: Filter by scope
            project_id: Filter by project
            limit: Maximum number of results

        Returns:
            List of memories with relevance scores
        """
        pass

    @abstractmethod
    async def search_work_memory(
        self,
        user_id: str,
        query: str,
        limit: int = 3,
    ) -> list[MemorySearchResult]:
        """
        Search work memories (procedures, rules) specifically.

        Used by Planner Agent for task breakdown.

        Args:
            user_id: Owner user ID
            query: Search query
            limit: Maximum number of results

        Returns:
            List of work memories with relevance scores
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str, memory_id: UUID) -> bool:
        """
        Delete a memory.

        Args:
            user_id: Owner user ID
            memory_id: Memory ID

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def get_user_memories(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
    ) -> list[Memory]:
        """
        Get all user-scope memories.

        Convenience method for loading user profile context.

        Args:
            user_id: Owner user ID
            memory_type: Optional filter by type (FACT/PREFERENCE/PATTERN)

        Returns:
            List of user memories
        """
        pass
