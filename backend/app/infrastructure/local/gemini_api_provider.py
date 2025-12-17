"""
Gemini API provider for local development.

Uses Gemini API with API Key (no GCP project required).
"""

from app.core.config import get_settings
from app.interfaces.llm_provider import ILLMProvider


class GeminiAPIProvider(ILLMProvider):
    """Gemini API provider using API Key (works in local/gcp)."""

    def __init__(self, model_name: str):
        """
        Initialize Gemini API provider.

        Args:
            model_name: Gemini model name (e.g., "gemini-2.0-flash")
        """
        self._model_name = model_name
        self._settings = get_settings()

        if not self._settings.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is required for Gemini API provider. "
                "Get your API key from https://aistudio.google.com/apikey"
            )

    def get_model(self) -> str:
        """
        Get Gemini model name for ADK.

        ADK will use GOOGLE_API_KEY environment variable automatically.

        Returns:
            Model name string
        """
        return self._model_name

    def get_model_name(self) -> str:
        """Get human-readable model name."""
        return f"Gemini API ({self._model_name})"

    def supports_vision(self) -> bool:
        """Gemini models support vision."""
        return True

    def supports_function_calling(self) -> bool:
        """Gemini models support function calling."""
        return True

