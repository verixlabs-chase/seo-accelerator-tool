from __future__ import annotations

from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.temporal import MomentumMetric
from app.models.tenant import Tenant
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation


def test_automation_guardrail_manual_lock_field(db_session) -> None:
    tenant = db_session.query(Tenant).order_by(Tenant.created_at.asc()).first()
    assert tenant is not None

    campaign = Campaign(
        tenant_id=tenant.id,
        name='Manual Lock Campaign',
        domain='manual-lock.example',
        setup_state='Active',
        manual_automation_lock=True,
    )
    db_session.add(campaign)
    db_session.commit()

    when = datetime(2026, 7, 10, tzinfo=UTC)
    db_session.add_all(
        [
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.2,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when,
                deterministic_hash='h1',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.15,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when.replace(day=9),
                deterministic_hash='h2',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.1,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when.replace(day=8),
                deterministic_hash='h3',
                profile_version='profile-v1',
            ),
        ]
    )
    db_session.commit()

    result = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=when)

    assert result['status'] == 'frozen'
    assert 'manual_lock_mode' in result['triggered_rules']