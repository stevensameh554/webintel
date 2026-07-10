from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from fastapi import status

from app.core.errors import AppError
from app.services.crawler.url_normalizer import UrlNormalizationError, normalize_url


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
    try:
        start_url = normalize_url(raw_url, reject_non_public_ip=True)
    except UrlNormalizationError as exc:
        raise _validation_error(str(exc)) from exc

    parsed = urlsplit(start_url)
    if parsed.hostname is None:
        raise _validation_error("URL does not contain a hostname")
    root_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return NormalizedTarget(domain=parsed.hostname, root_url=root_url, start_url=start_url)
