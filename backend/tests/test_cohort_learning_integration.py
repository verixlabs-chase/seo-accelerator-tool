from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.intelligence.feature_aggregator import describe_campaign_cohort
from app.models.strategy_cohort_pattern import StrategyCohortPattern
from app.services.strategy_engine.engine import build_campaign_strategy
from app.services.strategy_engine.schemas import StrategyWindow
from tests.conftest import create_test_campaign


def _priority_for(recommendations, scenario_id: str) -> float:
    for rec in recommendations:
        if rec.scenario_id == scenario_id:
            return float(rec.priority_score)
    raise AssertionError(f'Missing scenario: {scenario_id}')


def test_strategy_engine_applies_cohort_pattern_multiplier(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Integration Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Integration Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Integration Campaign',
        domain='plumber-integration.example',
    )
    db_session.commit()

    window = StrategyWindow(
        date_from=datetime.now(UTC) - timedelta(days=30),
        date_to=datetime.now(UTC),
    )
    raw_signals = {
        'position_delta': 6.0,
        'traffic_growth_percent': -0.3,
    }

    baseline = build_campaign_strategy(
        campaign_id=campaign.id,
        window=window,
        raw_signals=raw_signals,
        tier='pro',
        db=db_session,
    )
    baseline_priority = _priority_for(baseline.recommendations, 'ranking_decline_detected')

    cohort_definition = describe_campaign_cohort(db_session, campaign.id)['cohort']
    db_session.add(
        StrategyCohortPattern(
            pattern_name='low_technical_issues_faster_ranking_improvements',
            feature_name='ranking_velocity',
            cohort_definition=cohort_definition,
            pattern_strength=0.9,
            support_count=10,
            confidence=0.9,
        )
    )
    db_session.commit()

    influenced = build_campaign_strategy(
        campaign_id=campaign.id,
        window=window,
        raw_signals=raw_signals,
        tier='pro',
        db=db_session,
    )
    influenced_priority = _priority_for(influenced.recommendations, 'ranking_decline_detected')

    assert influenced_priority > baseline_priority
