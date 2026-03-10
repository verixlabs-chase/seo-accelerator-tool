from __future__ import annotations

from app.events import EventType, publish_event
from app.events.subscriber_registry import register_default_subscribers
from app.intelligence.causal.causal_learning_engine import learn_from_experiment_completed
from app.intelligence.causal.causal_query_engine import (
    get_policies_with_high_confidence,
    get_policies_with_positive_effect,
    get_top_policies_for_feature,
)
from app.intelligence.portfolio.portfolio_engine import run_portfolio_cycle
from app.models.campaign import Campaign
from app.models.causal_edge import CausalEdge
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.recommendation_outcome import RecommendationOutcome
from app.models.tenant import Tenant
from app.utils.enum_guard import ensure_enum
from app.enums import StrategyRecommendationStatus


def test_experiment_completed_event_creates_causal_edge(db_session) -> None:
    register_default_subscribers(force_reset=True)

    publish_event(
        EventType.EXPERIMENT_COMPLETED.value,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.4,
            'confidence': 0.8,
            'industry': 'local',
            'sample_size': 12,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )

    row = db_session.query(CausalEdge).filter(CausalEdge.policy_id == 'policy-a').one()
    assert row.source_node == 'industry::local'
    assert row.target_node == 'outcome::success'
    assert float(row.effect_size) == 0.4
    assert float(row.confidence) == 0.8
    assert int(row.sample_size) == 12


def test_multiple_experiments_aggregate_existing_edge(db_session) -> None:
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.2,
            'confidence': 0.5,
            'industry': 'local',
            'sample_size': 10,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-a',
            'effect_size': 0.8,
            'confidence': 0.9,
            'industry': 'local',
            'sample_size': 30,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.commit()

    row = db_session.query(CausalEdge).filter(CausalEdge.policy_id == 'policy-a').one()
    assert float(row.effect_size) == 0.65
    assert float(row.confidence) == 0.8
    assert int(row.sample_size) == 40


def test_query_engine_returns_expected_policies(db_session) -> None:
    for policy_id, effect_size, confidence, sample_size, source_node in [
        ('policy-a', 0.25, 0.95, 18, 'industry::local'),
        ('policy-b', 0.55, 0.85, 9, 'industry::local'),
        ('policy-c', -0.10, 0.99, 11, 'industry::local'),
        ('policy-d', 0.35, 0.65, 13, 'industry::local'),
    ]:
        learn_from_experiment_completed(
            db_session,
            {
                'policy_id': policy_id,
                'effect_size': effect_size,
                'confidence': confidence,
                'industry': 'local',
                'sample_size': sample_size,
                'source_node': source_node,
                'target_node': 'outcome::success',
            },
        )
    db_session.commit()

    top_for_feature = get_top_policies_for_feature(db_session, 'industry::local')
    positive = get_policies_with_positive_effect(db_session, 'local')
    high_confidence = get_policies_with_high_confidence(db_session, industry='local', min_confidence=0.9)

    assert [item.policy_id for item in top_for_feature[:3]] == ['policy-a', 'policy-b', 'policy-d']
    assert [item.policy_id for item in positive[:3]] == ['policy-a', 'policy-b', 'policy-d']
    assert [item.policy_id for item in high_confidence] == ['policy-c', 'policy-a']


def test_portfolio_engine_prefers_positive_high_confidence_causal_policies(db_session) -> None:
    tenant = Tenant(name='Causal Portfolio Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    active_campaign = Campaign(tenant_id=tenant.id, name='Active Campaign', domain='active.example')
    peer_campaign = Campaign(tenant_id=tenant.id, name='Peer Campaign', domain='peer.example')
    db_session.add_all([active_campaign, peer_campaign])
    db_session.flush()

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=active_campaign.id,
        recommendation_type='policy::policy-a',
        rationale='trigger portfolio refresh',
        confidence=0.5,
        confidence_score=0.5,
        evidence_json='{"policy_id":"policy-a","industry":"local"}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.flush()

    db_session.add_all(
        [
            PolicyPerformance(policy_id='policy-a', campaign_id=active_campaign.id, industry='local', success_score=0.7, execution_count=5, confidence=0.5),
            PolicyPerformance(policy_id='policy-b', campaign_id=peer_campaign.id, industry='local', success_score=0.45, execution_count=4, confidence=0.4),
        ]
    )
    learn_from_experiment_completed(
        db_session,
        {
            'policy_id': 'policy-b',
            'effect_size': 0.8,
            'confidence': 0.95,
            'industry': 'local',
            'sample_size': 20,
            'source_node': 'industry::local',
            'target_node': 'outcome::success',
        },
    )
    db_session.flush()

    outcome = RecommendationOutcome(
        recommendation_id=recommendation.id,
        campaign_id=active_campaign.id,
        metric_before=100.0,
        metric_after=105.0,
        delta=5.0,
    )
    db_session.add(outcome)
    db_session.flush()

    result = run_portfolio_cycle(db_session, outcome)
    assert result is not None
    assert result.allocations
    assert result.allocations[0].policy_id == 'policy-b'
