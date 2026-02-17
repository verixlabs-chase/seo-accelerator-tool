from app.providers import rank


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, *_args, **_kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def post(self, url: str, json: dict, headers: dict, timeout: float):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse({"data": {"position": 7, "confidence": 0.88}})

    def get(self, url: str, params: dict, timeout: float):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(
            {
                "organic_results": [
                    {"position": 1, "link": "https://other.com/page"},
                    {"position": 4, "link": "https://www.rank.com/service"},
                ]
            }
        )


def test_synthetic_rank_provider_contract():
    provider = rank.SyntheticRankProvider()
    row = provider.collect_keyword_snapshot(keyword="local seo", location_code="US")
    assert "position" in row
    assert "confidence" in row
    assert isinstance(row["position"], int)
    assert isinstance(row["confidence"], float)


def test_http_json_rank_provider_reads_data_wrapper(monkeypatch):
    fake_client = _FakeClient()
    monkeypatch.setattr(rank.httpx, "Client", lambda: fake_client)
    provider = rank.HttpJsonRankProvider(
        endpoint="https://provider.example/rank",
        timeout_seconds=9.0,
        auth_header="X-API-Key",
        auth_token="secret",
    )
    row = provider.collect_keyword_snapshot(keyword="local seo", location_code="US")
    assert row["position"] == 7
    assert row["confidence"] == 0.88
    assert fake_client.calls[0]["json"]["keyword"] == "local seo"
    assert fake_client.calls[0]["json"]["location_code"] == "US"
    assert fake_client.calls[0]["headers"]["X-API-Key"] == "secret"


def test_http_json_rank_provider_requires_position(monkeypatch):
    class _NoPositionClient(_FakeClient):
        def post(self, url: str, json: dict, headers: dict, timeout: float):  # noqa: A002
            return _FakeResponse({"data": {"confidence": 0.9}})

    monkeypatch.setattr(rank.httpx, "Client", lambda: _NoPositionClient())
    provider = rank.HttpJsonRankProvider(endpoint="https://provider.example/rank")
    try:
        provider.collect_keyword_snapshot(keyword="local seo", location_code="US")
    except ValueError as exc:
        assert "position" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing position.")


def test_get_rank_provider_http_json_backend(monkeypatch):
    rank.get_rank_provider.cache_clear()
    monkeypatch.setattr(
        rank,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "rank_provider_backend": "http_json",
                "rank_provider_http_endpoint": "https://provider.example/rank",
                "rank_provider_http_timeout_seconds": 5.0,
                "rank_provider_http_auth_header": "Authorization",
                "rank_provider_http_auth_token": "Bearer abc",
                "rank_provider_http_keyword_field": "q",
                "rank_provider_http_location_field": "loc",
            },
        )(),
    )
    provider = rank.get_rank_provider()
    assert isinstance(provider, rank.HttpJsonRankProvider)
    rank.get_rank_provider.cache_clear()


def test_serpapi_rank_provider_matches_target_domain(monkeypatch):
    fake_client = _FakeClient()
    monkeypatch.setattr(rank.httpx, "Client", lambda: fake_client)
    provider = rank.SerpApiRankProvider(api_key="k")
    row = provider.collect_keyword_snapshot(keyword="best local seo", location_code="US", target_domain="rank.com")
    assert row["position"] == 4
    assert row["confidence"] == 0.9
    assert fake_client.calls[0]["params"]["q"] == "best local seo"
    assert fake_client.calls[0]["params"]["gl"] == "us"


def test_serpapi_rank_provider_returns_100_when_domain_not_found(monkeypatch):
    class _NoMatchClient(_FakeClient):
        def get(self, url: str, params: dict, timeout: float):
            return _FakeResponse({"organic_results": [{"position": 1, "link": "https://other.com/page"}]})

    monkeypatch.setattr(rank.httpx, "Client", lambda: _NoMatchClient())
    provider = rank.SerpApiRankProvider(api_key="k")
    row = provider.collect_keyword_snapshot(keyword="best local seo", location_code="US", target_domain="rank.com")
    assert row["position"] == 100
    assert row["confidence"] == 0.65


def test_get_rank_provider_serpapi_backend(monkeypatch):
    rank.get_rank_provider.cache_clear()
    monkeypatch.setattr(
        rank,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "rank_provider_backend": "serpapi",
                "rank_provider_serpapi_api_key": "k",
                "rank_provider_serpapi_endpoint": "https://serpapi.com/search.json",
                "rank_provider_serpapi_timeout_seconds": 5.0,
                "rank_provider_serpapi_engine": "google",
                "rank_provider_serpapi_default_gl": "us",
                "rank_provider_serpapi_default_hl": "en",
            },
        )(),
    )
    provider = rank.get_rank_provider()
    assert isinstance(provider, rank.SerpApiRankProvider)
    rank.get_rank_provider.cache_clear()
