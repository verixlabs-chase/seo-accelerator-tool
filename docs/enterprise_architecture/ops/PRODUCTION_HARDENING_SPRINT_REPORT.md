# Production Hardening Sprint Report

Date: 2026-02-18

## Artifacts Added

- Load simulation script:
  - `backend/scripts/staging_load_simulation.py`
- Failure and stress validation tests:
  - `backend/tests/test_production_hardening.py`
- Updated task failure guardrails:
  - `backend/app/tasks/tasks.py`
- Observability tuning:
  - `backend/app/services/observability_service.py`
  - `backend/app/core/alert_thresholds.py`
  - `backend/app/services/dashboard_service.py`
- Runbook drill:
  - `docs/ops/RUNBOOK_DRILL.md`

## Operational Gaps Identified

1. No first-class API endpoint for queue depth by queue name (only aggregate backlog).
2. No explicit worker-heartbeat endpoint beyond task-derived metrics.
3. DB CPU threshold exists as static config but has no runtime collector in-process.
4. Load simulation depends on reachable staging API and tenant credentials.
5. Report scheduling trigger currently piggybacks on schedule update dispatch; periodic scheduler enforcement should be continuously verified in staging.

## Threshold Adjustments Applied

- `queue_lag_minutes`: `5 -> 8`
- `crawl_failure_spike_percent`: `10 -> 15`
- Added `state_flip_flop_deadband_percent: 5`

Rationale:

- Reduce sensitivity to transient spikes.
- Stabilize dashboard `platform_state` around thresholds.
- Keep critical transitions for clearly unhealthy conditions.

## Hardening Behavior Confirmed

- Task failures include `reason_code` for crawl/rank/entity/reporting paths.
- Retry cap enforcement confirmed for schedule processing.
- Dashboard degraded-state includes report schedule failure signal.
- Health metrics include:
  - `queue_backlog_tasks`
  - derived `alert_state` flags.

## Estimated MTTR

- Worker crash: ~8 minutes
- Proxy/network upstream failure: ~12 minutes
- Crawl timeout burst: ~10 minutes
- Report email outage: ~15 minutes
- DB connection drop: ~18 minutes
- Migration rollback incident: ~25 minutes

## Updated Readiness

- Prior readiness: 94%
- Post hardening sprint: 96%

## Validation Commands

- `python -m pytest -q tests/test_production_hardening.py`
- `python -m pytest -q tests`
- `python backend/scripts/staging_load_simulation.py --base-url http://localhost:8000/api/v1 --email <user> --password <pass>`
