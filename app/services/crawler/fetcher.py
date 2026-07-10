import asyncio
import ssl
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from time import monotonic
from urllib.parse import urlsplit

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

from app.core.config import Settings
from app.services.crawler.url_normalizer import (
    ResolvedPublicTarget,
    normalize_url,
    validate_public_url,
)

HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
DEFAULT_RETRY_BACKOFF_SECONDS = (1.0, 3.0, 5.0, 10.0, 20.0)

UrlValidator = Callable[[str], Awaitable[ResolvedPublicTarget]]
Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    text: str | None
    response_time_ms: int
    attempts: int
    redirect_chain: tuple[str, ...]
    content_length: int | None

    @property
    def is_html(self) -> bool:
        return self.content_type in HTML_CONTENT_TYPES


@dataclass(frozen=True, slots=True)
class _FetchedResponse:
    status_code: int
    headers: httpx.Headers
    content_type: str | None
    text: str | None


class FetchError(RuntimeError):
    def __init__(self, message: str, *, url: str, attempts: int, response_time_ms: int) -> None:
        super().__init__(message)
        self.url = url
        self.attempts = attempts
        self.response_time_ms = response_time_ms


class FetchTimeoutError(FetchError):
    """Raised after all timeout retries are exhausted."""


class FetchNetworkError(FetchError):
    """Raised after all transport retries are exhausted."""


class RedirectFetchError(FetchError):
    """Raised for an invalid redirect or an excessive redirect chain."""


class ResponseTooLargeError(FetchError):
    """Raised before a response can exceed the configured in-memory limit."""


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect hostnames only to addresses approved by URL validation."""

    def __init__(self, backend: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._backend = backend or AutoBackend()
        self._approved: dict[tuple[str, int], tuple[str, ...]] = {}

    def approve(self, target: ResolvedPublicTarget) -> None:
        parsed = urlsplit(target.url)
        if parsed.hostname is None:
            raise ValueError("Approved target does not have a hostname")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._approved[(parsed.hostname, port)] = tuple(
            str(address) for address in target.addresses
        )

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - required httpcore interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        addresses = self._approved.get((host, port))
        if not addresses:
            raise httpcore.ConnectError(f"No validated address is approved for {host}:{port}")

        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:  # httpcore backends expose several connection errors.
                last_error = exc
        assert last_error is not None
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - required httpcore interface
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not supported by the crawler")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose TCP backend uses prevalidated IP addresses."""

    def __init__(self, backend: PinnedNetworkBackend) -> None:
        super().__init__(verify=ssl.create_default_context(), trust_env=False, retries=0)
        # HTTPX 0.28 builds this pool internally; its version is intentionally pinned.
        self._pool._network_backend = backend


class PageFetcher:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 10.0,
        retries: int = 2,
        max_redirects: int = 5,
        max_response_bytes: int = 5_000_000,
        retry_backoff_seconds: tuple[float, ...] = DEFAULT_RETRY_BACKOFF_SECONDS,
        validator: UrlValidator = validate_public_url,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("user_agent must not be empty")
        if timeout_seconds <= 0 or retries < 0 or max_redirects < 0 or max_response_bytes < 1:
            raise ValueError("fetch limits must be positive")
        if retries > len(retry_backoff_seconds):
            raise ValueError("retry_backoff_seconds must include one delay per retry")

        self._validator = validator
        self._sleep = sleep
        self._retries = retries
        self._max_redirects = max_redirects
        self._max_response_bytes = max_response_bytes
        self._backoffs = retry_backoff_seconds
        self._pinned_backend: PinnedNetworkBackend | None = None
        if transport is None:
            self._pinned_backend = PinnedNetworkBackend()
            transport = PinnedAsyncHTTPTransport(self._pinned_backend)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            },
        )

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: object) -> "PageFetcher":
        return cls(
            user_agent=settings.crawler_user_agent,
            timeout_seconds=settings.fetch_timeout_seconds,
            retries=settings.fetch_retries,
            max_redirects=settings.fetch_max_redirects,
            max_response_bytes=settings.fetch_max_response_bytes,
            **kwargs,
        )

    async def __aenter__(self) -> "PageFetcher":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        accepted_content_types: frozenset[str] = HTML_CONTENT_TYPES,
    ) -> FetchResult:
        started = monotonic()
        requested_url = normalize_url(url, reject_non_public_ip=True)
        current_url = requested_url
        redirect_chain: list[str] = []
        total_attempts = 0

        while True:
            target = await self._validator(current_url)
            current_url = target.url
            if self._pinned_backend is not None:
                self._pinned_backend.approve(target)

            try:
                response, attempts = await self._request_with_retries(
                    current_url,
                    accepted_content_types=accepted_content_types,
                )
            except ResponseTooLargeError as exc:
                raise ResponseTooLargeError(
                    str(exc),
                    url=current_url,
                    attempts=total_attempts + exc.attempts,
                    response_time_ms=_elapsed_ms(started),
                ) from exc
            except httpx.TimeoutException as exc:
                attempts = self._retries + 1
                raise FetchTimeoutError(
                    f"Timed out fetching {current_url} after {attempts} attempts",
                    url=current_url,
                    attempts=total_attempts + attempts,
                    response_time_ms=_elapsed_ms(started),
                ) from exc
            except httpx.TransportError as exc:
                attempts = self._retries + 1
                raise FetchNetworkError(
                    f"Network error fetching {current_url} after {attempts} attempts",
                    url=current_url,
                    attempts=total_attempts + attempts,
                    response_time_ms=_elapsed_ms(started),
                ) from exc

            total_attempts += attempts
            location = response.headers.get("location")
            if response.status_code in REDIRECT_STATUS_CODES and location:
                if len(redirect_chain) >= self._max_redirects:
                    raise RedirectFetchError(
                        f"Redirect limit of {self._max_redirects} exceeded",
                        url=current_url,
                        attempts=total_attempts,
                        response_time_ms=_elapsed_ms(started),
                    )
                redirect_chain.append(current_url)
                current_url = normalize_url(location, base_url=current_url)
                continue

            return FetchResult(
                requested_url=requested_url,
                final_url=current_url,
                status_code=response.status_code,
                content_type=response.content_type,
                text=response.text,
                response_time_ms=_elapsed_ms(started),
                attempts=total_attempts,
                redirect_chain=tuple(redirect_chain),
                content_length=_content_length(response.headers.get("content-length")),
            )

    async def _request_with_retries(
        self,
        url: str,
        *,
        accepted_content_types: frozenset[str],
    ) -> tuple[_FetchedResponse, int]:
        for attempt in range(self._retries + 1):
            response: httpx.Response | None = None
            try:
                request = self._client.build_request("GET", url)
                response = await self._client.send(request, stream=True)
                if response.status_code in TRANSIENT_STATUS_CODES and attempt < self._retries:
                    await response.aclose()
                    response = None
                    await self._sleep(self._backoffs[attempt])
                    continue

                content_type = _media_type(response.headers.get("content-type"))
                text = None
                is_redirect = response.status_code in REDIRECT_STATUS_CODES and bool(
                    response.headers.get("location")
                )
                if not is_redirect and content_type in accepted_content_types:
                    content = await _read_limited(response, self._max_response_bytes)
                    encoding = response.encoding or "utf-8"
                    text = content.decode(encoding, errors="replace")
                return (
                    _FetchedResponse(
                        status_code=response.status_code,
                        headers=response.headers,
                        content_type=content_type,
                        text=text,
                    ),
                    attempt + 1,
                )
            except ResponseTooLargeError as exc:
                raise ResponseTooLargeError(
                    str(exc),
                    url=url,
                    attempts=attempt + 1,
                    response_time_ms=0,
                ) from exc
            except (httpx.TimeoutException, httpx.TransportError):
                if response is not None:
                    await response.aclose()
                    response = None
                if attempt >= self._retries:
                    raise
                await self._sleep(self._backoffs[attempt])
            finally:
                if response is not None:
                    await response.aclose()
        raise AssertionError("retry loop did not return or raise")


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    declared_length = _content_length(response.headers.get("content-length"))
    if declared_length is not None and declared_length > limit:
        raise ResponseTooLargeError(
            f"Response exceeds the {limit}-byte limit",
            url=str(response.url),
            attempts=1,
            response_time_ms=0,
        )

    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise ResponseTooLargeError(
                f"Response exceeds the {limit}-byte limit",
                url=str(response.url),
                attempts=1,
                response_time_ms=0,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _media_type(value: str | None) -> str | None:
    if value is None:
        return None
    media_type = value.partition(";")[0].strip().lower()
    return media_type or None


def _content_length(value: str | None) -> int | None:
    try:
        length = int(value) if value is not None else None
    except ValueError:
        return None
    return length if length is not None and length >= 0 else None


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
