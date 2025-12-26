"""
Chat session repository interface.

Defines the contract for chat history persistence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.chat_session import ChatSession, ChatMessage


class IChatSessionRepository(ABC):
    """Abstract interface for chat session persistence."""

    @abstractmethod
    async def touch_session(
        self,
        user_id: str,
        session_id: str,
        title: Optional[str] = None,
    ) -> ChatSession:
        """
        Create or update a chat session.

        Args:
            user_id: Owner user ID
            session_id: Session ID
            title: Optional session title

        Returns:
            ChatSession
        """
        pass

    @abstractmethod
    async def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSession]:
        """
        List chat sessions for a user.

        Args:
            user_id: Owner user ID
            limit: Max sessions
            offset: Pagination offset

        Returns:
            List of chat sessions
        """
        pass

    @abstractmethod
    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        title: Optional[str] = None,
    ) -> ChatMessage:
        """
        Add a message to a session.

        Args:
            user_id: Owner user ID
            session_id: Session ID
            role: Message role (user/assistant/system)
            content: Message content
            title: Optional session title update

        Returns:
            ChatMessage
        """
        pass

    @abstractmethod
    async def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """
        List messages for a session.

        Args:
            user_id: Owner user ID
            session_id: Session ID
            limit: Max messages
            offset: Pagination offset

        Returns:
            List of chat messages
        """
        pass
