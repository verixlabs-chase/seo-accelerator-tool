# Analytics Layer V1 Architecture

## Problem Statement
The platform historically served campaign performance and reporting from two unstable sources:
- live upstream provider calls in `backend/app/services/campaign_performance_service.py`
- direct reads from operational tables such as `ranking_snapshots`, `technical_issues`, `intelligence_scores`, and `review_velocity_snapshots`

That approach makes reporting sensitive to provider latency, credential state, upstream outages, and replay timing. Analytics Layer v1 introduces a canonical daily fact table for campaign-level metrics so reporting can read from a deterministic, replay-safe store when that store is populated.

## Why Live-Provider-Only Reporting Is Unstable
Implemented live-provider reporting still exists in `backend/app/services/campaign_performance_service.py` and depends on:
- `SearchConsoleProviderAdapter`
- `GoogleAnalyticsProviderAdapter`
- organization provider credentials resolved by `backend/app/services/provider_credentials_service.py`

Failure modes include:
- provider credentials missing or stale
- upstream API outages or rate limits
- drifting results between repeated reads of the same window
- direct request-path dependence on external systems

Analytics Layer v1 reduces this by preferring stored rows from `campaign_daily_metrics` when the requested window has complete daily coverage.

## Implemented Canonical Fact Model
Implemented model: `backend/app/models/campaign_daily_metric.py`
Implemented migration: `backend/alembic/versions/20260302_0039_add_campaign_daily_metrics.py`

Table: `campaign_daily_metrics`

Base facts only:
- scope: `organization_id`, `portfolio_id`, `sub_account_id`, `campaign_id`, `metric_date`
- traffic/performance: `clicks`, `impressions`, `avg_position`, `sessions`, `conversions`
- operational/quality: `technical_issue_count`, `intelligence_score`, `reviews_last_30d`, `avg_rating_last_30d`
- financial readiness: `cost`, `revenue`
- control fields: `normalization_version`, `deterministic_hash`, `created_at`, `updated_at`

Explicit exclusions in v1:
- no `tenant_id`
- no derived metrics (`ctr`, rates, ratios)
- no provider telemetry counters
- no forecasting fields
- no strategy metadata

Constraints and indexes:
- unique: `(campaign_id, metric_date)`
- indexes: `organization_id`, `portfolio_id`, `campaign_id`, `metric_date`, and explicit `(campaign_id, metric_date)`

## Implemented Normalization Flow
Normalization service: `backend/app/services/analytics_service.py`

Implemented behavior:
1. `CampaignDailyMetricInput` captures only canonical inputs.
2. `normalize_campaign_daily_metric(...)` converts the input into a row payload.
3. `deterministic_hash` is computed from a sorted, normalized JSON payload.
4. `upsert_campaign_daily_metric(...)` compares the stored hash before writing.
5. `rollup_campaign_daily_metrics_for_date(...)` aggregates per-campaign daily rows without any live provider calls.

Current rollup sources are local database tables only:
- `ranking_snapshots` for `avg_position`
- `technical_issues` for `technical_issue_count`
- `intelligence_scores` for `intelligence_score`
- `review_velocity_snapshots` for review velocity fields

Current gaps:
- `clicks`, `impressions`, `sessions`, `conversions`, `cost`, and `revenue` are schema-ready but not yet populated by the nightly rollup because there is no stored ingestion layer for those facts yet.

## Idempotency Guarantees
Implemented guarantees in `backend/app/services/analytics_service.py`:
- row identity is fixed by `(campaign_id, metric_date)`
- writes compare `deterministic_hash` before mutation
- identical replays skip updates entirely
- changed inputs update the existing row instead of creating duplicates
- `updated_at` is configured with `onupdate` so mutation time reflects actual changes

This is covered by `backend/tests/test_campaign_daily_metrics.py`.

## Rollup Strategy
Implemented:
- service-level rollup: `rollup_campaign_daily_metrics_for_date(...)`
- Celery task: `analytics.rollup_daily` in `backend/app/tasks/tasks.py`
- nightly beat schedule: `analytics-rollup-nightly` in `backend/app/tasks/celery_app.py`

Current behavior:
- the nightly task rolls up all campaigns created before the end of the target day
- organization scoping is enforced; campaigns without `organization_id` fail rollup instead of producing unscoped facts
- portfolio and organization rollups are available as service-level grouped reads via `rollup_campaign_metrics_by_scope(...)`

## Transitional Reporting Integration
Implemented read-path integration:
- `backend/app/services/campaign_performance_service.py` now prefers `campaign_daily_metrics` for summary/trend windows when daily coverage is complete enough to serve the request safely
- `backend/app/services/reporting_service.py` now prefers the latest `campaign_daily_metrics` row for KPI fields it can source deterministically (`technical_issues`, `intelligence_score`, review velocity)
- `backend/app/services/dashboard_service.py` now prefers the latest daily metric for technical score calculation and falls back to live issue counting otherwise

Fallback behavior remains in place:
- if the requested performance window is not fully covered, the system falls back to live provider reads
- no existing endpoint was removed in v1

## Replay Considerations
Implemented replay-safe behavior:
- normalization is a pure function over supplied inputs
- no live provider calls occur inside normalization or rollup
- identical source state produces the same `deterministic_hash`
- repeated daily rollups are skip-safe

No replay-governed tables were modified by this change set. Existing replay infrastructure in `backend/alembic/versions/20260224_0027_replay_governance_foundation.py` and related strategy governance paths remains untouched.

## Migration Determinism
The new revision `20260302_0039` is deterministic and offline-safe when isolated:
- `alembic upgrade 20260302_0038:20260302_0039 --sql` emits clean static SQL

Important historical constraint:
- the full repo-wide chain `alembic upgrade head --sql` is still not clean because older revision `20260218_0013` uses SQLite batch reflection in offline mode. That issue predates Analytics Layer v1.

## Future ROI / Forecast Extension Plan
Planned, not implemented:
1. Persist daily spend and revenue facts from actual ingestion paths into `cost` and `revenue`.
2. Add attribution and allocation logic above `campaign_daily_metrics`, not inside it.
3. Build ROI rollups from stored daily facts rather than live provider requests.
4. Add forecast models as separate derived tables or services, not as extra columns in `campaign_daily_metrics`.
5. Keep `campaign_daily_metrics` as the minimal canonical base fact layer.
