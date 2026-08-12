from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.action_plan import ActionPlanMeasurement, ActionPlanOccurrence, ActionPlanStep
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


def _completed_plan(
    db_session,
    *,
    organization_id: str,
    campaign: Campaign,
    location: BusinessLocation,
    cadence: str,
    period_key: str,
    completed_at: datetime,
) -> ActionPlanOccurrence:
    recommendation = StrategyRecommendation(
        tenant_id=organization_id,
        campaign_id=campaign.id,
        recommendation_type=f"policy::{cadence}::{period_key}",
        rationale="Complete the saved work plan.",
        evidence_json='{"evidence":["saved checklist"]}',
        rollback_plan_json='{"steps":["review the saved work"]}',
    )
    db_session.add(recommendation)
    db_session.flush()
    stable_suffix = f"{cadence}-{period_key}".encode("utf-8").hex()[:32]
    occurrence = ActionPlanOccurrence(
        tenant_id=organization_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        recommendation_id=recommendation.id,
        action_id=f"plan.{cadence}.{period_key}",
        cadence=cadence,
        period_key=period_key,
        status="waiting_for_results",
        lexicon_id="seo-intelligence-core",
        lexicon_version="1.0.0",
        content_hash=(stable_suffix + "a" * 64)[:64],
        idempotency_key=(stable_suffix + "b" * 64)[:64],
        completed_at=completed_at,
    )
    db_session.add(occurrence)
    db_session.flush()
    db_session.add(
        ActionPlanStep(
            tenant_id=organization_id,
            organization_id=organization_id,
            occurrence_id=occurrence.id,
            step_key="required-work",
            position=1,
            instruction="Finish the required work.",
            required=True,
            status="done",
            evidence=["Saved completion proof"],
            completed_at=completed_at,
        )
    )
    db_session.flush()
    return occurrence


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
    assert measured_data["next_milestone"]["rule_key"] == "habit.first_weekly_plan"
    assert measured_data["next_milestone"]["category"] == "habit"
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


def test_weekly_and_monthly_habits_require_completed_required_steps(client, db_session) -> None:
    token, organization_id = _login(client)
    campaign, location = _foundation_campaign(db_session, organization_id)
    started_at = datetime.now(UTC) - timedelta(days=28)
    incomplete = _completed_plan(
        db_session,
        organization_id=organization_id,
        campaign=campaign,
        location=location,
        cadence="weekly",
        period_key="2026-W28",
        completed_at=started_at - timedelta(days=7),
    )
    incomplete_step = (
        db_session.query(ActionPlanStep)
        .filter(ActionPlanStep.occurrence_id == incomplete.id)
        .one()
    )
    incomplete_step.status = "in_progress"
    incomplete_step.completed_at = None
    for offset, period_key in enumerate(("2026-W29", "2026-W30", "2026-W31")):
        _completed_plan(
            db_session,
            organization_id=organization_id,
            campaign=campaign,
            location=location,
            cadence="weekly",
            period_key=period_key,
            completed_at=started_at + timedelta(days=offset * 7),
        )
    _completed_plan(
        db_session,
        organization_id=organization_id,
        campaign=campaign,
        location=location,
        cadence="monthly",
        period_key="2026-07",
        completed_at=started_at + timedelta(days=24),
    )
    db_session.commit()

    response = _evaluate(client, token, campaign.id)
    assert response.status_code == 200
    data = response.json()["data"]
    earned_keys = {item["rule_key"] for item in data["newly_earned"]}
    assert earned_keys == {
        "foundation.location_ready",
        "habit.first_weekly_plan",
        "habit.three_weekly_plans",
        "habit.first_monthly_plan",
    }
    assert data["habit_earned_count"] == 3
    assert data["habit_total"] == 3
    assert data["progress_earned_count"] == 4
    assert data["progress_total"] == 6
    weekly = next(
        item
        for item in data["newly_earned"]
        if item["rule_key"] == "habit.three_weekly_plans"
    )
    assert len(weekly["evidence"]) == 3
    assert all(item["evidence_type"] == "checklist_completion" for item in weekly["evidence"])
    assert _evaluate(client, token, campaign.id).json()["data"]["newly_earned"] == []


def test_multi_location_badges_wait_until_every_active_location_qualifies(client, db_session) -> None:
    token, organization_id = _login(client)
    campaign, first_location = _foundation_campaign(db_session, organization_id)
    second_location = BusinessLocation(
        organization_id=organization_id,
        name="Dallas Service Team",
        domain="dallas.example",
        city="Dallas",
        region="Texas",
        status="active",
    )
    db_session.add(second_location)
    db_session.flush()
    second_campaign = Campaign(
        tenant_id=organization_id,
        organization_id=organization_id,
        business_location_id=second_location.id,
        name="Dallas visibility",
        domain="dallas.example",
    )
    db_session.add(second_campaign)
    db_session.flush()
    recent_success = datetime.now(UTC) - timedelta(days=2)
    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=first_location.id,
            campaign_id=campaign.id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:service.example",
            status="connected",
            last_success_at=recent_success,
        )
    )
    db_session.commit()

    waiting = _evaluate(client, token, campaign.id)
    assert waiting.status_code == 200
    waiting_data = waiting.json()["data"]
    waiting_keys = {item["rule_key"] for item in waiting_data["newly_earned"]}
    assert "multi_location.all_locations_ready" in waiting_keys
    assert "multi_location.all_locations_current" not in waiting_keys
    team_ready = next(
        item
        for item in waiting_data["newly_earned"]
        if item["rule_key"] == "multi_location.all_locations_ready"
    )
    assert team_ready["scope"] == {
        "type": "organization",
        "id": organization_id,
        "label": "All active locations",
    }

    db_session.add(
        DataConnection(
            tenant_id=organization_id,
            organization_id=organization_id,
            business_location_id=second_location.id,
            campaign_id=second_campaign.id,
            provider_name="google_search_console",
            external_resource_id="sc-domain:dallas.example",
            status="connected",
            last_success_at=recent_success + timedelta(hours=1),
        )
    )
    db_session.commit()

    current = _evaluate(client, token, campaign.id)
    assert current.status_code == 200
    current_data = current.json()["data"]
    assert [item["rule_key"] for item in current_data["newly_earned"]] == [
        "multi_location.all_locations_current"
    ]
    evidence = current_data["newly_earned"][0]["evidence"][0]
    assert evidence["evidence_type"] == "portfolio_data_current"
    assert evidence["active_location_count"] == 2
    assert evidence["freshness_window_days"] == 21
    assert current_data["multi_location_earned_count"] == 2
    assert current_data["multi_location_total"] == 2
