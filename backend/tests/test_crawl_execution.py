from app.models.campaign import Campaign
from app.models.crawl import CrawlFrontierUrl, CrawlPageResult, CrawlRun, TechnicalIssue
from app.models.user import User
from app.services import crawl_service


class _FakeResponse:
    def __init__(self, status_code: int, text: str, content_type: str = "text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}


class _FakeClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow:")
        if "missing" in url:
            return _FakeResponse(200, "<html><body>No title here</body></html>")
        if "noindex" in url:
            return _FakeResponse(200, "<html><head><meta name=\"robots\" content=\"noindex\"><title>X</title></head></html>")
        return _FakeResponse(404, "")


class _DisallowClient(_FakeClient):
    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow: /private")
        return _FakeResponse(200, "<html><title>Private</title></html>")


class _ExpansionClient(_FakeClient):
    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow:")
        if url.rstrip("/").endswith("example.com"):
            return _FakeResponse(200, '<html><head><title>Home</title></head><body><a href="/p1">P1</a><a href="/p2">P2</a></body></html>')
        if url.endswith("/p1"):
            return _FakeResponse(200, '<html><head><title>P1</title></head><body><h1>P1</h1></body></html>')
        if url.endswith("/p2"):
            return _FakeResponse(200, '<html><head><title>P2</title></head><body><h1>P2</h1></body></html>')
        return _FakeResponse(404, "")


def test_execute_run_persists_results_and_issues(db_session, monkeypatch):
    monkeypatch.setattr(crawl_service.httpx, "Client", _FakeClient)
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None

    campaign = Campaign(tenant_id=user.tenant_id, name="Exec Crawl", domain="example.com")
    db_session.add(campaign)
    db_session.flush()
    run = CrawlRun(tenant_id=user.tenant_id, campaign_id=campaign.id, crawl_type="deep", status="scheduled", seed_url="https://example.com")
    db_session.add(run)
    db_session.commit()

    result = crawl_service.execute_run(
        db_session,
        crawl_run_id=run.id,
        provided_urls=["https://example.com/missing", "https://example.com/noindex", "https://example.com/not-found"],
    )
    assert result["processed_urls"] == 3

    page_results = db_session.query(CrawlPageResult).filter(CrawlPageResult.crawl_run_id == run.id).all()
    issues = db_session.query(TechnicalIssue).filter(TechnicalIssue.crawl_run_id == run.id).all()
    assert len(page_results) == 3
    assert len(issues) >= 3


def test_execute_run_respects_robots_disallow(db_session, monkeypatch):
    monkeypatch.setattr(crawl_service.httpx, "Client", _DisallowClient)
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None

    campaign = Campaign(tenant_id=user.tenant_id, name="Robots Crawl", domain="example.com")
    db_session.add(campaign)
    db_session.flush()
    run = CrawlRun(tenant_id=user.tenant_id, campaign_id=campaign.id, crawl_type="deep", status="scheduled", seed_url="https://example.com")
    db_session.add(run)
    db_session.commit()

    result = crawl_service.execute_run(db_session, crawl_run_id=run.id, provided_urls=["https://example.com/private/page"])
    assert result["processed_urls"] == 0


def test_execute_run_discovers_internal_links_with_limit(db_session, monkeypatch):
    monkeypatch.setattr(crawl_service.httpx, "Client", _ExpansionClient)
    monkeypatch.setattr(
        crawl_service,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "crawl_min_request_interval_seconds": 0.0,
                "crawl_use_playwright": False,
                "crawl_timeout_seconds": 10.0,
                "crawl_max_pages_per_run": 2,
                "crawl_max_discovered_links_per_page": 10,
            },
        )(),
    )
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None

    campaign = Campaign(tenant_id=user.tenant_id, name="Expansion Crawl", domain="example.com")
    db_session.add(campaign)
    db_session.flush()
    run = CrawlRun(tenant_id=user.tenant_id, campaign_id=campaign.id, crawl_type="deep", status="scheduled", seed_url="https://example.com")
    db_session.add(run)
    db_session.commit()

    result = crawl_service.execute_run(db_session, crawl_run_id=run.id)
    assert result["processed_urls"] == 2


def test_execute_run_frontier_batches_until_complete(db_session, monkeypatch):
    monkeypatch.setattr(crawl_service.httpx, "Client", _ExpansionClient)
    monkeypatch.setattr(
        crawl_service,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "crawl_min_request_interval_seconds": 0.0,
                "crawl_use_playwright": False,
                "crawl_timeout_seconds": 10.0,
                "crawl_max_pages_per_run": 5,
                "crawl_max_discovered_links_per_page": 10,
                "crawl_frontier_batch_size": 1,
            },
        )(),
    )
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None

    campaign = Campaign(tenant_id=user.tenant_id, name="Batched Frontier Crawl", domain="example.com")
    db_session.add(campaign)
    db_session.flush()
    run = CrawlRun(tenant_id=user.tenant_id, campaign_id=campaign.id, crawl_type="deep", status="scheduled", seed_url="https://example.com")
    db_session.add(run)
    db_session.commit()

    first = crawl_service.execute_run(db_session, crawl_run_id=run.id, batch_size=1)
    assert first["status"] == "running"
    assert first["processed_urls"] == 1
    assert first["pending_urls"] >= 1

    second = crawl_service.execute_run(db_session, crawl_run_id=run.id, batch_size=20)
    assert second["status"] == "complete"
    frontier_rows = db_session.query(CrawlFrontierUrl).filter(CrawlFrontierUrl.crawl_run_id == run.id).all()
    assert frontier_rows
    assert all(row.status != "processing" for row in frontier_rows)
