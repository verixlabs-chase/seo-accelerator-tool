from datetime import UTC, date, datetime, timedelta
import json

import pytest
from fastapi import HTTPException

from app.models.campaign import Campaign
from app.models.business_location import BusinessLocation
from app.models.data_connection import DataConnection
from app.models.google_business_profile import GoogleBusinessProfileDailyMetric
from app.models.action_plan import (
    ActionPlanForecast,
    ActionPlanMeasurement,
    ActionPlanOccurrence,
    ActionPlanStep,
)
from app.models.intelligence import StrategyRecommendation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.website_performance import WebsitePerformanceMeasurement
from app.intelligence.lexicon import get_active_lexicon
from app.schemas.intelligence import IntelligenceScoreOut, RecommendationOut
from app.services import action_plan_measurement_service, intelligence_service


def test_intelligence_score_recommendations_and_advance_month(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None

    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Intelligence Campaign",
        domain="intel.com",
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    score = intelligence_service.get_latest_score(db_session, tenant_id=tenant.id, campaign_id=campaign.id)
    score_payload = IntelligenceScoreOut.model_validate(score).model_dump(mode="json")
    assert "score_value" in score_payload

    recs = intelligence_service.get_recommendations(db_session, tenant_id=tenant.id, campaign_id=campaign.id)
    items = [RecommendationOut.model_validate(row).model_dump(mode="json") for row in recs]
    assert len(items) >= 1
    first = items[0]
    assert "confidence_score" in first
    assert isinstance(first["confidence_score"], float)
    assert 0.0 <= first["confidence_score"] <= 1.0
    assert "evidence" in first
    assert isinstance(first["evidence"], list)
    assert len(first["evidence"]) >= 1
    assert "risk_tier" in first
    assert isinstance(first["risk_tier"], int)
    assert 0 <= first["risk_tier"] <= 4
    assert "rollback_plan" in first
    assert isinstance(first["rollback_plan"], dict)
    assert len(first["rollback_plan"]) >= 1
    assert first["engine_source"] == "heuristic_threshold_v1"

    with pytest.raises(HTTPException) as invalid_transition:
        intelligence_service.transition_recommendation_state(
            db_session,
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            recommendation_id=first["id"],
            target_state="APPROVED",
        )
    assert invalid_transition.value.status_code == 400

    validated = intelligence_service.transition_recommendation_state(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_id=first["id"],
        target_state="VALIDATED",
    )
    assert validated.status == "VALIDATED"

    approved = intelligence_service.transition_recommendation_state(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_id=first["id"],
        target_state="APPROVED",
    )
    assert approved.status == "APPROVED"

    with pytest.raises(HTTPException) as blocked:
        intelligence_service.advance_month(
            db_session,
            tenant_id=tenant.id,
            campaign_id=campaign.id,
            override=False,
        )
    assert blocked.value.status_code == 400

    advanced = intelligence_service.advance_month(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        override=True,
    )
    assert advanced["advanced_to_month"] == 2


def test_deep_recommendation_contract_exposes_evidence_and_engine_source():
    payload = RecommendationOut.model_validate(
        {
            "id": "recommendation-id",
            "tenant_id": "tenant-id",
            "campaign_id": "campaign-id",
            "recommendation_type": "policy::technical_health::fix_titles",
            "rationale": "Fix missing page titles.",
            "confidence": 0.84,
            "confidence_score": 0.84,
            "evidence_json": json.dumps(
                {
                    "evidence": ["12 pages are missing titles"],
                    "policy_id": "technical_health",
                }
            ),
            "risk_tier": 2,
            "rollback_plan_json": json.dumps({"steps": ["restore prior titles"]}),
            "status": "GENERATED",
            "created_at": datetime.now(UTC),
        }
    ).model_dump(mode="json")

    assert payload["evidence"] == ["12 pages are missing titles"]
    assert payload["engine_source"] == "orchestrator_v1"


def test_recommendation_action_plan_uses_canonical_lexicon_steps(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    recommendation = StrategyRecommendation(
        id="recommendation-plan-id",
        tenant_id=tenant.id,
        campaign_id="campaign-id",
        recommendation_type=(
            "policy::core_web_vitals_failure::technical.reduce_render_blocking"
        ),
        rationale="The main content is loading too slowly.",
        confidence=0.91,
        confidence_score=0.91,
        evidence_json=json.dumps({"evidence": ["LCP is above the poor boundary"]}),
        risk_tier=3,
        rollback_plan_json=json.dumps({"steps": ["restore prior asset loading"]}),
        status="GENERATED",
    )

    plans = intelligence_service.build_recommendation_action_plans(
        db_session,
        tenant_id=tenant.id,
        recommendations=[recommendation],
    )

    plan = plans[recommendation.id]
    assert plan["action_id"] == "technical.reduce_render_blocking"
    assert plan["display_name"] == "Reduce files that delay the main content"
    assert len(plan["steps"]) == 3
    assert plan["effort"] == "medium"
    assert plan["owner_role"] == "developer"
    assert plan["observation_window_days"] == 28
    assert plan["primary_metric_id"] == "cwv.lcp"
    assert plan["measurement_track"] == "website"
    assert plan["lexicon_version"] == "1.0.0"


def test_action_plan_checklist_persists_progress_and_completes_required_work(
    db_session,
):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert tenant is not None
    assert user is not None
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Checklist Campaign",
        domain="checklist.example",
    )
    db_session.add(campaign)
    db_session.flush()
    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type=(
            "policy::core_web_vitals_failure::technical.reduce_render_blocking"
        ),
        rationale="The main content is loading too slowly.",
        confidence=0.91,
        confidence_score=0.91,
        evidence_json=json.dumps({"evidence": ["LCP is above the poor boundary"]}),
        risk_tier=3,
        rollback_plan_json=json.dumps({"steps": ["restore prior asset loading"]}),
        status="GENERATED",
    )
    db_session.add(recommendation)
    db_session.add(
        WebsitePerformanceMeasurement(
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            requested_url="https://checklist.example",
            measured_url="https://checklist.example",
            source="crux_field",
            scope="url",
            form_factor="PHONE",
            status="ready",
            lcp_ms=4200.0,
            collection_start=date(2026, 7, 1),
            collection_end=date(2026, 7, 28),
            metric_contract_versions={"web.crux.lcp": "1.0"},
            scope_key="checklist-url-phone",
            lexicon_id="seo-intelligence-core",
            lexicon_version="1.0.0",
            idempotency_key="checklist-baseline-lcp",
            captured_at=datetime(2026, 8, 2, 16, 30, tzinfo=UTC),
        )
    )
    db_session.commit()

    plans = intelligence_service.build_recommendation_action_plans(
        db_session,
        tenant_id=tenant.id,
        recommendations=[recommendation],
    )
    now = datetime(2026, 8, 3, 16, 30, tzinfo=UTC)
    first = intelligence_service.ensure_action_plan_occurrences(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendations=[recommendation],
        action_plans=plans,
        now=now,
    )[recommendation.id]
    repeated = intelligence_service.ensure_action_plan_occurrences(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendations=[recommendation],
        action_plans=plans,
        now=now,
    )[recommendation.id]

    assert first["id"] == repeated["id"]
    assert first["cadence"] == "daily"
    assert first["period_key"] == "2026-08-03"
    assert first["progress"] == {
        "completed_required": 0,
        "required_total": 3,
        "completed_total": 0,
        "total": 3,
    }
    assert db_session.query(ActionPlanOccurrence).count() == 1
    assert db_session.query(ActionPlanStep).count() == 3

    work_item = first
    for index, step in enumerate(first["steps"]):
        work_item = intelligence_service.update_action_plan_step(
            db_session,
            tenant_id=tenant.id,
            organization_id=tenant.id,
            campaign_id=campaign.id,
            occurrence_id=first["id"],
            step_id=step["id"],
            step_status="done",
            blocker_reason=None,
            evidence=None,
            actor_user_id=user.id,
        )
        if index == 0:
            baseline = db_session.query(ActionPlanMeasurement).one()
            assert baseline.baseline_metrics[0]["value"] == 4200.0
            assert baseline.result_classification == "waiting_for_results"
            assert baseline.measurement_contract["version"] == "2.0"
            assert baseline.measurement_contract["track"] == "website"
            assert baseline.measurement_contract["primary_metric_id"] == "cwv.lcp"
            forecast = db_session.query(ActionPlanForecast).one()
            assert forecast.forecast_status == "available"
            assert forecast.data_quality == "strong"
            metric_forecast = forecast.metric_forecasts[0]
            assert metric_forecast["metric_id"] == "cwv.lcp"
            assert metric_forecast["current_value"] == 4200.0
            assert metric_forecast["target_value"] == 2500.0
            assert metric_forecast["conservative_value"] == 3945.0
            assert metric_forecast["expected_value"] == 3690.0
            assert metric_forecast["optimistic_value"] == 3350.0
            assert metric_forecast["range_low"] == 3350.0
            assert metric_forecast["range_high"] == 3945.0
            assert metric_forecast["source"] == "Chrome UX Report field data"
            assert metric_forecast["scope"] == "url:PHONE"
            assert metric_forecast["confidence"] == "moderate"
            initial_forecast_hash = forecast.artifact_hash
            db_session.add(
                WebsitePerformanceMeasurement(
                    tenant_id=tenant.id,
                    organization_id=tenant.id,
                    campaign_id=campaign.id,
                    requested_url="https://checklist.example",
                    measured_url="https://checklist.example",
                    source="crux_field",
                    scope="url",
                    form_factor="PHONE",
                    status="ready",
                    lcp_ms=2400.0,
                    collection_start=date(2026, 8, 1),
                    collection_end=date(2026, 8, 28),
                    metric_contract_versions={"web.crux.lcp": "1.0"},
                    scope_key="checklist-url-phone",
                    lexicon_id="seo-intelligence-core",
                    lexicon_version="1.0.0",
                    idempotency_key="checklist-follow-up-lcp",
                    captured_at=datetime.now(UTC) + timedelta(days=29),
                )
            )
            db_session.commit()

    assert work_item["status"] == "waiting_for_results"
    assert work_item["due_state"] == "waiting_for_results"
    assert work_item["progress"]["completed_required"] == 3
    assert work_item["next_step"] is None
    assert all(step["completed_by_user_id"] == user.id for step in work_item["steps"])
    measurement = work_item["measurement"]
    assert measurement["measurement_status"] == "waiting_for_results"
    assert measurement["baseline_metrics"][0]["value"] == 4200.0
    assert measurement["baseline_available_count"] == 1
    assert len(measurement["completion_proof"]) == 3
    assert work_item["forecast"]["forecast_status"] == "available"
    assert work_item["forecast"]["promise"] is False
    assert work_item["forecast"]["unknown_effects"] == [
        "rankings",
        "visits",
        "leads",
        "revenue",
    ]
    assert work_item["forecast"]["artifact_hash"] == initial_forecast_hash

    measured = action_plan_measurement_service.evaluate_action_plan_outcome(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        occurrence_id=first["id"],
        measured_at=datetime.now(UTC) + timedelta(days=29),
    )
    assert measured["measurement_status"] == "measured"
    assert measured["outcome_status"] == "helped"
    assert measured["result_classification"] == "improved"
    assert measured["measurement_contract"]["result"]["classification"] == "improved"
    assert measured["measurement_contract"]["managed_wordpress_safety"]["status"] == "not_applicable"
    assert measured["outcome_metrics"][0]["baseline_value"] == 4200.0
    assert measured["outcome_metrics"][0]["value"] == 2400.0
    compared_forecast = db_session.query(ActionPlanForecast).one()
    assert compared_forecast.artifact_hash == initial_forecast_hash
    assert compared_forecast.outcome_comparisons == [
        {
            "metric_id": "cwv.lcp",
            "status": "outside_range",
            "position": "better_than_range",
            "observed_value": 2400.0,
            "range_low": 3350.0,
            "range_high": 3945.0,
            "expected_value": 3690.0,
        }
    ]


def test_action_plan_outcome_requires_new_post_completion_evidence():
    completed_at = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    baseline = {
        "metric_id": "cwv.lcp",
        "value": 4200.0,
        "direction": "lower_is_better",
        "source_record_id": "same-field-record",
    }
    observed = {
        "metric_id": "cwv.lcp",
        "value": 4200.0,
        "direction": "lower_is_better",
        "source_record_id": "same-field-record",
        "measured_at": completed_at.isoformat(),
    }

    comparison = action_plan_measurement_service._comparison(
        baseline,
        observed,
        work_completed_at=completed_at,
    )

    assert comparison["comparison"] == "insufficient_data"
    assert comparison["change"] is None


def test_action_plan_outcome_rejects_a_different_measurement_scope():
    completed_at = datetime(2026, 8, 3, 18, 0, tzinfo=UTC)
    baseline = {
        "metric_id": "cwv.lcp",
        "value": 4200.0,
        "direction": "lower_is_better",
        "source_provider": "chrome_ux_report",
        "aggregation": "p75",
        "scope": "url:PHONE",
        "measurement_window_days": 28,
        "entity_scope": {
            "campaign_id": "campaign-a",
            "business_location_id": "location-a",
            "measured_url": "https://example.com/service-a",
            "form_factor": "PHONE",
        },
        "source_record_id": "baseline-record",
    }
    observed = {
        **baseline,
        "value": 2200.0,
        "entity_scope": {
            **baseline["entity_scope"],
            "measured_url": "https://example.com/service-b",
        },
        "source_record_id": "outcome-record",
        "measured_at": (completed_at + timedelta(days=29)).isoformat(),
    }

    comparison = action_plan_measurement_service._comparison(
        baseline,
        observed,
        work_completed_at=completed_at,
    )

    assert comparison["comparison"] == "insufficient_data"
    assert comparison["comparison_requirements_met"] is False
    assert "does not match" in comparison["insufficient_reasons"][-1]


def test_primary_metric_controls_the_action_result():
    classification = action_plan_measurement_service._classify_primary_result(
        [
            {"metric_id": "primary", "comparison": "worse"},
            {"metric_id": "secondary", "comparison": "improved"},
        ],
        ["primary", "secondary"],
    )

    assert classification[0] == "worse"
    assert classification[1] == "did_not_help"
    assert classification[2]["metric_id"] == "primary"


def test_google_business_profile_measurement_is_location_scoped(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    location = BusinessLocation(
        organization_id=tenant.id,
        name="Measurement Location",
        domain="measurement.example",
    )
    db_session.add(location)
    db_session.flush()
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        business_location_id=location.id,
        name="Measurement Campaign",
        domain="measurement.example",
    )
    db_session.add(campaign)
    db_session.flush()
    connection = DataConnection(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        business_location_id=location.id,
        campaign_id=campaign.id,
        provider_name="google_business_profile",
        external_resource_id="locations/measurement",
        resource_scope="location",
        status="current",
    )
    db_session.add(connection)
    db_session.flush()
    for offset, value in enumerate((3, 5, 7)):
        db_session.add(
            GoogleBusinessProfileDailyMetric(
                connection_id=connection.id,
                tenant_id=tenant.id,
                organization_id=tenant.id,
                campaign_id=campaign.id,
                business_location_id=location.id,
                metric_date=date(2026, 8, 1) + timedelta(days=offset),
                metric_name="WEBSITE_CLICKS",
                metric_value=value,
                source_name="google_business_profile",
                metric_contract_id="gbp.performance.website_clicks",
                metric_contract_version="1.0",
                source_account_id="accounts/measurement",
                external_resource_id="locations/measurement",
                scope_key="measurement-profile-scope",
                captured_at=datetime(2026, 8, 4, tzinfo=UTC),
            )
        )
    db_session.commit()
    metric = get_active_lexicon(db_session, tenant_id=tenant.id).metric_index[
        "local.gbp.website_clicks"
    ]

    captured = action_plan_measurement_service._google_business_profile_metric(
        db_session,
        tenant_id=tenant.id,
        organization_id=tenant.id,
        campaign_id=campaign.id,
        business_location_id=location.id,
        metric=metric,
        captured_at=datetime(2026, 8, 3, 23, 59, tzinfo=UTC),
        observation_window_days=7,
    )

    assert captured["status"] == "available"
    assert captured["value"] == 15.0
    assert captured["source_provider"] == "google_business_profile"
    assert captured["entity_scope"]["business_location_id"] == location.id
    assert captured["measurement_window_days"] == 7


def test_deep_recommendation_can_enter_human_review(db_session):
    tenant = db_session.query(Tenant).filter(Tenant.name == "Tenant A").first()
    assert tenant is not None
    campaign = Campaign(
        tenant_id=tenant.id,
        organization_id=tenant.id,
        name="Deep Recommendation Campaign",
        domain="deep-recommendation.example",
    )
    db_session.add(campaign)
    db_session.flush()
    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type="policy::technical_health::fix_titles",
        rationale="Fix missing page titles.",
        confidence=0.84,
        confidence_score=0.84,
        evidence_json=json.dumps(
            {
                "evidence": ["12 pages are missing titles"],
                "policy_id": "technical_health",
            }
        ),
        risk_tier=2,
        rollback_plan_json=json.dumps({"steps": ["restore prior titles"]}),
        status="GENERATED",
    )
    db_session.add(recommendation)
    db_session.commit()

    reviewed = intelligence_service.transition_recommendation_state(
        db_session,
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_id=recommendation.id,
        target_state="VALIDATED",
    )

    assert reviewed.status == "VALIDATED"
