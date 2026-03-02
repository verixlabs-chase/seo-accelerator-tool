# Operational Maturity Model

## Current Maturity Score
Current practical maturity assessment:
- Data maturity: 2.5 / 5
- Reporting maturity: 3 / 5
- ROI maturity: 1 / 5
- Forecast maturity: 1 / 5
- Enterprise readiness: 2.5 / 5

This reflects the current codebase after Analytics Layer v1, not the roadmap intent.

## Definitions

### Data Maturity
Definition:
- stable ingestion
- normalized canonical storage
- deterministic replay-safe aggregation
- organization-scoped reporting facts

Current state:
- improved by `campaign_daily_metrics` and `analytics_service.py`
- still incomplete because core traffic and financial facts are not yet stored by the nightly rollup

### Reporting Maturity
Definition:
- dashboards and reports prefer stored facts over volatile live reads
- export paths are stable
- freshness and gaps are explicit

Current state:
- selected reporting paths now prefer stored daily facts when coverage exists
- fallback logic still depends on live provider reads
- report exports remain basic and artifact delivery is not yet a full enterprise export surface

### ROI Maturity
Definition:
- revenue and cost are both ingested, normalized, and attributable
- ROI can be computed deterministically from stored facts

Current state:
- not reached
- schema readiness exists, runtime readiness does not

### Forecast Maturity
Definition:
- stable historical fact base
- explicit forecast models
- stored forecast outputs
- surfaced in reporting and allocation workflows

Current state:
- not reached
- only low-level allocation and momentum helpers exist outside a forecast product path

### Enterprise Readiness
Definition:
- deterministic migrations
- repeatable onboarding
- stored analytics
- controlled reporting surfaces
- operational validation and test coverage

Current state:
- materially improved by the analytics fact layer and added tests
- still limited by manual onboarding, partial live-provider dependency, and historical offline migration debt

## Target State Definition
Target enterprise-ready state:
1. onboarding is one-pass and idempotent
2. provider ingestion writes normalized stored facts on a schedule
3. reporting reads primarily from canonical fact tables
4. ROI and pacing are computed from stored financial facts
5. forecasting is separated into derived services and views
6. `alembic upgrade head --sql` is fully clean across the entire history

## Phased Roadmap

### Phase 1: Analytics Backbone (implemented in part)
Implemented:
- `campaign_daily_metrics`
- deterministic normalization service
- nightly rollup task
- selected reporting integration
- test coverage for idempotency and migration presence

Remaining in this phase:
- populate traffic and financial metrics from stored ingestion paths
- add freshness indicators for analytics coverage

### Phase 2: Reporting Stabilization
Planned:
- expand stored-read coverage across reporting endpoints
- reduce request-time dependence on Google APIs
- improve export surfaces and artifact serving

### Phase 3: ROI Readiness
Planned:
- ingest spend and revenue
- implement attribution and allocation
- expose ROI in reports and dashboards

### Phase 4: Forecast Readiness
Planned:
- add forecast models and persistence
- integrate forecast outputs into portfolio and capital views

### Phase 5: Onboarding and Operations Hardening
Planned:
- unify onboarding into an automated flow
- remove manual setup-state dependence where possible
- resolve historical Alembic offline SQL issues in older batch migrations
