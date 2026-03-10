"""
Email provider interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class IEmailProvider(ABC):
    """Abstract interface for sending emails."""

    @abstractmethod
    async def send_email(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        """Send an email to one or more recipients."""
        pass
