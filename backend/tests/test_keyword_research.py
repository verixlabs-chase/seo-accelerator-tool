import json
from decimal import Decimal

import httpx

from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.keyword_research import (
    KeywordRelevanceFeedback,
    KeywordResearchRun,
    KeywordResearchSuggestion,
)
from app.models.rank import CampaignKeyword
from app.providers.keyword_research import DataForSeoKeywordResearchProvider
from app.services import business_service_service, keyword_research_service


class FakeKeywordResearchProvider:
    def ranked_keywords(self, **kwargs):  # noqa: ANN003
        assert kwargs["target"] == "plumber.example"
        return {
            "items": [
                {
                    "keyword_data": {
                        "keyword": "emergency plumber",
                        "keyword_info": {"search_volume": 260, "cpc": 18.25},
                        "keyword_properties": {"keyword_difficulty": 31},
                    },
                    "ranked_serp_element": {"serp_item": {"rank_absolute": 8}},
                },
                {
                    "keyword_data": {
                        "keyword": "water heater repair",
                        "keyword_info": {"search_volume": 170, "cpc": 12.0},
                    }
                },
            ],
            "cost": Decimal("0.12"),
        }

    def keyword_ideas(self, **kwargs):  # noqa: ANN003
        assert "emergency plumber" in kwargs["keywords"]
        return {
            "items": [
                {
                    "keyword_data": {
                        "keyword": "same day plumber",
                        "keyword_info": {"search_volume": 90, "cpc": 9.5},
                    }
                }
            ],
            "cost": Decimal("0.12"),
        }

    def search_volume(self, **kwargs):  # noqa: ANN003
        assert "water heater repair" in kwargs["keywords"]
        return {
            "items": [
                {
                    "keyword": "emergency plumber",
                    "search_volume": 320,
                    "cpc": 19.0,
                    "competition_level": "HIGH",
                    "monthly_searches": [{"year": 2026, "month": 7, "search_volume": 320}],
                }
            ],
            "cost": Decimal("0.06"),
        }


class FakeCompetitorKeywordProvider:
    def __init__(self) -> None:
        self.ranked_targets: list[str] = []

    def ranked_keywords(self, **kwargs):  # noqa: ANN003
        target = kwargs["target"]
        self.ranked_targets.append(target)
        if target == "junk.example":
            return {"items": [], "cost": Decimal("0.02")}
        assert target == "trusted-competitor.example"
        return {
            "items": [
                {
                    "keyword_data": {
                        "keyword": "trash hauling reno",
                        "keyword_info": {"search_volume": 140, "cpc": 8.25},
                        "keyword_properties": {"keyword_difficulty": 27},
                    },
                    "ranked_serp_element": {
                        "serp_item": {
                            "rank_absolute": 4,
                            "url": "https://trusted-competitor.example/trash-hauling-reno",
                        }
                    },
                },
                {
                    "keyword_data": {
                        "keyword": "the biggest little city",
                        "keyword_info": {"search_volume": 900},
                    },
                    "ranked_serp_element": {
                        "serp_item": {"rank_absolute": 2}
                    },
                },
            ],
            "cost": Decimal("0.02"),
        }

    def keyword_ideas(self, **_kwargs):  # noqa: ANN003
        return {"items": [], "cost": Decimal("0.01")}

    def search_volume(self, **_kwargs):  # noqa: ANN003
        return {"items": [], "cost": Decimal("0.01")}


def test_provider_uses_current_endpoints_and_resolved_location_code() -> None:
    requests: list[tuple[str, list[dict]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        requests.append((request.url.path, payload))
        if request.url.path.endswith("/search_volume/live"):
            result: list[dict] = [
                {"keyword": "free tv recycling reno nv", "search_volume": 10}
            ]
        else:
            result = [{"items": []}]
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "status_message": "Ok.",
                        "cost": 0.01,
                        "result": result,
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = DataForSeoKeywordResearchProvider(
        login="test-login",
        password="test-password",
        client=client,
    )
    try:
        provider.ranked_keywords(
            target="example.com",
            location_name="Reno, Nevada, United States",
            language_code="en",
            limit=25,
        )
        provider.keyword_ideas(
            keywords=["junk removal, reno"],
            location_name="Reno, Nevada, United States",
            language_code="en",
            limit=25,
        )
        volume_result = provider.search_volume(
            keywords=["free tv recycling reno, nv"],
            location_name="Reno, Nevada, United States",
            language_code="en",
            location_code="1022653",
        )
    finally:
        client.close()

    assert [path for path, _payload in requests] == [
        "/v3/dataforseo_labs/google/ranked_keywords/live",
        "/v3/dataforseo_labs/google/keyword_ideas/live",
        "/v3/keywords_data/google/search_volume/live",
    ]
    assert requests[0][1][0]["location_name"] == "United States"
    assert requests[1][1][0]["location_name"] == "United States"
    assert requests[2][1][0]["location_code"] == 1022653
    assert "location_name" not in requests[2][1][0]
    ideas_payload = requests[1][1][0]
    assert ideas_payload["keywords"] == ["junk removal reno"]
    assert "include_seed_keyword" not in ideas_payload
    assert ideas_payload["order_by"] == ["keyword_info.search_volume,desc"]
    volume_payload = requests[2][1][0]
    assert volume_payload["keywords"] == ["free tv recycling reno nv"]
    assert volume_result["items"][0]["keyword"] == "free tv recycling reno, nv"


def test_provider_warning_is_customer_safe() -> None:
    warning = keyword_research_service._plain_provider_warning(
        ValueError("DataForSEO internal provider detail"),
        "ranked searches",
    )
    assert "DataForSEO" not in warning
    assert warning == (
        "Fresh ranked searches are temporarily unavailable. Saved search data is still shown."
    )


def test_confirmed_service_uses_bounded_versioned_synonyms() -> None:
    service = type(
        "ConfirmedService",
        (),
        {
            "id": "service-1",
            "name": "Junk Removal",
            "normalized_name": "junk removal",
            "aliases": [],
        },
    )()

    matched, score = business_service_service.match_keyword_to_service(
        "trash hauling reno",
        [service],
    )
    unrelated, unrelated_score = business_service_service.match_keyword_to_service(
        "biggest little city",
        [service],
    )

    assert business_service_service.SERVICE_MATCH_RULES_VERSION == (
        "service-synonyms-2026-08-v1"
    )
    assert matched is service
    assert score == 0.84
    assert unrelated is None
    assert unrelated_score == 0

def test_ranked_search_keeps_the_page_that_is_already_showing() -> None:
    parsed = keyword_research_service._parse_labs_item(
        {
            "keyword_data": {"keyword": "emergency plumber"},
            "ranked_serp_element": {
                "serp_item": {
                    "rank_absolute": 8,
                    "url": "https://plumber.example/emergency-plumbing",
                }
            },
        }
    )

    assert parsed["current_position"] == 8
    assert parsed["ranked_url"] == "https://plumber.example/emergency-plumbing"


def test_planning_context_groups_customer_needs_and_maps_a_real_page() -> None:
    planned = keyword_research_service._add_planning_context(
        {
            "keyword": "emergency plumber reno",
            "intent": "Ready to hire",
            "relevance_status": "relevant",
            "matched_service_name": "Emergency Plumbing",
            "matched_service_area_name": "Reno",
            "evidence": {"location": "Reno"},
        },
        target_pages=[
            {
                "url": "https://plumber.example/emergency-plumbing-reno",
                "title": "Emergency Plumbing in Reno",
                "meta_description": "Same-day help for plumbing emergencies.",
                "heading_text": "Emergency plumbing service",
            }
        ],
    )

    assert planned["cluster"] == {
        "key": "emergency-plumbing-urgent-reno",
        "label": "Emergency Plumbing: Urgent jobs in Reno",
        "service_name": "Emergency Plumbing",
        "problem": "Urgent jobs",
        "location_name": "Reno",
        "intent": "Ready to hire",
    }
    assert planned["target_page"]["status"] == "existing"
    assert planned["target_page"]["url"] == (
        "https://plumber.example/emergency-plumbing-reno"
    )


def test_planning_context_keeps_missing_pages_and_uncertain_searches_honest() -> None:
    missing_page = keyword_research_service._add_planning_context(
        {
            "keyword": "junk removal cost reno",
            "intent": "Comparing options",
            "relevance_status": "relevant",
            "matched_service_name": "Junk Removal",
            "matched_service_area_name": "Reno",
            "evidence": {},
        },
        target_pages=[],
    )
    uncertain = keyword_research_service._add_planning_context(
        {
            "keyword": "biggest little city",
            "intent": "Researching",
            "relevance_status": "needs_review",
            "matched_service_name": None,
            "matched_service_area_name": "Reno",
            "evidence": {},
        },
        target_pages=[],
    )

    assert missing_page["cluster"]["problem"] == "Price questions"
    assert missing_page["target_page"]["status"] == "needs_page"
    assert uncertain["target_page"]["status"] == "review"
    assert "Confirm this search" in uncertain["target_page"]["reason"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_keyword_research_api_returns_empty_state_before_first_run(client) -> None:
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign = client.post(
        "/api/v1/campaigns",
        json={"name": "Research API Campaign", "domain": "research-api.example"},
        headers=headers,
    ).json()["data"]

    response = client.get(
        f"/api/v1/keyword-research?campaign_id={campaign['id']}",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "run": None,
        "items": [],
        "summary": {
            "total": 0,
            "quick_wins": 0,
            "new_opportunities": 0,
            "already_found": 0,
            "tracked": 0,
            "best_matches": 0,
            "needs_review": 0,
            "hidden_unrelated": 0,
        },
    }


def test_keyword_feedback_api_saves_a_scoped_owner_choice(client, db_session) -> None:
    token = _login(client, "a@example.com", "pass-a")
    headers = {"Authorization": f"Bearer {token}"}
    campaign_payload = client.post(
        "/api/v1/campaigns",
        json={"name": "Feedback API Campaign", "domain": "feedback-api.example"},
        headers=headers,
    ).json()["data"]
    campaign = db_session.get(Campaign, campaign_payload["id"])
    assert campaign is not None
    service_response = client.post(
        "/api/v1/business-services",
        json={"campaign_id": campaign.id, "name": "Junk Removal"},
        headers=headers,
    )
    assert service_response.status_code == 200
    service = service_response.json()["data"]["items"][0]

    run = KeywordResearchRun(
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        status="complete",
        location_name="United States",
    )
    db_session.add(run)
    db_session.flush()
    suggestion = KeywordResearchSuggestion(
        run_id=run.id,
        tenant_id=campaign.tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        keyword="trash hauling",
        normalized_keyword="trash hauling",
        source_types=["website_content"],
        evidence={"sources": ["website_content"]},
        intent="Ready to hire",
        opportunity_group="new_opportunity",
        relevance_score=55,
        relevance_status="needs_review",
        opportunity_score=48,
        recommended_action="Review this search",
        recommendation_reason="Confirm that it matches work you offer.",
    )
    db_session.add(suggestion)
    db_session.commit()

    response = client.post(
        "/api/v1/keyword-research/feedback",
        json={
            "campaign_id": campaign.id,
            "suggestion_id": suggestion.id,
            "decision": "relevant",
            "service_id": service["id"],
        },
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["feedback"]["decision"] == "relevant"
    assert payload["items"][0]["owner_feedback"] == "relevant"
    assert payload["items"][0]["matched_service_name"] == "Junk Removal"
    feedback = db_session.query(KeywordRelevanceFeedback).one()
    assert feedback.tenant_id == campaign.tenant_id
    assert feedback.campaign_id == campaign.id
    assert feedback.created_by_user_id is not None

def test_discovery_scores_real_sources_and_promotes_selected_searches(
    db_session,
    create_test_org,
) -> None:
    organization = create_test_org(name="Keyword Research Org")
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Plumbing Shop",
        domain="plumber.example",
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    payload = keyword_research_service.discover(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        max_suggestions=25,
        provider=FakeKeywordResearchProvider(),
    )

    assert payload["run"]["status"] == "complete"
    assert payload["run"]["sources"] == [
        "dataforseo_ideas",
        "dataforseo_ranked",
        "dataforseo_volume",
    ]
    assert payload["summary"]["total"] == 3
    emergency = next(item for item in payload["items"] if item["keyword"] == "emergency plumber")
    assert emergency["search_volume"] == 320
    assert emergency["current_position"] == 8
    assert emergency["opportunity_group"] == "quick_win"
    assert emergency["recommended_action"] == "Improve the page already showing"
    assert emergency["intent"] == "Ready to hire"
    assert emergency["relevance_status"] == "needs_review"

    tracked = keyword_research_service.track_suggestions(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        suggestion_ids=[emergency["id"]],
    )
    assert tracked["created_count"] == 1
    assert db_session.query(CampaignKeyword).filter(
        CampaignKeyword.campaign_id == campaign.id,
        CampaignKeyword.keyword == "emergency plumber",
    ).count() == 1
    persisted = db_session.get(KeywordResearchSuggestion, emergency["id"])
    assert persisted is not None and persisted.tracked_at is not None
    assert db_session.query(KeywordResearchRun).filter(
        KeywordResearchRun.campaign_id == campaign.id
    ).count() == 1


def test_discovery_adds_saved_competitor_gaps_without_overwriting_customer_position(
    db_session,
    create_test_org,
) -> None:
    organization = create_test_org(name="Competitor Keyword Org")
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Junk Removal Shop",
        domain="junk.example",
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.flush()
    business_service_service.add_manual_service(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        name="Junk Removal",
    )
    competitor = Competitor(
        tenant_id=organization.id,
        campaign_id=campaign.id,
        domain="https://trusted-competitor.example/",
        label="Trusted Haulers",
    )
    db_session.add(competitor)
    db_session.commit()

    provider = FakeCompetitorKeywordProvider()
    payload = keyword_research_service.discover(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        max_suggestions=25,
        provider=provider,
    )

    assert provider.ranked_targets == ["junk.example", "trusted-competitor.example"]
    assert "competitor_rankings" in payload["run"]["sources"]
    gap = next(item for item in payload["items"] if item["keyword"] == "trash hauling reno")
    assert gap["current_position"] is None
    assert gap["relevance_status"] == "needs_review"
    assert gap["recommended_action"] == "Review this competitor gap"
    assert gap["competitor_evidence"] == [
        {
            "competitor_id": competitor.id,
            "domain": "trusted-competitor.example",
            "label": "Trusted Haulers",
            "position": 4.0,
            "url": "https://trusted-competitor.example/trash-hauling-reno",
            "observed_at": gap["competitor_evidence"][0]["observed_at"],
        }
    ]
    unrelated = next(
        item for item in payload["items"] if item["keyword"] == "the biggest little city"
    )
    assert unrelated["relevance_status"] == "unrelated"
    assert unrelated["search_volume"] == 900
    assert unrelated["recommended_action"] == "Keep this hidden"


def test_owner_relevance_choice_is_audited_and_survives_future_refreshes(
    db_session,
    create_test_org,
) -> None:
    organization = create_test_org(name="Keyword Feedback Org")
    campaign = Campaign(
        tenant_id=organization.id,
        organization_id=organization.id,
        name="Plumbing Shop",
        domain="plumber.example",
        setup_state="Active",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    business_service_service.add_manual_service(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        name="Plumbing",
    )
    service = business_service_service.confirmed_services_for_campaign(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
    )[0]

    first = keyword_research_service.discover(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        max_suggestions=25,
        provider=FakeKeywordResearchProvider(),
    )
    suggestion = next(
        item for item in first["items"] if item["keyword"] == "emergency plumber"
    )
    assert suggestion["relevance_status"] == "needs_review"

    saved = keyword_research_service.save_relevance_feedback(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        suggestion_id=suggestion["id"],
        decision="relevant",
        service_id=service.id,
        created_by_user_id=None,
    )
    saved_item = next(
        item for item in saved["items"] if item["keyword"] == "emergency plumber"
    )
    assert saved_item["relevance_status"] == "relevant"
    assert saved_item["owner_feedback"] == "relevant"
    assert saved_item["matched_service_name"] == "Plumbing"

    refreshed = keyword_research_service.discover(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        max_suggestions=25,
        provider=FakeKeywordResearchProvider(),
    )
    refreshed_item = next(
        item for item in refreshed["items"] if item["keyword"] == "emergency plumber"
    )
    assert refreshed_item["relevance_status"] == "relevant"
    assert refreshed_item["owner_feedback"] == "relevant"

    cleared = keyword_research_service.save_relevance_feedback(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        suggestion_id=refreshed_item["id"],
        decision="cleared",
        service_id=None,
        created_by_user_id=None,
    )
    cleared_item = next(
        item for item in cleared["items"] if item["keyword"] == "emergency plumber"
    )
    assert cleared_item["relevance_status"] == "needs_review"
    assert cleared_item["owner_feedback"] is None

    hidden = keyword_research_service.save_relevance_feedback(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        suggestion_id=cleared_item["id"],
        decision="unrelated",
        service_id=None,
        created_by_user_id=None,
    )
    hidden_item = next(
        item for item in hidden["items"] if item["keyword"] == "emergency plumber"
    )
    assert hidden_item["relevance_status"] == "unrelated"
    assert hidden_item["owner_feedback"] == "unrelated"

    hidden_refresh = keyword_research_service.discover(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        max_suggestions=25,
        provider=FakeKeywordResearchProvider(),
    )
    hidden_refresh_item = next(
        item
        for item in hidden_refresh["items"]
        if item["keyword"] == "emergency plumber"
    )
    assert hidden_refresh_item["relevance_status"] == "unrelated"
    assert hidden_refresh_item["owner_feedback"] == "unrelated"
    assert (
        db_session.query(KeywordRelevanceFeedback)
        .filter(KeywordRelevanceFeedback.campaign_id == campaign.id)
        .count()
        == 3
    )
def test_latest_keyword_research_is_tenant_scoped(
    db_session,
    create_test_org,
    create_test_tenant,
) -> None:
    first_tenant = create_test_tenant(name="First Research Tenant")
    second_tenant = create_test_tenant(name="Second Research Tenant")
    first = create_test_org(
        organization_id=first_tenant.id,
        tenant_id=first_tenant.id,
        name="First Research Org",
    )
    second = create_test_org(
        organization_id=second_tenant.id,
        tenant_id=second_tenant.id,
        name="Second Research Org",
    )
    campaign = Campaign(
        tenant_id=first.id,
        organization_id=first.id,
        name="Scoped Campaign",
        domain="scoped.example",
    )
    db_session.add(campaign)
    db_session.commit()

    try:
        keyword_research_service.get_latest(
            db_session,
            tenant_id=second.id,
            campaign_id=campaign.id,
        )
    except Exception as exc:  # FastAPI's HTTPException is the expected public boundary.
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Cross-tenant keyword research access should fail.")
