from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import health
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    settings = Settings(_env_file=None, environment="test")
    application = create_app(settings)
    application.state.settings = settings
    application.state.database_engine = object()
    application.state.redis = object()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_health_returns_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok", "service": "WebIntel", "version": "0.1.0"},
    }


@pytest.mark.asyncio
async def test_ready_when_dependencies_are_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def available(_dependency: object) -> health.CheckResult:
        return {"status": "up", "detail": None}

    monkeypatch.setattr(health, "check_postgresql", available)
    monkeypatch.setattr(health, "check_redis", available)

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"


@pytest.mark.asyncio
async def test_not_ready_when_a_dependency_is_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def database_down(_dependency: object) -> health.CheckResult:
        return {"status": "down", "detail": "ConnectionError"}

    async def redis_up(_dependency: object) -> health.CheckResult:
        return {"status": "up", "detail": None}

    monkeypatch.setattr(health, "check_postgresql", database_down)
    monkeypatch.setattr(health, "check_redis", redis_up)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["data"]["checks"]["postgresql"]["status"] == "down"
