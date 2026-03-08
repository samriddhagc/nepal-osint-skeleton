"""Application configuration using Pydantic settings."""
from functools import lru_cache
from typing import Optional, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Nepal OSINT"
    app_env: Literal["development", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://nepal_osint:nepal_osint_dev@localhost:5433/nepal_osint_v5"

    # Redis
    redis_url: str = "redis://localhost:6380/0"

    # CORS (supports comma-separated env: CORS_ORIGINS or ALLOWED_ORIGINS)
    allowed_origins: Optional[str] = None
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @model_validator(mode="after")
    def _validate_settings(self):
        # Back-compat: ALLOWED_ORIGINS overrides cors_origins when provided.
        if self.allowed_origins:
            self.cors_origins = [s.strip() for s in self.allowed_origins.split(",") if s.strip()]

        if self.app_env == "production":
            if not self.jwt_secret_key:
                raise ValueError("JWT_SECRET_KEY must be set in production")
            if self.jwt_secret_key.startswith("CHANGE_ME"):
                raise ValueError("JWT_SECRET_KEY must be changed in production")
            if len(self.jwt_secret_key) < 32:
                raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")

            # Force safe defaults
            self.debug = False

        return self

    # RSS Ingestion
    rss_poll_interval_priority: int = 300  # 5 minutes
    rss_poll_interval_all: int = 900  # 15 minutes
    rss_max_concurrent: int = 10
    rss_timeout: int = 30

    # BIPAD Portal Settings
    bipad_base_url: str = "https://bipadportal.gov.np/api/v1"
    bipad_poll_interval: int = 300  # 5 minutes
    bipad_max_concurrent: int = 5
    bipad_timeout: int = 30
    bipad_incident_days_back: int = 30
    bipad_earthquake_days_back: int = 7
    bipad_min_earthquake_magnitude: float = 4.0
    bipad_significance_death_threshold: int = 0
    bipad_significance_loss_threshold: float = 2_500_000

    # Paths
    sources_config_path: str = "config/sources.yaml"
    relevance_rules_path: str = "config/relevance_rules.yaml"

    # Twitter/X API Settings - FREE TIER OPTIMIZED
    twitter_bearer_token: Optional[str] = None
    twitter_api_tier: str = "free"
    twitter_poll_interval: int = 43200
    twitter_max_per_query: int = 10
    twitter_cache_ttl_hours: int = 6

    # Authentication / JWT Settings
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_SECRET_KEY"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Google OAuth
    google_client_id: Optional[str] = None

    # Guest login
    guest_token_expire_hours: int = 24

    # Resend (email OTP verification)
    resend_api_key: Optional[str] = None
    resend_from_email: str = "Nepal OSINT <noreply@nepalosint.dev>"

    # Scheduler - automatically starts background jobs (RSS, scraping, etc.)
    run_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
