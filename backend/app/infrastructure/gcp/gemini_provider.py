"""
Vertex AI provider for GCP environment.

Uses Vertex AI (requires GCP project and service account).
"""

from app.core.config import get_settings
from app.interfaces.llm_provider import ILLMProvider


class VertexAIProvider(ILLMProvider):
    """Vertex AI provider for GCP environment (requires service account)."""

    def __init__(self, model_name: str):
        """
        Initialize Vertex AI provider.

        Args:
            model_name: Gemini model name (e.g., "gemini-2.0-flash")
        """
        self._model_name = model_name
        self._settings = get_settings()

        if not self._settings.GOOGLE_CLOUD_PROJECT:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is required for Vertex AI provider"
            )

        if not self._settings.GOOGLE_APPLICATION_CREDENTIALS:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS is required for Vertex AI provider"
            )

    def get_model(self) -> str:
        """
        Get Vertex AI model name for ADK.

        ADK will use GOOGLE_APPLICATION_CREDENTIALS automatically.

        Returns:
            Model name string (Vertex AI format)
        """
        # Vertex AI uses format: projects/{project}/locations/{location}/publishers/google/models/{model}
        # But ADK might handle this automatically, so return model name for now
        return self._model_name

    def get_model_name(self) -> str:
        """Get human-readable model name."""
        return f"Vertex AI ({self._model_name})"

    def supports_vision(self) -> bool:
        """Gemini models support vision."""
        return True

    def supports_function_calling(self) -> bool:
        """Gemini models support function calling."""
        return True

