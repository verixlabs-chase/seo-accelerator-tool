from __future__ import annotations

from datetime import UTC, date, datetime

from app.intelligence.cohort_pattern_engine import discover_cohort_patterns
from app.intelligence.strategy_memory_engine import record_validated_pattern, update_pattern_statistics
from app.models.campaign_daily_metric import CampaignDailyMetric
from app.models.strategy_memory_pattern import StrategyMemoryPattern
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from tests.conftest import create_test_campaign


def test_record_validated_pattern_promotion_rule(db_session) -> None:
    not_promoted = record_validated_pattern(
        db_session,
        {
            'pattern_name': 'low_support',
            'feature_name': 'ranking_velocity',
            'pattern_description': 'insufficient support',
            'support_count': 5,
            'avg_outcome_delta': 1.0,
            'confidence_score': 0.9,
        },
    )
    assert not_promoted is None

    promoted = record_validated_pattern(
        db_session,
        {
            'pattern_name': 'internal_link_density_boost',
            'feature_name': 'internal_link_count',
            'pattern_description': 'validated internal link uplift',
            'support_count': 10,
            'avg_outcome_delta': 2.3,
            'confidence_score': 0.81,
        },
    )
    assert promoted is not None
    assert promoted.support_count == 10
    assert promoted.confidence_score == 0.81


def test_update_pattern_statistics_is_deterministic(db_session) -> None:
    row = StrategyMemoryPattern(
        pattern_name='ranking_velocity_improvement',
        feature_name='ranking_velocity',
        pattern_description='base memory pattern',
        support_count=10,
        avg_outcome_delta=2.0,
        confidence_score=0.8,
    )
    db_session.add(row)
    db_session.commit()

    updated = update_pattern_statistics(db_session, row.id, outcome_delta=4.0)
    assert updated is not None
    assert updated.support_count == 11
    assert round(updated.avg_outcome_delta, 6) == round((2.0 * 10 + 4.0) / 11, 6)
    assert updated.confidence_score == 0.81


def test_cohort_pattern_promotion_writes_strategy_memory(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Memory Cohort Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Memory Cohort Org')

    campaigns = [
        create_test_campaign(db_session, org.id, tenant_id=tenant.id, name=f'Memory Cohort {idx}', domain=f'mem-{idx}.example')
        for idx in range(10)
    ]

    for idx, campaign in enumerate(campaigns):
        now = datetime.now(UTC)
        db_session.add_all(
            [
                CampaignDailyMetric(
                    organization_id=org.id,
                    campaign_id=campaign.id,
                    metric_date=date(2026, 3, 4),
                    sessions=100,
                    technical_issue_count=8,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'mem-a-{idx}',
                ),
                CampaignDailyMetric(
                    organization_id=org.id,
                    campaign_id=campaign.id,
                    metric_date=date(2026, 3, 5),
                    sessions=125,
                    technical_issue_count=6,
                    normalization_version='analytics-v1',
                    deterministic_hash=f'mem-b-{idx}',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='internal_link_ratio',
                    metric_value=0.2,
                    observed_at=now,
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'mem-{idx}-1',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='ranking_velocity',
                    metric_value=0.25,
                    observed_at=now,
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'mem-{idx}-2',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='technical_issue_density',
                    metric_value=0.08,
                    observed_at=now,
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'mem-{idx}-3',
                ),
                TemporalSignalSnapshot(
                    campaign_id=campaign.id,
                    signal_type=TemporalSignalType.CUSTOM,
                    metric_name='content_growth_rate',
                    metric_value=0.12,
                    observed_at=now,
                    source='feature_store_v1',
                    confidence=1.0,
                    version_hash=f'mem-{idx}-4',
                ),
            ]
        )
    db_session.commit()

    patterns = discover_cohort_patterns(db_session, persist=True)
    assert patterns

    memory_rows = db_session.query(StrategyMemoryPattern).all()
    assert memory_rows
    assert any(row.support_count >= 10 and row.confidence_score >= 0.7 for row in memory_rows)
