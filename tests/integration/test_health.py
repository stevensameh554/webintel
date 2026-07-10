from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.routes import health
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(_env_file=None, environment="test")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"status": "ok", "service": "WebIntel", "version": "0.1.0"},
    }


def test_ready_when_dependencies_are_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def available(_dependency: object) -> health.CheckResult:
        return {"status": "up", "detail": None}

    monkeypatch.setattr(health, "check_postgresql", available)
    monkeypatch.setattr(health, "check_redis", available)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"


def test_not_ready_when_a_dependency_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def database_down(_dependency: object) -> health.CheckResult:
        return {"status": "down", "detail": "ConnectionError"}

    async def redis_up(_dependency: object) -> health.CheckResult:
        return {"status": "up", "detail": None}

    monkeypatch.setattr(health, "check_postgresql", database_down)
    monkeypatch.setattr(health, "check_redis", redis_up)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["data"]["checks"]["postgresql"]["status"] == "down"
