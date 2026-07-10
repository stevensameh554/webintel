from app.services.crawler.link_extractor import extract_links


def test_extracts_classifies_and_deduplicates_links() -> None:
    html = """
    <html><body>
      <a href="/about/"> About us </a>
      <a href="https://EXAMPLE.com/about?utm_source=nav">Duplicate about</a>
      <a href="//external.example/pricing">External pricing</a>
      <a href="mailto:team@example.com">Email</a>
      <a href="tel:+123456789">Phone</a>
      <a href="javascript:void(0)">Action</a>
      <a href="#team">Team section</a>
      <a>No href</a>
    </body></html>
    """

    links = extract_links(
        html,
        page_url="https://example.com/company",
        crawl_root_url="https://example.com",
    )

    assert len(links) == 2
    assert links[0].target_url == "https://example.com/about/"
    assert links[0].normalized_target_url == "https://example.com/about"
    assert links[0].link_text == "About us"
    assert links[0].is_internal is True
    assert links[1].normalized_target_url == "https://external.example/pricing"
    assert links[1].is_internal is False


def test_respects_html_base_url_and_protocol_relative_links() -> None:
    html = """
    <head><base href="/docs/v2/"></head>
    <body>
      <a href="getting-started/">Start <strong>here</strong></a>
      <a href="../api?b=2&a=1#methods">API</a>
    </body>
    """

    links = extract_links(html, page_url="https://example.com/docs/index")

    assert [link.normalized_target_url for link in links] == [
        "https://example.com/docs/v2/getting-started",
        "https://example.com/docs/api?a=1&b=2",
    ]
    assert links[0].link_text == "Start here"


def test_invalid_base_falls_back_to_page_url() -> None:
    html = '<base href="javascript:alert(1)"><a href="next/">Next</a>'

    links = extract_links(html, page_url="https://example.com/current/")

    assert links[0].normalized_target_url == "https://example.com/current/next"


def test_uses_exact_hostname_for_internal_classification() -> None:
    html = """
    <a href="https://www.example.com/a">Same host</a>
    <a href="https://example.com/b">Apex host</a>
    <a href="https://blog.www.example.com/c">Subdomain</a>
    """

    links = extract_links(
        html,
        page_url="https://www.example.com",
        crawl_root_url="https://www.example.com",
    )

    assert [link.is_internal for link in links] == [True, False, False]


def test_truncates_oversized_link_text() -> None:
    html = f'<a href="/large">{"x" * 2000}</a>'

    link = extract_links(html, page_url="https://example.com")[0]

    assert link.link_text is not None
    assert len(link.link_text) == 1024
