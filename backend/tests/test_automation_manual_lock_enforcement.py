from __future__ import annotations

from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.temporal import MomentumMetric, StrategyPhaseHistory
from app.models.tenant import Tenant
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation


def test_manual_lock_prevents_phase_change(db_session) -> None:
    tenant = db_session.query(Tenant).order_by(Tenant.created_at.asc()).first()
    assert tenant is not None

    campaign = Campaign(
        tenant_id=tenant.id,
        name='Manual Lock Enforcement Campaign',
        domain='manual-lock-enforcement.example',
        setup_state='Active',
        manual_automation_lock=True,
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    phase_anchor = datetime(2026, 6, 1, tzinfo=UTC)
    db_session.add(
        StrategyPhaseHistory(
            campaign_id=campaign.id,
            prior_phase='stabilization',
            new_phase='growth',
            trigger_reason='seed',
            momentum_score=0.5,
            effective_date=phase_anchor,
            version_hash='seed-v1',
        )
    )

    when = datetime(2026, 7, 10, tzinfo=UTC)
    db_session.add_all(
        [
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.4,
                acceleration=0.0,
                volatility=0.05,
                window_days=30,
                computed_at=when,
                deterministic_hash='ml1',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.35,
                acceleration=0.0,
                volatility=0.05,
                window_days=30,
                computed_at=when.replace(day=9),
                deterministic_hash='ml2',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.3,
                acceleration=0.0,
                volatility=0.05,
                window_days=30,
                computed_at=when.replace(day=8),
                deterministic_hash='ml3',
                profile_version='profile-v1',
            ),
        ]
    )
    db_session.commit()

    result = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=when)

    assert result['status'] == 'frozen'
    assert result['prior_phase'] == 'growth'
    assert result['new_phase'] == 'growth'
    assert 'manual_lock_mode' in result['triggered_rules']

    histories = (
        db_session.query(StrategyPhaseHistory)
        .filter(StrategyPhaseHistory.campaign_id == campaign.id)
        .order_by(StrategyPhaseHistory.effective_date.asc(), StrategyPhaseHistory.id.asc())
        .all()
    )
    assert len(histories) == 1
    assert histories[0].new_phase == 'growth'