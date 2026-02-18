from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.competitor import Competitor, CompetitorPage
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.tenant import Tenant


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_entity_report_endpoint_returns_contract_and_emits_event(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}

    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    campaign = Campaign(tenant_id=tenant.id, name="Entity API Campaign", domain="entityapi.com")
    db_session.add(campaign)
    db_session.flush()

    page = Page(tenant_id=tenant.id, campaign_id=campaign.id, url="https://entityapi.com/local-seo-tips")
    db_session.add(page)
    db_session.flush()
    run = CrawlRun(tenant_id=tenant.id, campaign_id=campaign.id, crawl_type="deep", status="complete", seed_url="https://entityapi.com")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        CrawlPageResult(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            crawl_run_id=run.id,
            page_id=page.id,
            status_code=200,
            title="Local SEO tips for law firms",
        )
    )

    competitor = Competitor(tenant_id=tenant.id, campaign_id=campaign.id, domain="competitorapi.com", label="Comp API")
    db_session.add(competitor)
    db_session.flush()
    db_session.add(
        CompetitorPage(
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            competitor_id=competitor.id,
            url="https://competitorapi.com/law-firm-local-seo-guide",
            visibility_score=0.88,
        )
    )
    db_session.commit()

    response = client.get(f"/api/v1/entity/report?campaign_id={campaign.id}", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert 0.0 <= data["entity_score"] <= 100.0
    assert "missing_entities" in data
    assert isinstance(data["missing_entities"], list)
    assert 0.0 <= data["confidence_score"] <= 1.0
    assert isinstance(data["evidence"], list)
    assert "recommendations" in data
    for rec in data["recommendations"]:
        assert "confidence_score" in rec
        assert "evidence" in rec

    event_row = (
        db_session.query(AuditLog)
        .filter(AuditLog.tenant_id == tenant.id, AuditLog.event_type == "entity.analysis.completed")
        .first()
    )
    assert event_row is not None

    metrics = client.get("/api/v1/health/metrics", headers=headers)
    assert metrics.status_code == 200
    assert metrics.json()["data"]["metrics"]["entity_analysis_runs"] >= 1
