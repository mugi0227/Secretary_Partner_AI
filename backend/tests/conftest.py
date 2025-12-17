"""
Pytest configuration and shared fixtures.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.local.database import Base


@pytest.fixture
async def db_session():
    """
    Create an in-memory SQLite database session for testing.

    Yields:
        AsyncSession: Database session
    """
    # Use in-memory SQLite for tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
def session_factory(db_session):
    """
    Create a session factory that returns the test session.

    Args:
        db_session: Test database session

    Returns:
        Callable that returns the session
    """
    def _factory():
        return db_session
    return _factory


@pytest.fixture
def test_user_id() -> str:
    """Test user ID for testing."""
    return "test_user_123"


@pytest.fixture
def mock_user():
    """Mock user object."""
    from app.interfaces.auth_provider import User
    return User(
        id="test_user_123",
        email="test@example.com",
        display_name="Test User",
    )

