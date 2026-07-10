from app.services.crawler.link_extractor import ExtractedLink
from app.services.crawler.social_link_detector import detect_social_links


def link(url: str) -> ExtractedLink:
    return ExtractedLink(
        target_url=url,
        normalized_target_url=url,
        link_text=None,
        is_internal=False,
    )


def test_detects_profiles_and_ignores_sharing_and_content_urls() -> None:
    candidates = detect_social_links(
        [
            link("https://linkedin.com/company/acme"),
            link("https://x.com/acme"),
            link("https://youtube.com/@acme"),
            link("https://youtube.com/watch?v=123"),
            link("https://twitter.com/intent/tweet?url=x"),
            link("https://notlinkedin.com/company/acme"),
            link("https://github.com/acme"),
            link("https://github.com/acme"),
        ]
    )

    assert [(item.platform, item.url) for item in candidates] == [
        ("linkedin", "https://linkedin.com/company/acme"),
        ("twitter", "https://x.com/acme"),
        ("youtube", "https://youtube.com/@acme"),
        ("github", "https://github.com/acme"),
    ]
