"""
SQLite database configuration and ORM models.

This module defines the SQLAlchemy ORM models and database initialization.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


# ===========================================
# ORM Models
# ===========================================


class TaskORM(Base):
    """Task ORM model."""

    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    project_id = Column(String(36), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="TODO", index=True)
    importance = Column(String(10), default="MEDIUM")
    urgency = Column(String(10), default="MEDIUM")
    energy_level = Column(String(10), default="LOW")
    estimated_minutes = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)
    parent_id = Column(String(36), nullable=True, index=True)
    source_capture_id = Column(String(36), nullable=True)
    created_by = Column(String(10), default="USER")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectORM(Base):
    """Project ORM model."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="ACTIVE")
    context_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentTaskORM(Base):
    """AgentTask ORM model."""

    __tablename__ = "agent_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    trigger_time = Column(DateTime, nullable=False, index=True)
    action_type = Column(String(30), nullable=False)
    status = Column(String(20), default="PENDING", index=True)
    payload = Column(Text, nullable=True)  # JSON string
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MemoryORM(Base):
    """Memory ORM model."""

    __tablename__ = "memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    scope = Column(String(20), nullable=False, index=True)
    memory_type = Column(String(20), nullable=False)
    project_id = Column(String(36), nullable=True, index=True)
    content = Column(Text, nullable=False)
    tags = Column(Text, nullable=True)  # JSON array string
    source = Column(String(20), default="agent")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CaptureORM(Base):
    """Capture ORM model."""

    __tablename__ = "captures"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    content_type = Column(String(10), nullable=False)
    content_url = Column(String(500), nullable=True)
    raw_text = Column(Text, nullable=True)
    transcription = Column(Text, nullable=True)
    image_analysis = Column(Text, nullable=True)
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ===========================================
# Database Session Management
# ===========================================


def get_engine():
    """Get async engine instance."""
    settings = get_settings()
    return create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)


def get_session_factory():
    """Get async session factory."""
    engine = get_engine()
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initialize database tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncSession:
    """Get database session (for dependency injection)."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session
