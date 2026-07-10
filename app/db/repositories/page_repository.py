import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page


class PageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        website_id: uuid.UUID,
        crawl_job_id: uuid.UUID,
        url: str,
        normalized_url: str,
        crawled_at: datetime,
        title: str | None = None,
        meta_description: str | None = None,
        headings: list[dict[str, Any]] | None = None,
        status_code: int | None = None,
        content_type: str | None = None,
        response_time_ms: int | None = None,
        content_hash: str | None = None,
        page_size_bytes: int | None = None,
        text_preview: str | None = None,
        fetch_error: str | None = None,
    ) -> Page:
        page = Page(
            website_id=website_id,
            crawl_job_id=crawl_job_id,
            url=url,
            normalized_url=normalized_url,
            crawled_at=crawled_at,
            title=title,
            meta_description=meta_description,
            headings=headings or [],
            status_code=status_code,
            content_type=content_type,
            response_time_ms=response_time_ms,
            content_hash=content_hash,
            page_size_bytes=page_size_bytes,
            text_preview=text_preview,
            fetch_error=fetch_error,
        )
        self.session.add(page)
        await self.session.flush()
        return page

    async def get_by_id(self, page_id: uuid.UUID) -> Page | None:
        return await self.session.get(Page, page_id)

    async def list_for_website(
        self, website_id: uuid.UUID, *, offset: int = 0, limit: int = 100
    ) -> list[Page]:
        statement: Select[tuple[Page]] = (
            select(Page)
            .where(Page.website_id == website_id)
            .order_by(Page.crawled_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())
