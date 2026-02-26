from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.campaign import Campaign
from app.models.temporal import TemporalSignalSnapshot, TemporalSignalType
from app.models.tenant import Tenant
from app.services.strategy_engine.modules.temporal_diagnostics import run_temporal_diagnostics
from app.services.strategy_engine.schemas import StrategyWindow


def _window() -> StrategyWindow:
    date_from = datetime(2026, 2, 1, tzinfo=UTC)
    date_to = datetime(2026, 2, 10, tzinfo=UTC)
    return StrategyWindow(date_from=date_from, date_to=date_to)


def _seed_campaign(db_session) -> Campaign:
    tenant = db_session.query(Tenant).order_by(Tenant.created_at.asc()).first()
    assert tenant is not None
    campaign = Campaign(tenant_id=tenant.id, name='Temporal Campaign', domain='example.com')
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return campaign


def test_temporal_diagnostics_sparse_data_returns_empty(db_session) -> None:
    campaign = _seed_campaign(db_session)
    window = _window()
    results = run_temporal_diagnostics(
        db_session,
        campaign_id=campaign.id,
        window=window,
        window_reference='window-a',
        tier='enterprise',
    )
    assert results == []


def test_temporal_diagnostics_detects_rank_and_competitive_pressure(db_session) -> None:
    campaign = _seed_campaign(db_session)
    window = _window()

    rank_values = [4.0, 5.0, 6.0, 7.0]
    our_sov = [0.20, 0.21, 0.22, 0.23]
    competitor_sov = [0.30, 0.33, 0.36, 0.39]
    content_values = [6.0, 5.0, 4.0, 3.0]
    review_values = [12.0, 11.0, 9.0, 7.0]

    for idx, value in enumerate(rank_values):
        observed_at = window.date_from + timedelta(days=idx)
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.RANK,
                metric_name='avg_position',
                metric_value=value,
                observed_at=observed_at,
                source='test-suite',
                confidence=1.0,
                version_hash='vhash',
            )
        )
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.COMPETITOR,
                metric_name='our_share_of_voice',
                metric_value=our_sov[idx],
                observed_at=observed_at,
                source='test-suite',
                confidence=1.0,
                version_hash='vhash',
            )
        )
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.COMPETITOR,
                metric_name='competitor_share_of_voice',
                metric_value=competitor_sov[idx],
                observed_at=observed_at,
                source='test-suite',
                confidence=1.0,
                version_hash='vhash',
            )
        )
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.CONTENT,
                metric_name='published_assets_count',
                metric_value=content_values[idx],
                observed_at=observed_at,
                source='test-suite',
                confidence=1.0,
                version_hash='vhash',
            )
        )
        db_session.add(
            TemporalSignalSnapshot(
                campaign_id=campaign.id,
                signal_type=TemporalSignalType.REVIEW,
                metric_name='reviews_last_30d',
                metric_value=review_values[idx],
                observed_at=observed_at,
                source='test-suite',
                confidence=1.0,
                version_hash='vhash',
            )
        )

    db_session.commit()

    results = run_temporal_diagnostics(
        db_session,
        campaign_id=campaign.id,
        window=window,
        window_reference='window-b',
        tier='enterprise',
    )
    scenario_ids = {result.scenario_id for result in results}
    assert 'rank_negative_momentum' in scenario_ids
    assert 'review_velocity_declining' in scenario_ids
    assert 'content_velocity_decline' in scenario_ids
    assert scenario_ids & {'competitive_momentum_gap', 'competitive_momentum_volatile'}
