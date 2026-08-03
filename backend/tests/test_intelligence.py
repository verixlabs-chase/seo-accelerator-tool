from datetime import UTC, datetime
import json

import pytest
from fastapi import HTTPException

from app.models.campaign import Campaign
from app.models.action_plan import ActionPlanOccurrence, ActionPlanStep
from app.models.intelligence import StrategyRecommendation
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.intelligence import IntelligenceScoreOut, RecommendationOut
from app.services import intelligence_service


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
    for step in first["steps"]:
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

    assert work_item["status"] == "waiting_for_results"
    assert work_item["due_state"] == "completed"
    assert work_item["progress"]["completed_required"] == 3
    assert work_item["next_step"] is None
    assert all(step["completed_by_user_id"] == user.id for step in work_item["steps"])


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
