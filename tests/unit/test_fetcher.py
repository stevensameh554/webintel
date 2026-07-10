import ipaddress

import httpcore
import httpx
import pytest

from app.services.crawler.fetcher import (
    FetchTimeoutError,
    PageFetcher,
    PinnedNetworkBackend,
    RedirectFetchError,
    ResponseTooLargeError,
)
from app.services.crawler.url_normalizer import (
    ResolvedPublicTarget,
    UnsafeTargetError,
    UrlNormalizationError,
    normalize_url,
)


async def approve_public(url: str) -> ResolvedPublicTarget:
    return ResolvedPublicTarget(
        url=normalize_url(url, reject_non_public_ip=True),
        addresses=(ipaddress.ip_address("93.184.216.34"),),
    )


def make_fetcher(
    handler: httpx.MockTransport,
    **kwargs: object,
) -> PageFetcher:
    return PageFetcher(
        user_agent="WebIntelBot/0.1",
        transport=handler,
        validator=approve_public,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_fetches_html_and_records_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "WebIntelBot/0.1"
        return httpx.Response(
            200,
            headers={"content-type": "Text/HTML; charset=utf-8", "content-length": "31"},
            content=b"<html><title>Acme</title></html>",
        )

    async with make_fetcher(httpx.MockTransport(handler)) as fetcher:
        result = await fetcher.fetch("https://EXAMPLE.com/")

    assert result.requested_url == "https://example.com"
    assert result.final_url == "https://example.com"
    assert result.status_code == 200
    assert result.content_type == "text/html"
    assert result.text == "<html><title>Acme</title></html>"
    assert result.is_html is True
    assert result.attempts == 1
    assert result.response_time_ms >= 0


@pytest.mark.asyncio
async def test_returns_404_html_response_without_raising() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            404,
            headers={"content-type": "text/html"},
            text="<h1>Missing</h1>",
        )
    )
    async with make_fetcher(transport) as fetcher:
        result = await fetcher.fetch("https://example.com/missing")

    assert result.status_code == 404
    assert result.text == "<h1>Missing</h1>"


@pytest.mark.asyncio
async def test_does_not_buffer_non_html_content() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "application/pdf", "content-length": "12000"},
            content=b"pdf bytes",
        )
    )
    async with make_fetcher(transport) as fetcher:
        result = await fetcher.fetch("https://example.com/brochure.pdf")

    assert result.content_type == "application/pdf"
    assert result.text is None
    assert result.content_length == 12000
    assert result.is_html is False


@pytest.mark.asyncio
async def test_validates_every_redirect_hop() -> None:
    validated: list[str] = []

    async def validator(url: str) -> ResolvedPublicTarget:
        validated.append(url)
        return await approve_public(url)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(301, headers={"location": "https://www.example.org/home"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

    async with PageFetcher(
        user_agent="WebIntelBot/0.1",
        transport=httpx.MockTransport(handler),
        validator=validator,
    ) as fetcher:
        result = await fetcher.fetch("https://example.com")

    assert validated == ["https://example.com", "https://www.example.org/home"]
    assert result.final_url == "https://www.example.org/home"
    assert result.redirect_chain == ("https://example.com",)
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_retries_transient_status_with_backoff() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = 503 if calls == 1 else 200
        return httpx.Response(status, headers={"content-type": "text/html"}, text="ok")

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with make_fetcher(httpx.MockTransport(handler), sleep=sleep) as fetcher:
        result = await fetcher.fetch("https://example.com")

    assert result.status_code == 200
    assert result.attempts == 2
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_raises_typed_timeout_after_retries() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow origin", request=request)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with make_fetcher(httpx.MockTransport(handler), sleep=sleep) as fetcher:
        with pytest.raises(FetchTimeoutError) as error:
            await fetcher.fetch("https://example.com")

    assert calls == 3
    assert delays == [1.0, 3.0]
    assert error.value.attempts == 3


class TimeoutStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise httpx.ReadTimeout("slow response body")
        yield b""  # pragma: no cover


@pytest.mark.asyncio
async def test_retries_timeout_while_streaming_response_body() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                stream=TimeoutStream(),
            )
        return httpx.Response(200, headers={"content-type": "text/html"}, text="ok")

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async with make_fetcher(httpx.MockTransport(handler), sleep=sleep) as fetcher:
        result = await fetcher.fetch("https://example.com")

    assert result.text == "ok"
    assert result.attempts == 2
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_rejects_invalid_url_before_transport() -> None:
    transport = httpx.MockTransport(lambda _request: pytest.fail("transport should not run"))
    async with make_fetcher(transport) as fetcher:
        with pytest.raises(UrlNormalizationError):
            await fetcher.fetch("not a URL")
        with pytest.raises(UnsafeTargetError):
            await fetcher.fetch("http://127.0.0.1/admin")


@pytest.mark.asyncio
async def test_rejects_redirect_to_private_address() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(302, headers={"location": "http://169.254.169.254"})
    )
    async with make_fetcher(transport) as fetcher:
        with pytest.raises(UnsafeTargetError):
            await fetcher.fetch("https://example.com")


@pytest.mark.asyncio
async def test_enforces_redirect_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params.get("n", "0"))
        return httpx.Response(302, headers={"location": f"/?n={number + 1}"})

    async with make_fetcher(httpx.MockTransport(handler), max_redirects=1) as fetcher:
        with pytest.raises(RedirectFetchError):
            await fetcher.fetch("https://example.com?n=0")


@pytest.mark.asyncio
async def test_enforces_html_response_size_limit() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 20,
        )
    )
    async with make_fetcher(transport, max_response_bytes=10) as fetcher:
        with pytest.raises(ResponseTooLargeError) as error:
            await fetcher.fetch("https://example.com")

    assert error.value.url == "https://example.com"


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(self, host: str, port: int, **_kwargs: object) -> object:
        self.hosts.append(host)
        return object()


@pytest.mark.asyncio
async def test_pinned_backend_connects_to_approved_ip_not_hostname() -> None:
    recording = RecordingBackend()
    backend = PinnedNetworkBackend(recording)
    backend.approve(await approve_public("https://example.com"))

    await backend.connect_tcp("example.com", 443)

    assert recording.hosts == ["93.184.216.34"]


@pytest.mark.asyncio
async def test_pinned_backend_rejects_unapproved_connection() -> None:
    backend = PinnedNetworkBackend(RecordingBackend())

    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("example.com", 443)
