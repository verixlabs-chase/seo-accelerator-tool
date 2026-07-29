from __future__ import annotations

from app.intelligence.workers.learning_worker import process


def test_learning_worker_records_observation_without_policy_updates() -> None:
    result = process({'campaign_id': 'campaign-1'})

    assert result['status'] == 'observed'
    assert result['worker'] == 'learning'
    assert result['legacy_pipeline_active'] is False
    assert result['mode'] == 'observation_only'
    assert result['policy_updates_applied'] == 0
    assert result['causal_claim_created'] is False
    assert result['observation']['campaign_id'] == 'campaign-1'
    assert result['observation']['direction'] == 'no_material_change'
    assert result['payload'] == {'campaign_id': 'campaign-1'}
