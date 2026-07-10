from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.crawl_job import CrawlJob
    from app.db.models.email import Email
    from app.db.models.important_page import ImportantPage
    from app.db.models.page import Page
    from app.db.models.social_link import SocialLink
    from app.db.models.technology import Technology


class Website(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "websites"

    domain: Mapped[str] = mapped_column(String(253), nullable=False, unique=True, index=True)
    root_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    has_email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    has_pricing_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    has_careers_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    has_blog: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    has_contact_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    crawl_jobs: Mapped[list[CrawlJob]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
    pages: Mapped[list[Page]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
    emails: Mapped[list[Email]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
    social_links: Mapped[list[SocialLink]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
    technologies: Mapped[list[Technology]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
    important_pages: Mapped[list[ImportantPage]] = relationship(
        back_populates="website", cascade="all, delete-orphan", passive_deletes=True
    )
