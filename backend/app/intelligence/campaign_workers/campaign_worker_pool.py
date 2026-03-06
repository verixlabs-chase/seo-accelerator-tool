from __future__ import annotations

from threading import Event, Lock
from typing import Any, Callable

from app.intelligence.campaign_workers.campaign_partitioning import partition_for_campaign
from app.intelligence.campaign_workers.campaign_queue import CampaignQueue
from app.intelligence.campaign_workers.campaign_worker import CampaignWorker


class CampaignWorkerPool:
    def __init__(
        self,
        *,
        worker_count: int,
        processor: Callable[[str], dict[str, Any]],
    ) -> None:
        if worker_count <= 0:
            raise ValueError('worker_count must be greater than zero')

        self.worker_count = int(worker_count)
        self._processor = processor
        self._queues = [CampaignQueue() for _ in range(self.worker_count)]
        self._stop_event = Event()
        self._result_lock = Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._workers = [
            CampaignWorker(
                worker_id=index,
                partition_id=index,
                campaign_queue=self._queues[index],
                processor=self._processor,
                on_result=self._on_result,
                stop_event=self._stop_event,
            )
            for index in range(self.worker_count)
        ]

    def start(self) -> None:
        for worker in self._workers:
            if not worker.is_alive():
                worker.start()

    def enqueue_campaign(self, campaign_id: str) -> int:
        partition = partition_for_campaign(campaign_id, self.worker_count)
        self._queues[partition].enqueue_campaign(campaign_id, partition)
        return partition

    def enqueue_many(self, campaign_ids: list[str]) -> dict[str, int]:
        assignments: dict[str, int] = {}
        for campaign_id in campaign_ids:
            assignments[campaign_id] = self.enqueue_campaign(campaign_id)
        return assignments

    def wait_for_completion(self) -> None:
        for queue in self._queues:
            queue.join()

    def stop(self) -> None:
        self._stop_event.set()
        for worker in self._workers:
            worker.join(timeout=2.0)

    def process_campaigns(self, campaign_ids: list[str]) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
        assignments = self.enqueue_many(campaign_ids)
        self.start()
        self.wait_for_completion()
        self.stop()
        return assignments, self.results()

    def health_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                'worker_id': worker.worker_id,
                'partition_id': worker.partition_id,
                'alive': worker.is_alive(),
                'processed': worker.processed_count(),
            }
            for worker in self._workers
        ]

    def results(self) -> dict[str, dict[str, Any]]:
        with self._result_lock:
            return dict(self._results)

    def _on_result(self, campaign_id: str, result: dict[str, Any]) -> None:
        with self._result_lock:
            self._results[campaign_id] = dict(result)
