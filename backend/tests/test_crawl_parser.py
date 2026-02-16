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

