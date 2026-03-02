# Campaign Intelligence System Overview

## System Boundary
The current campaign intelligence stack spans:
- ingestion and operational tasks in `backend/app/tasks/tasks.py`
- provider adapters in `backend/app/providers/`
- normalization in `backend/app/services/analytics_service.py`
- aggregation and KPI assembly in `backend/app/services/reporting_service.py`, `backend/app/services/dashboard_service.py`, and `backend/app/services/campaign_performance_service.py`
- interpretation and automation in `backend/app/services/intelligence_service.py` and `backend/app/services/strategy_engine/`

## Implemented Layering

### 1. Ingestion Layer
Implemented adapters:
- Google Search Console: `backend/app/providers/google_search_console.py`
- Google Analytics: `backend/app/providers/google_analytics.py`
- Google Places: `backend/app/providers/google_places.py`
- rank providers: `backend/app/providers/rank.py`
- crawl provider: `backend/app/providers/crawl.py`
- local/authority adapters: `backend/app/providers/local.py`, `backend/app/providers/authority.py`

Implemented task orchestration:
- crawl, rank, content, authority, local, reporting, strategy automation, and analytics rollup tasks in `backend/app/tasks/tasks.py`

Current execution model:
- mostly asynchronous batch execution
- not near real-time
- provider-backed campaign performance still uses request-time provider reads when stored analytics coverage is missing

### 2. Normalization Layer
Implemented canonical normalization:
- `backend/app/services/analytics_service.py`
- model: `backend/app/models/campaign_daily_metric.py`

Responsibilities:
- convert stored source facts into a single campaign-day row
- compute deterministic hashes
- upsert replay-safely
- provide grouped rollups for organization or portfolio scopes

### 3. Aggregation Layer
Implemented stored aggregates:
- `campaign_daily_metrics`
- `portfolio_usage_daily`
- `monthly_reports`
- intelligence and local/rank snapshot tables already present from earlier phases

Implemented aggregation services:
- campaign-day rollup in `analytics_service.py`
- portfolio usage rollup in `portfolio_usage_service.py`
- report KPI assembly in `reporting_service.py`

### 4. Interpretation Layer
Implemented deterministic interpretation:
- `backend/app/services/intelligence_service.py`
- `backend/app/services/strategy_build_service.py`
- `backend/app/services/strategy_engine/engine.py`
- `backend/app/services/strategy_engine/automation_engine.py`

Implemented outputs:
- intelligence scores
- anomalies
- recommendations
- decision hashes and automation events

Not implemented in this layer:
- ROI-aware recommendations
- budget pacing
- capital forecasting

### 5. Automation Layer
Implemented automation:
- monthly strategy automation beat job in `backend/app/tasks/celery_app.py`
- nightly analytics rollup beat job in `backend/app/tasks/celery_app.py`
- task-level retries in `backend/app/tasks/tasks.py`

Current constraint:
- automation remains task-based and deterministic, but onboarding/bootstrap orchestration is still manual and fragmented.

### 6. Reporting Surfaces
Implemented surfaces:
- campaign dashboard and performance APIs in `backend/app/api/v1/campaigns.py`
- platform dashboard in `backend/app/api/v1/dashboard.py`
- report generation and report APIs in `backend/app/api/v1/reports.py`
- sub-account dashboard in `backend/app/api/v1/subaccounts.py`

Read behavior after Analytics Layer v1:
- prefer canonical daily facts when coverage is complete
- fall back to legacy live-provider reads when canonical coverage is missing

## Data Flow

### Performance Read Path
```text
provider APIs (legacy path)
    -> campaign_performance_service.py
    -> /api/v1/campaigns/{id}/performance-summary
    -> /api/v1/campaigns/{id}/performance-trend
```

```text
stored snapshots (rank/intelligence/local/crawl)
    -> analytics_service.rollup_campaign_daily_metrics_for_date()
    -> campaign_daily_metrics
    -> campaign_performance_service.py / reporting_service.py / dashboard_service.py
    -> existing API endpoints
```

### Nightly Analytics Path
```text
Celery beat
    -> analytics.rollup_daily
    -> analytics_service.rollup_campaign_daily_metrics_for_date()
    -> upsert campaign_daily_metrics
```

### Strategy Path
```text
operational signals + intelligence state
    -> strategy_build_service.py
    -> strategy_engine/
    -> strategy recommendations / automation events
```

## Determinism Boundaries
Deterministic components:
- `analytics_service.py` normalization and hash generation
- strategy build hashes and automation decision hashes in `strategy_engine/`
- idempotent upserts into `campaign_daily_metrics`

Non-deterministic or externally variable boundaries:
- live Google provider reads in `campaign_performance_service.py`
- upstream provider availability, credentials, and latency
- manual onboarding and manually triggered campaign workflows

## Implemented vs Planned
Implemented:
- minimal canonical analytics fact layer
- nightly analytics rollup task
- stored-read preference in selected reporting services

Planned:
- stored provider-performance ingestion for clicks/impressions/sessions/conversions
- ROI calculation on top of daily facts
- forecasting views derived from daily facts
- end-to-end automated onboarding bootstrap
