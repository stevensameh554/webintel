import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CrawlJob, CrawlJobStatus


class CrawlJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, website_id: uuid.UUID, start_url: str, max_pages: int = 20
    ) -> CrawlJob:
        job = CrawlJob(website_id=website_id, start_url=start_url, max_pages=max_pages)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> CrawlJob | None:
        return await self.session.get(CrawlJob, job_id)

    async def list(
        self, *, website_id: uuid.UUID | None = None, offset: int = 0, limit: int = 50
    ) -> list[CrawlJob]:
        statement: Select[tuple[CrawlJob]] = select(CrawlJob)
        if website_id is not None:
            statement = statement.where(CrawlJob.website_id == website_id)
        statement = statement.order_by(CrawlJob.created_at.desc()).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def mark_running(self, job: CrawlJob) -> CrawlJob:
        job.status = CrawlJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.finished_at = None
        job.error_message = None
        await self.session.flush()
        return job

    async def mark_completed(
        self, job: CrawlJob, *, pages_crawled: int, pages_failed: int
    ) -> CrawlJob:
        job.status = CrawlJobStatus.COMPLETED
        job.pages_crawled = pages_crawled
        job.pages_failed = pages_failed
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def mark_failed(self, job: CrawlJob, *, error_message: str) -> CrawlJob:
        job.status = CrawlJobStatus.FAILED
        job.error_message = error_message
        job.finished_at = datetime.now(UTC)
        await self.session.flush()
        return job

    async def reset_for_retry(self, job: CrawlJob) -> CrawlJob:
        if job.status is not CrawlJobStatus.FAILED:
            raise ValueError("Only failed crawl jobs can be retried")
        job.status = CrawlJobStatus.QUEUED
        job.pages_crawled = 0
        job.pages_failed = 0
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        await self.session.flush()
        return job
