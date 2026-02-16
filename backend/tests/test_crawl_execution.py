from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, TechnicalIssue
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

