from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Comment

from app.services.crawler.email_extractor import NON_VISIBLE_TAGS, extract_emails
from app.services.crawler.important_page_detector import (
    ImportantPageCandidate,
    detect_important_pages,
)
from app.services.crawler.link_extractor import ExtractedLink, extract_links
from app.services.crawler.social_link_detector import SocialLinkCandidate, detect_social_links


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class ParsedPage:
    title: str | None
    meta_description: str | None
    headings: tuple[Heading, ...]
    emails: tuple[str, ...]
    social_links: tuple[SocialLinkCandidate, ...]
    important_pages: tuple[ImportantPageCandidate, ...]
    links: tuple[ExtractedLink, ...]
    text_preview: str | None


def _clean_text(value: str, *, limit: int | None = None) -> str | None:
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return cleaned[:limit] if limit is not None else cleaned


def _meta_description(soup: BeautifulSoup) -> str | None:
    fallback: str | None = None
    for meta in soup.find_all("meta"):
        content = meta.get("content")
        if not isinstance(content, str):
            continue
        name = meta.get("name")
        property_name = meta.get("property")
        if isinstance(name, str) and name.lower() == "description":
            return _clean_text(content, limit=2000)
        if isinstance(property_name, str) and property_name.lower() == "og:description":
            fallback = _clean_text(content, limit=2000)
    return fallback


def _headings(soup: BeautifulSoup) -> tuple[Heading, ...]:
    headings: list[Heading] = []
    for element in soup.find_all(["h1", "h2", "h3"]):
        text = _clean_text(element.get_text(" ", strip=True), limit=1000)
        if text is not None:
            headings.append(Heading(level=int(element.name[1]), text=text))
    return tuple(headings)


def _visible_text(soup: BeautifulSoup, limit: int) -> str | None:
    parts: list[str] = []
    for node in soup.find_all(string=True):
        if isinstance(node, Comment) or node.parent is None or node.parent.name in NON_VISIBLE_TAGS:
            continue
        cleaned = _clean_text(str(node))
        if cleaned is not None:
            parts.append(cleaned)
    return _clean_text(" ".join(parts), limit=limit)


def parse_html(
    html: str,
    *,
    page_url: str,
    crawl_root_url: str | None = None,
    text_preview_limit: int = 1000,
) -> ParsedPage:
    if text_preview_limit < 1:
        raise ValueError("text_preview_limit must be positive")

    soup = BeautifulSoup(html, "lxml")
    links = extract_links(html, page_url=page_url, crawl_root_url=crawl_root_url)
    title = _clean_text(soup.title.get_text(" ", strip=True), limit=512) if soup.title else None
    return ParsedPage(
        title=title,
        meta_description=_meta_description(soup),
        headings=_headings(soup),
        emails=extract_emails(soup),
        social_links=detect_social_links(links),
        important_pages=detect_important_pages(links),
        links=tuple(links),
        text_preview=_visible_text(soup, text_preview_limit),
    )
