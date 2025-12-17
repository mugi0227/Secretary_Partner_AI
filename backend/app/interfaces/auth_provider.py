"""
Authentication provider interface.

Defines the contract for authentication services.
Implementations: Firebase Auth, Mock (for local), Cognito
"""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class User(BaseModel):
    """Authenticated user model."""

    id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_anonymous: bool = False


class IAuthProvider(ABC):
    """Abstract interface for authentication providers."""

    @abstractmethod
    async def verify_token(self, token: str) -> User:
        """
        Verify an authentication token and return user info.

        Args:
            token: JWT or session token

        Returns:
            Authenticated user

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User if found, None otherwise
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """
        Check if authentication is enabled.

        Returns:
            True if authentication is enabled
        """
        pass
