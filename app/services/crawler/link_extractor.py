from dataclasses import dataclass
from html import unescape
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup

from app.services.crawler.url_normalizer import (
    CrawlScope,
    UrlNormalizationError,
    normalize_url,
)


@dataclass(frozen=True, slots=True)
class ExtractedLink:
    target_url: str
    normalized_target_url: str
    link_text: str | None
    is_internal: bool


def _document_base(soup: BeautifulSoup, page_url: str) -> str:
    base_element = soup.find("base", href=True)
    if base_element is None:
        return page_url
    href = base_element.get("href")
    if not isinstance(href, str):
        return page_url
    try:
        absolute_base = urljoin(page_url, unescape(href).strip())
        normalize_url(absolute_base)
        return absolute_base
    except UrlNormalizationError:
        return page_url


def extract_links(
    html: str,
    *,
    page_url: str,
    crawl_root_url: str | None = None,
) -> list[ExtractedLink]:
    """Extract unique, crawlable HTTP(S) anchors in document order."""

    normalized_page_url = normalize_url(page_url)
    scope = CrawlScope.from_url(crawl_root_url or normalized_page_url)
    soup = BeautifulSoup(html, "lxml")
    resolution_base = _document_base(soup, page_url)
    links_by_url: dict[str, ExtractedLink] = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        href = unescape(href).strip()
        if not href or href.startswith("#"):
            continue
        try:
            normalized_target = normalize_url(href, resolution_base)
        except UrlNormalizationError:
            continue
        if normalized_target in links_by_url:
            continue

        resolved_target = urldefrag(urljoin(resolution_base, href))[0]
        text = " ".join(anchor.get_text(" ", strip=True).split())[:1024] or None
        links_by_url[normalized_target] = ExtractedLink(
            target_url=resolved_target,
            normalized_target_url=normalized_target,
            link_text=text,
            is_internal=scope.contains(normalized_target),
        )

    return list(links_by_url.values())
