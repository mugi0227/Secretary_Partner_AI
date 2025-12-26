"""Abstract interfaces for infrastructure abstraction."""

from app.interfaces.task_repository import ITaskRepository
from app.interfaces.project_repository import IProjectRepository
from app.interfaces.agent_task_repository import IAgentTaskRepository
from app.interfaces.memory_repository import IMemoryRepository
from app.interfaces.capture_repository import ICaptureRepository
from app.interfaces.chat_session_repository import IChatSessionRepository
from app.interfaces.llm_provider import ILLMProvider
from app.interfaces.speech_provider import ISpeechToTextProvider
from app.interfaces.storage_provider import IStorageProvider
from app.interfaces.auth_provider import IAuthProvider

__all__ = [
    "ITaskRepository",
    "IProjectRepository",
    "IAgentTaskRepository",
    "IMemoryRepository",
    "ICaptureRepository",
    "IChatSessionRepository",
    "ILLMProvider",
    "ISpeechToTextProvider",
    "IStorageProvider",
    "IAuthProvider",
]
