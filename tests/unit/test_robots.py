import ipaddress

import httpx
import pytest

from app.services.crawler.fetcher import PageFetcher
from app.services.crawler.robots import RobotsPolicy
from app.services.crawler.url_normalizer import ResolvedPublicTarget, normalize_url


async def approve_public(url: str) -> ResolvedPublicTarget:
    return ResolvedPublicTarget(
        url=normalize_url(url, reject_non_public_ip=True),
        addresses=(ipaddress.ip_address("93.184.216.34"),),
    )


@pytest.mark.asyncio
async def test_robots_policy_blocks_disallowed_paths_and_is_cached() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url.path == "/robots.txt"
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="User-agent: WebIntelBot\nDisallow: /private\nCrawl-delay: 2",
        )

    async with PageFetcher(
        user_agent="WebIntelBot/0.1",
        validator=approve_public,
        transport=httpx.MockTransport(handler),
    ) as fetcher:
        policy = RobotsPolicy(fetcher, user_agent="WebIntelBot/0.1")
        private = await policy.check("https://example.com/private/report")
        public = await policy.check("https://example.com/about")

    assert private.allowed is False
    assert private.crawl_delay_seconds == 2.0
    assert public.allowed is True
    assert requests == 1


@pytest.mark.asyncio
async def test_missing_robots_file_allows_crawling() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(404))
    async with PageFetcher(
        user_agent="WebIntelBot/0.1",
        validator=approve_public,
        transport=transport,
    ) as fetcher:
        policy = RobotsPolicy(fetcher, user_agent="WebIntelBot/0.1")

        assert await policy.can_fetch("https://example.com/anything") is True
