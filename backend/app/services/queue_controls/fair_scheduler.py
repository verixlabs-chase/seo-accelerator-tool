from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScheduledJob:
    tenant_id: str
    queue_name: str
    payload: dict[str, Any]
    cost: int = 1


class WeightedFairScheduler:
    def __init__(self, *, weights: dict[str, int]) -> None:
        if not weights:
            raise ValueError("weights must not be empty")
        self._weights = {tenant: max(1, weight) for tenant, weight in weights.items()}
        self._deficit: dict[str, int] = {tenant: 0 for tenant in self._weights}
        self._queues: dict[str, deque[ScheduledJob]] = {tenant: deque() for tenant in self._weights}

    def enqueue(self, job: ScheduledJob) -> None:
        if job.tenant_id not in self._queues:
            self._queues[job.tenant_id] = deque()
            self._weights[job.tenant_id] = 1
            self._deficit[job.tenant_id] = 0
        self._queues[job.tenant_id].append(job)

    def next_job(self) -> ScheduledJob | None:
        for tenant_id in self._weights:
            self._deficit[tenant_id] += self._weights[tenant_id]
            queue = self._queues[tenant_id]
            if not queue:
                continue
            job = queue[0]
            if job.cost <= self._deficit[tenant_id]:
                self._deficit[tenant_id] -= job.cost
                return queue.popleft()
        return None


def emit_scheduler_metric_stub(*, queue_name: str, tenant_id: str) -> None:
    _ = (queue_name, tenant_id)
