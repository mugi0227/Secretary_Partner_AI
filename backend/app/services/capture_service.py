"""
Capture service for processing audio/image/text inputs.

Orchestrates Speech-to-Text, Vision, and Storage providers.
"""

from uuid import uuid4

from app.core.exceptions import InfrastructureError
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.speech_provider import ISpeechToTextProvider
from app.interfaces.storage_provider import IStorageProvider
from app.interfaces.llm_provider import ILLMProvider
from app.models.capture import Capture, CaptureCreate
from app.models.enums import ContentType


class CaptureService:
    """
    Service for processing captures (audio, image, text).

    Handles:
    - Audio transcription via Speech-to-Text
    - Image analysis via Vision API
    - File storage
    - Capture persistence
    """

    def __init__(
        self,
        capture_repo: ICaptureRepository,
        storage: IStorageProvider,
        speech: ISpeechToTextProvider,
        llm: ILLMProvider,
    ):
        self.capture_repo = capture_repo
        self.storage = storage
        self.speech = speech
        self.llm = llm

    async def process_text(self, user_id: str, text: str) -> Capture:
        """
        Process text input.

        Args:
            user_id: User ID
            text: Text content

        Returns:
            Created capture
        """
        capture = CaptureCreate(
            content_type=ContentType.TEXT,
            raw_text=text,
        )
        return await self.capture_repo.create(user_id=user_id, capture=capture)

    async def process_audio(
        self,
        user_id: str,
        audio_bytes: bytes,
        content_type: str = "audio/wav",
    ) -> Capture:
        """
        Process audio input.

        Steps:
        1. Upload audio to storage
        2. Transcribe with Speech-to-Text
        3. Create capture record

        Args:
            user_id: User ID
            audio_bytes: Audio file bytes
            content_type: MIME type

        Returns:
            Created capture with transcription
        """
        # Upload to storage
        storage_path = f"captures/{user_id}/audio/{uuid4()}.wav"
        content_url = await self.storage.upload(
            path=storage_path,
            data=audio_bytes,
            content_type=content_type,
        )

        # Transcribe
        try:
            transcription = await self.speech.transcribe_bytes(
                audio_bytes=audio_bytes,
                content_type=content_type,
                language="ja-JP",
            )
        except Exception as e:
            raise InfrastructureError(f"Speech-to-text failed: {e}")

        # Create capture
        capture = CaptureCreate(
            content_type=ContentType.AUDIO,
            content_url=content_url,
            transcription=transcription,
        )
        return await self.capture_repo.create(user_id=user_id, capture=capture)

    async def process_image(
        self,
        user_id: str,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
    ) -> Capture:
        """
        Process image input.

        Steps:
        1. Upload image to storage
        2. Analyze with Vision API (if supported by LLM)
        3. Create capture record

        Args:
            user_id: User ID
            image_bytes: Image file bytes
            content_type: MIME type

        Returns:
            Created capture with analysis
        """
        # Upload to storage
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        ext = ext_map.get(content_type, ".jpg")
        storage_path = f"captures/{user_id}/images/{uuid4()}{ext}"
        content_url = await self.storage.upload(
            path=storage_path,
            data=image_bytes,
            content_type=content_type,
        )

        # Analyze image (if Vision supported)
        analysis = ""
        if self.llm.supports_vision():
            try:
                # TODO: Implement vision analysis via LLM
                # This would require calling the LLM with the image
                analysis = "Image analysis not yet implemented"
            except Exception as e:
                analysis = f"Image analysis failed: {e}"

        # Create capture
        capture = CaptureCreate(
            content_type=ContentType.IMAGE,
            content_url=content_url,
            image_analysis=analysis,
        )
        return await self.capture_repo.create(user_id=user_id, capture=capture)

    async def get_capture_text(self, capture: Capture) -> str:
        """
        Get the text content from a capture regardless of type.

        Args:
            capture: Capture object

        Returns:
            Text content (raw_text, transcription, or image_analysis)
        """
        return capture.text_content
