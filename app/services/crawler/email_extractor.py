import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Comment

EMAIL_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9_.+-])([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)"
)
DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
ASSET_TLDS = frozenset(
    {"avif", "css", "gif", "ico", "jpeg", "jpg", "js", "png", "svg", "webp", "woff", "woff2"}
)
NON_VISIBLE_TAGS = frozenset({"script", "style", "noscript", "template"})


def _normalize_email(candidate: str) -> str | None:
    candidate = candidate.strip(",:;<>[](){}\"'").lower()
    if len(candidate) > 320 or candidate.count("@") != 1:
        return None
    local, domain = candidate.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        return None
    try:
        domain = domain.rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = domain.split(".")
    if len(labels) < 2 or any(not DNS_LABEL.fullmatch(label) for label in labels):
        return None
    if labels[-1] in ASSET_TLDS:
        return None
    return f"{local}@{domain}"


def _add_matches(value: str, emails: dict[str, None]) -> None:
    for match in EMAIL_PATTERN.finditer(value):
        email = _normalize_email(match.group(1))
        if email is not None:
            emails.setdefault(email, None)


def extract_emails(soup: BeautifulSoup) -> tuple[str, ...]:
    """Extract unique emails from visible text and mailto anchors."""

    emails: dict[str, None] = {}
    for node in soup.find_all(string=True):
        if isinstance(node, Comment) or node.parent is None or node.parent.name in NON_VISIBLE_TAGS:
            continue
        _add_matches(str(node), emails)

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.lower().startswith("mailto:"):
            continue
        recipients = unquote(urlsplit(href).path)
        for recipient in re.split(r"[,;]", recipients):
            email = _normalize_email(recipient)
            if email is not None:
                emails.setdefault(email, None)

    return tuple(emails)
