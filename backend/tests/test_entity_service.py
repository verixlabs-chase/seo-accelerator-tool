from app.models.campaign import Campaign
from app.models.competitor import Competitor, CompetitorPage
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.tenant import Tenant
from app.services import entity_service


def test_entity_analysis_service_generates_score_and_gaps(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    campaign = Campaign(tenant_id=tenant.id, name="Entity Campaign", domain="entity.com")
    db_session.add(campaign)
    db_session.flush()

    page = Page(tenant_id=tenant.id, campaign_id=campaign.id, url="https://entity.com/local-seo-services")
    db_session.add(page)
    db_session.flush()
    run = CrawlRun(tenant_id=tenant.id, campaign_id=campaign.id, crawl_type="deep", status="complete", seed_url="https://entity.com")
    db_session.add(run)
    db_session.flush()
    result = CrawlPageResult(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        crawl_run_id=run.id,
        page_id=page.id,
        status_code=200,
        title="Local SEO services for dentists",
    )
    db_session.add(result)

    competitor = Competitor(tenant_id=tenant.id, campaign_id=campaign.id, domain="competitor.com", label="Comp")
    db_session.add(competitor)
    db_session.flush()
    comp_page = CompetitorPage(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        competitor_id=competitor.id,
        url="https://competitor.com/dental-seo-growth",
        visibility_score=0.8,
    )
    db_session.add(comp_page)
    db_session.commit()

    payload = entity_service.run_entity_analysis(db_session, tenant_id=tenant.id, campaign_id=campaign.id)
    assert "entity_score" in payload
    assert 0.0 <= payload["entity_score"] <= 100.0
    assert isinstance(payload["missing_entities"], list)
    assert isinstance(payload["evidence"], list)
    assert len(payload["evidence"]) >= 1
