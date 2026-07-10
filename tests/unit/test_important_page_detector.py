from app.db.models import ImportantPageType
from app.services.crawler.important_page_detector import detect_important_pages
from app.services.crawler.link_extractor import ExtractedLink


def link(url: str, text: str, *, internal: bool = True) -> ExtractedLink:
    return ExtractedLink(
        target_url=url,
        normalized_target_url=url,
        link_text=text,
        is_internal=internal,
    )


def test_detects_hub_pages_without_marking_detail_pages() -> None:
    candidates = detect_important_pages(
        [
            link("https://example.com/pricing", "See pricing"),
            link("https://example.com/careers/backend-engineer", "Backend Engineer"),
            link("https://example.com/company", "About us"),
            link("https://external.example/pricing", "Pricing", internal=False),
        ]
    )

    assert [(item.page_type, item.confidence) for item in candidates] == [
        (ImportantPageType.PRICING, 0.99),
        (ImportantPageType.ABOUT, 0.99),
    ]


def test_path_only_match_has_high_confidence() -> None:
    candidate = detect_important_pages(
        [link("https://example.com/legal/privacy-policy", "Legal notice")]
    )[0]

    assert candidate.page_type is ImportantPageType.PRIVACY
    assert candidate.confidence == 0.95
