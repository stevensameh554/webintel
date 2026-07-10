import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.services.crawler.fetcher import FetchError, PageFetcher
from app.services.crawler.url_normalizer import UrlNormalizationError, normalize_url

logger = logging.getLogger(__name__)
ROBOTS_CONTENT_TYPES = frozenset({"text/plain", "text/html", "application/octet-stream"})


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    crawl_delay_seconds: float | None


class RobotsPolicy:
    """Load and cache one robots.txt policy per origin for a crawl."""

    def __init__(self, fetcher: PageFetcher, *, user_agent: str) -> None:
        self._fetcher = fetcher
        self._user_agent = user_agent.split("/", maxsplit=1)[0]
        self._policies: dict[str, RobotFileParser] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def check(self, url: str) -> RobotsDecision:
        normalized = normalize_url(url, reject_non_public_ip=True)
        origin = _origin(normalized)
        policy = await self._policy_for(origin)
        delay = policy.crawl_delay(self._user_agent)
        return RobotsDecision(
            allowed=policy.can_fetch(self._user_agent, normalized),
            crawl_delay_seconds=float(delay) if delay is not None else None,
        )

    async def can_fetch(self, url: str) -> bool:
        return (await self.check(url)).allowed

    async def _policy_for(self, origin: str) -> RobotFileParser:
        if origin in self._policies:
            return self._policies[origin]
        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin not in self._policies:
                self._policies[origin] = await self._load(origin)
        return self._policies[origin]

    async def _load(self, origin: str) -> RobotFileParser:
        robots_url = f"{origin}/robots.txt"
        policy = RobotFileParser(robots_url)
        try:
            result = await self._fetcher.fetch(
                robots_url,
                accepted_content_types=ROBOTS_CONTENT_TYPES,
            )
        except (FetchError, UrlNormalizationError) as exc:
            logger.warning("robots_fetch_failed", extra={"url": robots_url, "error": str(exc)})
            policy.parse(["User-agent: *", "Allow: /"])
            return policy

        if 200 <= result.status_code < 300 and result.text is not None:
            policy.parse(result.text.splitlines())
        else:
            policy.parse(["User-agent: *", "Allow: /"])
        return policy


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
