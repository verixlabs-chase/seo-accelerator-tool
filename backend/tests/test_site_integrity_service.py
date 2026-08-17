from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.data_connection import DataConnection
from app.models.organization import Organization
from app.models.site_integrity import (
    SearchConsoleSitemapSnapshot,
    UrlInspectionSnapshot,
)
from app.providers.execution_types import ProviderExecutionResult
from app.services import site_integrity_service


class _SiteIntegrityProvider:
    def __init__(self, *, db) -> None:
        self.db = db

    def execute(self, request):
        if request.operation == "sitemaps_list":
            return ProviderExecutionResult(
                success=True,
                latency_ms=1,
                raw_payload={
                    "dataset": "sitemaps",
                    "rows": [
                        {
                            "site_url": "sc-domain:example.com",
                            "sitemap_url": "https://example.com/sitemap.xml",
                            "sitemap_type": "sitemap",
                            "is_pending": False,
                            "is_sitemaps_index": False,
                            "warnings": 1,
                            "errors": 0,
                            "submitted_url_count": 12,
                            "contents": [{"type": "web", "submitted": 12}],
                            "last_submitted_at": "2026-08-12T08:00:00Z",
                            "last_downloaded_at": "2026-08-12T09:00:00Z",
                        }
                    ],
                },
            )
        return ProviderExecutionResult(
            success=True,
            latency_ms=1,
            raw_payload={
                "dataset": "url_inspection",
                "record": {
                    "inspection_url": request.payload["inspection_url"],
                    "site_url": request.payload["site_url"],
                    "verdict": "FAIL",
                    "coverage_state": "Excluded by 'noindex' tag",
                    "robots_txt_state": "ALLOWED",
                    "indexing_state": "BLOCKED_BY_META_TAG",
                    "page_fetch_state": "SUCCESSFUL",
                    "google_canonical": None,
                    "user_canonical": request.payload["inspection_url"],
                    "crawled_as": "MOBILE",
                    "last_crawl_time": "2026-08-12T10:00:00Z",
                    "sitemap_urls": ["https://example.com/sitemap.xml"],
                    "referring_urls": ["https://example.com/"],
                },
            },
        )


def _seed_campaign(db_session) -> tuple[Campaign, DataConnection]:
    organization = db_session.query(Organization).order_by(Organization.id.asc()).first()
    assert organization is not None
    location = BusinessLocation(
        organization_id=organization.id,
        name=f"Site integrity {uuid.uuid4().hex[:8]}",
        domain="example.com",
        country_code="US",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        name="Example service business",
        domain="example.com",
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.flush()
    connection = DataConnection(
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        campaign_id=campaign.id,
        provider_name="google_search_console",
        external_resource_id="sc-domain:example.com",
        external_resource_name="example.com",
        resource_scope="domain",
        status="connected",
        connection_metadata={},
    )
    run = CrawlRun(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="completed",
        seed_url="https://example.com/",
        pages_discovered=1,
    )
    page = Page(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        url="https://example.com/service",
    )
    db_session.add_all([connection, run, page])
    db_session.flush()
    db_session.add(
        CrawlPageResult(
            tenant_id=organization.id,
            campaign_id=campaign.id,
            crawl_run_id=run.id,
            page_id=page.id,
            status_code=200,
            is_indexable=1,
            title="Service",
        )
    )
    db_session.commit()
    return campaign, connection


def test_refresh_persists_google_evidence_and_builds_plain_language_findings(
    db_session,
    monkeypatch,
) -> None:
    campaign, _connection = _seed_campaign(db_session)
    monkeypatch.setattr(
        site_integrity_service,
        "SearchConsoleSiteIntegrityAdapter",
        _SiteIntegrityProvider,
    )
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

    result = site_integrity_service.refresh_site_integrity(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        max_urls=10,
        now=now,
    )

    assert result["refresh"]["inspected_urls"] == 1
    assert result["refresh"]["sitemaps_read"] == 1
    integrity = result["integrity"]
    assert integrity["summary"]["indexed_urls"] == 0
    assert integrity["summary"]["attention_urls"] == 1
    assert integrity["status"] == "attention"
    titles = {finding["title"] for finding in integrity["findings"]}
    assert "This page tells Google not to index it" in titles
    assert "Google is not showing this page in its index" not in titles
    noindex_finding = next(
        finding for finding in integrity["findings"] if finding["code"] == "noindex_blocked"
    )
    assert noindex_finding["url"] == "https://example.com/service"
    assert "deprecated sitemap indexed field" in integrity["coverage_note"]
    assert db_session.query(UrlInspectionSnapshot).count() == 1
    assert db_session.query(SearchConsoleSitemapSnapshot).count() == 1


def test_summary_requires_a_connection_without_hiding_saved_crawl_data(db_session) -> None:
    organization = db_session.query(Organization).order_by(Organization.id.asc()).first()
    assert organization is not None
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Unconnected business",
        domain="unconnected.example",
    )
    db_session.add(campaign)
    db_session.commit()

    result = site_integrity_service.get_site_integrity(
        db_session,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )

    assert result["status"] == "needs_connection"
    assert result["connection"]["connected"] is False
    assert result["next_action"]["href"] == "/settings"
