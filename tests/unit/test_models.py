from sqlalchemy import Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base
from app.db.models import CrawlJob, CrawlJobStatus, Page


def test_metadata_contains_complete_phase_two_schema() -> None:
    assert set(Base.metadata.tables) == {
        "websites",
        "crawl_jobs",
        "pages",
        "links",
        "emails",
        "social_links",
        "technologies",
        "important_pages",
    }


def test_page_urls_are_unique_within_a_crawl_job() -> None:
    unique_constraints = {
        constraint.name
        for constraint in Page.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_pages_job_normalized_url" in unique_constraints


def test_postgresql_specific_extraction_types_are_configured() -> None:
    assert isinstance(Page.__table__.c.headings.type, JSONB)
    assert Page.__table__.c.crawled_at.type.timezone is True


def test_crawl_status_enum_uses_api_values() -> None:
    status_type = CrawlJob.__table__.c.status.type

    assert isinstance(status_type, Enum)
    assert status_type.enums == [status.value for status in CrawlJobStatus]
