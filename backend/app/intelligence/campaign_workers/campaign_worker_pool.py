from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from app.core.config import get_settings
from app.intelligence.campaign_workers.campaign_partitioning import partition_for_campaign
from app.intelligence.campaign_workers.campaign_task_runner import process_campaign


class CampaignWorkerPool:
    def __init__(self, *, worker_count: int, processor: Callable[[str], dict[str, Any]] | None = None) -> None:
        if worker_count <= 0:
            raise ValueError('worker_count must be greater than zero')
        self.worker_count = int(worker_count)
        self._processor = processor
        self._results: dict[str, dict[str, Any]] = {}
        self._health: list[dict[str, Any]] = [
            {'worker_id': index, 'partition_id': index, 'alive': False, 'processed': 0, 'mode': 'idle'}
            for index in range(self.worker_count)
        ]

    def start(self) -> None:
        for row in self._health:
            row['alive'] = True
            row['mode'] = 'celery' if self._processor is None else 'local'

    def enqueue_campaign(self, campaign_id: str) -> int:
        return partition_for_campaign(campaign_id, self.worker_count)

    def enqueue_many(self, campaign_ids: list[str]) -> dict[str, int]:
        return {campaign_id: self.enqueue_campaign(campaign_id) for campaign_id in campaign_ids}

    def wait_for_completion(self) -> None:
        return None

    def stop(self) -> None:
        for row in self._health:
            row['alive'] = False

    def process_campaigns(self, campaign_ids: list[str]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
        assignments = self.enqueue_many(campaign_ids)
        self.start()
        self._results = self._run_campaigns(campaign_ids, assignments)
        self.stop()
        return assignments, self.results()

    def health_snapshot(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._health]

    def results(self) -> dict[str, dict[str, Any]]:
        return dict(self._results)

    def _run_campaigns(self, campaign_ids: list[str], assignments: dict[str, int]) -> dict[str, dict[str, Any]]:
        if self._processor is not None:
            return self._run_local_processor(campaign_ids, assignments)
        return self._run_celery_processor(campaign_ids, assignments)

    def _run_local_processor(self, campaign_ids: list[str], assignments: dict[str, int]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            futures = {executor.submit(self._processor, campaign_id): campaign_id for campaign_id in campaign_ids}
            for future in as_completed(futures):
                campaign_id = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001
                    result = {'campaign_id': campaign_id, 'error': str(exc)}
                results[campaign_id] = dict(result)
                partition = assignments[campaign_id]
                self._health[partition]['processed'] += 1
        return results

    def _run_celery_processor(self, campaign_ids: list[str], assignments: dict[str, int]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        settings = get_settings()
        async_results = {}
        for campaign_id in campaign_ids:
            partition = assignments[campaign_id]
            queue_name = f'intelligence_partition_{partition % self.worker_count}'
            async_results[campaign_id] = process_campaign.apply_async(args=[campaign_id], queue=queue_name)
        for campaign_id, async_result in async_results.items():
            if settings.celery_task_always_eager or settings.app_env.lower() == 'test':
                payload = async_result.get()
            else:
                payload = async_result.get(timeout=300)
            results[campaign_id] = dict(payload)
            partition = assignments[campaign_id]
            self._health[partition]['processed'] += 1
        return results
