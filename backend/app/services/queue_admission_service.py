from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.services.infra_service import queue_depth_count
from app.services.queue_controls.fair_scheduler import ScheduledJob, WeightedFairScheduler
from app.services.queue_controls.starvation_monitor import evaluate_starvation
from app.services.queue_controls.token_bucket import TokenBucket, TokenBucketState

_CRITICAL_QUEUE_LAG = 180
_WARNING_QUEUE_LAG = 60
_DEFAULT_BUCKET_CAPACITY = 120
_DEFAULT_BUCKET_REFILL_PER_SECOND = 2.0
_TARGET_GOVERNANCE_WAIT_SECONDS = 30.0

_NON_CRITICAL_QUEUES = {"crawl_queue", "rank_queue", "content_queue", "authority_queue"}

_lock = threading.Lock()
_shadow_replay_enabled = True
_buckets: dict[tuple[str, str], TokenBucket] = {}
_scheduler = WeightedFairScheduler(weights={"system": 1})


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str


def admit_enqueue(*, tenant_id: str, queue_name: str) -> AdmissionDecision:
    global _shadow_replay_enabled

    tenant = tenant_id.strip() if tenant_id.strip() else "system"
    now_epoch = int(time.time())
    queue_depth = queue_depth_count(queue_name)
    with _lock:
        if queue_depth is not None and queue_depth >= _CRITICAL_QUEUE_LAG:
            _shadow_replay_enabled = False
        elif queue_depth is not None and queue_depth < _WARNING_QUEUE_LAG:
            _shadow_replay_enabled = True

        governance_depth = queue_depth_count("default_queue")
        if governance_depth is not None:
            starvation = evaluate_starvation(
                max_wait_seconds=float(governance_depth),
                target_wait_seconds=_TARGET_GOVERNANCE_WAIT_SECONDS,
            )
            if starvation.level == "critical" and queue_name in _NON_CRITICAL_QUEUES:
                return AdmissionDecision(allowed=False, reason="auto_throttled_for_governance_starvation")

        bucket_key = (tenant, queue_name)
        bucket = _buckets.get(bucket_key)
        if bucket is None:
            bucket = TokenBucket(
                TokenBucketState(
                    capacity=_DEFAULT_BUCKET_CAPACITY,
                    refill_rate_per_second=_DEFAULT_BUCKET_REFILL_PER_SECOND,
                    tokens=float(_DEFAULT_BUCKET_CAPACITY),
                    last_refill_epoch=now_epoch,
                )
            )
            _buckets[bucket_key] = bucket

        if not bucket.try_consume(now_epoch=now_epoch):
            return AdmissionDecision(allowed=False, reason="token_bucket_rejected")

        if queue_depth is not None and queue_depth >= _CRITICAL_QUEUE_LAG and queue_name in _NON_CRITICAL_QUEUES:
            return AdmissionDecision(allowed=False, reason="critical_queue_lag")

        current_job = ScheduledJob(tenant_id=tenant, queue_name=queue_name, payload={})
        _scheduler.enqueue(current_job)
        selected = _scheduler.next_job()
        if selected is None:
            return AdmissionDecision(allowed=False, reason="fair_scheduler_empty")
        if selected.tenant_id != tenant:
            _scheduler.enqueue(selected)
            return AdmissionDecision(allowed=False, reason="fair_scheduler_deferred")

    return AdmissionDecision(allowed=True, reason="allowed")


def shadow_replay_allowed() -> bool:
    with _lock:
        return _shadow_replay_enabled
