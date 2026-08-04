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
    assert signals["canonical"] == "/relative-canonical"
    assert signals["h1_count"] == 2
    issues = crawl_parser.build_issue_taxonomy(404, signals)
    codes = {item["issue_code"] for item in issues}
    assert "http_error" in codes
    assert "missing_title" in codes
    assert "invalid_canonical" in codes
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
    assert "https://example.com/contact#team" in links
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
