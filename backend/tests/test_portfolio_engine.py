from __future__ import annotations

from app.enums import StrategyRecommendationStatus
from app.intelligence.outcome_tracker import record_outcome
from app.intelligence.portfolio.campaign_index import build_campaign_index, rank_campaigns
from app.intelligence.portfolio.policy_performance import update_policy_performance
from app.intelligence.portfolio.portfolio_engine import run_portfolio_cycle
from app.intelligence.portfolio.portfolio_models import PolicyPerformanceSnapshot
from app.intelligence.portfolio.strategy_allocator import allocate_strategies
from app.models.intelligence import StrategyRecommendation
from app.models.policy_performance import PolicyPerformance
from app.models.tenant import Tenant
from app.models.campaign import Campaign
from app.utils.enum_guard import ensure_enum


def test_campaign_ranking_uses_velocity_score() -> None:
    slow = build_campaign_index(
        campaign_id='campaign-slow',
        ranking_velocity=0.1,
        content_velocity=0.2,
        link_velocity=0.1,
        review_velocity=0.0,
    )
    fast = build_campaign_index(
        campaign_id='campaign-fast',
        ranking_velocity=0.8,
        content_velocity=0.7,
        link_velocity=0.9,
        review_velocity=0.6,
    )

    ranked = rank_campaigns([slow, fast])

    assert ranked[0].campaign_id == 'campaign-fast'
    assert ranked[0].campaign_performance_score > ranked[1].campaign_performance_score



def test_policy_success_scoring_updates_running_average(db_session) -> None:
    tenant = Tenant(name='Portfolio Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    campaign = Campaign(tenant_id=tenant.id, name='Portfolio Campaign', domain='portfolio.example')
    db_session.add(campaign)
    db_session.flush()

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='policy::legacy::gbp_low_review_velocity',
        rationale='test rationale',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{"policy_id":"legacy::gbp_low_review_velocity","industry":"local"}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.commit()

    first = record_outcome(
        db_session,
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        metric_before=100.0,
        metric_after=120.0,
    )
    row = db_session.query(PolicyPerformance).filter(PolicyPerformance.policy_id == 'legacy::gbp_low_review_velocity').one()
    assert row.execution_count == 1
    assert row.success_score > 0
    assert row.confidence == 0.1

    second = record_outcome(
        db_session,
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        metric_before=120.0,
        metric_after=108.0,
    )
    updated = update_policy_performance(db_session, second)
    assert updated is not None
    assert updated.execution_count == 3
    assert updated.confidence == 0.3



def test_strategy_allocation_balances_exploit_and_explore() -> None:
    rows = [
        PolicyPerformanceSnapshot(policy_id='policy-a', campaign_id='c1', industry='unknown', success_score=0.9, execution_count=10, confidence=0.9),
        PolicyPerformanceSnapshot(policy_id='policy-b', campaign_id='c1', industry='unknown', success_score=0.8, execution_count=8, confidence=0.8),
        PolicyPerformanceSnapshot(policy_id='policy-c', campaign_id='c1', industry='unknown', success_score=0.4, execution_count=1, confidence=0.2),
        PolicyPerformanceSnapshot(policy_id='policy-d', campaign_id='c1', industry='unknown', success_score=0.3, execution_count=0, confidence=0.1),
    ]

    allocations = allocate_strategies(rows, total_slots=4)

    assert [item.mode for item in allocations].count('exploit') == 3
    assert [item.mode for item in allocations].count('explore') == 1
    assert allocations[0].policy_id == 'policy-a'
    assert allocations[-1].policy_id == 'policy-d'



def test_portfolio_engine_runs_after_outcome_tracking(db_session) -> None:
    tenant = Tenant(name='Portfolio Integration Tenant', status='Active')
    db_session.add(tenant)
    db_session.flush()

    campaign = Campaign(tenant_id=tenant.id, name='Portfolio Integration Campaign', domain='portfolio-int.example')
    db_session.add(campaign)
    db_session.flush()

    recommendation = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='policy::legacy::gbp_low_review_velocity',
        rationale='test rationale',
        confidence=0.7,
        confidence_score=0.7,
        evidence_json='{"policy_id":"legacy::gbp_low_review_velocity","industry":"local"}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.GENERATED, StrategyRecommendationStatus),
    )
    db_session.add(recommendation)
    db_session.commit()

    outcome = record_outcome(
        db_session,
        recommendation_id=recommendation.id,
        campaign_id=campaign.id,
        metric_before=50.0,
        metric_after=60.0,
    )

    result = run_portfolio_cycle(db_session, outcome)

    assert result is not None
    assert result.updated_policy_id == 'legacy::gbp_low_review_velocity'
    assert result.allocations
