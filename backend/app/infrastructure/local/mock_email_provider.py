"""
Mock email provider for local development.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.interfaces.email_provider import IEmailProvider

logger = logging.getLogger(__name__)


class MockEmailProvider(IEmailProvider):
    """Logs emails instead of sending them. Used for local development."""

    async def send_email(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        logger.info(
            "[MockEmail] To: %s | Subject: %s\n%s",
            ", ".join(to),
            subject,
            body_text,
        )
