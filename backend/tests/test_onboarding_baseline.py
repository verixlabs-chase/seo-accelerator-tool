from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.crawl import CrawlRun, TechnicalIssue
from app.models.data_connection import DataConnection
from app.models.onboarding_baseline import OnboardingBaseline
from app.models.rank import CampaignKeyword, KeywordCluster, RankingSnapshot
from app.models.reporting import MonthlyReport
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_performance import WebsitePerformanceMeasurement
from app.services import onboarding_baseline_ai_service, onboarding_baseline_service


def _login(client, email: str = "org-admin@example.com") -> tuple[str, dict]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "pass-org-admin"}
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]


def _campaign(db_session, user: dict, *, name: str) -> Campaign:
    location = BusinessLocation(
        organization_id=user["organization_id"],
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        domain="baseline.example",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        business_location_id=location.id,
        name=name,
        domain="baseline.example",
    )
    db_session.add(campaign)
    db_session.commit()
    return campaign


def _completed_crawl(db_session, campaign: Campaign, *, issue_count: int = 1) -> CrawlRun:
    now = datetime.now(UTC)
    crawl = CrawlRun(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="completed",
        seed_url="https://baseline.example",
        pages_discovered=10,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    db_session.add(crawl)
    db_session.flush()
    for index in range(issue_count):
        db_session.add(
            TechnicalIssue(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                crawl_run_id=crawl.id,
                issue_code="missing_meta_description",
                severity="high" if index == 0 else "medium",
                details_json=json.dumps({"page": index + 1}),
            )
        )
    db_session.commit()
    return crawl


def _synced_search_connection(db_session, campaign: Campaign) -> DataConnection:
    now = datetime.now(UTC)
    connection = DataConnection(
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        business_location_id=campaign.business_location_id,
        campaign_id=campaign.id,
        provider_name="google_search_console",
        external_resource_id="sc-domain:baseline.example",
        external_resource_name="baseline.example",
        resource_scope="property",
        status="current",
        last_sync_started_at=now,
        last_sync_completed_at=now,
        last_success_at=now,
    )
    db_session.add(connection)
    db_session.commit()
    return connection


def _complete_optional_evidence(db_session, campaign: Campaign) -> None:
    today = date.today()
    _synced_search_connection(db_session, campaign)
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=today,
            clicks=12,
            impressions=200,
            ctr=0.06,
            avg_position=8.0,
            property_uri="sc-domain:baseline.example",
            deterministic_hash="s" * 64,
        )
    )
    db_session.add(
        AnalyticsDailyMetric(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            metric_date=today,
            sessions=20,
            engaged_sessions=14,
            conversions=2,
            deterministic_hash="a" * 64,
        )
    )
    cluster = KeywordCluster(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        name="Core service",
    )
    db_session.add(cluster)
    db_session.flush()
    keyword = CampaignKeyword(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        cluster_id=cluster.id,
        keyword="service near me",
        location_code="US",
    )
    db_session.add(keyword)
    db_session.flush()
    db_session.add(
        RankingSnapshot(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            keyword_id=keyword.id,
            position=7,
            confidence=0.9,
            captured_at=datetime.now(UTC),
            month_partition=today.isoformat()[:7],
        )
    )
    db_session.add(
        WebsitePerformanceMeasurement(
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            business_location_id=campaign.business_location_id,
            campaign_id=campaign.id,
            requested_url="https://baseline.example",
            measured_url="https://baseline.example",
            source="pagespeed_lab",
            scope="url",
            form_factor="mobile",
            status="ready",
            lcp_ms=2200,
            inp_ms=180,
            cls_value=0.08,
            performance_score=0.84,
            metric_contract_versions={},
            scope_key="baseline-scope",
            lexicon_id="test-lexicon",
            lexicon_version="1",
            distribution={},
            diagnostics={},
            idempotency_key=f"baseline-performance:{campaign.id}",
        )
    )
    db_session.commit()


def test_baseline_waits_for_completed_website_scan(client, db_session) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Collecting baseline")
    _synced_search_connection(db_session, campaign)
    db_session.add(
        CrawlRun(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            status="scheduled",
            seed_url="https://baseline.example",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["state"] == "collecting"
    assert payload["completion_required"] is True
    assert payload["completion_satisfied"] is False
    assert payload["basic_access_blocked"] is False
    assert payload["baseline"] is None
    assert db_session.query(OnboardingBaseline).filter_by(campaign_id=campaign.id).count() == 0


def test_baseline_freezes_detailed_evidence_report_and_is_idempotent(
    client, db_session
) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Complete baseline")
    _completed_crawl(db_session, campaign, issue_count=2)
    _complete_optional_evidence(db_session, campaign)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}", headers=headers
    )

    assert created.status_code == 200
    payload = created.json()["data"]
    assert payload["created"] is True
    assert payload["state"] == "ready"
    assert payload["completion_satisfied"] is True
    baseline = payload["baseline"]
    assert baseline["immutable"] is True
    assert baseline["window"]["days"] == 28
    assert baseline["evidence"]["website"]["issue_count"] == 2
    assert baseline["evidence"]["organic_search"]["clicks"] == 12
    assert baseline["evidence"]["traffic"]["sessions"] == 20
    assert baseline["evidence"]["rank_tracking"]["top_10"] == 1
    assert baseline["scores"]["overall"] is not None
    assert baseline["scores"]["missing_is_not_zero"] is True
    assert baseline["diagnosis"]["fixes"][0]["key"].startswith("crawl:")
    assert baseline["diagnosis"]["analysis"]["causal_proof"] is False
    assert len(baseline["baseline_hash"]) == 64
    assert len(baseline["report_snapshot_hash"]) == 64

    saved_report = db_session.get(MonthlyReport, baseline["report_id"])
    report_snapshot = json.loads(saved_report.summary_json)
    assert report_snapshot["baseline"]["immutable"] is True
    assert report_snapshot["executive_summary"]["headline"] == baseline["diagnosis"]["headline"]
    assert any(item["key"] == "website_sessions" for item in report_snapshot["metrics"])

    repeated = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}", headers=headers
    )
    assert repeated.status_code == 200
    repeated_payload = repeated.json()["data"]
    assert repeated_payload["created"] is False
    assert repeated_payload["baseline"]["id"] == baseline["id"]
    assert repeated_payload["baseline"]["report_id"] == baseline["report_id"]
    assert db_session.query(OnboardingBaseline).filter_by(campaign_id=campaign.id).count() == 1


def test_baseline_requires_google_search_connection_before_official_report(
    client, db_session
) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Search connection required")
    _completed_crawl(db_session, campaign)

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["state"] == "needs_search_connection"
    assert payload["completion_satisfied"] is False
    assert payload["basic_access_blocked"] is False
    assert payload["baseline"] is None
    assert payload["actions"][0]["code"] == "connect_google_search"
    assert "Google Search data" in payload["message"]
    assert db_session.query(OnboardingBaseline).filter_by(campaign_id=campaign.id).count() == 0


def test_baseline_waits_for_first_google_search_sync(client, db_session) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Search sync required")
    _completed_crawl(db_session, campaign)
    db_session.add(
        DataConnection(
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            business_location_id=campaign.business_location_id,
            campaign_id=campaign.id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:baseline.example",
            external_resource_name="baseline.example",
            resource_scope="property",
            status="connected",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["state"] == "collecting"
    assert payload["completion_satisfied"] is False
    assert payload["baseline"] is None
    sources = {item["key"]: item for item in payload["sources"]}
    assert sources["search_console"]["state"] == "collecting"


def test_baseline_is_limited_without_optional_analytics_and_never_scores_missing_as_zero(
    client, db_session
) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Limited baseline")
    _completed_crawl(db_session, campaign)
    _synced_search_connection(db_session, campaign)

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    baseline = response.json()["data"]["baseline"]
    assert baseline["status"] == "limited"
    assert baseline["scores"]["components"]["website_performance"] is None
    assert baseline["scores"]["components"]["organic_visibility"] is None
    assert baseline["scores"]["components"]["traffic_engagement"] is None
    assert baseline["scores"]["overall"] == baseline["scores"]["components"]["website_health"]
    sources = {item["key"]: item for item in baseline["sources"]}
    assert sources["search_console"]["state"] == "not_enough_history"
    assert sources["search_console"]["optional"] is False
    assert sources["analytics"]["state"] == "not_connected"
    assert sources["analytics"]["optional"] is True
    assert "not scored as zero" in sources["analytics"]["detail"]


def test_baseline_report_uses_validated_ai_wording_without_changing_fixes(
    client, db_session, monkeypatch
) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Explained baseline")
    _completed_crawl(db_session, campaign, issue_count=2)
    _complete_optional_evidence(db_session, campaign)

    def validated_narrative(
        _db,
        *,
        evidence,
        scores,
        diagnosis,
        source_states,
        **_kwargs,
    ):
        return {
            "state": "validated",
            "narrative": {
                "headline": "Start with the two website problems found in the scan",
                "summary": (
                    "The saved evidence shows two pages that need attention. "
                    "Follow the measured fixes in the order shown."
                ),
                "themes": [
                    {
                        "title": "Website descriptions need attention",
                        "explanation": "Two pages share the same saved problem.",
                        "evidence_used": ["website:summary"],
                    }
                ],
                "priority_order": [
                    item["key"] for item in diagnosis.get("fixes") or []
                ],
                "evidence_used": ["website:summary"],
                "uncertainties": [],
            },
            "context_hash": onboarding_baseline_ai_service.baseline_context_hash(
                evidence=evidence,
                scores=scores,
                diagnosis=diagnosis,
                source_states=source_states,
            ),
            "run_id": "governed-ai-run",
            "idempotent_replay": False,
        }

    monkeypatch.setattr(
        onboarding_baseline_service.onboarding_baseline_ai_service,
        "generate_baseline_narrative",
        validated_narrative,
    )

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    baseline = response.json()["data"]["baseline"]
    assert baseline["diagnosis"]["headline"] == (
        "Start with the two website problems found in the scan"
    )
    assert baseline["diagnosis"]["analysis"]["narrative_source"] == "governed_ai"
    assert baseline["diagnosis"]["analysis"]["ai_enrichment"] == "validated"
    assert baseline["diagnosis"]["fixes"][0]["key"].startswith("crawl:")
    saved_report = db_session.get(MonthlyReport, baseline["report_id"])
    report_snapshot = json.loads(saved_report.summary_json)
    assert report_snapshot["executive_summary"]["headline"] == (
        baseline["diagnosis"]["headline"]
    )
    assert report_snapshot["next_priorities"] == baseline["diagnosis"]["fixes"][:5]


def test_optional_ai_failure_does_not_block_the_deterministic_baseline(
    client, db_session, monkeypatch
) -> None:
    token, user = _login(client)
    campaign = _campaign(db_session, user, name="Deterministic fallback baseline")
    _completed_crawl(db_session, campaign)
    _synced_search_connection(db_session, campaign)

    def unavailable_narrative(*_args, **_kwargs):
        raise RuntimeError("simulated optional provider failure")

    monkeypatch.setattr(
        onboarding_baseline_service.onboarding_baseline_ai_service,
        "generate_baseline_narrative",
        unavailable_narrative,
    )

    response = client.post(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["created"] is True
    assert payload["baseline"]["diagnosis"]["analysis"]["narrative_source"] == (
        "deterministic"
    )
    assert payload["baseline"]["diagnosis"]["analysis"]["ai_enrichment"] == (
        "unavailable_non_blocking"
    )


def test_baseline_rejects_cross_organization_campaign(client, db_session) -> None:
    token, _user = _login(client)
    other_login = client.post(
        "/api/v1/auth/login", json={"email": "b@example.com", "password": "pass-b"}
    )
    assert other_login.status_code == 200
    other_user = other_login.json()["data"]["user"]
    campaign = _campaign(db_session, other_user, name="Other organization baseline")

    response = client.get(
        f"/api/v1/onboarding/baseline/{campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
