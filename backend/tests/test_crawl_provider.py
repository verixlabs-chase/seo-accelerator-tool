from app.providers import crawl as crawl_provider


class _Response:
    def __init__(self, url: str, status_code: int, *, location: str | None = None):
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": "text/html"}
        if location:
            self.headers["location"] = location
        self.text = "<html><head><title>Final page</title></head></html>"
        self.history: list[_Response] = []


class _Client:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def get(self, _url: str, timeout: float):  # noqa: ARG002
        first = _Response(
            "https://example.com/old",
            301,
            location="/middle",
        )
        second = _Response(
            "https://example.com/middle",
            302,
            location="/final",
        )
        final = _Response("https://example.com/final", 200)
        final.history = [first, second]
        return final


def test_default_adapter_preserves_redirect_chain(monkeypatch):
    monkeypatch.setattr(crawl_provider.httpx, "Client", _Client)
    adapter = crawl_provider.DefaultCrawlAdapter(retry_attempts=1)

    result = adapter.fetch_url(
        "https://example.com/old",
        timeout_seconds=5,
        use_playwright=False,
    )

    assert result.requested_url == "https://example.com/old"
    assert result.final_url == "https://example.com/final"
    assert result.status_code == 200
    assert [hop["status_code"] for hop in result.redirect_chain] == [301, 302]
    assert [hop["location"] for hop in result.redirect_chain] == ["/middle", "/final"]
