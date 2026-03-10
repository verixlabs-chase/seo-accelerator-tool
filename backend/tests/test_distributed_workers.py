from app.intelligence.campaign_workers import CampaignWorkerPool, partition_for_campaign


def test_partitioning_is_stable() -> None:
    first = partition_for_campaign('campaign-123', 8)
    second = partition_for_campaign('campaign-123', 8)
    assert first == second


def test_worker_pool_uses_local_processor_for_tests() -> None:
    pool = CampaignWorkerPool(worker_count=2, processor=lambda campaign_id: {'campaign_id': campaign_id, 'status': 'ok'})
    assignments, results = pool.process_campaigns(['a', 'b'])
    assert set(assignments) == {'a', 'b'}
    assert results['a']['status'] == 'ok'
    assert results['b']['status'] == 'ok'
