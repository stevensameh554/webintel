import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_have_local_development_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.fetch_timeout_seconds == 10
    assert settings.fetch_retries == 2
    assert settings.fetch_max_response_bytes == 5_000_000


def test_readiness_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, readiness_timeout_seconds=0)


def test_fetch_limits_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, fetch_retries=-1)
