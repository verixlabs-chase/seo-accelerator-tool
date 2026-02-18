# Production Hardening Runbook Drill

## Drill Scope

- Worker crash
- DB connection drop
- Migration rollback scenario

## 1. Worker Crash Drill

### Simulation

- Stop worker process:
  - `celery -A app.tasks.celery_app.celery_app worker -Q default -l INFO`
- Confirm task failures/retries:
  - `reporting.process_schedule`
  - `crawl.fetch_batch`
  - `entity.analyze_campaign`

### Expected Signals

- `reason_code` present in failed task execution payload.
- Retry counts increase and cap is enforced for schedule processing.
- Dashboard reflects schedule failure (`report_status_summary.schedule.has_failure=true`).
- `platform_state` degrades to `Degraded` or `Critical`.

### Recovery

1. Restart worker.
2. Re-run failed schedules or replay queued operations.
3. Confirm:
   - `/api/v1/health/metrics`
   - `/api/v1/dashboard?campaign_id=<id>`

## 2. DB Connection Drop Drill

### Simulation

- Temporarily invalidate DB host or stop DB service.
- Hit:
  - `GET /api/v1/health/readiness`

### Expected Signals

- Readiness status becomes `degraded`.
- DB dependency marked false in readiness payload.

### Recovery

1. Restore DB connectivity.
2. Verify readiness returns `ready`.
3. Run smoke checks:
   - auth login
   - campaign list
   - dashboard fetch

## 3. Migration Rollback Drill

### Simulation

1. Apply latest migrations:
   - `alembic upgrade head`
2. Roll back one revision:
   - `alembic downgrade -1`
3. Re-apply:
   - `alembic upgrade head`

### Expected Signals

- Migration commands complete cleanly.
- API boots successfully after re-apply.
- `report_schedules` table restored at head.

### Recovery Checklist

1. Pause deploy traffic.
2. Restore last known-good DB schema revision.
3. Restart API + worker + beat.
4. Validate health/readiness/metrics.
5. Resume traffic.

## Recovery Time Targets (Operational)

- Worker crash: 5-10 minutes
- DB drop: 10-20 minutes
- Migration rollback/forward: 15-30 minutes
