from __future__ import annotations

from datetime import UTC, datetime

from app.models.campaign import Campaign
from app.models.temporal import MomentumMetric
from app.models.tenant import Tenant
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation


def test_automation_observability_hooks_do_not_change_result(db_session, monkeypatch) -> None:
    tenant = db_session.query(Tenant).order_by(Tenant.created_at.asc()).first()
    assert tenant is not None

    campaign = Campaign(tenant_id=tenant.id, name='Obs Hook Campaign', domain='obs-hook.example', setup_state='Active')
    db_session.add(campaign)
    db_session.commit()

    when = datetime(2026, 8, 14, tzinfo=UTC)
    db_session.add_all(
        [
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.3,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when,
                deterministic_hash='o1',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.2,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when.replace(day=13),
                deterministic_hash='o2',
                profile_version='profile-v1',
            ),
            MomentumMetric(
                campaign_id=campaign.id,
                metric_name='rank_avg_position_momentum',
                slope=-0.1,
                acceleration=0.0,
                volatility=0.1,
                window_days=30,
                computed_at=when.replace(day=12),
                deterministic_hash='o3',
                profile_version='profile-v1',
            ),
        ]
    )
    db_session.commit()

    calls: list[tuple[str, dict]] = []

    def _capture(event_name: str):
        def _inner(**kwargs):
            calls.append((event_name, kwargs))

        return _inner

    monkeypatch.setattr('app.services.strategy_engine.automation_engine.emit_automation_event', _capture('automation_event'))
    monkeypatch.setattr('app.services.strategy_engine.automation_engine.emit_rule_trigger', _capture('rule_trigger'))
    monkeypatch.setattr('app.services.strategy_engine.automation_engine.emit_phase_transition', _capture('phase_transition'))

    result = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=when)

    assert result['status'] == 'evaluated'
    assert len(result['decision_hash']) == 64
    emitted = {name for name, _kwargs in calls}
    assert 'automation_event' in emitted
    assert 'rule_trigger' in emitted