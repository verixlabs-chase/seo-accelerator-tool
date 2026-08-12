from __future__ import annotations

from datetime import UTC, datetime

from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.engagement import AchievementGrant
from app.models.intelligence import StrategyRecommendation
from app.models.product_analytics import ProductAnalyticsEvent
from app.models.tenant import Tenant


def _login(client, email: str = "a@example.com", password: str = "pass-a") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _foundation_campaign(db_session, organization_id: str) -> tuple[Campaign, BusinessLocation]:
    location = BusinessLocation(
        organization_id=organization_id,
        name="Austin Service Team",
        domain="service.example",
        city="Austin",
        region="Texas",
        status="active",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=location.id,
        name="Austin visibility",
        domain="service.example",
    )
    db_session.add(campaign)
    db_session.commit()
    return campaign, location


def _evaluate(client, token: str, campaign_id: str):
    return client.post(
        "/api/v1/engagement/achievements/evaluate",
        params={"campaign_id": campaign_id},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_foundation_achievements_are_evidence_backed_and_replay_safe(client, db_session) -> None:
    token, organization_id = _login(client)
    campaign, location = _foundation_campaign(db_session, organization_id)

    first = _evaluate(client, token, campaign.id)
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert [item["rule_key"] for item in first_data["newly_earned"]] == [
        "foundation.location_ready"
    ]
    assert first_data["next_milestone"]["rule_key"] == "foundation.first_live_sync"
    assert first_data["newly_earned"][0]["scope"] == {
        "type": "location",
        "id": location.id,
        "label": "Austin Service Team",
    }
    assert first_data["newly_earned"][0]["evidence"][0]["evidence_type"] == "location_setup"

    replay = _evaluate(client, token, campaign.id)
    assert replay.status_code == 200
    assert replay.json()["data"]["newly_earned"] == []
    assert db_session.query(AchievementGrant).count() == 1

    successful_at = datetime(2026, 8, 12, 15, 0, tzinfo=UTC)
    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location.id,
            campaign_id=campaign.id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:service.example",
            external_resource_name="service.example",
            status="connected",
            last_success_at=successful_at,
        )
    )
    db_session.commit()

    connected = _evaluate(client, token, campaign.id)
    assert connected.status_code == 200
    connected_data = connected.json()["data"]
    assert [item["rule_key"] for item in connected_data["newly_earned"]] == [
        "foundation.first_live_sync"
    ]
    live_evidence = connected_data["newly_earned"][0]["evidence"][0]
    assert live_evidence["evidence_type"] == "successful_data_sync"
    assert live_evidence["successful_at"].startswith("2026-08-12T15:00:00")

    recommendation = StrategyRecommendation(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        recommendation_type="policy::technical_health::fix_titles",
        rationale="Important pages need clearer titles.",
        evidence_json='{"evidence":["3 pages need titles"]}',
        rollback_plan_json='{"steps":["restore prior titles"]}',
    )
    db_session.add(recommendation)
    db_session.flush()
    occurrence = ActionPlanOccurrence(
        tenant_id=organization_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        recommendation_id=recommendation.id,
        action_id="technical.fix_titles",
        cadence="weekly",
        period_key="2026-W33",
        status="ready",
        lexicon_id="seo-intelligence-core",
        lexicon_version="1.0.0",
        content_hash="a" * 64,
        idempotency_key="b" * 64,
    )
    db_session.add(occurrence)
    db_session.flush()
    captured_at = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
    db_session.add(
        ActionPlanMeasurement(
            tenant_id=organization_id,
            organization_id=organization_id,
            campaign_id=campaign.id,
            business_location_id=location.id,
            occurrence_id=occurrence.id,
            recommendation_id=recommendation.id,
            action_id=occurrence.action_id,
            measurement_status="baseline_ready",
            outcome_status="pending",
            result_classification="waiting_for_results",
            measurement_contract={
                "version": "2.0",
                "track": "website",
                "primary_metric_id": "search.clicks",
            },
            success_metric_ids=["search.clicks"],
            baseline_metrics=[
                {
                    "metric_id": "search.clicks",
                    "status": "available",
                    "value": 42,
                    "unit": "clicks",
                    "source": "Google Search Console",
                    "source_record_id": "metric-row-42",
                }
            ],
            baseline_evidence=[{"source_record_id": "metric-row-42"}],
            implementation_scope={"campaign_id": campaign.id},
            completion_proof=[],
            outcome_metrics=[],
            outcome_evidence=[],
            observation_window_days=28,
            baseline_captured_at=captured_at,
            action_plan_hash=occurrence.content_hash,
            lexicon_id=occurrence.lexicon_id,
            lexicon_version=occurrence.lexicon_version,
        )
    )
    db_session.commit()

    measured = _evaluate(client, token, campaign.id)
    assert measured.status_code == 200
    measured_data = measured.json()["data"]
    assert [item["rule_key"] for item in measured_data["newly_earned"]] == [
        "foundation.first_trustworthy_baseline"
    ]
    assert measured_data["earned_count"] == 3
    assert measured_data["foundation_earned_count"] == 3
    assert measured_data["next_milestone"] is None
    assert measured_data["safety"]["verified_result_rewards_enabled"] is False
    baseline_evidence = measured_data["newly_earned"][0]["evidence"][0]
    assert baseline_evidence["measurement_id"]
    assert baseline_evidence["metric_id"] == "search.clicks"
    assert baseline_evidence["source_record_id"] == "metric-row-42"

    final_replay = _evaluate(client, token, campaign.id)
    assert final_replay.status_code == 200
    assert final_replay.json()["data"]["newly_earned"] == []
    assert db_session.query(AchievementGrant).count() == 3
    assert {
        row.category for row in db_session.query(AchievementGrant).all()
    } == {"foundation"}
    achievement_events = (
        db_session.query(ProductAnalyticsEvent)
        .filter(ProductAnalyticsEvent.event_name == "achievement.earned")
        .all()
    )
    assert len(achievement_events) == 3
    assert all(event.source == "product_server" for event in achievement_events)


def test_stale_connection_and_untrusted_baseline_do_not_grant(client, db_session) -> None:
    token, organization_id = _login(client)
    campaign, location = _foundation_campaign(db_session, organization_id)
    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=location.id,
            campaign_id=campaign.id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:service.example",
            status="connected",
            last_success_at=None,
        )
    )
    db_session.commit()

    response = _evaluate(client, token, campaign.id)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["earned_count"] == 1
    assert data["next_milestone"]["rule_key"] == "foundation.first_live_sync"
    assert all(item["category"] != "verified_result" for item in data["achievements"])


def test_preferences_do_not_delete_history_and_campaigns_are_tenant_scoped(client, db_session) -> None:
    token, organization_id = _login(client)
    campaign, _location = _foundation_campaign(db_session, organization_id)
    assert _evaluate(client, token, campaign.id).status_code == 200

    preference = client.patch(
        "/api/v1/engagement/achievement-preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"celebrations_enabled": False, "notifications_enabled": False},
    )
    assert preference.status_code == 200
    assert preference.json()["data"]["preferences"] == {
        "celebrations_enabled": False,
        "notifications_enabled": False,
    }

    history = client.get(
        "/api/v1/engagement/achievements",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()["data"]["earned_count"] == 1
    assert history.json()["data"]["preferences"]["celebrations_enabled"] is False

    tenant_b = db_session.query(Tenant).filter(Tenant.name == "Tenant B").one()
    other_location = BusinessLocation(
        organization_id=tenant_b.id,
        name="Other location",
        domain="other.example",
        city="Dallas",
    )
    db_session.add(other_location)
    db_session.flush()
    other_campaign = Campaign(
        tenant_id=tenant_b.id,
        organization_id=tenant_b.id,
        business_location_id=other_location.id,
        name="Other campaign",
        domain="other.example",
    )
    db_session.add(other_campaign)
    db_session.commit()

    forbidden = _evaluate(client, token, other_campaign.id)
    assert forbidden.status_code == 404
    assert db_session.query(AchievementGrant).count() == 1
