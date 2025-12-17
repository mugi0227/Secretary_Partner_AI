"""
Unit tests for Capture Repository.
"""

import pytest
from uuid import uuid4

from app.infrastructure.local.database import get_session_factory, init_db
from app.infrastructure.local.capture_repository import SqliteCaptureRepository
from app.models.capture import CaptureCreate
from app.models.enums import ContentType


@pytest.fixture
async def capture_repo():
    """Create in-memory capture repository."""
    # Use in-memory SQLite
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.infrastructure.local.database import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    repo = SqliteCaptureRepository(session_factory)

    yield repo

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_text_capture(capture_repo):
    """Test creating a text capture."""
    user_id = "test_user"
    capture = CaptureCreate(
        content_type=ContentType.TEXT,
        raw_text="テストテキスト",
    )

    result = await capture_repo.create(user_id, capture)

    assert result.id is not None
    assert result.user_id == user_id
    assert result.content_type == ContentType.TEXT
    assert result.raw_text == "テストテキスト"
    assert result.processed is False


@pytest.mark.asyncio
async def test_create_audio_capture(capture_repo):
    """Test creating an audio capture."""
    user_id = "test_user"
    capture = CaptureCreate(
        content_type=ContentType.AUDIO,
        content_url="file:///path/to/audio.wav",
        transcription="音声のテキスト",
    )

    result = await capture_repo.create(user_id, capture)

    assert result.content_type == ContentType.AUDIO
    assert result.content_url == "file:///path/to/audio.wav"
    assert result.transcription == "音声のテキスト"


@pytest.mark.asyncio
async def test_get_capture(capture_repo):
    """Test getting a capture by ID."""
    user_id = "test_user"
    capture = CaptureCreate(
        content_type=ContentType.TEXT,
        raw_text="取得テスト",
    )

    created = await capture_repo.create(user_id, capture)
    retrieved = await capture_repo.get(user_id, created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.raw_text == "取得テスト"


@pytest.mark.asyncio
async def test_list_captures(capture_repo):
    """Test listing captures."""
    user_id = "test_user"

    # Create multiple captures
    for i in range(3):
        await capture_repo.create(
            user_id,
            CaptureCreate(
                content_type=ContentType.TEXT,
                raw_text=f"Capture {i}",
            ),
        )

    captures = await capture_repo.list(user_id)

    assert len(captures) == 3


@pytest.mark.asyncio
async def test_mark_processed(capture_repo):
    """Test marking a capture as processed."""
    user_id = "test_user"
    capture = CaptureCreate(
        content_type=ContentType.TEXT,
        raw_text="処理テスト",
    )

    created = await capture_repo.create(user_id, capture)
    assert created.processed is False

    marked = await capture_repo.mark_processed(user_id, created.id)

    assert marked.processed is True


@pytest.mark.asyncio
async def test_delete_capture(capture_repo):
    """Test deleting a capture."""
    user_id = "test_user"
    capture = CaptureCreate(
        content_type=ContentType.TEXT,
        raw_text="削除テスト",
    )

    created = await capture_repo.create(user_id, capture)
    deleted = await capture_repo.delete(user_id, created.id)

    assert deleted is True

    # Verify it's gone
    retrieved = await capture_repo.get(user_id, created.id)
    assert retrieved is None


@pytest.mark.asyncio
async def test_text_content_property():
    """Test Capture.text_content property."""
    from app.models.capture import Capture
    from datetime import datetime

    # Text capture
    text_capture = Capture(
        id=uuid4(),
        user_id="test",
        content_type=ContentType.TEXT,
        raw_text="テキスト",
        created_at=datetime.now(),
    )
    assert text_capture.text_content == "テキスト"

    # Audio capture
    audio_capture = Capture(
        id=uuid4(),
        user_id="test",
        content_type=ContentType.AUDIO,
        transcription="音声文字起こし",
        created_at=datetime.now(),
    )
    assert audio_capture.text_content == "音声文字起こし"

    # Image capture
    image_capture = Capture(
        id=uuid4(),
        user_id="test",
        content_type=ContentType.IMAGE,
        image_analysis="画像解析結果",
        created_at=datetime.now(),
    )
    assert image_capture.text_content == "画像解析結果"
