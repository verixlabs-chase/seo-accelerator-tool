from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue


@dataclass(frozen=True)
class CampaignQueueEvent:
    campaign_id: str
    partition: int
    enqueued_at: str


class CampaignQueue:
    def __init__(self) -> None:
        self._queue: Queue[CampaignQueueEvent] = Queue()

    def enqueue_campaign(self, campaign_id: str, partition: int) -> CampaignQueueEvent:
        event = CampaignQueueEvent(
            campaign_id=str(campaign_id),
            partition=int(partition),
            enqueued_at=datetime.now(UTC).isoformat(),
        )
        self._queue.put(event)
        return event

    def dequeue_campaign(self, timeout: float = 0.1) -> CampaignQueueEvent | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def task_done(self) -> None:
        self._queue.task_done()

    def join(self) -> None:
        self._queue.join()

    def size(self) -> int:
        return self._queue.qsize()
