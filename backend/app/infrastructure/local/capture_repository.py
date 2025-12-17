"""
SQLite implementation of Capture repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.interfaces.capture_repository import ICaptureRepository
from app.models.capture import Capture, CaptureCreate
from app.models.enums import ContentType
from app.infrastructure.local.database import CaptureORM, get_session_factory


class SqliteCaptureRepository(ICaptureRepository):
    """SQLite implementation of capture repository."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def _orm_to_model(self, orm: CaptureORM) -> Capture:
        """Convert ORM object to Pydantic model."""
        return Capture(
            id=UUID(orm.id),
            user_id=orm.user_id,
            content_type=ContentType(orm.content_type),
            content_url=orm.content_url,
            raw_text=orm.raw_text,
            transcription=orm.transcription,
            image_analysis=orm.image_analysis,
            processed=orm.processed,
            created_at=orm.created_at,
        )

    async def create(self, user_id: str, capture: CaptureCreate) -> Capture:
        """Create a new capture."""
        async with self._session_factory() as session:
            orm = CaptureORM(
                id=str(uuid4()),
                user_id=user_id,
                content_type=capture.content_type.value,
                content_url=capture.content_url,
                raw_text=capture.raw_text,
                transcription=capture.transcription,
                image_analysis=capture.image_analysis,
            )
            session.add(orm)
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def get(self, user_id: str, capture_id: UUID) -> Optional[Capture]:
        """Get a capture by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(CaptureORM).where(
                    and_(CaptureORM.id == str(capture_id), CaptureORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()
            return self._orm_to_model(orm) if orm else None

    async def list(
        self,
        user_id: str,
        processed: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Capture]:
        """List captures with optional filters."""
        async with self._session_factory() as session:
            query = select(CaptureORM).where(CaptureORM.user_id == user_id)

            if processed is not None:
                query = query.where(CaptureORM.processed == processed)

            query = query.order_by(CaptureORM.created_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return [self._orm_to_model(orm) for orm in result.scalars().all()]

    async def mark_processed(self, user_id: str, capture_id: UUID) -> Capture:
        """Mark a capture as processed."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(CaptureORM).where(
                    and_(CaptureORM.id == str(capture_id), CaptureORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                raise NotFoundError(f"Capture {capture_id} not found")

            orm.processed = True
            await session.commit()
            await session.refresh(orm)
            return self._orm_to_model(orm)

    async def delete(self, user_id: str, capture_id: UUID) -> bool:
        """Delete a capture."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(CaptureORM).where(
                    and_(CaptureORM.id == str(capture_id), CaptureORM.user_id == user_id)
                )
            )
            orm = result.scalar_one_or_none()

            if not orm:
                return False

            await session.delete(orm)
            await session.commit()
            return True
