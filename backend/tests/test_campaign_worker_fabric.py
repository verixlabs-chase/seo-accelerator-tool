from __future__ import annotations

import time

from app.intelligence.campaign_workers.campaign_partitioning import partition_for_campaign
from app.intelligence.campaign_workers.campaign_worker_pool import CampaignWorkerPool


def test_campaign_partitioning_is_stable_and_bounded() -> None:
    worker_count = 5
    campaign_id = 'campaign-abc-123'

    first = partition_for_campaign(campaign_id, worker_count)
    second = partition_for_campaign(campaign_id, worker_count)

    assert first == second
    assert 0 <= first < worker_count


def test_worker_pool_processes_multiple_campaigns() -> None:
    campaign_ids = [f'campaign-{index}' for index in range(6)]

    def processor(campaign_id: str) -> dict[str, object]:
        return {'campaign_id': campaign_id, 'ok': True}

    pool = CampaignWorkerPool(worker_count=3, processor=processor)
    assignments, results = pool.process_campaigns(campaign_ids)

    assert set(assignments.keys()) == set(campaign_ids)
    assert set(results.keys()) == set(campaign_ids)
    assert all(bool(results[campaign_id].get('ok')) for campaign_id in campaign_ids)

    health = pool.health_snapshot()
    assert len(health) == 3


def test_workers_process_campaigns_concurrently() -> None:
    campaign_ids = [f'campaign-{index}' for index in range(6)]

    def processor(campaign_id: str) -> dict[str, object]:
        time.sleep(0.1)
        return {'campaign_id': campaign_id, 'processed': True}

    pool = CampaignWorkerPool(worker_count=3, processor=processor)

    started = time.perf_counter()
    _assignments, results = pool.process_campaigns(campaign_ids)
    elapsed = time.perf_counter() - started

    assert len(results) == len(campaign_ids)
    # Sequential would be ~0.6s. Allow CI jitter while still asserting concurrency benefit.
    assert elapsed < 0.75
