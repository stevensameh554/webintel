from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.routes import crawl_jobs
from app.core.config import Settings
from app.db.models import CrawlJob, Website
from app.db.repositories import CrawlJobRepository
from app.db.session import create_database_engine, create_session_factory
from app.main import create_app


@dataclass
class ApiHarness:
    client: AsyncClient
    engine: AsyncEngine
    dispatched: list[UUID]


@pytest.fixture
async def api_harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ApiHarness]:
    settings = Settings(_env_file=None, environment="test")
    engine = create_database_engine(settings)
    application = create_app(settings)
    application.state.settings = settings
    application.state.database_engine = engine
    application.state.session_factory = create_session_factory(engine)
    dispatched: list[UUID] = []
    monkeypatch.setattr(crawl_jobs, "enqueue_crawl_job", dispatched.append)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield ApiHarness(client=client, engine=engine, dispatched=dispatched)

    session_factory = create_session_factory(engine)
    async with session_factory() as session, session.begin():
        await session.execute(delete(Website).where(Website.domain.like("phase3-%")))
    await engine.dispose()


def make_test_url() -> str:
    return f"https://phase3-{uuid4().hex}.example.com/about/"


@pytest.mark.asyncio
async def test_create_get_and_list_crawl_job(api_harness: ApiHarness) -> None:
    create_response = await api_harness.client.post(
        "/api/v1/crawl-jobs", json={"url": make_test_url(), "max_pages": 25}
    )

    assert create_response.status_code == 202
    created = create_response.json()["data"]
    job_id = created["job_id"]
    assert created["status"] == "queued"
    assert api_harness.dispatched == [UUID(job_id)]

    detail_response = await api_harness.client.get(f"/api/v1/crawl-jobs/{job_id}")
    list_response = await api_harness.client.get(
        "/api/v1/crawl-jobs", params={"status": "queued", "limit": 10}
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["start_url"].endswith("/about")
    assert detail_response.json()["data"]["max_pages"] == 25
    listing = list_response.json()["data"]
    assert any(item["id"] == job_id for item in listing["items"])
    assert listing["total"] >= 1
    assert listing["limit"] == 10


@pytest.mark.asyncio
async def test_reuses_website_for_new_job(api_harness: ApiHarness) -> None:
    url = make_test_url()

    first = await api_harness.client.post("/api/v1/crawl-jobs", json={"url": url})
    second = await api_harness.client.post("/api/v1/crawl-jobs", json={"url": url})

    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["website_id"] == second.json()["data"]["website_id"]
    assert first.json()["data"]["job_id"] != second.json()["data"]["job_id"]


@pytest.mark.asyncio
async def test_retry_requires_failed_job(api_harness: ApiHarness) -> None:
    created = await api_harness.client.post("/api/v1/crawl-jobs", json={"url": make_test_url()})
    job_id = UUID(created.json()["data"]["job_id"])

    conflict = await api_harness.client.post(f"/api/v1/crawl-jobs/{job_id}/retry")

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "INVALID_JOB_STATE"

    session_factory = create_session_factory(api_harness.engine)
    async with session_factory() as session, session.begin():
        repository = CrawlJobRepository(session)
        job = await repository.get_by_id(job_id)
        assert job is not None
        await repository.mark_failed(job, error_message="timeout")

    retried = await api_harness.client.post(f"/api/v1/crawl-jobs/{job_id}/retry")

    assert retried.status_code == 202
    assert retried.json()["data"]["status"] == "queued"
    assert api_harness.dispatched.count(job_id) == 2


@pytest.mark.asyncio
async def test_queue_failure_is_persisted(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    def queue_down(_job_id: UUID) -> None:
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr(crawl_jobs, "enqueue_crawl_job", queue_down)

    response = await api_harness.client.post("/api/v1/crawl-jobs", json={"url": make_test_url()})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_UNAVAILABLE"

    session_factory = create_session_factory(api_harness.engine)
    async with session_factory() as session:
        job = await session.scalar(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(1))
        assert job is not None
        assert job.status.value == "failed"
        assert job.error_message is not None
        assert "Queue unavailable" in job.error_message


@pytest.mark.asyncio
async def test_validation_and_not_found_errors_use_standard_shape(
    api_harness: ApiHarness,
) -> None:
    invalid = await api_harness.client.post(
        "/api/v1/crawl-jobs", json={"url": "http://127.0.0.1", "max_pages": 0}
    )
    missing = await api_harness.client.get(f"/api/v1/crawl-jobs/{uuid4()}")

    assert invalid.status_code == 422
    assert invalid.json()["success"] is False
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
