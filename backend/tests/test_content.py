from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.content import ContentBrief
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion


def _login(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_content_asset_lifecycle_and_internal_links(client):
    token = _login(client, "a@example.com", "pass-a")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Content Campaign", "domain": "content.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    a1 = client.post(
        "/api/v1/content/assets",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Local SEO",
            "title": "Local SEO Starter Guide",
            "planned_month": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert a1.status_code == 200
    asset1_id = a1.json()["data"]["id"]

    a2 = client.post(
        "/api/v1/content/assets",
        json={
            "campaign_id": campaign["id"],
            "cluster_name": "Technical SEO",
            "title": "Technical SEO Audit Checklist",
            "planned_month": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert a2.status_code == 200
    asset2_id = a2.json()["data"]["id"]

    bad_transition = client.patch(
        f"/api/v1/content/assets/{asset1_id}",
        json={"status": "published"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad_transition.status_code == 400

    for asset_id, url in [(asset1_id, "https://content.com/local-seo-guide"), (asset2_id, "https://content.com/tech-seo-checklist")]:
        assert client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "draft"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 200
        assert client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {token}"},
        ).status_code == 200
        published = client.patch(
            f"/api/v1/content/assets/{asset_id}",
            json={"status": "published", "target_url": url},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "published"

    plan = client.get(
        f"/api/v1/content/plan?campaign_id={campaign['id']}&month_number=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert plan.status_code == 200
    assert len(plan.json()["data"]["items"]) >= 2

    links = client.get(
        f"/api/v1/internal-links/recommendations?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert links.status_code == 200
    assert len(links.json()["data"]["items"]) >= 2


def test_content_workspace_combines_saved_pages_and_draft_briefs(client, db_session):
    token = _login(client, "a@example.com", "pass-a")
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Content Workspace", "domain": "workspace-content.com"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    now = datetime.now(UTC)
    crawl = CrawlRun(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        crawl_type="deep",
        status="completed",
        seed_url="https://workspace-content.com",
        pages_discovered=1,
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    page = Page(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        url="https://workspace-content.com/plumbing",
        last_crawled_at=now,
    )
    db_session.add_all([crawl, page])
    db_session.flush()
    db_session.add(
        CrawlPageResult(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            crawl_run_id=crawl.id,
            page_id=page.id,
            status_code=200,
            is_indexable=1,
            title="Plumbing services",
            meta_description=None,
            final_url=page.url,
            word_count=80,
            crawled_at=now,
        )
    )
    run = KeywordResearchRun(
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        status="complete",
        location_name="Reno, Nevada",
        sources=["saved_search_evidence"],
        completed_at=now,
    )
    competitor = Competitor(
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
        domain="confirmed-competitor.example",
        discovery_source="manual",
        review_status="confirmed",
    )
    db_session.add_all([run, competitor])
    db_session.flush()
    suggestion = KeywordResearchSuggestion(
        run_id=run.id,
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        keyword="emergency plumber reno",
        normalized_keyword="emergency plumber reno",
        source_types=["saved_search_evidence"],
        evidence={},
        intent="service",
        opportunity_group="new_opportunity",
        relevance_score=95,
        relevance_status="relevant",
        opportunity_score=88,
        recommended_action="create_content_brief",
        recommendation_reason="A confirmed competitor appears for this saved search.",
        source_updated_at=now,
    )
    db_session.add(suggestion)
    db_session.flush()
    db_session.add(
        ContentBrief(
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            business_location_id=campaign.business_location_id,
            suggestion_id=suggestion.id,
            competitor_id=competitor.id,
            idempotency_key=f"workspace-brief:{campaign.id}",
            status="draft",
            title="Improve emergency plumbing for Reno",
            primary_keyword=suggestion.keyword,
            recommended_page_action="improve_existing_page",
            target_url=page.url,
            competitor_domain=competitor.domain,
            service_name="Emergency plumbing",
            service_area_name="Reno",
            evidence={
                "owner_position": None,
                "competitor_position": 4,
                "source_updated_at": now.isoformat(),
                "internal_research_run_id": run.id,
            },
            outline=[
                {
                    "order": 1,
                    "heading": "Make the service clear",
                    "guidance": "Explain who the service helps.",
                }
            ],
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/content/workspace?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["truth"]["state"] == "measured"
    assert payload["summary"] == {
        "pages": 1,
        "pages_needing_attention": 1,
        "draft_briefs": 1,
        "planned_work": 0,
        "published_work": 0,
    }
    assert payload["pages"][0]["source_label"] == "Website scan"
    assert payload["pages"][0]["attention"] == [
        "Add a clear search description",
        "Review whether this page gives customers enough useful detail",
    ]
    assert payload["briefs"][0]["primary_search"] == "emergency plumber reno"
    assert payload["briefs"][0]["evidence"] == {
        "owner_position": None,
        "competitor_position": 4,
        "source_updated_at": now.isoformat(),
    }
    assert payload["briefs"][0]["outline"][0]["heading"] == "Make the service clear"
    assert payload["next_action"]["code"] == "review_content_brief"
    assert "provider" not in str(payload).lower()

    brief_id = payload["briefs"][0]["id"]
    review = client.put(
        f"/api/v1/content/briefs/{brief_id}/review",
        json={"campaign_id": campaign.id, "decision": "accept"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert review.status_code == 200
    reviewed = review.json()["data"]
    assert reviewed["changed"] is True
    assert reviewed["item"]["status"] == "accepted"
    assert reviewed["safety"] == {
        "brief_evidence_changed": False,
        "draft_generated": False,
        "publishing_enabled": False,
        "website_changed": False,
    }

    repeated = client.put(
        f"/api/v1/content/briefs/{brief_id}/review",
        json={"campaign_id": campaign.id, "decision": "accept"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["changed"] is False

    conflicting = client.put(
        f"/api/v1/content/briefs/{brief_id}/review",
        json={"campaign_id": campaign.id, "decision": "decline"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert conflicting.status_code == 409

    refreshed = client.get(
        f"/api/v1/content/workspace?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    assert refreshed["summary"]["draft_briefs"] == 0
    assert refreshed["briefs"][0]["status"] == "accepted"
    assert refreshed["next_action"]["code"] == "review_page_attention"


def test_content_workspace_is_tenant_scoped(client):
    token_a = _login(client, "a@example.com", "pass-a")
    token_b = _login(client, "b@example.com", "pass-b")
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Private Content", "domain": "private-content.com"},
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()["data"]

    response = client.get(
        f"/api/v1/content/workspace?campaign_id={campaign['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
