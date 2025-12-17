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
    # - litellm: LiteLLM (Bedrock, OpenAI, etc.)
    LLM_PROVIDER: Literal["gemini-api", "vertex-ai", "litellm"] = "gemini-api"

    # Gemini model name (for gemini-api and vertex-ai)
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # LiteLLM model identifier (for litellm provider)
    LITELLM_MODEL: str = "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"

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
    # Firebase Auth
    # ===========================================
    FIREBASE_PROJECT_ID: str = ""

    # ===========================================
    # Server
    # ===========================================
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    # ===========================================
    # Scheduler (Quiet Hours)
    # ===========================================
    QUIET_HOURS_START: str = "02:00"
    QUIET_HOURS_END: str = "06:00"

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
    # Whisper model size for local development
    WHISPER_MODEL_SIZE: str = "base"  # tiny, base, small, medium, large

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
