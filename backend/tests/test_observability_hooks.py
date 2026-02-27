from app.observability.events import emit_automation_event


def test_emit_does_not_throw() -> None:
    emit_automation_event(
        campaign_id='campaign-test',
        evaluation_date='2026-02-01T00:00:00+00:00',
        status='evaluated',
        decision_hash='a' * 64,
    )
    assert True