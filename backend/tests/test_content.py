from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.content import ContentBrief
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.services import content_service


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
    assert payload["capabilities"]["working_drafts_available"] is True
    assert payload["summary"] == {
        "pages": 1,
        "pages_needing_attention": 1,
        "draft_briefs": 1,
        "working_drafts": 0,
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
    premature_draft = client.post(
        f"/api/v1/content/briefs/{brief_id}/draft",
        json={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert premature_draft.status_code == 409

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
    assert refreshed["next_action"]["code"] == "start_content_draft"

    create_draft = client.post(
        f"/api/v1/content/briefs/{brief_id}/draft",
        json={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_draft.status_code == 200
    draft_payload = create_draft.json()["data"]
    assert draft_payload["created"] is True
    assert draft_payload["item"]["revision"] == 1
    assert draft_payload["item"]["sections"][0]["body"] == ""
    assert draft_payload["safety"] == {
        "ai_generated": False,
        "automatic_publishing_allowed": False,
        "website_changed": False,
        "approval_to_publish_recorded": False,
    }

    repeat_draft = client.post(
        f"/api/v1/content/briefs/{brief_id}/draft",
        json={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeat_draft.status_code == 200
    assert repeat_draft.json()["data"]["created"] is False

    draft_id = draft_payload["item"]["id"]
    sections = [
        {
            "order": item["order"],
            "heading": item["heading"],
            "body": "Owner-written wording for this section.",
        }
        for item in draft_payload["item"]["sections"]
    ]
    saved = client.put(
        f"/api/v1/content/drafts/{draft_id}",
        json={
            "campaign_id": campaign.id,
            "title": "Emergency plumbing in Reno",
            "sections": sections,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert saved.status_code == 200
    saved_payload = saved.json()["data"]
    assert saved_payload["changed"] is True
    assert saved_payload["item"]["revision"] == 2
    assert saved_payload["item"]["sections"][0]["body"].startswith("Owner-written")

    repeated_save = client.put(
        f"/api/v1/content/drafts/{draft_id}",
        json={
            "campaign_id": campaign.id,
            "title": "Emergency plumbing in Reno",
            "sections": sections,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert repeated_save.status_code == 200
    assert repeated_save.json()["data"]["changed"] is False

    with_draft = client.get(
        f"/api/v1/content/workspace?campaign_id={campaign.id}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    assert with_draft["summary"]["working_drafts"] == 1
    assert with_draft["briefs"][0]["working_draft"]["revision"] == 2
    metadata = with_draft["briefs"][0]["working_draft"][
        "metadata_recommendations"
    ]
    assert [item["code"] for item in metadata] == [
        "seo_title",
        "meta_description",
    ]
    assert metadata[0]["current_value"] == "Plumbing services"
    assert metadata[0]["proposed_value"] == "Emergency plumbing in Reno"
    assert metadata[0]["state"] == "review"
    assert metadata[1]["current_value"] is None
    assert metadata[1]["state"] == "add"
    assert metadata[1]["proposed_character_count"] <= 160
    assert metadata[1]["safety"] == {
        "owner_approval_required": True,
        "automatic_publishing_allowed": False,
        "website_changed": False,
    }
    assert "Google ranking rule" in metadata[0]["limitations"][0]
    structured = with_draft["briefs"][0]["working_draft"][
        "structured_data_recommendation"
    ]
    assert structured["state"] == "add"
    assert structured["recommended_type"] == "Service"
    assert structured["recommended_type_label"] == "Service details"
    assert structured["current_types"] == []
    assert structured["current_state"] == "not_found"
    fields = {item["code"]: item for item in structured["fields"]}
    assert fields["service_name"] == {
        "code": "service_name",
        "label": "Service name",
        "value": "Emergency plumbing",
        "state": "confirmed",
        "required": True,
    }
    assert fields["service_area"]["value"] == "Reno"
    assert fields["service_area"]["state"] == "confirmed"
    assert fields["page_url"]["value"] == "https://workspace-content.com/plumbing"
    assert fields["page_url"]["state"] == "confirmed"
    assert fields["business_identity"]["value"] is None
    assert fields["business_identity"]["state"] == "owner_confirmation_required"
    assert structured["safety"] == {
        "owner_approval_required": True,
        "publishable_code_created": False,
        "automatic_publishing_allowed": False,
        "website_changed": False,
    }
    assert any("higher rankings" in item for item in structured["limitations"])
    internal_links = with_draft["briefs"][0]["working_draft"][
        "internal_link_recommendations"
    ]
    assert internal_links["state"] == "no_related_pages"
    assert internal_links["target"] == {
        "title": "Plumbing services",
        "url": "https://workspace-content.com/plumbing",
    }
    assert internal_links["items"] == []
    assert internal_links["safety"] == {
        "owner_approval_required": True,
        "link_insertion_allowed": False,
        "automatic_publishing_allowed": False,
        "website_changed": False,
    }
    assert any("exact shared accepted wording" in item for item in internal_links["limitations"])
    readiness = with_draft["briefs"][0]["working_draft"]["content_readiness"]
    assert readiness["state"] == "ready_for_owner_review"
    assert readiness["facts"]["planned_sections"] == 1
    assert readiness["facts"]["completed_sections"] == 1
    assert readiness["facts"]["blocked_checks"] == 0
    assert readiness["facts"]["checks_needing_attention"] == 0
    assert {item["state"] for item in readiness["checks"]} == {"passed"}
    assert readiness["safety"]["owner_approval_recorded"] is False
    assert readiness["safety"]["publishing_allowed"] is False
    assert with_draft["next_action"]["code"] == "continue_content_draft"


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


def test_internal_link_recommendations_use_exact_saved_page_evidence():
    brief = SimpleNamespace(
        target_url="https://example.com/emergency-plumbing",
        service_name="Emergency plumbing",
        service_area_name="Reno",
        primary_keyword="emergency plumber reno",
        title="Emergency plumbing in Reno",
    )
    observed_at = datetime(2026, 8, 15, tzinfo=UTC)
    result = content_service._internal_link_recommendations(
        brief,
        page_metadata={
            "url": brief.target_url,
            "title": "Emergency plumbing",
        },
        page_inventory=[
            {
                "url": brief.target_url,
                "title": "Emergency plumbing",
                "eligible_for_internal_links": True,
                "outgoing_internal_links": [],
                "source_label": "Website scan",
                "observed_at": observed_at,
            },
            {
                "url": "https://example.com/emergency-plumbing-tips",
                "title": "Emergency plumbing tips",
                "eligible_for_internal_links": True,
                "outgoing_internal_links": [],
                "source_label": "Website scan",
                "observed_at": observed_at,
            },
            {
                "url": "https://example.com/reno-emergency-guide",
                "title": "Reno emergency guide",
                "eligible_for_internal_links": True,
                "outgoing_internal_links": ["/emergency-plumbing/#contact"],
                "source_label": "Connected website",
                "observed_at": observed_at,
            },
            {
                "url": "https://example.com/plumber-options",
                "title": "Reno plumber options",
                "eligible_for_internal_links": True,
                "outgoing_internal_links": ["/emergency-plumbing/#contact"],
                "source_label": "Connected website",
                "observed_at": observed_at,
            },
            {
                "url": "https://example.com/about",
                "title": "About the company",
                "eligible_for_internal_links": True,
                "outgoing_internal_links": [],
                "source_label": "Website scan",
                "observed_at": observed_at,
            },
            {
                "url": "https://example.com/plumbing-draft",
                "title": "Emergency plumbing draft",
                "eligible_for_internal_links": False,
                "outgoing_internal_links": [],
                "source_label": "Connected website",
                "observed_at": observed_at,
            },
        ],
    )

    assert result["state"] == "recommendations_ready"
    assert [item["state"] for item in result["items"]] == [
        "recommended",
        "already_exists",
    ]
    recommendation = result["items"][0]
    assert recommendation["source_title"] == "Emergency plumbing tips"
    assert recommendation["source_url"] == "https://example.com/emergency-plumbing-tips"
    assert recommendation["target_url"] == brief.target_url
    assert recommendation["suggested_anchor"] == "Emergency plumbing"
    assert recommendation["existing_link_found"] is False
    assert recommendation["relationship_evidence"] == [
        "Saved source page: Emergency plumbing tips",
        "Shared accepted wording: plumbing",
    ]
    assert result["items"][1]["existing_link_found"] is True
    assert result["items"][1]["source_title"] == "Reno plumber options"
    assert all(item["source_title"] != "Reno emergency guide" for item in result["items"])
    assert all(item["source_title"] != "About the company" for item in result["items"])
    assert all(item["source_title"] != "Emergency plumbing draft" for item in result["items"])
    assert result["safety"]["link_insertion_allowed"] is False


def test_content_readiness_separates_owner_review_from_publishing():
    brief = SimpleNamespace(
        id="brief-1",
        title="Emergency plumbing in Reno",
        primary_keyword="emergency plumber reno",
        recommended_page_action="improve_existing_page",
        target_url="https://example.com/emergency-plumbing",
        competitor_domain="competitor.example",
        competitor_url=None,
        service_name="Emergency plumbing",
        service_area_name="Reno",
        evidence={"competitor_position": 4},
        outline=[
            {"order": 1, "heading": "Explain the service"},
            {"order": 2, "heading": "Explain the next step"},
        ],
    )
    unsafe_copy = "Guaranteed 20 years <script>alert('no')</script>"
    draft = SimpleNamespace(
        title="Emergency plumbing",
        sections=[
            {
                "order": 1,
                "heading": "Explain the service",
                "body": unsafe_copy,
            }
        ],
        source_brief_hash=content_service._content_brief_hash(brief),
    )

    result = content_service._content_readiness(draft, brief)

    assert result["state"] == "blocked"
    checks = {item["code"]: item for item in result["checks"]}
    assert checks["accepted_brief"]["state"] == "passed"
    assert checks["required_sections"]["state"] == "blocked"
    assert checks["service_fact"]["state"] == "passed"
    assert checks["service_area_fact"]["state"] == "action_needed"
    assert checks["safe_plain_text"]["state"] == "blocked"
    assert checks["business_claims"]["state"] == "owner_confirmation"
    assert unsafe_copy not in str(result)
    assert result["safety"] == {
        "owner_approval_recorded": False,
        "publishing_allowed": False,
        "automatic_publishing_allowed": False,
        "website_changed": False,
    }
    assert "not approval" in result["limitations"][0]
