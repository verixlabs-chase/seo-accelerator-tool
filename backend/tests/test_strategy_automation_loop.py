from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import inspect

from app.models.campaign import Campaign
from app.models.intelligence import StrategyRecommendation
from app.models.temporal import MomentumMetric, StrategyPhaseHistory
from app.models.tenant import Tenant
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation
from app.tasks import tasks
from app.tasks.celery_app import celery_app


def _seed_campaign(db_session, *, name: str = 'Automation Campaign', setup_state: str = 'Active') -> Campaign:
    tenant = db_session.query(Tenant).order_by(Tenant.created_at.asc()).first()
    assert tenant is not None
    campaign = Campaign(tenant_id=tenant.id, name=name, domain=f'{name.lower().replace(" ", "-")}.example', setup_state=setup_state)
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    return campaign


def _seed_momentum(db_session, campaign_id: str, values: list[tuple[float, float]], when: datetime) -> None:
    for idx, (slope, volatility) in enumerate(values):
        db_session.add(
            MomentumMetric(
                campaign_id=campaign_id,
                metric_name='rank_avg_position_momentum',
                slope=slope,
                acceleration=0.0,
                volatility=volatility,
                window_days=30,
                computed_at=when.replace(day=max(1, when.day - idx)),
                deterministic_hash=f'hash-{idx}',
                profile_version='profile-v1',
            )
        )
    db_session.commit()


def test_automation_guardrail_freezes_with_insufficient_history(db_session) -> None:
    campaign = _seed_campaign(db_session)
    evaluation_date = datetime(2026, 3, 18, tzinfo=UTC)
    _seed_momentum(db_session, campaign.id, [(0.15, 0.2)], evaluation_date)

    result = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=evaluation_date)

    assert result['status'] == 'frozen'
    assert 'insufficient_historical_window' in result['triggered_rules']
    assert result['prior_phase'] == 'stabilization'
    assert result['new_phase'] == 'stabilization'


def test_automation_promotes_recommendation_and_advances_phase(db_session) -> None:
    campaign = _seed_campaign(db_session, name='Automation Growth')
    evaluation_date = datetime(2026, 4, 12, tzinfo=UTC)
    _seed_momentum(db_session, campaign.id, [(-0.30, 0.05), (-0.22, 0.08), (-0.18, 0.09)], evaluation_date)

    db_session.add(
        StrategyRecommendation(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
            recommendation_type='content_boost',
            rationale='promote this',
            confidence=0.9,
            confidence_score=0.9,
            evidence_json='["momentum_positive"]',
            risk_tier=1,
            rollback_plan_json='{"steps":["undo"]}',
            status='GENERATED',
        )
    )
    db_session.commit()

    result = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=evaluation_date)

    assert result['status'] == 'evaluated'
    assert result['new_phase'] == 'growth'
    transitions = result['action_summary']['recommendation_transitions']
    assert len(transitions) == 1
    assert transitions[0]['from'] == 'GENERATED'
    assert transitions[0]['to'] == 'VALIDATED'

    latest_phase = (
        db_session.query(StrategyPhaseHistory)
        .filter(StrategyPhaseHistory.campaign_id == campaign.id)
        .order_by(StrategyPhaseHistory.effective_date.desc(), StrategyPhaseHistory.id.desc())
        .first()
    )
    assert latest_phase is not None
    assert latest_phase.new_phase == 'growth'


def test_automation_is_idempotent_per_month_anchor(db_session) -> None:
    campaign = _seed_campaign(db_session, name='Automation Idempotent')
    evaluation_date = datetime(2026, 5, 9, tzinfo=UTC)
    _seed_momentum(db_session, campaign.id, [(-0.15, 0.1), (-0.14, 0.1), (-0.12, 0.1)], evaluation_date)

    first = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=evaluation_date)
    second = evaluate_campaign_for_automation(campaign.id, db_session, evaluation_date=evaluation_date)

    assert first['status'] in {'evaluated', 'frozen'}
    assert second['status'] == 'already_evaluated'


def test_strategy_automation_task_non_blocking_on_campaign_error(db_session, monkeypatch) -> None:
    campaign_a = _seed_campaign(db_session, name='Task Campaign A')
    _seed_campaign(db_session, name='Task Campaign B')

    calls = {'count': 0}

    def _fake_eval(campaign_id: str, db, evaluation_date=None):  # noqa: ANN001
        calls['count'] += 1
        if campaign_id == campaign_a.id:
            raise RuntimeError('synthetic automation failure')
        return {'campaign_id': campaign_id, 'status': 'evaluated', 'event_id': 'evt-1'}

    monkeypatch.setattr('app.services.strategy_engine.automation_engine.evaluate_campaign_for_automation', _fake_eval)

    summary = tasks.run_strategy_automation_for_all_campaigns.run(evaluation_date_iso='2026-06-01T00:00:00Z')

    assert calls['count'] >= 2
    assert summary['campaigns_scanned'] >= 2
    assert summary['campaign_failures'] >= 1
    assert summary['campaigns_evaluated'] >= 1


def test_strategy_automation_monthly_schedule_registered() -> None:
    schedule = celery_app.conf.beat_schedule
    assert 'strategy-automation-monthly' in schedule
    assert schedule['strategy-automation-monthly']['task'] == 'strategy.run_automation_for_all_campaigns'


def test_strategy_automation_events_table_present(db_session) -> None:
    inspector = inspect(db_session.get_bind())
    assert 'strategy_automation_events' in inspector.get_table_names()
