"""
LiteLLM provider implementation for local development.

Supports Bedrock, OpenAI, and other providers via LiteLLM.
"""

from typing import Any

from litellm import LiteLLM

from app.core.config import get_settings
from app.interfaces.llm_provider import ILLMProvider


class LiteLLMProvider(ILLMProvider):
    """LiteLLM provider for local environment."""

    def __init__(self, model_name: str):
        """
        Initialize LiteLLM provider.

        Args:
            model_name: LiteLLM model identifier (e.g., "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0")
        """
        self._model_name = model_name
        self._settings = get_settings()
        self._litellm = LiteLLM(model=model_name)

    def get_model(self) -> LiteLLM:
        """
        Get LiteLLM instance for ADK.

        Returns:
            LiteLLM wrapper instance
        """
        return self._litellm

    def get_model_name(self) -> str:
        """Get human-readable model name."""
        return f"LiteLLM ({self._model_name})"

    def supports_vision(self) -> bool:
        """
        Check if model supports vision.

        Most modern models via LiteLLM support vision.
        """
        # Claude 3.5 and GPT-4o support vision
        vision_models = ["claude-3", "gpt-4o", "gpt-4-vision"]
        return any(vm in self._model_name.lower() for vm in vision_models)

    def supports_function_calling(self) -> bool:
        """
        Check if model supports function calling.

        Most modern models via LiteLLM support function calling.
        """
        return True

