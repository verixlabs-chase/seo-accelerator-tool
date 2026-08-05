from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.services.search_value_service import build_search_value
from tests.conftest import create_test_campaign


NOW = datetime(2026, 8, 4, 18, 0, tzinfo=UTC)


def _run(db_session, campaign, *, saved_at: datetime, location: str = "Reno, Nevada"):
    row = KeywordResearchRun(
        id=str(uuid.uuid4()),
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=None,
        status="complete",
        location_name=location,
        language_code="en",
        sources=["saved_market_research", "google_search_console"],
        warnings=[],
        suggestion_count=0,
        started_at=saved_at - timedelta(minutes=2),
        completed_at=saved_at,
        created_at=saved_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _suggestion(
    db_session,
    campaign,
    run,
    *,
    keyword: str,
    cpc: str | None,
    search_volume: int | None,
    position: float | None,
    gsc_clicks: float | None = None,
    gsc_impressions: float | None = None,
    relevance_status: str = "relevant",
):
    normalized = " ".join(keyword.lower().split())
    row = KeywordResearchSuggestion(
        id=str(uuid.uuid4()),
        run_id=run.id,
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        business_location_id=None,
        keyword=keyword,
        normalized_keyword=normalized,
        source_types=(
            ["google_search_console", "market_research"]
            if gsc_clicks is not None
            else ["market_research"]
        ),
        evidence={},
        search_volume=search_volume,
        cpc=Decimal(cpc) if cpc is not None else None,
        competition=0.5,
        competition_level="MEDIUM",
        keyword_difficulty=25,
        monthly_searches=[],
        current_position=position,
        gsc_clicks=gsc_clicks,
        gsc_impressions=gsc_impressions,
        gsc_position=position if gsc_clicks is not None else None,
        intent="commercial",
        opportunity_group="quick_win",
        relevance_score=90,
        relevance_status=relevance_status,
        matched_service_name="Junk removal",
        matched_service_area_name="Reno",
        area_match_type="direct",
        relevance_reason="Matches the confirmed service and area.",
        opportunity_score=80,
        recommended_action="Improve the matching service page",
        recommendation_reason="This useful search is already visible.",
        source_updated_at=run.completed_at,
        created_at=run.created_at,
    )
    db_session.add(row)
    run.suggestion_count += 1
    db_session.flush()
    return row


def _seed_current_value(db_session, campaign, *, saved_at: datetime = NOW):
    run = _run(db_session, campaign, saved_at=saved_at)
    _suggestion(
        db_session,
        campaign,
        run,
        keyword="junk removal reno",
        cpc="5.00",
        search_volume=1000,
        position=3,
        gsc_clicks=90,
        gsc_impressions=900,
    )
    _suggestion(
        db_session,
        campaign,
        run,
        keyword="appliance pickup reno",
        cpc="10.00",
        search_volume=500,
        position=5,
    )
    _suggestion(
        db_session,
        campaign,
        run,
        keyword="the biggest little city",
        cpc="12.00",
        search_volume=5000,
        position=2,
        relevance_status="unrelated",
    )
    db_session.commit()
    return run


def test_search_value_is_deterministic_and_auditable(db_session, create_test_org) -> None:
    org = create_test_org(name="Search value org")
    campaign = create_test_campaign(db_session, org.id, tenant_id=org.id, name="Reno Local SEO")
    _seed_current_value(db_session, campaign)

    first = build_search_value(db_session, campaign_id=campaign.id, tenant_id=campaign.tenant_id, now=NOW)
    second = build_search_value(db_session, campaign_id=campaign.id, tenant_id=campaign.tenant_id, now=NOW)

    assert first == second
    assert first["status"] == "available"
    assert first["estimate"]["central"] == "450.00"
    assert first["estimate"]["lower"] == "345.00"
    assert first["estimate"]["upper"] == "555.00"
    assert first["coverage"]["percent"] == 100.0
    assert first["coverage"]["valued_phrases"] == 2
    assert first["source_split"]["measured_value"] == "150.00"
    assert first["source_split"]["modeled_value"] == "300.00"
    assert first["source_split"]["measured_share_percent"] == 33.3
    assert {item["click_method"] for item in first["keywords"]} == {"measured", "modeled"}
    assert all(item["source_date"] for item in first["keywords"])
    assert len(first["input_hash"]) == 64
    assert "biggest little city" not in str(first).lower()


def test_search_value_compares_saved_runs_without_new_provider_work(db_session, create_test_org) -> None:
    org = create_test_org(name="Search value history org")
    campaign = create_test_campaign(db_session, org.id, tenant_id=org.id)
    previous = _run(db_session, campaign, saved_at=NOW - timedelta(days=30))
    _suggestion(
        db_session,
        campaign,
        previous,
        keyword="junk removal reno",
        cpc="4.00",
        search_volume=800,
        position=6,
        gsc_clicks=60,
        gsc_impressions=700,
    )
    db_session.commit()
    _seed_current_value(db_session, campaign)

    payload = build_search_value(db_session, campaign_id=campaign.id, tenant_id=campaign.tenant_id, now=NOW)

    assert len(payload["history"]) == 2
    assert payload["comparison"]["previous_run_id"] == previous.id
    assert payload["comparison"]["formula_changed"] is False
    assert {item["key"] for item in payload["comparison"]["signals"]} == {
        "rankings",
        "demand",
        "cpc",
        "coverage",
        "model",
    }
    assert payload["research"]["new_paid_check_required"] is False


def test_search_value_models_queries_when_search_console_sample_is_too_small(
    db_session,
    create_test_org,
) -> None:
    org = create_test_org(name="Low sample search value org")
    campaign = create_test_campaign(db_session, org.id, tenant_id=org.id)
    run = _run(db_session, campaign, saved_at=NOW)
    _suggestion(
        db_session,
        campaign,
        run,
        keyword="small sample junk pickup",
        cpc="4.00",
        search_volume=100,
        position=4,
        gsc_clicks=1,
        gsc_impressions=3,
    )
    db_session.commit()

    payload = build_search_value(
        db_session,
        campaign_id=campaign.id,
        tenant_id=campaign.tenant_id,
        now=NOW,
    )

    assert payload["keywords"][0]["click_method"] == "modeled"
    assert payload["source_split"]["measured_share_percent"] == 0.0


def test_search_value_withholds_stale_research(db_session, create_test_org) -> None:
    org = create_test_org(name="Stale search value org")
    campaign = create_test_campaign(db_session, org.id, tenant_id=org.id)
    _seed_current_value(db_session, campaign, saved_at=NOW - timedelta(days=91))

    payload = build_search_value(db_session, campaign_id=campaign.id, tenant_id=campaign.tenant_id, now=NOW)

    assert payload["status"] == "withheld"
    assert payload["estimate"]["central"] is None
    assert payload["keywords"][0]["contribution"] is None
    assert payload["confidence"]["level"] == "low"


def test_search_value_api_is_tenant_scoped_and_hides_market_supplier(
    client,
    db_session,
    create_test_org,
) -> None:
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pass-a"})
    token = login.json()["data"]["access_token"]
    tenant_id = login.json()["data"]["user"]["tenant_id"]
    campaign = create_test_campaign(db_session, tenant_id, tenant_id=tenant_id, name="Reno Local SEO")
    _seed_current_value(db_session, campaign)

    response = client.get(
        f"/api/v1/campaigns/{campaign.id}/search-value",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["estimate"]["central"] == "450.00"
    assert data["scope"]["location_name"] == "Reno, Nevada"
    assert "dataforseo" not in str(data).lower()
    assert "not revenue" in data["explanation"].lower()

    other_org = create_test_org(name="Other tenant search value")
    other_campaign = create_test_campaign(db_session, other_org.id, tenant_id=other_org.id)
    forbidden = client.get(
        f"/api/v1/campaigns/{other_campaign.id}/search-value",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert forbidden.status_code == 404
