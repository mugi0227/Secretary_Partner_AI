"""
AgentTask repository interface.

Defines the contract for agent task (autonomous actions) persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.models.agent_task import AgentTask, AgentTaskCreate, AgentTaskUpdate
from app.models.enums import AgentTaskStatus


class IAgentTaskRepository(ABC):
    """Abstract interface for agent task persistence."""

    @abstractmethod
    async def create(self, user_id: str, task: AgentTaskCreate) -> AgentTask:
        """
        Create a new agent task.

        Args:
            user_id: Target user ID
            task: Agent task creation data

        Returns:
            Created agent task
        """
        pass

    @abstractmethod
    async def get(self, user_id: str, task_id: UUID) -> Optional[AgentTask]:
        """
        Get an agent task by ID.

        Args:
            user_id: Target user ID
            task_id: Agent task ID

        Returns:
            Agent task if found, None otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        user_id: str,
        status: Optional[AgentTaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentTask]:
        """
        List agent tasks with optional filters.

        Args:
            user_id: Target user ID
            status: Filter by status
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of agent tasks
        """
        pass

    @abstractmethod
    async def get_pending(
        self,
        user_id: str,
        before: datetime,
        limit: int = 10,
    ) -> list[AgentTask]:
        """
        Get pending agent tasks that should be executed.

        Args:
            user_id: Target user ID
            before: Get tasks with trigger_time before this time
            limit: Maximum number of tasks to return

        Returns:
            List of pending agent tasks ready for execution
        """
        pass

    @abstractmethod
    async def update(
        self, user_id: str, task_id: UUID, update: AgentTaskUpdate
    ) -> AgentTask:
        """
        Update an agent task.

        Args:
            user_id: Target user ID
            task_id: Agent task ID
            update: Fields to update

        Returns:
            Updated agent task
        """
        pass

    @abstractmethod
    async def mark_completed(self, task_id: UUID) -> AgentTask:
        """
        Mark an agent task as completed.

        Args:
            task_id: Agent task ID

        Returns:
            Updated agent task
        """
        pass

    @abstractmethod
    async def mark_failed(self, task_id: UUID, error: str) -> AgentTask:
        """
        Mark an agent task as failed and increment retry count.

        Args:
            task_id: Agent task ID
            error: Error message

        Returns:
            Updated agent task
        """
        pass

    @abstractmethod
    async def cancel(self, user_id: str, task_id: UUID) -> bool:
        """
        Cancel an agent task.

        Args:
            user_id: Target user ID
            task_id: Agent task ID

        Returns:
            True if cancelled, False if not found or already completed
        """
        pass
