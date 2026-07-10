import asyncio
import ipaddress
import posixpath
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

MAX_URL_LENGTH = 4096
ALLOWED_SCHEMES = frozenset({"http", "https"})
TRACKING_PARAMETERS = frozenset(
    {
        "dclid",
        "fbclid",
        "gclid",
        "gbraid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "twclid",
        "wbraid",
    }
)
UNRESERVED_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
PERCENT_ESCAPE = re.compile(r"%([0-9a-fA-F]{2})")
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
CONTROL_OR_SPACE = re.compile(r"[\x00-\x20\x7f]")
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[Iterable[str]]]


class UrlNormalizationError(ValueError):
    """Raised when a URL cannot be safely canonicalized."""


class UnsafeTargetError(UrlNormalizationError):
    """Raised when a target resolves to a non-public network address."""


class HostResolutionError(UrlNormalizationError):
    """Raised when a target hostname cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ResolvedPublicTarget:
    url: str
    addresses: tuple[IPAddress, ...]


@dataclass(frozen=True, slots=True)
class CrawlScope:
    hostname: str

    @classmethod
    def from_url(cls, url: str) -> "CrawlScope":
        normalized = normalize_url(url)
        hostname = urlsplit(normalized).hostname
        if hostname is None:
            raise UrlNormalizationError("URL does not contain a hostname")
        return cls(hostname=hostname)

    def contains(self, url: str) -> bool:
        try:
            normalized = normalize_url(url)
        except UrlNormalizationError:
            return False
        return urlsplit(normalized).hostname == self.hostname


def _canonicalize_hostname(hostname: str) -> str:
    try:
        canonical = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UrlNormalizationError("URL contains an invalid hostname") from exc
    if not canonical:
        raise UrlNormalizationError("URL does not contain a hostname")
    return canonical


def _normalize_percent_encoding(value: str) -> str:
    if INVALID_PERCENT_ESCAPE.search(value):
        raise UrlNormalizationError("URL contains an invalid percent escape")

    def replace(match: re.Match[str]) -> str:
        byte = int(match.group(1), 16)
        character = chr(byte)
        return character if character in UNRESERVED_CHARACTERS else f"%{byte:02X}"

    return PERCENT_ESCAPE.sub(replace, value)


def _normalize_path(path: str) -> str:
    if not path or path == "/":
        return ""
    normalized = posixpath.normpath(_normalize_percent_encoding(path))
    if path.startswith("/") and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized in {".", "/"}:
        return ""
    return normalized.rstrip("/")


def _normalize_query(query: str) -> str:
    if not query:
        return ""
    if INVALID_PERCENT_ESCAPE.search(query):
        raise UrlNormalizationError("URL contains an invalid percent escape")
    parameters = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    parameters.sort(key=lambda item: (item[0], item[1]))
    return urlencode(parameters, doseq=True)


def _direct_address(hostname: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def _ensure_public_address(address: IPAddress) -> None:
    if not address.is_global:
        raise UnsafeTargetError(
            f"Target address {address} is private, loopback, link-local, or otherwise non-public"
        )


def normalize_url(
    value: str,
    base_url: str | None = None,
    *,
    reject_non_public_ip: bool = False,
) -> str:
    """Resolve and canonicalize an HTTP(S) URL for deduplication."""

    candidate = unescape(value).strip()
    if not candidate or len(candidate) > MAX_URL_LENGTH:
        raise UrlNormalizationError("URL is empty or exceeds the maximum length")
    if CONTROL_OR_SPACE.search(candidate):
        raise UrlNormalizationError("URL contains whitespace or control characters")
    if base_url is not None:
        raw_base = unescape(base_url).strip()
        normalized_base = normalize_url(raw_base)
        if urlsplit(raw_base).path.endswith("/") and urlsplit(normalized_base).path:
            normalized_base = f"{normalized_base}/"
        candidate = urljoin(normalized_base, candidate)

    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        raise UrlNormalizationError("URL must use HTTP or HTTPS and include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UrlNormalizationError("URLs containing credentials are not allowed")

    hostname = _canonicalize_hostname(parsed.hostname)
    try:
        port = parsed.port
    except ValueError as exc:
        raise UrlNormalizationError("URL contains an invalid port") from exc

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeTargetError("Localhost targets are not allowed")
    direct_address = _direct_address(hostname)
    if direct_address is None:
        labels = hostname.split(".")
        if (
            len(hostname) > 253
            or len(labels) < 2
            or any(not DNS_LABEL.fullmatch(label) for label in labels)
        ):
            raise UrlNormalizationError("URL contains an invalid public hostname")
    if reject_non_public_ip and direct_address is not None:
        _ensure_public_address(direct_address)

    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port is None or default_port else f"{display_host}:{port}"
    path = _normalize_path(parsed.path)
    query = _normalize_query(parsed.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def is_internal_url(url: str, root_url: str) -> bool:
    """Return whether a URL has the exact crawl hostname."""

    try:
        return CrawlScope.from_url(root_url).contains(url)
    except UrlNormalizationError:
        return False


async def _system_resolver(hostname: str, port: int) -> Iterable[str]:
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise HostResolutionError(f"Could not resolve hostname {hostname}") from exc
    return [record[4][0] for record in records]


async def validate_public_url(
    url: str, *, resolver: Resolver | None = None
) -> ResolvedPublicTarget:
    """Resolve a URL and reject it if any returned address is not globally routable."""

    normalized = normalize_url(url, reject_non_public_ip=True)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname
    if hostname is None:
        raise UrlNormalizationError("URL does not contain a hostname")

    direct_address = _direct_address(hostname)
    if direct_address is not None:
        return ResolvedPublicTarget(url=normalized, addresses=(direct_address,))

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address_values = await (resolver or _system_resolver)(hostname, port)
    addresses: list[IPAddress] = []
    for value in address_values:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise HostResolutionError(f"Resolver returned invalid address {value}") from exc
        _ensure_public_address(address)
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise HostResolutionError(f"Hostname {hostname} did not resolve to an address")
    return ResolvedPublicTarget(url=normalized, addresses=tuple(addresses))
