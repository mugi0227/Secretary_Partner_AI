"""
Local file system storage provider.
"""

import os
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.exceptions import NotFoundError, InfrastructureError
from app.interfaces.storage_provider import IStorageProvider


class LocalStorageProvider(IStorageProvider):
    """
    Local file system storage implementation.

    Stores files in a local directory structure.
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize local storage provider.

        Args:
            base_path: Base directory for file storage (default: ./storage)
        """
        settings = get_settings()
        self.base_path = Path(base_path or "./storage")
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def upload(
        self,
        path: str,
        data: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload a file to local storage."""
        try:
            file_path = self.base_path / path
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "wb") as f:
                f.write(data)

            # Return local file path
            return str(file_path.absolute())

        except Exception as e:
            raise InfrastructureError(f"Failed to upload file: {e}")

    async def download(self, path: str) -> bytes:
        """Download a file from local storage."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                raise NotFoundError(f"File not found: {path}")

            with open(file_path, "rb") as f:
                return f.read()

        except NotFoundError:
            raise
        except Exception as e:
            raise InfrastructureError(f"Failed to download file: {e}")

    async def delete(self, path: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return False

            file_path.unlink()
            return True

        except Exception as e:
            raise InfrastructureError(f"Failed to delete file: {e}")

    async def exists(self, path: str) -> bool:
        """Check if a file exists."""
        file_path = self._resolve_path(path)
        return file_path.exists()

    def get_public_url(self, path: str) -> str:
        """
        Get a public URL for a file.

        For local storage, returns HTTP URL relative to BASE_URL.
        """
        settings = get_settings()
        return f"{settings.BASE_URL}/storage/{path}"

    def _resolve_path(self, path: str) -> Path:
        """Resolve path to absolute Path object."""
        # If path is already absolute (from upload), use it directly
        if Path(path).is_absolute():
            return Path(path)
        # Otherwise, resolve relative to base_path
        return self.base_path / path
