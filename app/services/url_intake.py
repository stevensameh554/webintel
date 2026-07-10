import ipaddress
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from fastapi import status

from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class NormalizedTarget:
    domain: str
    root_url: str
    start_url: str


def _validation_error(message: str) -> AppError:
    return AppError(
        code="VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def normalize_crawl_target(raw_url: str) -> NormalizedTarget:
    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise _validation_error("URL must use HTTP or HTTPS and include a hostname")
    if parsed.username or parsed.password:
        raise _validation_error("URLs containing credentials are not allowed")

    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise _validation_error("URL contains an invalid hostname or port") from exc

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise _validation_error("Local network targets are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise _validation_error("Private, loopback, and link-local targets are not allowed")

    scheme = parsed.scheme.lower()
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = display_host if port is None or default_port else f"{display_host}:{port}"
    root_url = urlunsplit(SplitResult(scheme, netloc, "", "", ""))
    path = parsed.path.rstrip("/") if parsed.path not in {"", "/"} else ""
    start_url = urlunsplit(SplitResult(scheme, netloc, path, parsed.query, ""))
    return NormalizedTarget(domain=hostname, root_url=root_url, start_url=start_url)
