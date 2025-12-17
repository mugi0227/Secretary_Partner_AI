"""
Integration tests for CaptureService.

Note: Whisper tests are skipped by default as they require the model download.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import tempfile
import shutil

from app.services.capture_service import CaptureService
from app.infrastructure.local.capture_repository import SqliteCaptureRepository
from app.infrastructure.local.storage_provider import LocalStorageProvider
from app.models.enums import ContentType


@pytest.fixture
async def capture_repo():
    """Create in-memory capture repository."""
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


@pytest.fixture
def temp_storage():
    """Create temporary storage provider."""
    temp_dir = tempfile.mkdtemp()
    provider = LocalStorageProvider(base_path=temp_dir)
    yield provider
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_speech_provider():
    """Create mock speech provider."""
    mock = AsyncMock()
    mock.transcribe_bytes.return_value = "これは音声のテストです"
    mock.get_supported_formats.return_value = ["audio/wav", "audio/mp3"]
    return mock


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    mock = MagicMock()
    mock.supports_vision.return_value = False
    return mock


@pytest.fixture
async def capture_service(capture_repo, temp_storage, mock_speech_provider, mock_llm_provider):
    """Create CaptureService with mocked dependencies."""
    return CaptureService(
        capture_repo=capture_repo,
        storage=temp_storage,
        speech=mock_speech_provider,
        llm=mock_llm_provider,
    )


@pytest.mark.asyncio
async def test_process_text(capture_service):
    """Test processing text input."""
    user_id = "test_user"
    text = "確定申告の準備をしなければ"

    capture = await capture_service.process_text(user_id, text)

    assert capture.id is not None
    assert capture.content_type == ContentType.TEXT
    assert capture.raw_text == text
    assert capture.processed is False


@pytest.mark.asyncio
async def test_process_audio(capture_service, mock_speech_provider):
    """Test processing audio input."""
    user_id = "test_user"
    audio_bytes = b"fake_audio_data"

    capture = await capture_service.process_audio(user_id, audio_bytes)

    assert capture.id is not None
    assert capture.content_type == ContentType.AUDIO
    assert capture.content_url is not None
    assert capture.transcription == "これは音声のテストです"

    # Verify speech provider was called
    mock_speech_provider.transcribe_bytes.assert_called_once()


@pytest.mark.asyncio
async def test_process_image(capture_service):
    """Test processing image input."""
    user_id = "test_user"
    image_bytes = b"fake_image_data"

    capture = await capture_service.process_image(user_id, image_bytes)

    assert capture.id is not None
    assert capture.content_type == ContentType.IMAGE
    assert capture.content_url is not None


@pytest.mark.asyncio
async def test_get_capture_text(capture_service):
    """Test getting text from various capture types."""
    user_id = "test_user"

    # Text capture
    text_capture = await capture_service.process_text(user_id, "テキスト")
    text_content = await capture_service.get_capture_text(text_capture)
    assert text_content == "テキスト"

    # Audio capture
    audio_capture = await capture_service.process_audio(user_id, b"audio")
    audio_text = await capture_service.get_capture_text(audio_capture)
    assert audio_text == "これは音声のテストです"


@pytest.mark.asyncio
@pytest.mark.skipif(True, reason="Requires Whisper model download")
async def test_process_audio_with_real_whisper(capture_repo, temp_storage):
    """
    Test with real Whisper provider.

    Skipped by default - requires openai-whisper package and model download.
    Run with: pytest -k test_process_audio_with_real_whisper -v
    """
    from app.infrastructure.local.whisper_provider import WhisperProvider
    from app.infrastructure.local.litellm_provider import LiteLLMProvider

    speech = WhisperProvider("tiny")
    llm = LiteLLMProvider("gemini/gemini-2.0-flash")

    service = CaptureService(
        capture_repo=capture_repo,
        storage=temp_storage,
        speech=speech,
        llm=llm,
    )

    # Would need actual audio file bytes here
    # capture = await service.process_audio("test_user", audio_bytes)
    # assert capture.transcription is not None
