from app.enums import StrategyRecommendationStatus
from app.intelligence.policy_engine import score_policy
from app.intelligence.policy_update_engine import load_policy_weights, update_policy_priority_weights
from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_outcome import RecommendationOutcome


def test_policy_updates_persist_and_influence_scoring(db_session) -> None:
    campaign = Campaign(tenant_id='tenant-1', organization_id=None, portfolio_id=None, sub_account_id=None, name='Test Campaign', domain='example.com')
    db_session.add(campaign)
    db_session.flush()

    recommendation = StrategyRecommendation(
        campaign_id=campaign.id,
        tenant_id='tenant-1',
        recommendation_type='policy::prioritize_internal_linking::add_contextual_links',
        rationale='test',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='[]',
        risk_tier=1,
        rollback_plan_json='{"steps": []}',
        status=StrategyRecommendationStatus.EXECUTED,
        idempotency_key='policy-test-1',
    )
    db_session.add(recommendation)
    db_session.flush()
    db_session.add(
        RecommendationOutcome(
            recommendation_id=recommendation.id,
            campaign_id=campaign.id,
            delta=1.2,
            metric_before=10.0,
            metric_after=11.2,
        )
    )
    db_session.commit()

    persisted = update_policy_priority_weights(db_session)
    db_session.commit()

    stored = load_policy_weights(db_session)
    assert 'policy::prioritize_internal_linking' in stored
    assert persisted['prioritize_internal_linking'] >= 0.5

    scored = score_policy(
        {
            'policy_id': 'prioritize_internal_linking',
            'priority_weight': 0.75,
            'pattern_confidence': 0.8,
            'risk_tier': 1,
            'recommended_actions': ['add_contextual_links'],
        },
        {'internal_link_ratio': 0.2, 'technical_issue_density': 0.1},
        db=db_session,
    )
    assert scored['learned_weight'] > 0.5
    assert scored['priority_score'] > 0.6
