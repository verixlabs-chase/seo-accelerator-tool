import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.campaign import Campaign
from app.models.task_execution import TaskExecution
from app.models.user import User
from app.tasks.celery_app import celery_app
from app.tasks import tasks


def test_task_failure_payload_includes_dead_letter_metadata():
    fake_task = SimpleNamespace(request=SimpleNamespace(retries=3), max_retries=3)
    payload = tasks._task_failure_payload(fake_task, TimeoutError("timed out"))
    assert payload["reason_code"] == "timeout"
    assert payload["retryable"] is True
    assert payload["dead_letter"] is True
    assert payload["current_retry"] == 3
    assert payload["max_retries"] == 3


@pytest.mark.parametrize(
    ("task_name", "monkeypatch_target", "runner", "expected_reason_code", "error"),
    [
        (
            "rank.schedule_window",
            "app.tasks.tasks.rank_service.run_snapshot_collection",
            lambda campaign_id, tenant_id: tasks.rank_schedule_window.run(
                campaign_id=campaign_id, tenant_id=tenant_id, location_code="US"
            ),
            "timeout",
            TimeoutError("rank timeout"),
        ),
        (
            "entity.analyze_campaign",
            "app.tasks.tasks.entity_service.run_entity_analysis",
            lambda campaign_id, tenant_id: tasks.entity_analyze_campaign.run(tenant_id=tenant_id, campaign_id=campaign_id),
            "connection_error",
            ConnectionError("entity upstream offline"),
        ),
    ],
)
def test_task_failures_persist_reason_codes(db_session, monkeypatch, task_name, monkeypatch_target, runner, expected_reason_code, error):
    user = db_session.query(User).filter(User.email == "a@example.com").first()
    assert user is not None

    campaign = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        name=f"Task Failure {task_name}",
        domain=f"{task_name.replace('.', '-')}.example",
        created_at=datetime.now(UTC),
    )
    db_session.add(campaign)
    db_session.commit()

    def _fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(monkeypatch_target, _fail)
    with pytest.raises(type(error)):
        runner(campaign.id, user.tenant_id)

    row = (
        db_session.query(TaskExecution)
        .filter(TaskExecution.tenant_id == user.tenant_id, TaskExecution.task_name == task_name)
        .order_by(TaskExecution.created_at.desc())
        .first()
    )
    assert row is not None
    payload = json.loads(row.result_json or "{}")
    assert payload["reason_code"] == expected_reason_code



def test_celery_beat_includes_traffic_fact_sync_schedule() -> None:
    schedule = celery_app.conf.beat_schedule
    assert 'traffic-fact-sync-nightly' in schedule
    assert schedule['traffic-fact-sync-nightly']['task'] == 'traffic.nightly_sync_traffic_facts'


def test_nightly_sync_traffic_facts_tolerates_campaign_failures(db_session, monkeypatch) -> None:
    user = db_session.query(User).filter(User.email == 'a@example.com').first()
    assert user is not None

    campaign_one = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name='Traffic Sync One',
        domain='sync-one.example',
        setup_state='Active',
        created_at=datetime.now(UTC),
    )
    campaign_two = Campaign(
        id=str(uuid.uuid4()),
        tenant_id=user.tenant_id,
        organization_id=user.tenant_id,
        name='Traffic Sync Two',
        domain='sync-two.example',
        setup_state='Active',
        created_at=datetime.now(UTC),
    )
    db_session.add_all([campaign_one, campaign_two])
    db_session.commit()

    def _search_run(*, campaign_id, start_date, end_date, tenant_id=None):
        return {
            'campaign_id': campaign_id,
            'start_date': start_date,
            'end_date': end_date,
            'requested_days': 2,
        }

    def _analytics_run(*, campaign_id, start_date, end_date, tenant_id=None):
        if campaign_id == campaign_two.id:
            raise RuntimeError('ga failed')
        return {
            'campaign_id': campaign_id,
            'start_date': start_date,
            'end_date': end_date,
            'requested_days': 2,
        }

    monkeypatch.setattr(tasks.sync_search_console_daily_metrics_for_campaign, 'run', _search_run)
    monkeypatch.setattr(tasks.sync_analytics_daily_metrics_for_campaign, 'run', _analytics_run)
    monkeypatch.setattr(
        tasks.analytics_service,
        'rollup_campaign_daily_metrics_for_range',
        lambda **_kwargs: SimpleNamespace(days_processed=2),
    )

    result = tasks.nightly_sync_traffic_facts.run(lookback_days=2)

    assert result['processed_campaigns'] == 2
    assert result['failed_campaigns'] == 1
    assert result['search_synced_days'] == 2
    assert result['analytics_synced_days'] == 2
    assert result['rollup_days_processed'] == 2
