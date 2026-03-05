from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.outcome_tracker import compute_reward, record_outcome
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.tenant import Tenant
from app.utils.enum_guard import ensure_enum


def test_record_outcome_and_compute_reward(db_session) -> None:
    tenant = Tenant(name='Outcome Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    campaign = Campaign(tenant_id=tenant.id, name='Outcome Campaign', domain='outcome.example')
    db_session.add(campaign)
    db_session.flush()

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='test_recommendation',
        rationale='test rationale',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    outcome = record_outcome(
        db_session,
        recommendation_id=rec.id,
        campaign_id=campaign.id,
        metric_before=100.0,
        metric_after=120.0,
    )

    assert outcome.id
    assert round(outcome.delta, 2) == 20.0

    saved = db_session.get(RecommendationOutcome, outcome.id)
    assert saved is not None
    assert saved.recommendation_id == rec.id

    reward = compute_reward(100.0, 120.0)
    assert round(reward, 2) == 0.2
