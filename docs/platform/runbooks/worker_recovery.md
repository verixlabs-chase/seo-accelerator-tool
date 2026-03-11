# Worker Recovery

## Symptoms

- `infra:worker:heartbeat` missing
- queue depth rising
- tasks timing out or staying queued
- `/api/v1/system/operational-health` shows degraded queue state

## Recovery procedure

1. Confirm Redis is reachable.
2. Confirm Celery worker processes are running.
3. Inspect active queues using Celery inspect or the operational health endpoint.
4. Restart affected worker processes.
5. Recheck `infra:worker:heartbeat`.
6. Verify queue depth begins draining.

## Intelligence worker specifics

If the issue is in the intelligence dispatch path:

- inspect `backend/app/events/queue.py` failed-job records
- retry failed jobs if payloads are known-good
- verify `intelligence.run_worker` tasks are executing
- confirm whether the failing path is `experiment`, `learning`, or `outbox`

## Outbox recovery

If outbox processing is stuck:

1. Inspect `event_outbox` rows by `status`.
2. Restart the worker responsible for `outbox`.
3. Re-run the outbox worker in a controlled batch.
4. Watch for rows flipping from `pending` to `processed` or `failed`.

## After recovery

- verify queue depth normalizes
- verify event DLQ is not growing
- verify learning reports and experiments resume updating if the incident affected experiment processing
