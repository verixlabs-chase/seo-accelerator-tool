from __future__ import annotations

from types import SimpleNamespace

from app.enums import StrategyRecommendationStatus
from app.intelligence import recommendation_execution_engine as execution_engine
from app.intelligence.recommendation_execution_engine import approve_execution, execute_recommendation, schedule_execution
from app.models.intelligence import StrategyRecommendation
from app.models.recommendation_execution import RecommendationExecution
from app.services.strategy_engine.automation_engine import evaluate_campaign_for_automation
from app.utils.enum_guard import ensure_enum
from tests.conftest import create_test_campaign


def test_outcome_metric_read_does_not_republish_signals(db_session, monkeypatch) -> None:
    signal_reads: list[dict] = []

    def _record_signal_read(*_args, **kwargs):
        signal_reads.append(dict(kwargs))
        return {"avg_rank": 7.0}

    monkeypatch.setattr(execution_engine, "assemble_signals", _record_signal_read)
    monkeypatch.setattr(
        execution_engine,
        "record_execution_outcome",
        lambda *_args, **_kwargs: None,
    )
    execution = SimpleNamespace(
        id="execution-test",
        campaign_id="campaign-test",
        execution_type="improve_internal_links",
        execution_payload='{"metric_before": 8.0, "metric_name": "avg_rank"}',
        status="completed",
    )

    execution_engine._record_outcome_if_possible(db_session, execution, {})

    assert signal_reads == [{"db": db_session, "publish": False}]


def test_schedule_and_execute_recommendation_idempotently(
    db_session,
    create_test_tenant,
    create_test_org,
    monkeypatch,
) -> None:
    signal_reads: list[dict] = []
    original_assemble_signals = execution_engine.assemble_signals

    def _record_signal_read(*args, **kwargs):
        signal_reads.append(dict(kwargs))
        return original_assemble_signals(*args, **kwargs)

    monkeypatch.setattr(execution_engine, "assemble_signals", _record_signal_read)
    tenant = create_test_tenant(name='Exec Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Exec Org')
    org.plan_type = 'multi_location'
    db_session.commit()
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Exec Campaign',
        domain='exec.example',
    )

    rec = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='improve_internal_links',
        rationale='deterministic execution test',
        confidence=0.9,
        confidence_score=0.9,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    db_session.add(rec)
    db_session.commit()

    first = schedule_execution(rec.id, db=db_session)
    assert first is not None
    assert first.status == 'scheduled'

    second = schedule_execution(rec.id, db=db_session)
    assert second is not None
    assert second.id == first.id
    assert signal_reads
    assert all(item.get("publish") is False for item in signal_reads)
    signal_reads.clear()

    planned = execute_recommendation(first.id, db=db_session, dry_run=True)
    assert isinstance(planned, dict)
    approve_execution(
        first.id,
        approved_by="test-owner",
        preview_hash=planned["preview"]["preview_hash"],
        db=db_session,
    )

    executed = execute_recommendation(first.id, db=db_session)
    assert executed is not None
    assert executed.status == 'completed'


def test_automation_engine_enqueues_for_approved_or_scheduled(db_session, create_test_tenant, create_test_org) -> None:
    tenant = create_test_tenant(name='Auto Exec Tenant')
    org = create_test_org(tenant_id=tenant.id, name='Auto Exec Org')
    campaign = create_test_campaign(
        db_session,
        org.id,
        tenant_id=tenant.id,
        name='Auto Exec Campaign',
        domain='autoexec.example',
    )

    approved = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='fix_missing_title',
        rationale='approved',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.APPROVED, StrategyRecommendationStatus),
    )
    scheduled = StrategyRecommendation(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        recommendation_type='optimize_gbp_profile',
        rationale='scheduled',
        confidence=0.8,
        confidence_score=0.8,
        evidence_json='{}',
        rollback_plan_json='{}',
        status=ensure_enum(StrategyRecommendationStatus.SCHEDULED, StrategyRecommendationStatus),
    )
    db_session.add_all([approved, scheduled])
    db_session.commit()

    result = evaluate_campaign_for_automation(campaign.id, db_session)
    assert result['campaign_id'] == campaign.id

    count = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.campaign_id == campaign.id)
        .count()
    )
    # Managed WordPress work now fails closed until this campaign has an
    # enabled site policy. Non-WordPress automation continues to schedule.
    assert count == 1
    execution = (
        db_session.query(RecommendationExecution)
        .filter(RecommendationExecution.campaign_id == campaign.id)
        .one()
    )
    assert execution.recommendation_id == scheduled.id
