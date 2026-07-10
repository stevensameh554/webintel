from dataclasses import dataclass
from urllib.parse import urlsplit

from app.services.crawler.link_extractor import ExtractedLink

SOCIAL_DOMAINS = {
    "facebook": ("facebook.com",),
    "github": ("github.com",),
    "instagram": ("instagram.com",),
    "linkedin": ("linkedin.com",),
    "tiktok": ("tiktok.com",),
    "twitter": ("twitter.com", "x.com"),
    "youtube": ("youtube.com", "youtu.be"),
}
SHARE_PATH_PREFIXES = (
    "/dialog/share",
    "/intent/",
    "/share",
    "/sharer",
    "/sharing/",
)


@dataclass(frozen=True, slots=True)
class SocialLinkCandidate:
    platform: str
    url: str


def _platform_for_host(hostname: str) -> str | None:
    hostname = hostname.removeprefix("www.").removeprefix("m.")
    for platform, domains in SOCIAL_DOMAINS.items():
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains):
            return platform
    return None


def _is_profile_path(platform: str, path: str) -> bool:
    lowered = path.lower()
    if not lowered or lowered == "/" or lowered.startswith(SHARE_PATH_PREFIXES):
        return False
    if platform == "youtube" and lowered.startswith(("/watch", "/shorts/", "/results")):
        return False
    return True


def detect_social_links(links: list[ExtractedLink]) -> tuple[SocialLinkCandidate, ...]:
    candidates: dict[tuple[str, str], SocialLinkCandidate] = {}
    for link in links:
        parsed = urlsplit(link.normalized_target_url)
        if parsed.hostname is None:
            continue
        platform = _platform_for_host(parsed.hostname)
        if platform is None or not _is_profile_path(platform, parsed.path):
            continue
        key = (platform, link.normalized_target_url)
        candidates.setdefault(
            key,
            SocialLinkCandidate(platform=platform, url=link.normalized_target_url),
        )
    return tuple(candidates.values())
