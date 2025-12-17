"""
OpenAI Whisper speech-to-text provider (local).

Note: Requires openai-whisper package (pip install openai-whisper)
"""

from typing import Optional
import tempfile
from pathlib import Path

from app.core.exceptions import InfrastructureError
from app.interfaces.speech_provider import ISpeechToTextProvider


class WhisperProvider(ISpeechToTextProvider):
    """
    OpenAI Whisper implementation for local speech-to-text.

    Uses the open-source Whisper model running locally.
    """

    def __init__(self, model_size: str = "base"):
        """
        Initialize Whisper provider.

        Args:
            model_size: Model size (tiny, base, small, medium, large)
        """
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        """Lazy load Whisper model."""
        if self._model is None:
            try:
                import whisper
                self._model = whisper.load_model(self.model_size)
            except ImportError:
                raise InfrastructureError(
                    "openai-whisper not installed. "
                    "Install with: pip install openai-whisper"
                )

    async def transcribe(
        self,
        audio_source: str,
        language: str = "ja",
    ) -> str:
        """
        Transcribe audio file to text.

        Args:
            audio_source: Path to audio file
            language: Language code (default: ja for Japanese)

        Returns:
            Transcribed text
        """
        self._load_model()

        try:
            # Whisper expects language code without country
            lang = language.split("-")[0]  # "ja-JP" -> "ja"

            result = self._model.transcribe(
                audio_source,
                language=lang,
                fp16=False,  # Disable FP16 for CPU compatibility
            )

            return result["text"].strip()

        except Exception as e:
            raise InfrastructureError(f"Whisper transcription failed: {e}")

    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/wav",
        language: str = "ja",
    ) -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data
            content_type: MIME type of audio
            language: Language code

        Returns:
            Transcribed text
        """
        self._load_model()

        # Determine file extension from content type
        ext_map = {
            "audio/wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/m4a": ".m4a",
            "audio/ogg": ".ogg",
        }
        ext = ext_map.get(content_type, ".wav")

        # Write to temporary file
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            # Transcribe temporary file
            result = await self.transcribe(tmp_path, language)
            return result
        finally:
            # Clean up temporary file
            Path(tmp_path).unlink(missing_ok=True)

    def get_supported_formats(self) -> list[str]:
        """Get list of supported audio formats."""
        return [
            "audio/wav",
            "audio/mp3",
            "audio/mpeg",
            "audio/m4a",
            "audio/ogg",
            "audio/flac",
        ]
