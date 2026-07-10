import ipaddress

import pytest

from app.services.crawler.url_normalizer import (
    CrawlScope,
    HostResolutionError,
    UnsafeTargetError,
    UrlNormalizationError,
    is_internal_url,
    normalize_url,
    validate_public_url,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Example.COM:443/", "https://example.com"),
        ("http://Example.COM:80/about/", "http://example.com/about"),
        ("https://example.com/a/../pricing/", "https://example.com/pricing"),
        ("https://example.com/%7euser/%2f", "https://example.com/~user/%2F"),
        ("https://example.com?a=2&utm_source=x&b=&a=1", "https://example.com?a=1&a=2&b="),
        ("https://example.com/page#section", "https://example.com/page"),
        ("https://BÜCHER.example/", "https://xn--bcher-kva.example"),
    ],
)
def test_normalizes_canonical_urls(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected
    assert normalize_url(expected) == expected


def test_resolves_relative_url_using_directory_semantics() -> None:
    result = normalize_url(
        "../Pricing/?utm_medium=email&plan=pro",
        "https://example.com/products/current/",
    )

    assert result == "https://example.com/products/Pricing?plan=pro"


@pytest.mark.parametrize(
    "url",
    [
        "mailto:team@example.com",
        "javascript:alert(1)",
        "ftp://example.com/file",
        "https://user:password@example.com",
        "https://example.com:99999",
        "https://example.com/bad%escape",
        "https://example.com/a path",
        "https://intranet/dashboard",
        "https://bad_label.example.com",
        "https://-bad.example.com",
        "https://example..com",
        "",
    ],
)
def test_rejects_invalid_or_ignored_urls(url: str) -> None:
    with pytest.raises(UrlNormalizationError):
        normalize_url(url)


def test_crawl_scope_uses_exact_hostname_but_allows_scheme_change() -> None:
    scope = CrawlScope.from_url("http://www.example.com")

    assert scope.contains("https://www.example.com/pricing") is True
    assert scope.contains("https://example.com/pricing") is False
    assert scope.contains("https://blog.www.example.com") is False
    assert is_internal_url("https://www.example.com/about", "http://www.example.com") is True


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://10.0.0.10",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]",
    ],
)
def test_rejects_nonpublic_literal_addresses(url: str) -> None:
    with pytest.raises(UnsafeTargetError):
        normalize_url(url, reject_non_public_ip=True)


@pytest.mark.asyncio
async def test_validates_all_resolved_addresses() -> None:
    async def public_resolver(hostname: str, port: int) -> list[str]:
        assert hostname == "example.com"
        assert port == 443
        return ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]

    target = await validate_public_url("https://example.com", resolver=public_resolver)

    assert target.url == "https://example.com"
    assert target.addresses == (
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"),
    )


@pytest.mark.asyncio
async def test_rejects_hostname_with_any_private_dns_answer() -> None:
    async def rebinding_resolver(_hostname: str, _port: int) -> list[str]:
        return ["93.184.216.34", "127.0.0.1"]

    with pytest.raises(UnsafeTargetError):
        await validate_public_url("https://example.com", resolver=rebinding_resolver)


@pytest.mark.asyncio
async def test_rejects_empty_dns_answer() -> None:
    async def empty_resolver(_hostname: str, _port: int) -> list[str]:
        return []

    with pytest.raises(HostResolutionError):
        await validate_public_url("https://example.com", resolver=empty_resolver)
