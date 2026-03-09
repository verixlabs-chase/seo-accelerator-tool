# E2E Campaign Flow (Staging Validation Sprint)

## Objective

Prove V1 campaign usability end-to-end with the single-call dashboard and report scheduling.

## Automated Test Path

- `backend/tests/test_staging_e2e.py`

Run:

- `cd backend`
- `python -m pytest -q tests/test_staging_e2e.py`

## Flow Steps

1. Tenant create
   - `POST /api/v1/tenants`
   - Requires `platform_admin`.
   - Assert success envelope (`data`, `meta`, `error`).

2. Campaign create
   - `POST /api/v1/campaigns`
   - Assert campaign created with `setup_state=Draft`.

3. Campaign lifecycle transitions
   - `PATCH /api/v1/campaigns/{id}/setup-state` to:
     - `Configured`
     - `BaselineRunning`
     - `Active`
   - Assert legal transitions accepted.

4. Baseline crawl
   - `POST /api/v1/crawl/schedule`
   - Assert run queued/scheduled and visible.

5. Rank snapshot
   - `POST /api/v1/rank/keywords`
   - `POST /api/v1/rank/schedule`
   - Assert `snapshots_created >= 1`.

6. Entity analyze
   - `POST /api/v1/entity/analyze`
   - Assert accepted/queued (or completed).

7. Single dashboard fetch
   - `GET /api/v1/dashboard?campaign_id=...`
   - Assert required product cohesion fields are present:
     - `technical_score`
     - `entity_score`
     - `recommendation_summary`
     - `latest_crawl_status`
     - `report_status_summary`
     - `slo_health_snapshot`
     - `platform_state`

8. Report schedule
   - `PUT /api/v1/reports/schedule`
   - `GET /api/v1/reports/schedule?campaign_id=...`
   - Assert schedule persisted and enabled.

9. Schedule processing
   - Trigger task:
     - `reporting_process_schedule.run(tenant_id, campaign_id)`
   - Assert status `success` or `not_due`.

10. Report generate and deliver
    - `POST /api/v1/reports/generate`
    - `POST /api/v1/reports/{report_id}/deliver`
    - Assert success envelope and delivery status.

## Failure-Mode Validation

Test includes report schedule failure simulation:

- Force `run_due_report_schedule` to fail.
- Execute `reporting_process_schedule` until retry cap is reached.
- Assert:
  - schedule `last_status=max_retries_exceeded`
  - schedule disabled
  - dashboard `report_status_summary.schedule.has_failure=true`
  - dashboard `platform_state` becomes `Degraded` or `Critical`

## Guardrails Validated

- Crawl/rank/entity task failures include:
  - `error_type`
  - `reason_code`
  - retry metadata (`current_retry`, `max_retries`, `dead_letter`)
- Retries are capped for schedule processing.
- Failures are surfaced through dashboard summary and state derivation.

