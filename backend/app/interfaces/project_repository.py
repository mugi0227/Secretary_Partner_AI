"""
Project repository interface.

Defines the contract for project persistence operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from app.models.project import Project, ProjectCreate, ProjectUpdate, ProjectWithTaskCount


class IProjectRepository(ABC):
    """Abstract interface for project persistence."""

    @abstractmethod
    async def create(self, user_id: str, project: ProjectCreate) -> Project:
        """
        Create a new project.

        Args:
            user_id: Owner user ID
            project: Project creation data

        Returns:
            Created project
        """
        pass

    @abstractmethod
    async def get(self, user_id: str, project_id: UUID) -> Optional[Project]:
        """
        Get a project by ID.

        Args:
            user_id: Owner user ID
            project_id: Project ID

        Returns:
            Project if found, None otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        """
        List projects with optional filters.

        Args:
            user_id: Owner user ID
            status: Filter by status
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of projects
        """
        pass

    @abstractmethod
    async def list_with_task_count(
        self,
        user_id: str,
        status: Optional[str] = None,
    ) -> list[ProjectWithTaskCount]:
        """
        List projects with task statistics.

        Args:
            user_id: Owner user ID
            status: Filter by status

        Returns:
            List of projects with task counts
        """
        pass

    @abstractmethod
    async def update(
        self, user_id: str, project_id: UUID, update: ProjectUpdate
    ) -> Project:
        """
        Update an existing project.

        Args:
            user_id: Owner user ID
            project_id: Project ID
            update: Fields to update

        Returns:
            Updated project

        Raises:
            NotFoundError: If project not found
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str, project_id: UUID) -> bool:
        """
        Delete a project.

        Args:
            user_id: Owner user ID
            project_id: Project ID

        Returns:
            True if deleted, False if not found
        """
        pass
