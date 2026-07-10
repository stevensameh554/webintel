from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from WEBINTEL_* environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="WEBINTEL_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "WebIntel"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://webintel:webintel@localhost:5432/webintel"
    )
    redis_url: str = "redis://localhost:6379/0"
    crawl_queue_name: str = "crawl_jobs"
    database_pool_size: int = Field(default=5, ge=1, le=50)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    crawler_user_agent: str = Field(
        default="WebIntelBot/0.1 (respectful website intelligence crawler)",
        min_length=1,
        max_length=256,
    )
    fetch_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    fetch_retries: int = Field(default=2, ge=0, le=5)
    fetch_max_redirects: int = Field(default=5, ge=0, le=20)
    fetch_max_response_bytes: int = Field(default=5_000_000, ge=1_024, le=50_000_000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
