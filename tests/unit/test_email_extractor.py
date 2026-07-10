from bs4 import BeautifulSoup

from app.services.crawler.email_extractor import extract_emails


def test_extracts_visible_and_mailto_emails_in_stable_order() -> None:
    soup = BeautifulSoup(
        """
        <p>Primary: HELLO@Example.com.</p>
        <a href="mailto:sales%40example.com,hello@example.com?subject=Hi">Contact</a>
        <p>Duplicate hello@example.com and invalid logo@2x.png.</p>
        """,
        "lxml",
    )

    assert extract_emails(soup) == ("hello@example.com", "sales@example.com")


def test_ignores_nonvisible_and_malformed_candidates() -> None:
    soup = BeautifulSoup(
        """
        <script>const email = "script@example.com";</script>
        <style>.x { content: "style@example.com" }</style>
        <p>.bad@example.com bad..dots@example.com user@localhost</p>
        """,
        "lxml",
    )

    assert extract_emails(soup) == ()
