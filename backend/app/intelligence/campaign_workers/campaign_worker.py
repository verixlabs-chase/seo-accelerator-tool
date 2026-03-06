from __future__ import annotations

from threading import Event, Lock, Thread
from typing import Any, Callable

from app.events.event_bus import publish_event
from app.events.event_types import EventType
from app.intelligence.campaign_workers.campaign_queue import CampaignQueue


class CampaignWorker(Thread):
    def __init__(
        self,
        *,
        worker_id: int,
        partition_id: int,
        campaign_queue: CampaignQueue,
        processor: Callable[[str], dict[str, Any]],
        on_result: Callable[[str, dict[str, Any]], None],
        stop_event: Event,
    ) -> None:
        super().__init__(daemon=True, name=f'campaign-worker-{worker_id}-p{partition_id}')
        self.worker_id = int(worker_id)
        self.partition_id = int(partition_id)
        self._queue = campaign_queue
        self._processor = processor
        self._on_result = on_result
        self._stop_event = stop_event
        self._lock = Lock()
        self._processed_count = 0

    def run(self) -> None:
        while not self._stop_event.is_set() or self._queue.size() > 0:
            event = self._queue.dequeue_campaign(timeout=0.1)
            if event is None:
                continue

            try:
                publish_event(
                    EventType.CAMPAIGN_PROCESSING_STARTED.value,
                    {
                        'campaign_id': event.campaign_id,
                        'worker_id': self.worker_id,
                        'partition': self.partition_id,
                    },
                )
                result = self._processor(event.campaign_id)
                self._on_result(event.campaign_id, result)
                publish_event(
                    EventType.CAMPAIGN_PROCESSING_COMPLETED.value,
                    {
                        'campaign_id': event.campaign_id,
                        'worker_id': self.worker_id,
                        'partition': self.partition_id,
                    },
                )
                with self._lock:
                    self._processed_count += 1
            except Exception as exc:  # noqa: BLE001
                self._on_result(
                    event.campaign_id,
                    {
                        'campaign_id': event.campaign_id,
                        'error': str(exc),
                        'worker_id': self.worker_id,
                        'partition': self.partition_id,
                    },
                )
            finally:
                self._queue.task_done()

    def processed_count(self) -> int:
        with self._lock:
            return int(self._processed_count)
