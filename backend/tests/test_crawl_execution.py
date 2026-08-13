from app.models.campaign import Campaign
import json

from app.models.crawl import (
    CrawlFrontierUrl,
    CrawlInternalLink,
    CrawlPageResult,
    CrawlRun,
    Page,
    TechnicalIssue,
)
from app.models.organization import Organization
from app.models.user import User
from app.services import crawl_service
from tests.helpers.economic_setup import provision_test_organization


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        text: str,
        content_type: str = "text/html",
        *,
        url: str = "https://example.com/",
        history: list | None = None,
    ):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}
        self.url = url
        self.history = history or []


class _FakeClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow:", url=url)
        if "missing" in url:
            return _FakeResponse(200, "<html><body>No title here</body></html>", url=url)
        if "noindex" in url:
            return _FakeResponse(
                200,
                "<html><head><meta name=\"robots\" content=\"noindex\"><title>X</title></head></html>",
                url=url,
            )
        return _FakeResponse(404, "", url=url)


class _DisallowClient(_FakeClient):
    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow: /private", url=url)
        return _FakeResponse(200, "<html><title>Private</title></html>", url=url)


class _ExpansionClient(_FakeClient):
    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/robots.txt"):
            return _FakeResponse(200, "User-agent: *\nDisallow:", url=url)
        if url.rstrip("/").endswith("example.com"):
            return _FakeResponse(
                200,
                '<html><head><title>Home</title></head><body><a href="/p1">P1</a><a href="/p2">P2</a></body></html>',
                url=url,
            )
        if url.endswith("/p1"):
            return _FakeResponse(
                200,
                '<html><head><title>P1</title></head><body><h1>P1</h1></body></html>',
                url=url,
            )
        if url.endswith("/p2"):
            return _FakeResponse(
                200,
                '<html><head><title>P2</title></head><body><h1>P2</h1></body></html>',
                url=url,
            )
        return _FakeResponse(404, "", url=url)


class _SitemapClient(_FakeClient):
    def get(self, url: str, timeout: float = 10.0):  # noqa: ARG002
        if url.endswith("/sitemap-index.xml"):
            return _FakeResponse(
                200,
                """
                <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                  <sitemap><loc>https://example.com/pages.xml</loc></sitemap>
                  <sitemap><loc>https://other.example/external.xml</loc></sitemap>
                </sitemapindex>
                """,
                "application/xml",
                url=url,
            )
        if url.endswith("/pages.xml"):
            return _FakeResponse(
                200,
                """
                <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                  <url><loc>https://example.com/</loc></url>
                  <url><loc>https://example.com/unlinked</loc></url>
                  <url><loc>https://outside.example/not-owned</loc></url>
                </urlset>
                """,
                "application/xml",
                url=url,
            )
        return _FakeResponse(404, "", url=url)



def _provision_user_org(db_session, user: User) -> Organization:
    organization = db_session.query(Organization).filter(Organization.id == user.tenant_id).first()
    assert organization is not None
    return provision_test_organization(db_session, organization)


def _add_crawl_result(
    db_session,
    run: CrawlRun,
    page: Page,
    *,
    status_code: int = 200,
    content_hash: str | None = None,
    canonical_url: str | None = None,
) -> CrawlPageResult:
    result = CrawlPageResult(
        tenant_id=run.tenant_id,
        campaign_id=run.campaign_id,
        crawl_run_id=run.id,
        page_id=page.id,
        status_code=status_code,
        is_indexable=1,
        final_url=page.url,
        redirect_chain=[],
        redirect_count=0,
        canonical_url=canonical_url,
        content_hash=content_hash,
        word_count=50 if content_hash else 5,
        internal_link_count=0,
        structured_data_types=[],
        structured_data_valid=True,
    )
    db_session.add(result)
    return result


def test_sitemap_inventory_is_bounded_to_the_crawled_website():
    urls, loaded = crawl_service._discover_sitemap_inventory(
        _SitemapClient(),
        "https://example.com",
        "Sitemap: https://example.com/sitemap-index.xml",
        max_urls=10,
    )

    assert loaded is True
    assert urls == ["https://example.com/", "https://example.com/unlinked"]
    assert crawl_service.build_batch_urls("https://example.com", "deep") == [
        "https://example.com"
    ]



def test_execute_run_persists_results_and_issues(db_session, monkeypatch):
    monkeypatch.setattr(crawl_service.httpx, "Client", _FakeClient)
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    organization = _provision_user_org(db_session, user)

    campaign = Campaign(tenant_id=user.tenant_id, organization_id=organization.id, name="Exec Crawl", domain="example.com")
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
    organization = _provision_user_org(db_session, user)

    campaign = Campaign(tenant_id=user.tenant_id, organization_id=organization.id, name="Robots Crawl", domain="example.com")
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
    organization = _provision_user_org(db_session, user)

    campaign = Campaign(tenant_id=user.tenant_id, organization_id=organization.id, name="Expansion Crawl", domain="example.com")
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
    organization = _provision_user_org(db_session, user)

    campaign = Campaign(tenant_id=user.tenant_id, organization_id=organization.id, name="Batched Frontier Crawl", domain="example.com")
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


def test_finalize_run_integrity_requires_complete_coverage_for_sitewide_findings(
    db_session,
):
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None
    organization = _provision_user_org(db_session, user)
    campaign = Campaign(
        tenant_id=user.tenant_id,
        organization_id=organization.id,
        name="Integrity Crawl",
        domain="example.com",
    )
    db_session.add(campaign)
    db_session.flush()
    run = CrawlRun(
        tenant_id=user.tenant_id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="complete",
        seed_url="https://example.com",
    )
    db_session.add(run)
    db_session.flush()

    urls = {
        "home": "https://example.com",
        "broken": "https://example.com/broken",
        "service": "https://example.com/service",
        "copy": "https://example.com/service-copy",
        "orphan": "https://example.com/orphan",
        "canonical": "https://example.com/bad-canonical",
        "missing_preferred": "https://example.com/missing-preferred-page",
    }
    pages = {
        name: Page(
            tenant_id=user.tenant_id,
            campaign_id=campaign.id,
            url=url,
        )
        for name, url in urls.items()
    }
    db_session.add_all(pages.values())
    db_session.flush()

    duplicate_hash = "a" * 64
    _add_crawl_result(db_session, run, pages["home"])
    _add_crawl_result(db_session, run, pages["broken"], status_code=404)
    _add_crawl_result(
        db_session,
        run,
        pages["service"],
        content_hash=duplicate_hash,
    )
    _add_crawl_result(
        db_session,
        run,
        pages["copy"],
        content_hash=duplicate_hash,
    )
    _add_crawl_result(db_session, run, pages["orphan"])
    _add_crawl_result(
        db_session,
        run,
        pages["canonical"],
        canonical_url=urls["missing_preferred"],
    )
    _add_crawl_result(
        db_session,
        run,
        pages["missing_preferred"],
        status_code=404,
    )
    for target_name in ("broken", "service", "copy", "canonical"):
        db_session.add(
            CrawlInternalLink(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                source_page_id=pages["home"].id,
                target_url=urls[target_name],
                normalized_target_url=urls[target_name],
            )
        )
    db_session.add(
        CrawlFrontierUrl(
            tenant_id=run.tenant_id,
            campaign_id=run.campaign_id,
            crawl_run_id=run.id,
            url=urls["orphan"],
            normalized_url=urls["orphan"],
            status="complete",
            depth=0,
            discovered_from_url="sitemap",
        )
    )
    db_session.flush()

    partial = crawl_service.finalize_run_integrity(
        db_session,
        run,
        coverage_complete=False,
    )
    partial_codes = {issue.issue_code for issue in partial}
    assert partial_codes == {
        "broken_internal_link",
        "canonical_target_missing",
        "duplicate_content",
    }

    complete = crawl_service.finalize_run_integrity(
        db_session,
        run,
        coverage_complete=True,
    )
    complete_codes = [issue.issue_code for issue in complete]
    assert complete_codes.count("broken_internal_link") == 1
    assert complete_codes.count("duplicate_content") == 1
    assert complete_codes.count("orphan_page") == 1
    assert complete_codes.count("canonical_target_missing") == 1

    broken_issue = next(
        issue for issue in complete if issue.issue_code == "broken_internal_link"
    )
    broken_details = json.loads(broken_issue.details_json)
    assert broken_details["source_url"] == urls["home"]
    assert broken_details["target_url"] == urls["broken"]
    assert broken_details["status_code"] == 404

    persisted = (
        db_session.query(TechnicalIssue)
        .filter(
            TechnicalIssue.crawl_run_id == run.id,
            TechnicalIssue.issue_code.in_(crawl_service._RUN_DERIVED_ISSUES),
        )
        .all()
    )
    assert len(persisted) == 4
