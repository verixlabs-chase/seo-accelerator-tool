# Performance Audit

Date: 2026-03-10

## Scope

This audit combines code inspection with targeted local test execution. It is not a production benchmark.

## Measured Inputs

- Intelligence-focused test suite:
  - `26 passed, 1 warning in 109.19s`
- Existing system lifecycle and event/outbox tests reviewed for end-to-end path coverage.
- Manual load-profile scaffolds added under `backend/tests/load/` but not executed by default.

## Primary Bottlenecks

### Synchronous outcome path

- `backend/app/intelligence/outcome_tracker.py` still performs portfolio update and experiment attribution inline before returning.
- This is functionally correct but adds latency to execution completion.

### Duplicate recomputation

- `backend/app/intelligence/event_integration.py` can recompute signals and features after committed events.
- That overlaps orchestrator work and background learning worker work.

### Table-scan style telemetry

- Learning telemetry and report generation aggregate across experiments, evolution logs, and graph state.
- Current implementation is acceptable at small scale but not obviously bounded for large multi-tenant history.

### Queue abstraction depth

- `backend/app/events/queue.py` is lightweight.
- In test mode it runs inline.
- In production it delegates to Celery, but local queue-level metrics and retry visibility are thin.

## Load Readiness Assessment

| Scale | Assessment |
|---|---|
| 10 campaigns | Safe in current architecture |
| 100 campaigns | Likely workable with current worker split and existing indexes |
| 1000 campaigns | Not ready without pruning, batching, and stronger queue observability |

## Manual Load Profiles Added

File: `backend/tests/load/test_platform_load_profiles.py`

Profiles defined:

- 10,000 API requests
- 5,000 queued actions
- 1,000 concurrent workers
- report generation bursts

These are intentionally manual and gated behind `RUN_PLATFORM_LOAD_TESTS`.

## Performance Recommendations

1. Move more of the outcome-side learning work behind workers.
2. Remove duplicate feature recomputation from event replay paths.
3. Add queue backlog, worker throughput, and outbox lag metrics.
4. Materialize learning rollups instead of recomputing broad aggregates.
5. Add composite indexes for experiment attribution and graph-heavy analytics queries if load grows.
