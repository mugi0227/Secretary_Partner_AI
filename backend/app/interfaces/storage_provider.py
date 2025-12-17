"""
Storage provider interface.

Defines the contract for file storage services.
Implementations: Local file system, Google Cloud Storage, S3
"""

from abc import ABC, abstractmethod
from typing import Optional


class IStorageProvider(ABC):
    """Abstract interface for file storage providers."""

    @abstractmethod
    async def upload(
        self,
        path: str,
        data: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a file.

        Args:
            path: Destination path (e.g., "captures/user1/audio.wav")
            data: File content bytes
            content_type: Optional MIME type

        Returns:
            URL or path to access the uploaded file

        Raises:
            InfrastructureError: If upload fails
        """
        pass

    @abstractmethod
    async def download(self, path: str) -> bytes:
        """
        Download a file.

        Args:
            path: File path or URL

        Returns:
            File content bytes

        Raises:
            NotFoundError: If file not found
            InfrastructureError: If download fails
        """
        pass

    @abstractmethod
    async def delete(self, path: str) -> bool:
        """
        Delete a file.

        Args:
            path: File path or URL

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if a file exists.

        Args:
            path: File path or URL

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    def get_public_url(self, path: str) -> str:
        """
        Get a public URL for a file.

        Args:
            path: File path

        Returns:
            Public URL to access the file
        """
        pass
