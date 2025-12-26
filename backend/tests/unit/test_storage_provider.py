"""
Unit tests for Storage Provider.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from app.infrastructure.local.storage_provider import LocalStorageProvider
from app.core.config import get_settings
from app.core.exceptions import NotFoundError


@pytest.fixture
def temp_storage():
    """Create temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    provider = LocalStorageProvider(base_path=temp_dir)
    yield provider
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_upload_file(temp_storage):
    """Test uploading a file."""
    data = b"Hello, World!"
    path = "test/file.txt"

    url = await temp_storage.upload(path, data)

    assert url is not None
    assert Path(url).exists()
    assert await temp_storage.exists(path)


@pytest.mark.asyncio
async def test_download_file(temp_storage):
    """Test downloading a file."""
    data = b"Test content"
    path = "test/download.txt"

    # Upload first
    await temp_storage.upload(path, data)

    # Download
    downloaded = await temp_storage.download(path)

    assert downloaded == data


@pytest.mark.asyncio
async def test_download_nonexistent_file(temp_storage):
    """Test downloading a file that doesn't exist."""
    with pytest.raises(NotFoundError):
        await temp_storage.download("nonexistent/file.txt")


@pytest.mark.asyncio
async def test_delete_file(temp_storage):
    """Test deleting a file."""
    data = b"To be deleted"
    path = "test/delete.txt"

    # Upload first
    await temp_storage.upload(path, data)
    assert await temp_storage.exists(path)

    # Delete
    deleted = await temp_storage.delete(path)

    assert deleted is True
    assert not await temp_storage.exists(path)


@pytest.mark.asyncio
async def test_delete_nonexistent_file(temp_storage):
    """Test deleting a file that doesn't exist."""
    deleted = await temp_storage.delete("nonexistent/file.txt")
    assert deleted is False


@pytest.mark.asyncio
async def test_get_public_url(temp_storage):
    """Test getting public URL."""
    data = b"Public file"
    path = "test/public.txt"

    url = await temp_storage.upload(path, data)
    public_url = temp_storage.get_public_url(path)

    settings = get_settings()
    assert public_url.startswith(settings.BASE_URL)
    assert "public.txt" in public_url
