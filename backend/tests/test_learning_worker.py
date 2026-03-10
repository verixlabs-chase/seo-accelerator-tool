from __future__ import annotations

from app.intelligence.workers.learning_worker import process


def test_learning_worker_is_noop_compatibility_dispatch() -> None:
    result = process({'campaign_id': 'campaign-1'})

    assert result['status'] == 'noop'
    assert result['worker'] == 'learning'
    assert result['legacy_pipeline_active'] is False
    assert result['payload'] == {'campaign_id': 'campaign-1'}
