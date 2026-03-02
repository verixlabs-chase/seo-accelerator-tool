# Operational SLO Contract

## API

### Non-Provider Routes

- P95 latency: < 250ms
- P99 latency: < 600ms
- Error rate: < 1%

### Provider-Backed Routes

- P95 latency: < 900ms
- Error rate: < 3%
- Retry ceiling: 3 attempts per request path unless provider-specific policy is stricter

## Celery

- Queue depth soft ceiling: 100 tasks per queue
- Queue depth hard ceiling: 250 tasks per queue
- Task P95 execution bands:
  - Fast: < 250ms
  - Standard: < 1000ms
  - Heavy: < 5000ms

## Database

- Slow query threshold: 200ms
- Critical query threshold: 500ms

## Replay

- Determinism drift tolerance: 0
- Execution failure rate: < 0.5%

## Operational Notes

- These SLOs are the Phase 1 operational contract and apply to regression gating.
- Non-provider and provider latency are tracked independently.
- DB slow-query counts and queue depth are monitored through lightweight in-memory rolling windows in Phase 1.
- Any change that weakens replay determinism remains a release blocker.
