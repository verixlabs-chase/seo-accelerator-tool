# Staging Deployment Checklist

## 1. Environment Variables

Set these before starting API, worker, and scheduler:

- `APP_ENV=staging`
- `APP_NAME=LSOS API`
- `API_V1_PREFIX=/api/v1`
- `JWT_SECRET=<32+ char secret>`
- `JWT_ACCESS_TTL_SECONDS=900`
- `JWT_REFRESH_TTL_SECONDS=604800`
- `POSTGRES_DSN=postgresql+psycopg://<user>:<pass>@<host>:5432/<db>`
- `REDIS_URL=redis://<host>:6379/0`
- `CELERY_BROKER_URL=redis://<host>:6379/0`
- `CELERY_RESULT_BACKEND=redis://<host>:6379/1`
- `CRAWL_TIMEOUT_SECONDS=10.0` (or staging-safe value)
- `CRAWL_MIN_REQUEST_INTERVAL_SECONDS=0.2`
- `CRAWL_MAX_PAGES_PER_RUN=200`
- `CRAWL_FRONTIER_BATCH_SIZE=25`
- `CRAWL_MAX_ACTIVE_RUNS_PER_TENANT=5`
- `CRAWL_MAX_ACTIVE_RUNS_PER_CAMPAIGN=2`
- `RANK_PROVIDER_BACKEND=synthetic|http|serpapi`
- `LOCAL_PROVIDER_BACKEND=synthetic|provider`
- `AUTHORITY_PROVIDER_BACKEND=synthetic|provider`
- `PROXY_PROVIDER_CONFIG_JSON=<json>`
- `LOG_LEVEL=INFO`
- `METRICS_ENABLED=true`
- `OTEL_EXPORTER_ENDPOINT=<collector endpoint>`
- `REFERENCE_LIBRARY_LOADER_ENABLED=true`
- `REFERENCE_LIBRARY_ENFORCE_VALIDATION=true`

If using production-like staging, also set:

- `OBJECT_STORAGE_ENDPOINT`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_ACCESS_KEY`
- `OBJECT_STORAGE_SECRET_KEY`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`

## 2. Database Migration

1. Verify DB connectivity:
   - `python -c "from app.db.session import engine; print(engine.connect().closed == False)"`
2. Run migrations:
   - `alembic upgrade head`
3. Confirm new cohesion table exists:
   - `report_schedules`
4. Validate schema quickly:
   - `python -m pytest -q tests/test_migrations.py`

## 3. Service Startup

Start in this order:

1. PostgreSQL
2. Redis
3. API:
   - `uvicorn app.main:app --host 0.0.0.0 --port 8000`
4. Worker:
   - `celery -A app.tasks.celery_app.celery_app worker -Q default -l INFO`
5. Beat scheduler (if enabled in staging):
   - `celery -A app.tasks.celery_app.celery_app beat -l INFO`

## 4. Proxy Configuration

If running behind reverse proxy/load balancer:

1. Route `/api/v1/*` to API service on port `8000`.
2. Preserve header passthrough:
   - `Authorization`
   - `X-Request-ID`
3. Enable request timeout > max API route latency.
4. Enable upstream retry only for idempotent GET routes.
5. Do not terminate or alter JSON response envelopes.

## 5. Health Checks

Run these checks after deploy:

1. Liveness:
   - `GET /api/v1/health`
2. Readiness:
   - `GET /api/v1/health/readiness`
3. Metrics/SLO snapshot:
   - `GET /api/v1/health/metrics`
4. Dashboard cohesion check:
   - `GET /api/v1/dashboard?campaign_id=<id>`
5. Report schedule check:
   - `GET /api/v1/reports/schedule?campaign_id=<id>`

Expected:

- All health endpoints return success envelope.
- Non-2xx responses return global error envelope:
  - `{ "success": false, "errors": [...], "meta": {...} }`
- Dashboard returns:
  - `technical_score`, `entity_score`, `recommendation_summary`, `latest_crawl_status`, `report_status_summary`, `slo_health_snapshot`, `platform_state`.

## 6. Staging Validation Run

Execute:

- `python -m pytest -q tests/test_staging_e2e.py`

Then run all backend tests:

- `python -m pytest -q tests`

## 7. Real Staging Load Simulation (Production Hardening Gate)

Run the staging-only simulator:

- `python backend/scripts/staging_load_simulation.py --base-url https://<staging-host>/api/v1 --email <staging-admin-email> --password <staging-admin-password> --crawl-jobs 8 --entity-jobs 5 --scheduled-report-runs 3 --load-phase-seconds 300 --drain-phase-seconds 300 --out Docs/ops/reports/staging_load_simulation.json`

Pre-run requirements:

- Use staging hostname only (script blocks production-like hosts).
- Keep provider adapters enabled as in staging runtime config.
- Ensure worker + beat are running with intended concurrency values.
- Confirm `GET /api/v1/health/metrics` returns non-empty `metrics`, `slos`, and `alert_state`.

## 8. Load Test Success Thresholds

Evaluate `Docs/ops/reports/staging_load_simulation.json` using these gates.

### A) P95 API Latency (`Performance Metrics.P95_latency_ms`)

- `PASS`: `<= 1200 ms`
- `WARN`: `> 1200 ms` and `<= 2000 ms`
- `FAIL`: `> 2000 ms`

### B) Queue Drain Behavior (`Queue Metrics`)

Use:
- `drain_rate_after_load`
- `backlog_growth_rate`
- `max_queue_depth`
- final queue depth in `queue_depth_over_time`

Thresholds:

- `PASS`:
  - `drain_rate_after_load >= backlog_growth_rate`
  - final queue depth `<= 20%` of `max_queue_depth` by end of drain phase
- `WARN`:
  - `drain_rate_after_load < backlog_growth_rate` but `>= 80%` of `backlog_growth_rate`, or
  - final queue depth `> 20%` and `<= 40%` of `max_queue_depth`
- `FAIL`:
  - `drain_rate_after_load < 80%` of `backlog_growth_rate`, or
  - final queue depth `> 40%` of `max_queue_depth`

### C) Failure Rate (`Failure Metrics.failure_rate_by_task_type`)

- `PASS`: each task type failure rate `<= 2.0%`
- `WARN`: any task type `> 2.0%` and `<= 5.0%`
- `FAIL`: any task type `> 5.0%`

Hard-fail conditions regardless of percentages:

- `tasks_exceeded_retry_cap` is non-empty.
- `health.metrics` polling failures prevent reliable metric interpretation.

### D) Degraded-State Stability (`System Stability.time_in_degraded_state_seconds`)

Calculate against load-phase duration (`--load-phase-seconds`):

- `PASS`: degraded-state duration `<= 20%` of load phase
- `WARN`: degraded-state duration `> 20%` and `<= 35%` of load phase
- `FAIL`: degraded-state duration `> 35%` of load phase

Additional stability guardrail:

- `platform_state_transitions` should remain `<= 4` for a 5-minute load window.
- `> 4` transitions indicates state flapping and should be treated as `WARN` (or `FAIL` if combined with any other fail condition).

## 9. Post-Run Tuning Decision Rules

- Increase worker concurrency when queue gate is `WARN`/`FAIL` and latency remains in `PASS`/`WARN`.
- Tighten alerting only after concurrency is tuned and rerun confirms stable queue drain.
- Keep existing contract boundaries: no schema changes, no lifecycle contract edits, no adapter boundary violations.
- Update readiness estimate:
  - all gates `PASS` -> readiness `97-98%`
  - any `WARN` and no `FAIL` -> readiness `95-96%`
  - any `FAIL` -> remain at `94-95%` until rerun passes
