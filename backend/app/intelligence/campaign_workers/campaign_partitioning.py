from __future__ import annotations


def partition_for_campaign(campaign_id: str, worker_count: int) -> int:
    if worker_count <= 0:
        raise ValueError('worker_count must be greater than zero')
    normalized = str(campaign_id or '').strip()
    if not normalized:
        raise ValueError('campaign_id is required')
    return hash(normalized) % worker_count
