"""
SQLite implementation of Memory repository.
"""

from __future__ import annotations

import json
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.interfaces.memory_repository import IMemoryRepository
from app.models.memory import Memory, MemoryCreate, MemorySearchResult
from app.models.enums import MemoryScope, MemoryType
from app.infrastructure.local.database import MemoryORM, get_session_factory


class SqliteMemoryRepository(IMemoryRepository):
    """SQLite implementation of memory repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: MemoryORM) -> Memory:
        """Convert ORM object to Pydantic model."""
        tags = json.loads(orm.tags) if orm.tags else []
        return Memory(
            id=UUID(orm.id),
            user_id=orm.user_id,
            scope=MemoryScope(orm.scope),
            memory_type=MemoryType(orm.memory_type),
            project_id=UUID(orm.project_id) if orm.project_id else None,
            content=orm.content,
            tags=tags,
            source=orm.source,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    async def create(self, user_id: str, memory: MemoryCreate) -> Memory:
        """Create a new memory."""
        async with self._session_factory() as session:
            orm = MemoryORM(
                id=str(uuid4()),
                user_id=user_id,
                scope=memory.scope.value,
                memory_type=memory.memory_type.value,
                project_id=str(memory.project_id) if memory.project_id else None,
                content=memory.content,
                tags=json.dumps(memory.tags) if memory.tags else None,
                source=memory.source,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, memory_id: UUID) -> Optional[Memory]:
        """Get a memory by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryORM).where(
                    and_(MemoryORM.id == str(memory_id), MemoryORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def list(
        self,
        user_id: str,
        scope: Optional[MemoryScope] = None,
        memory_type: Optional[MemoryType] = None,
        project_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories with optional filters."""
        async with self._session_factory() as session:
            query = select(MemoryORM).where(MemoryORM.user_id == user_id)

            if scope:
                query = query.where(MemoryORM.scope == scope.value)
            if memory_type:
                query = query.where(MemoryORM.memory_type == memory_type.value)
            if project_id:
                query = query.where(MemoryORM.project_id == str(project_id))

            query = query.order_by(MemoryORM.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def search(
        self,
        user_id: str,
        query: str,
        scope: Optional[MemoryScope] = None,
        project_id: Optional[UUID] = None,
        limit: int = 5,
    ) -> list[MemorySearchResult]:
        """Search memories by content using simple string matching."""
        memories = await self.list(user_id, scope=scope, project_id=project_id)

        results = []
        query_lower = query.lower()

        for memory in memories:
            content_lower = memory.content.lower()
            # Simple relevance: keyword presence + similarity
            if query_lower in content_lower:
                score = 0.8 + 0.2 * SequenceMatcher(
                    None, query_lower, content_lower
                ).ratio()
            else:
                score = SequenceMatcher(None, query_lower, content_lower).ratio()

            if score > 0.3:  # Minimum threshold
                results.append(MemorySearchResult(memory=memory, relevance_score=score))

        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]

    async def search_work_memory(
        self,
        user_id: str,
        query: str,
        limit: int = 3,
    ) -> list[MemorySearchResult]:
        """Search work memories specifically."""
        return await self.search(
            user_id=user_id,
            query=query,
            scope=MemoryScope.WORK,
            limit=limit,
        )

    async def delete(self, user_id: str, memory_id: UUID) -> bool:
        """Delete a memory."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MemoryORM).where(
                    and_(MemoryORM.id == str(memory_id), MemoryORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            await session.delete(orm)
            await session.commit()
            return True

    async def get_user_memories(
        self,
        user_id: str,
        memory_type: Optional[MemoryType] = None,
    ) -> list[Memory]:
        """Get all user-scope memories."""
        return await self.list(
            user_id=user_id,
            scope=MemoryScope.USER,
            memory_type=memory_type,
        )
