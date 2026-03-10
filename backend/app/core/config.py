"""
Application configuration using Pydantic Settings.

Environment-based infrastructure switching is controlled by the ENVIRONMENT variable.
"""

from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ===========================================
    # Environment
    # ===========================================
    ENVIRONMENT: Literal["local", "gcp"] = "local"
    DEBUG: bool = True

    # ===========================================
    # Database
    # ===========================================
    DATABASE_URL: str = "sqlite+aiosqlite:///./secretary.db"

    # ===========================================
    # LLM Configuration
    # ===========================================
    # LLM Provider: "gemini-api" | "vertex-ai" | "litellm"
    # - gemini-api: Gemini API (API Key, works in local/gcp)
    # - vertex-ai: Vertex AI (GCP only, service account)
    # - litellm: LiteLLM (Bedrock, OpenAI, etc. with optional custom endpoint)
    LLM_PROVIDER: Literal["gemini-api", "vertex-ai", "litellm"] = "gemini-api"

    # Gemini model name (for gemini-api and vertex-ai)
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # LiteLLM model identifier (for litellm provider)
    LITELLM_MODEL: str = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"

    # LiteLLM custom endpoint (optional, for proxy servers)
    LITELLM_API_BASE: str = ""

    # LiteLLM custom API key (optional, for custom endpoints)
    LITELLM_API_KEY: str = ""

    # Available models for model selection UI (comma-separated).
    # For gemini-api/vertex-ai: list Gemini model names.
    # For litellm: leave empty to fetch from proxy server, or list model IDs.
    AVAILABLE_MODELS: str = ""

    # LiteLLM Vision model (optional, uses separate model for image processing)
    # If set, images will be processed by this model instead of the main model.
    # Example: "openai/qwen3-vl" or "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
    LITELLM_VISION_MODEL: str = ""

    # Google API Key (for gemini-api provider)
    GOOGLE_API_KEY: str = ""

    # ===========================================
    # Google Cloud
    # ===========================================
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # ===========================================
    # AWS (for Bedrock via LiteLLM)
    # ===========================================
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # ===========================================
    # Auth (OIDC/JWT)
    # ===========================================
    AUTH_PROVIDER: Literal["mock", "oidc", "local"] = "mock"
    OIDC_ISSUER: str = ""
    OIDC_AUDIENCE: str = ""
    OIDC_JWKS_URL: str = ""
    OIDC_EMAIL_CLAIM: str = "email"
    OIDC_NAME_CLAIM: str = "name"
    OIDC_ALLOW_EMAIL_LINKING: bool = False

    # ===========================================
    # Local Auth (password + JWT)
    # ===========================================
    LOCAL_JWT_SECRET: str = ""
    LOCAL_JWT_ISSUER: str = "secretary-local"
    LOCAL_JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ===========================================
    # Registration Whitelist
    # ===========================================
    # Comma-separated list of allowed email addresses for registration.
    # If empty, all emails are allowed (no restriction).
    # Example: "user1@example.com,user2@example.com"
    REGISTRATION_WHITELIST_EMAILS: str = ""

    # ===========================================
    # Firebase Auth (legacy placeholder)
    # ===========================================
    FIREBASE_PROJECT_ID: str = ""

    # ===========================================
    # Server
    # ===========================================
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    # URL for accessing the backend (for storage and callbacks)
    BASE_URL: str = "http://localhost:8000"

    # ===========================================
    # Scheduler (Quiet Hours)
    # ===========================================
    QUIET_HOURS_START: str = "02:00"
    QUIET_HOURS_END: str = "06:00"

    # ===========================================
    # Developer / Admin
    # ===========================================
    DEVELOPER_USER_ID: str = ""

    # ===========================================
    # Similarity Detection
    # ===========================================
    SIMILARITY_LOOKBACK_MINUTES: int = 10
    SIMILARITY_THRESHOLD: float = 0.8

    # ===========================================
    # Storage
    # ===========================================
    STORAGE_BASE_PATH: str = "./storage"
    # GCS bucket name (for GCP environment)
    GCS_BUCKET: str = ""

    # ===========================================
    # Speech-to-Text
    # ===========================================
    SPEECH_PROVIDER: Literal["whisper", "google-stt-v2", "amazon-transcribe"] = "whisper"
    # Whisper model size for local development
    WHISPER_MODEL_SIZE: str = "base"  # tiny, base, small, medium, large
    STT_V2_LOCATION: str = "us"
    STT_V2_MODEL: str = "chirp_3"
    STT_V2_LANGUAGE: str = "ja-JP"
    AWS_TRANSCRIBE_S3_BUCKET: str = ""
    AWS_TRANSCRIBE_S3_PREFIX: str = "transcribe-input"
    AWS_TRANSCRIBE_LANGUAGE: str = "ja-JP"
    AWS_TRANSCRIBE_POLL_SECONDS: float = 0.35
    AWS_TRANSCRIBE_TIMEOUT_SECONDS: int = 180

    # ===========================================
    # Developer Accounts
    # ===========================================
    # Comma-separated list of email addresses that are developer accounts.
    # Developer accounts can change issue statuses.
    # Example: "dev@example.com,admin@example.com"
    DEVELOPER_EMAILS: str = ""

    # ===========================================
    # Email
    # ===========================================
    EMAIL_PROVIDER: Literal["ses", "mock"] = "mock"
    SES_FROM_EMAIL: str = ""
    SES_REGION: str = "us-east-1"

    # ===========================================
    # Feature Flags
    # ===========================================
    ENABLE_ISSUES: bool = False

    # ===========================================
    # Input Validation Limits
    # ===========================================
    MAX_TEXT_LENGTH: int = 10000
    MAX_TRANSCRIPTION_LENGTH: int = 10000
    MAX_IMAGE_ANALYSIS_LENGTH: int = 5000

    @property
    def available_models(self) -> list[str]:
        """Get list of available model identifiers."""
        if not self.AVAILABLE_MODELS:
            return []
        return [m.strip() for m in self.AVAILABLE_MODELS.split(",") if m.strip()]

    @property
    def developer_emails(self) -> set[str]:
        """Get set of developer email addresses (lowercased)."""
        if not self.DEVELOPER_EMAILS:
            return set()
        return {e.strip().lower() for e in self.DEVELOPER_EMAILS.split(",") if e.strip()}

    @property
    def is_gcp(self) -> bool:
        """Check if running in GCP environment."""
        return self.ENVIRONMENT == "gcp"

    @property
    def is_local(self) -> bool:
        """Check if running in local environment."""
        return self.ENVIRONMENT == "local"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Using lru_cache ensures settings are loaded only once.
    """
    return Settings()
