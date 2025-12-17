"""
Capture repository interface.

Defines the contract for capture (input log) persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from uuid import UUID

from app.models.capture import Capture, CaptureCreate


class ICaptureRepository(ABC):
    """Abstract interface for capture persistence."""

    @abstractmethod
    async def create(self, user_id: str, capture: CaptureCreate) -> Capture:
        """
        Create a new capture.

        Args:
            user_id: Owner user ID
            capture: Capture creation data

        Returns:
            Created capture
        """
        pass

    @abstractmethod
    async def get(self, user_id: str, capture_id: UUID) -> Optional[Capture]:
        """
        Get a capture by ID.

        Args:
            user_id: Owner user ID
            capture_id: Capture ID

        Returns:
            Capture if found, None otherwise
        """
        pass

    @abstractmethod
    async def list(
        self,
        user_id: str,
        processed: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Capture]:
        """
        List captures with optional filters.

        Args:
            user_id: Owner user ID
            processed: Filter by processed status
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of captures
        """
        pass

    @abstractmethod
    async def mark_processed(self, user_id: str, capture_id: UUID) -> Capture:
        """
        Mark a capture as processed.

        Args:
            user_id: Owner user ID
            capture_id: Capture ID

        Returns:
            Updated capture

        Raises:
            NotFoundError: If capture not found
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str, capture_id: UUID) -> bool:
        """
        Delete a capture.

        Args:
            user_id: Owner user ID
            capture_id: Capture ID

        Returns:
            True if deleted, False if not found
        """
        pass
