from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import CrawlJobStatus

if TYPE_CHECKING:
    from app.db.models.page import Page
    from app.db.models.website import Website


class CrawlJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        CheckConstraint("max_pages BETWEEN 1 AND 100", name="max_pages_range"),
        CheckConstraint("pages_crawled >= 0", name="pages_crawled_nonnegative"),
        CheckConstraint("pages_failed >= 0", name="pages_failed_nonnegative"),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CrawlJobStatus] = mapped_column(
        Enum(
            CrawlJobStatus,
            name="crawl_job_status",
            values_callable=lambda enum: [e.value for e in enum],
        ),
        nullable=False,
        default=CrawlJobStatus.QUEUED,
        server_default=CrawlJobStatus.QUEUED.value,
        index=True,
    )
    max_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default=text("20")
    )
    pages_crawled: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    pages_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    website: Mapped[Website] = relationship(back_populates="crawl_jobs")
    pages: Mapped[list[Page]] = relationship(
        back_populates="crawl_job", cascade="all, delete-orphan", passive_deletes=True
    )
