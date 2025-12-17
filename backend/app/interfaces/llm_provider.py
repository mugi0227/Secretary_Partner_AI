"""
LLM provider interface.

Defines the contract for LLM (Large Language Model) access.
Implementations: Gemini, LiteLLM (for Bedrock, OpenAI, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Union


class ILLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def get_model(self) -> Union[str, Any]:
        """
        Get the model instance or identifier for ADK.

        For Gemini: Returns model name string (e.g., "gemini-2.0-flash")
        For LiteLLM: Returns LiteLlm wrapper instance

        Returns:
            Model identifier or instance compatible with ADK
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the human-readable model name.

        Returns:
            Model name string for logging/display
        """
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """
        Check if the model supports vision (image) inputs.

        Returns:
            True if vision is supported
        """
        pass

    @abstractmethod
    def supports_function_calling(self) -> bool:
        """
        Check if the model supports function calling.

        Returns:
            True if function calling is supported
        """
        pass
