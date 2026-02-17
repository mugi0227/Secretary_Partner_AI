"""
Project link request repository interface.

Defines the contract for project link request persistence operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from app.models.project_link import ProjectLinkRequest, ProjectLinkRequestCreate


class IProjectLinkRequestRepository(ABC):
    """Abstract interface for project link request persistence."""

    @abstractmethod
    async def create(
        self, request: ProjectLinkRequestCreate, requested_by: str
    ) -> ProjectLinkRequest:
        pass

    @abstractmethod
    async def get(self, request_id: UUID) -> Optional[ProjectLinkRequest]:
        pass

    @abstractmethod
    async def list_by_parent(
        self, parent_project_id: UUID, status: Optional[str] = None
    ) -> list[ProjectLinkRequest]:
        pass

    @abstractmethod
    async def approve(self, request_id: UUID) -> ProjectLinkRequest:
        pass

    @abstractmethod
    async def reject(self, request_id: UUID) -> ProjectLinkRequest:
        pass
