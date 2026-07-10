import uuid
from datetime import datetime

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.db.models import CrawlJobStatus


class CrawlJobCreate(BaseModel):
    url: AnyHttpUrl
    max_pages: int = Field(default=20, ge=1, le=100)


class CrawlJobCreated(BaseModel):
    job_id: uuid.UUID
    website_id: uuid.UUID
    status: CrawlJobStatus


class CrawlJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    website_id: uuid.UUID
    start_url: str
    status: CrawlJobStatus
    max_pages: int
    pages_crawled: int
    pages_failed: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CrawlJobList(BaseModel):
    items: list[CrawlJobRead]
    total: int
    offset: int
    limit: int
