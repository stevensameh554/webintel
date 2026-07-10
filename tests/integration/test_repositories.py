from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import CrawlJobStatus
from app.db.repositories import CrawlJobRepository, PageRepository, WebsiteRepository
from app.db.session import create_database_engine


@pytest.fixture
async def database_session() -> AsyncIterator[AsyncSession]:
    engine = create_database_engine(Settings(_env_file=None, environment="test"))
    try:
        connection = await engine.connect()
    except (OSError, DBAPIError) as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL is unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_read_website_and_crawl_job(database_session: AsyncSession) -> None:
    suffix = uuid4().hex
    website_repository = WebsiteRepository(database_session)
    job_repository = CrawlJobRepository(database_session)

    website = await website_repository.create(
        domain=f"{suffix}.example.com", root_url=f"https://{suffix}.example.com"
    )
    job = await job_repository.create(
        website_id=website.id, start_url=website.root_url, max_pages=25
    )
    database_session.expunge_all()

    stored_website = await website_repository.get_by_domain(website.domain)
    stored_job = await job_repository.get_by_id(job.id)

    assert stored_website is not None
    assert stored_website.id == website.id
    assert stored_job is not None
    assert stored_job.status is CrawlJobStatus.QUEUED
    assert stored_job.max_pages == 25


@pytest.mark.asyncio
async def test_create_page_and_complete_job(database_session: AsyncSession) -> None:
    suffix = uuid4().hex
    website_repository = WebsiteRepository(database_session)
    job_repository = CrawlJobRepository(database_session)
    page_repository = PageRepository(database_session)
    root_url = f"https://{suffix}.example.com"

    website = await website_repository.create(domain=f"{suffix}.example.com", root_url=root_url)
    job = await job_repository.create(website_id=website.id, start_url=root_url)
    await job_repository.mark_running(job)
    page = await page_repository.create(
        website_id=website.id,
        crawl_job_id=job.id,
        url=f"{root_url}/",
        normalized_url=root_url,
        crawled_at=datetime.now(UTC),
        status_code=200,
        content_type="text/html",
        title="Example",
        headings=[{"level": 1, "text": "Example"}],
    )
    await job_repository.mark_completed(job, pages_crawled=1, pages_failed=0)

    stored_pages = await page_repository.list_for_website(website.id)

    assert stored_pages == [page]
    assert stored_pages[0].headings[0]["text"] == "Example"
    assert job.status is CrawlJobStatus.COMPLETED
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_only_failed_jobs_can_be_reset(database_session: AsyncSession) -> None:
    suffix = uuid4().hex
    website_repository = WebsiteRepository(database_session)
    job_repository = CrawlJobRepository(database_session)
    website = await website_repository.create(
        domain=f"{suffix}.example.com", root_url=f"https://{suffix}.example.com"
    )
    job = await job_repository.create(website_id=website.id, start_url=website.root_url)

    with pytest.raises(ValueError, match="Only failed"):
        await job_repository.reset_for_retry(job)

    await job_repository.mark_failed(job, error_message="timeout")
    await job_repository.reset_for_retry(job)

    assert job.status is CrawlJobStatus.QUEUED
    assert job.error_message is None
    assert job.finished_at is None
