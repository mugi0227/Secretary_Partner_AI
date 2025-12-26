"""
Dependency injection for API endpoints.

This module provides FastAPI dependencies that inject the correct
infrastructure implementations based on environment configuration.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.interfaces.auth_provider import IAuthProvider, User
from app.interfaces.task_repository import ITaskRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.speech_provider import ISpeechToTextProvider
from app.interfaces.storage_provider import IStorageProvider


# ===========================================
# Repository Dependencies
# ===========================================


@lru_cache()
def get_task_repository() -> ITaskRepository:
    """Get task repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement Firestore repository
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.task_repository import SqliteTaskRepository
        return SqliteTaskRepository()


@lru_cache()
def get_project_repository() -> IProjectRepository:
    """Get project repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.project_repository import SqliteProjectRepository
        return SqliteProjectRepository()


@lru_cache()
def get_agent_task_repository() -> IAgentTaskRepository:
    """Get agent task repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.agent_task_repository import SqliteAgentTaskRepository
        return SqliteAgentTaskRepository()


@lru_cache()
def get_memory_repository() -> IMemoryRepository:
    """Get memory repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.memory_repository import SqliteMemoryRepository
        return SqliteMemoryRepository()


@lru_cache()
def get_capture_repository() -> ICaptureRepository:
    """Get capture repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Firestore not implemented yet")
    else:
        from app.infrastructure.local.capture_repository import SqliteCaptureRepository
        return SqliteCaptureRepository()


@lru_cache()
def get_chat_session_repository() -> IChatSessionRepository:
    """Get chat session repository instance."""
    settings = get_settings()
    if settings.is_gcp:
        raise NotImplementedError("Chat session repository not implemented for GCP")
    else:
        from app.infrastructure.local.chat_session_repository import SqliteChatSessionRepository
        return SqliteChatSessionRepository()


# ===========================================
# Provider Dependencies
# ===========================================


@lru_cache()
def get_llm_provider() -> ILLMProvider:
    """
    Get LLM provider instance based on LLM_PROVIDER setting.

    Supports:
    - gemini-api: Gemini API (API Key, works in local/gcp)
    - vertex-ai: Vertex AI (GCP only, service account)
    - litellm: LiteLLM (Bedrock, OpenAI, etc.)
    """
    settings = get_settings()

    if settings.LLM_PROVIDER == "gemini-api":
        from app.infrastructure.local.gemini_api_provider import GeminiAPIProvider
        return GeminiAPIProvider(settings.GEMINI_MODEL)

    elif settings.LLM_PROVIDER == "vertex-ai":
        if not settings.is_gcp:
            raise ValueError(
                "Vertex AI provider requires ENVIRONMENT=gcp. "
                "Use gemini-api or litellm for local development."
            )
        from app.infrastructure.gcp.gemini_provider import VertexAIProvider
        return VertexAIProvider(settings.GEMINI_MODEL)

    elif settings.LLM_PROVIDER == "litellm":
        from app.infrastructure.local.litellm_provider import LiteLLMProvider
        return LiteLLMProvider(settings.LITELLM_MODEL)

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")


@lru_cache()
def get_auth_provider() -> IAuthProvider:
    """Get auth provider instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement Firebase Auth
        raise NotImplementedError("Firebase Auth not implemented yet")
    else:
        from app.infrastructure.local.mock_auth import MockAuthProvider
        return MockAuthProvider(enabled=True)


@lru_cache()
def get_storage_provider() -> IStorageProvider:
    """Get storage provider instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement GCS provider
        raise NotImplementedError("Google Cloud Storage not implemented yet")
    else:
        from app.infrastructure.local.storage_provider import LocalStorageProvider
        return LocalStorageProvider(settings.STORAGE_BASE_PATH)


@lru_cache()
def get_speech_provider() -> ISpeechToTextProvider:
    """Get speech-to-text provider instance."""
    settings = get_settings()
    if settings.is_gcp:
        # TODO: Implement Google Cloud Speech provider
        raise NotImplementedError("Google Cloud Speech not implemented yet")
    else:
        from app.infrastructure.local.whisper_provider import WhisperProvider
        return WhisperProvider(settings.WHISPER_MODEL_SIZE)


# ===========================================
# User Authentication
# ===========================================


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    auth_provider: IAuthProvider = Depends(get_auth_provider),
) -> User:
    """
    Get current authenticated user.

    In local mode, returns a mock user.
    In GCP mode, validates Firebase token.
    """
    if not auth_provider.is_enabled():
        # Mock user for development
        return User(id="dev_user", email="dev@example.com", display_name="Developer")

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required",
        )

    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    try:
        return await auth_provider.verify_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


# ===========================================
# Type Aliases for Dependency Injection
# ===========================================

TaskRepo = Annotated[ITaskRepository, Depends(get_task_repository)]
ProjectRepo = Annotated[IProjectRepository, Depends(get_project_repository)]
AgentTaskRepo = Annotated[IAgentTaskRepository, Depends(get_agent_task_repository)]
MemoryRepo = Annotated[IMemoryRepository, Depends(get_memory_repository)]
CaptureRepo = Annotated[ICaptureRepository, Depends(get_capture_repository)]
ChatRepo = Annotated[IChatSessionRepository, Depends(get_chat_session_repository)]
LLMProvider = Annotated[ILLMProvider, Depends(get_llm_provider)]
StorageProvider = Annotated[IStorageProvider, Depends(get_storage_provider)]
SpeechProvider = Annotated[ISpeechToTextProvider, Depends(get_speech_provider)]
CurrentUser = Annotated[User, Depends(get_current_user)]
