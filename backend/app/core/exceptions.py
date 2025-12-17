"""
Custom exceptions for the application.
"""

from typing import Any, Optional


class SecretaryException(Exception):
    """Base exception for Secretary Partner AI."""

    def __init__(self, message: str, details: Optional[Any] = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(SecretaryException):
    """Resource not found."""

    pass


class DuplicateError(SecretaryException):
    """Duplicate resource detected."""

    pass


class ValidationError(SecretaryException):
    """Validation error."""

    pass


class LLMError(SecretaryException):
    """LLM-related error."""

    pass


class LLMValidationError(LLMError):
    """LLM output validation failed."""

    def __init__(self, message: str, raw_output: str, attempts: int = 1):
        super().__init__(message, details={"raw_output": raw_output, "attempts": attempts})
        self.raw_output = raw_output
        self.attempts = attempts


class AuthenticationError(SecretaryException):
    """Authentication failed."""

    pass


class AuthorizationError(SecretaryException):
    """Authorization failed."""

    pass


class InfrastructureError(SecretaryException):
    """Infrastructure-related error (DB, external services, etc.)."""

    pass
