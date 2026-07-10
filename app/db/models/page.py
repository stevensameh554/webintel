from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.crawl_job import CrawlJob
    from app.db.models.email import Email
    from app.db.models.link import Link
    from app.db.models.website import Website


class Page(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("crawl_job_id", "normalized_url", name="uq_pages_job_normalized_url"),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    meta_description: Mapped[str | None] = mapped_column(Text)
    headings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status_code: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    page_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    text_preview: Mapped[str | None] = mapped_column(Text)
    fetch_error: Mapped[str | None] = mapped_column(Text)
    crawled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    website: Mapped[Website] = relationship(back_populates="pages")
    crawl_job: Mapped[CrawlJob] = relationship(back_populates="pages")
    links: Mapped[list[Link]] = relationship(
        back_populates="source_page", cascade="all, delete-orphan", passive_deletes=True
    )
    emails: Mapped[list[Email]] = relationship(back_populates="page")
