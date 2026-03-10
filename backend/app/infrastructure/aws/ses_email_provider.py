"""
Amazon SES email provider.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.core.exceptions import InfrastructureError
from app.interfaces.email_provider import IEmailProvider

logger = logging.getLogger(__name__)


class SESEmailProvider(IEmailProvider):
    """Amazon SES implementation for sending emails."""

    def __init__(
        self,
        from_email: str,
        region_name: str = "us-east-1",
    ):
        self.from_email = (from_email or "").strip()
        self.region_name = (region_name or "us-east-1").strip() or "us-east-1"

        if not self.from_email:
            raise InfrastructureError(
                "SES_FROM_EMAIL is required when EMAIL_PROVIDER=ses"
            )

        self._boto3: Any | None = None
        self._ses_client: Any | None = None

    def _load_boto3(self) -> Any:
        if self._boto3 is None:
            try:
                import boto3
            except ImportError:
                raise InfrastructureError(
                    "boto3 is required for SES email provider. "
                    "Install with: pip install boto3"
                )
            self._boto3 = boto3
        return self._boto3

    def _get_ses_client(self) -> Any:
        if self._ses_client is None:
            boto3 = self._load_boto3()
            self._ses_client = boto3.client("ses", region_name=self.region_name)
        return self._ses_client

    async def send_email(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> None:
        """Send an email via Amazon SES."""
        if not to:
            return

        client = self._get_ses_client()

        body: dict[str, Any] = {
            "Text": {"Data": body_text, "Charset": "UTF-8"},
        }
        if body_html:
            body["Html"] = {"Data": body_html, "Charset": "UTF-8"}

        try:
            await asyncio.to_thread(
                client.send_email,
                Source=self.from_email,
                Destination={"ToAddresses": to},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body,
                },
            )
            logger.info("SES email sent to %s: %s", to, subject)
        except Exception as e:
            logger.error("Failed to send SES email to %s: %s", to, e)
            raise InfrastructureError(f"SES send_email failed: {e}") from e
