import pytest

from app.core.errors import AppError
from app.services.url_intake import normalize_crawl_target


def test_normalizes_crawl_target() -> None:
    target = normalize_crawl_target("HTTPS://Example.COM:443/about/#team")

    assert target.domain == "example.com"
    assert target.root_url == "https://example.com"
    assert target.start_url == "https://example.com/about"


def test_preserves_nondefault_port_and_query() -> None:
    target = normalize_crawl_target("http://Example.com:8080/search/?q=webintel#results")

    assert target.root_url == "http://example.com:8080"
    assert target.start_url == "http://example.com:8080/search?q=webintel"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://api.localhost",
        "http://127.0.0.1",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1",
        "https://user:password@example.com",
    ],
)
def test_rejects_unsafe_explicit_targets(url: str) -> None:
    with pytest.raises(AppError) as error:
        normalize_crawl_target(url)

    assert error.value.code == "VALIDATION_ERROR"
