"""
Speech-to-Text provider interface.

Defines the contract for speech recognition services.
Implementations: Google Cloud Speech, Whisper
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class ISpeechToTextProvider(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    async def transcribe(
        self,
        audio_source: str,
        language: str = "ja-JP",
    ) -> str:
        """
        Transcribe audio to text.

        Args:
            audio_source: Audio file path or URL
            language: Language code (default: Japanese)

        Returns:
            Transcribed text

        Raises:
            InfrastructureError: If transcription fails
        """
        pass

    @abstractmethod
    async def transcribe_bytes(
        self,
        audio_bytes: bytes,
        content_type: str = "audio/wav",
        language: str = "ja-JP",
    ) -> str:
        """
        Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data
            content_type: MIME type of audio
            language: Language code

        Returns:
            Transcribed text

        Raises:
            InfrastructureError: If transcription fails
        """
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """
        Get list of supported audio formats.

        Returns:
            List of MIME types (e.g., ["audio/wav", "audio/mp3"])
        """
        pass
