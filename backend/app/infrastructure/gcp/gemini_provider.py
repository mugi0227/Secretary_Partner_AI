"""
Vertex AI provider for GCP environment.

Uses Vertex AI with Application Default Credentials.
"""

from app.core.config import get_settings
from app.interfaces.llm_provider import ILLMProvider


class VertexAIProvider(ILLMProvider):
    """Vertex AI provider for GCP environment."""

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

    def get_model_id(self) -> str:
        """Get raw model identifier for API/cost lookups."""
        return self._model_name

    def supports_vision(self) -> bool:
        """Gemini models support vision."""
        return True

    def supports_function_calling(self) -> bool:
        """Gemini models support function calling."""
        return True

    def get_available_models(self) -> list[str]:
        """Return models from AVAILABLE_MODELS config, or default model."""
        models = self._settings.available_models
        if not models:
            return [self._model_name]
        if self._model_name not in models:
            return [self._model_name] + models
        return models

    def with_model(self, model_id: str) -> "VertexAIProvider":
        """Create a new provider with a different model name."""
        if model_id == self._model_name:
            return self
        return VertexAIProvider(model_name=model_id)

