import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import CrawlJob, CrawlJobStatus
from app.db.repositories import CrawlJobRepository, WebsiteRepository
from app.db.session import get_database_session
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.crawl_job import CrawlJobCreate, CrawlJobCreated, CrawlJobList, CrawlJobRead
from app.services.url_intake import normalize_crawl_target
from app.workers.dispatcher import enqueue_crawl_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/crawl-jobs", tags=["crawl jobs"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]

ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Crawl job not found"},
    409: {"model": ErrorResponse, "description": "Invalid crawl job state"},
    422: {"model": ErrorResponse, "description": "Request validation error"},
    503: {"model": ErrorResponse, "description": "Crawl queue unavailable"},
}


def _created_response(job: CrawlJob) -> SuccessResponse[CrawlJobCreated]:
    return SuccessResponse(
        data=CrawlJobCreated(job_id=job.id, website_id=job.website_id, status=job.status)
    )


async def _dispatch_or_mark_failed(
    session: AsyncSession, repository: CrawlJobRepository, job: CrawlJob
) -> None:
    try:
        await run_in_threadpool(enqueue_crawl_job, job.id)
    except Exception as exc:
        logger.exception("crawl_job_enqueue_failed", extra={"job_id": str(job.id)})
        async with session.begin():
            await repository.mark_failed(
                job, error_message=f"Queue unavailable: {type(exc).__name__}"
            )
        raise AppError(
            code="QUEUE_UNAVAILABLE",
            message="The crawl queue is temporarily unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


@router.post(
    "",
    response_model=SuccessResponse[CrawlJobCreated],
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
async def create_crawl_job(
    payload: CrawlJobCreate, session: DatabaseSession
) -> SuccessResponse[CrawlJobCreated]:
    target = normalize_crawl_target(str(payload.url))
    website_repository = WebsiteRepository(session)
    job_repository = CrawlJobRepository(session)

    async with session.begin():
        website = await website_repository.get_by_domain(target.domain)
        if website is None:
            website = await website_repository.create(
                domain=target.domain, root_url=target.root_url
            )
        job = await job_repository.create(
            website_id=website.id,
            start_url=target.start_url,
            max_pages=payload.max_pages,
        )

    await _dispatch_or_mark_failed(session, job_repository, job)
    logger.info(
        "crawl_job_created",
        extra={"job_id": str(job.id), "website_id": str(website.id)},
    )
    return _created_response(job)


@router.get("", response_model=SuccessResponse[CrawlJobList])
async def list_crawl_jobs(
    session: DatabaseSession,
    website_id: uuid.UUID | None = None,
    job_status: Annotated[CrawlJobStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SuccessResponse[CrawlJobList]:
    repository = CrawlJobRepository(session)
    jobs = await repository.list(
        website_id=website_id, status=job_status, offset=offset, limit=limit
    )
    total = await repository.count(website_id=website_id, status=job_status)
    return SuccessResponse(
        data=CrawlJobList(
            items=[CrawlJobRead.model_validate(job) for job in jobs],
            total=total,
            offset=offset,
            limit=limit,
        )
    )


@router.get(
    "/{job_id}",
    response_model=SuccessResponse[CrawlJobRead],
    responses={404: ERROR_RESPONSES[404]},
)
async def get_crawl_job(
    job_id: uuid.UUID, session: DatabaseSession
) -> SuccessResponse[CrawlJobRead]:
    job = await CrawlJobRepository(session).get_by_id(job_id)
    if job is None:
        raise AppError(
            code="NOT_FOUND",
            message="Crawl job not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return SuccessResponse(data=CrawlJobRead.model_validate(job))


@router.post(
    "/{job_id}/retry",
    response_model=SuccessResponse[CrawlJobCreated],
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
async def retry_crawl_job(
    job_id: uuid.UUID, session: DatabaseSession
) -> SuccessResponse[CrawlJobCreated]:
    repository = CrawlJobRepository(session)
    async with session.begin():
        job = await repository.get_by_id(job_id)
        if job is None:
            raise AppError(
                code="NOT_FOUND",
                message="Crawl job not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if job.status is not CrawlJobStatus.FAILED:
            raise AppError(
                code="INVALID_JOB_STATE",
                message="Only failed crawl jobs can be retried",
                status_code=status.HTTP_409_CONFLICT,
            )
        await repository.reset_for_retry(job)

    await _dispatch_or_mark_failed(session, repository, job)
    logger.info("crawl_job_retried", extra={"job_id": str(job.id)})
    return _created_response(job)
