import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.db.models import ImportantPageType
from app.services.crawler.link_extractor import ExtractedLink

PAGE_KEYWORDS = {
    ImportantPageType.PRICING: {"pricing", "plans"},
    ImportantPageType.CAREERS: {"careers", "jobs", "vacancies"},
    ImportantPageType.BLOG: {"blog", "news", "insights"},
    ImportantPageType.CONTACT: {"contact", "contact-us"},
    ImportantPageType.ABOUT: {"about", "about-us", "company"},
    ImportantPageType.DOCS: {"docs", "documentation", "developers"},
    ImportantPageType.LOGIN: {"login", "log-in", "signin", "sign-in"},
    ImportantPageType.SIGNUP: {"signup", "sign-up", "register"},
    ImportantPageType.TERMS: {"terms", "terms-of-service", "terms-of-use"},
    ImportantPageType.PRIVACY: {"privacy", "privacy-policy"},
}


@dataclass(frozen=True, slots=True)
class ImportantPageCandidate:
    page_type: ImportantPageType
    url: str
    confidence: float


def _tokens(value: str) -> set[str]:
    lowered = value.lower().strip()
    words = set(re.findall(r"[a-z0-9]+", lowered))
    if lowered:
        words.add(re.sub(r"\s+", "-", lowered))
    return words


def _confidence(link: ExtractedLink, keywords: set[str]) -> float:
    path_segments = [
        unquote(segment).lower()
        for segment in urlsplit(link.normalized_target_url).path.split("/")
        if segment
    ]
    path_match = bool(path_segments and path_segments[-1] in keywords)
    text_match = bool(link.link_text and _tokens(link.link_text) & keywords)
    if path_match and text_match:
        return 0.99
    if path_match:
        return 0.95
    if text_match:
        return 0.8
    return 0.0


def detect_important_pages(
    links: list[ExtractedLink],
) -> tuple[ImportantPageCandidate, ...]:
    candidates: dict[tuple[ImportantPageType, str], ImportantPageCandidate] = {}
    for link in links:
        if not link.is_internal:
            continue
        for page_type, keywords in PAGE_KEYWORDS.items():
            confidence = _confidence(link, keywords)
            if confidence == 0:
                continue
            key = (page_type, link.normalized_target_url)
            existing = candidates.get(key)
            if existing is None or confidence > existing.confidence:
                candidates[key] = ImportantPageCandidate(
                    page_type=page_type,
                    url=link.normalized_target_url,
                    confidence=confidence,
                )
    return tuple(candidates.values())
