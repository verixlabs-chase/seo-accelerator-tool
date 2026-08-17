from app.services import crawl_parser


def test_parse_signals_and_taxonomy():
    html = """
    <html>
      <head>
        <link rel="canonical" href="/relative-canonical">
        <meta name="description" content="">
      </head>
      <body>
        <h1>One</h1><h1>Two</h1>
        <a href="/internal"></a>
      </body>
    </html>
    """
    signals = crawl_parser.parse_signals("https://example.com/path", html)
    assert signals["canonical"] == "https://example.com/relative-canonical"
    assert signals["h1_count"] == 2
    issues = crawl_parser.build_issue_taxonomy(404, signals)
    codes = {item["issue_code"] for item in issues}
    assert "http_error" in codes
    assert "missing_title" in codes
    assert "invalid_canonical" not in codes
    assert "canonical_points_elsewhere" in codes
    assert "multiple_h1" in codes


def test_extract_internal_links_filters_external_and_special_schemes():
    html = """
    <html>
      <body>
        <a href="/about">About</a>
        <a href="https://example.com/contact#team">Contact</a>
        <a href="https://other.com/page">External</a>
        <a href="mailto:hello@example.com">Email</a>
        <a href="javascript:void(0)">Ignore</a>
      </body>
    </html>
    """
    links = crawl_parser.extract_internal_links("https://example.com/start", html, max_links=10)
    assert "https://example.com/about" in links
    assert "https://example.com/contact" in links
    assert all("other.com" not in link for link in links)


def test_parse_signals_keeps_bounded_page_copy_for_business_discovery():
    html = """
    <html>
      <head>
        <title>Junk Magicians &amp; Removal</title>
        <meta name="description" content="Hot tub removal for Reno homeowners">
        <style>.hidden { display: none; }</style>
      </head>
      <body>
        <h1><span>Hot Tub</span> Removal</h1>
        <h2>Appliance Removal</h2>
        <script>secretTrackingValue()</script>
        <p>We haul bulky household items.</p>
      </body>
    </html>
    """

    signals = crawl_parser.parse_signals("https://example.com/removal", html)

    assert signals["title"] == "Junk Magicians & Removal"
    assert signals["meta_description"] == "Hot tub removal for Reno homeowners"
    assert signals["heading_text"] == "Hot Tub Removal | Appliance Removal"
    assert "We haul bulky household items." in signals["body_text_excerpt"]
    assert "secretTrackingValue" not in signals["body_text_excerpt"]


def test_parse_signals_accepts_canonical_and_description_attributes_in_any_order():
    html = """
    <html>
      <head>
        <link href="/preferred" data-source="cms" rel="alternate canonical">
        <meta content="Local repair help" name="description">
      </head>
      <body><h1>Repair help</h1></body>
    </html>
    """

    signals = crawl_parser.parse_signals("https://EXAMPLE.com/service", html)

    assert signals["canonical"] == "https://EXAMPLE.com/preferred"
    assert signals["meta_description"] == "Local repair help"


def test_parse_signals_records_exact_content_and_structured_data_evidence():
    html = """
    <html>
      <head>
        <title>Emergency plumbing in Austin</title>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":["LocalBusiness","Plumber"]}
        </script>
        <script type="application/ld+json">{"@type": broken}</script>
      </head>
      <body>
        <h1>Emergency plumbing in Austin</h1>
        <p>Our licensed local plumbers repair burst pipes, leaking fixtures, and blocked drains for homes and businesses throughout Austin, Texas.</p>
      </body>
    </html>
    """

    signals = crawl_parser.parse_signals("https://example.com/plumbing", html)

    assert signals["content_hash"]
    assert signals["word_count"] >= 20
    assert signals["structured_data_types"] == ["LocalBusiness", "Plumber"]
    assert signals["structured_data_errors"] == 1
    codes = {
        item["issue_code"]
        for item in crawl_parser.build_issue_taxonomy(200, signals)
    }
    assert "invalid_structured_data" in codes


def test_taxonomy_preserves_multi_step_redirect_evidence():
    signals = crawl_parser.parse_signals(
        "https://example.com/old",
        "<html><head><title>Moved</title></head><body><h1>Moved</h1></body></html>",
    )
    signals["final_url"] = "https://example.com/new"
    signals["redirect_chain"] = [
        {"url": "https://example.com/old", "status_code": 301, "location": "/middle"},
        {"url": "https://example.com/middle", "status_code": 302, "location": "/new"},
    ]

    issues = crawl_parser.build_issue_taxonomy(200, signals)

    redirect_issue = next(item for item in issues if item["issue_code"] == "redirect_chain")
    assert redirect_issue["details"]["redirect_count"] == 2
    assert redirect_issue["details"]["final_url"] == "https://example.com/new"
