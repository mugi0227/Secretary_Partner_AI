"""
Task repository interface.

Defines the contract for task persistence operations.
Implementations: SQLite, Firestore
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.models.task import Task, TaskCreate, TaskUpdate, SimilarTask


class ITaskRepository(ABC):
    """Abstract interface for task persistence."""

    @abstractmethod
    async def create(self, user_id: str, task: TaskCreate) -> Task:
        """
        Create a new task.

        Args:
            user_id: Owner user ID
            task: Task creation data

        Returns:
            Created task with generated ID and timestamps
        """
        pass

    @abstractmethod
    async def get(self, user_id: str, task_id: UUID) -> Optional[Task]:
        """
        Get a task by ID.

        Args:
            user_id: Owner user ID
            task_id: Task ID

        Returns:
            Task if found, None otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        user_id: str,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
        parent_id: Optional[UUID] = None,
        include_done: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Task]:
        """
        List tasks with optional filters.

        Args:
            user_id: Owner user ID
            project_id: Filter by project (None = Inbox)
            status: Filter by status
            parent_id: Filter by parent task (for subtasks)
            include_done: Include completed tasks
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of tasks matching filters
        """
        pass

    @abstractmethod
    async def update(self, user_id: str, task_id: UUID, update: TaskUpdate) -> Task:
        """
        Update an existing task.

        Args:
            user_id: Owner user ID
            task_id: Task ID to update
            update: Fields to update

        Returns:
            Updated task

        Raises:
            NotFoundError: If task not found
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str, task_id: UUID) -> bool:
        """
        Delete a task.

        Args:
            user_id: Owner user ID
            task_id: Task ID to delete

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def find_similar(
        self,
        user_id: str,
        title: str,
        project_id: UUID | None = None,
        threshold: float = 0.8,
        limit: int = 5,
    ) -> list[SimilarTask]:
        """
        Find similar tasks for duplicate detection.

        Args:
            user_id: Owner user ID
            title: Title to compare against
            project_id: Filter by project (None = search in Inbox only)
            threshold: Minimum similarity score (0.0 to 1.0)
            limit: Maximum number of results

        Returns:
            List of similar tasks with scores
        """
        pass

    @abstractmethod
    async def get_by_capture_id(self, user_id: str, capture_id: UUID) -> list[Task]:
        """
        Get tasks created from a specific capture.

        Args:
            user_id: Owner user ID
            capture_id: Source capture ID

        Returns:
            List of tasks created from this capture
        """
        pass

    @abstractmethod
    async def get_subtasks(self, user_id: str, parent_id: UUID) -> list[Task]:
        """
        Get all subtasks of a parent task.

        Args:
            user_id: Owner user ID
            parent_id: Parent task ID

        Returns:
            List of subtasks
        """
        pass

    @abstractmethod
    async def count(
        self,
        user_id: str,
        project_id: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        Count tasks matching filters.

        Args:
            user_id: Owner user ID
            project_id: Filter by project
            status: Filter by status

        Returns:
            Count of matching tasks
        """
        pass
