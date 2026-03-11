# Incident Response

## Severity focus

Prioritize incidents in this order:

1. API unavailable
2. Redis unavailable
3. PostgreSQL unavailable or write failures
4. worker backlog or heartbeat loss
5. intelligence degradation without customer-facing outage

## First 10 minutes

1. Check API health endpoints.
2. Check Redis connectivity and heartbeat keys.
3. Check PostgreSQL connectivity.
4. Check `/api/v1/system/operational-health`.
5. Inspect queue depths and active queues.
6. Determine whether the issue is request-path, worker-path, or data freshness related.

## Quick diagnosis map

### API 5xx spike

Inspect:

- app logs from `RequestLoggingMiddleware`
- `/internal/metrics`
- slow query count from operational health
- Redis dependency failures

### Queue backlog

Inspect:

- `queue_depth`
- worker heartbeats
- active queue map from `infra_service.celery_queue_status`
- Celery task durations

### Intelligence pipeline failure

Inspect:

- event handler failures from `event_bus`
- Redis Stream retries/DLQ
- failed intelligence jobs from `backend/app/events/queue.py`
- outbox rows stuck in `pending` or `failed`

## Containment actions

- Disable noncritical scheduled load by stopping Beat.
- Scale specific worker queues instead of scaling the API blindly.
- If outbox replay is causing repeated failures, pause the outbox worker and inspect payloads before replaying.
- If DB is saturated, reduce graph-heavy or experiment-heavy workloads first.

## Recovery success criteria

- health endpoints stable
- queue depth trending down
- heartbeat keys present
- no growth in failed outbox rows or DLQ volume
- data freshness returning to expected window
