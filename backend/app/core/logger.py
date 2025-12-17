"""
Structured logging configuration.
"""

import logging
import sys
from typing import Optional

from app.core.config import get_settings


def setup_logger(
    name: str = "secretary",
    level: Optional[int] = None,
) -> logging.Logger:
    """
    Set up a structured logger.

    Args:
        name: Logger name
        level: Log level (defaults to DEBUG in debug mode, INFO otherwise)

    Returns:
        Configured logger instance
    """
    settings = get_settings()

    if level is None:
        level = logging.DEBUG if settings.DEBUG else logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Format: timestamp - name - level - message
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


# Default logger instance
logger = setup_logger()
