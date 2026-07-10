from pathlib import Path

import pytest

from app.db.models import ImportantPageType
from app.services.crawler.parser import parse_html

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_parses_company_homepage_fixture() -> None:
    html = (FIXTURES / "company_homepage.html").read_text(encoding="utf-8")

    page = parse_html(
        html,
        page_url="https://example.com",
        crawl_root_url="https://example.com",
    )

    assert page.title == "Acme Intelligence"
    assert page.meta_description == "Acme helps teams understand public company data."
    assert [(heading.level, heading.text) for heading in page.headings] == [
        (1, "Company intelligence, simplified"),
        (2, "Research with confidence"),
        (3, "Built for data teams"),
    ]
    assert page.emails == (
        "team@example.com",
        "sales@example.com",
        "partners@example.com",
    )
    assert [item.platform for item in page.social_links] == [
        "linkedin",
        "twitter",
        "github",
        "youtube",
    ]
    important_types = {item.page_type for item in page.important_pages}
    assert important_types == set(ImportantPageType) - {ImportantPageType.CAREERS}
    assert all("software-engineer" not in item.url for item in page.important_pages)
    assert "secret@script.example" not in (page.text_preview or "")
    assert "fake@style.example" not in (page.text_preview or "")


def test_parses_malformed_html_and_og_description_fallback() -> None:
    html = (FIXTURES / "malformed_page.html").read_text(encoding="utf-8")

    page = parse_html(html, page_url="https://example.org")

    assert page.title == "Broken page"
    assert page.meta_description == "Description from Open Graph."
    assert page.headings[0].text == "Still parseable See plans Write to support@example.org"
    assert page.emails == ("support@example.org",)
    assert page.important_pages[0].page_type is ImportantPageType.PRICING


def test_limits_text_preview_and_rejects_invalid_limit() -> None:
    page = parse_html(
        "<title>Example</title><p>One two three four</p>",
        page_url="https://example.com",
        text_preview_limit=11,
    )

    assert page.text_preview == "Example One"
    with pytest.raises(ValueError, match="positive"):
        parse_html("", page_url="https://example.com", text_preview_limit=0)


def test_handles_empty_document() -> None:
    page = parse_html("", page_url="https://example.com")

    assert page.title is None
    assert page.meta_description is None
    assert page.headings == ()
    assert page.emails == ()
    assert page.links == ()
    assert page.text_preview is None
