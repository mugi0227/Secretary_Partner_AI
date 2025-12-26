"""
SQLite implementation of Chat session repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_

from app.interfaces.chat_session_repository import IChatSessionRepository
from app.models.chat_session import ChatSession, ChatMessage
from app.infrastructure.local.database import ChatSessionORM, ChatMessageORM, get_session_factory


class SqliteChatSessionRepository(IChatSessionRepository):
    """SQLite implementation of chat session repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _session_orm_to_model(self, orm: ChatSessionORM) -> ChatSession:
        """Convert session ORM object to Pydantic model."""
        return ChatSession(
            session_id=orm.session_id,
            user_id=orm.user_id,
            title=orm.title or "New Chat",
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    def _message_orm_to_model(self, orm: ChatMessageORM) -> ChatMessage:
        """Convert message ORM object to Pydantic model."""
        return ChatMessage(
            id=UUID(orm.id),
            session_id=orm.session_id,
            user_id=orm.user_id,
            role=orm.role,
            content=orm.content,
            created_at=orm.created_at,
        )

    async def touch_session(
        self,
        user_id: str,
        session_id: str,
        title: Optional[str] = None,
    ) -> ChatSession:
        """Create or update a chat session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ChatSessionORM).where(
                    and_(
                        ChatSessionORM.session_id == session_id,
                        ChatSessionORM.user_id == user_id,
                    )
                )
            )
            orm = result.scalar_one_or_none()

            if orm:
                orm.updated_at = datetime.utcnow()
                if title and (not orm.title or orm.title == "New Chat"):
                    orm.title = title
            else:
                orm = ChatSessionORM(
                    session_id=session_id,
                    user_id=user_id,
                    title=title or "New Chat",
                )
                session.add(orm)

            await session.commit()
            await session.refresh(orm)
            return self._session_orm_to_model(orm)

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSession]:
        """List chat sessions for a user."""
        async with self._session_factory() as session:
            query = (
                select(ChatSessionORM)
                .where(ChatSessionORM.user_id == user_id)
                .order_by(ChatSessionORM.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query)
            return [self._session_orm_to_model(orm) for orm in result.scalars().all()]

    async def add_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        title: Optional[str] = None,
    ) -> ChatMessage:
        """Add a message to a session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ChatSessionORM).where(
                    and_(
                        ChatSessionORM.session_id == session_id,
                        ChatSessionORM.user_id == user_id,
                    )
                )
            )
            session_orm = result.scalar_one_or_none()
            if session_orm:
                session_orm.updated_at = datetime.utcnow()
                if title and (not session_orm.title or session_orm.title == "New Chat"):
                    session_orm.title = title
            else:
                session_orm = ChatSessionORM(
                    session_id=session_id,
                    user_id=user_id,
                    title=title or "New Chat",
                )
                session.add(session_orm)

            message_orm = ChatMessageORM(
                session_id=session_id,
                user_id=user_id,
                role=role,
                content=content or "",
            )
            session.add(message_orm)

            await session.commit()
            await session.refresh(message_orm)
            return self._message_orm_to_model(message_orm)

    async def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 500,
        offset: int = 0,
    ) -> list[ChatMessage]:
        """List messages for a session."""
        async with self._session_factory() as session:
            query = (
                select(ChatMessageORM)
                .where(
                    and_(
                        ChatMessageORM.session_id == session_id,
                        ChatMessageORM.user_id == user_id,
                    )
                )
                .order_by(ChatMessageORM.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query)
            return [self._message_orm_to_model(orm) for orm in result.scalars().all()]
