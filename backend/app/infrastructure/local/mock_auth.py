"""
Mock authentication provider for local development.
"""

from typing import Optional

from app.interfaces.auth_provider import IAuthProvider, User


class MockAuthProvider(IAuthProvider):
    """Mock auth provider that always returns a test user."""

    def __init__(self, enabled: bool = False):
        """
        Initialize mock auth provider.

        Args:
            enabled: Whether authentication is required
        """
        self._enabled = enabled
        self._mock_users = {
            "dev_user": User(
                id="dev_user",
                email="dev@example.com",
                display_name="Developer",
            ),
            "test_user": User(
                id="test_user",
                email="test@example.com",
                display_name="Test User",
            ),
        }

    async def verify_token(self, token: str) -> User:
        """
        Verify token - in mock mode, token is treated as user_id.

        Args:
            token: User ID (in mock mode)

        Returns:
            Mock user
        """
        if token in self._mock_users:
            return self._mock_users[token]
        # Default user for any token
        return User(id=token, email=f"{token}@example.com", display_name=token)

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self._mock_users.get(user_id)

    def is_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._enabled
