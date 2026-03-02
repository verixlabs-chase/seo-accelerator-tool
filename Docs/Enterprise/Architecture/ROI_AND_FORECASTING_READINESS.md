# ROI and Forecasting Readiness

## Executive Status
Current state:
- Analytics storage is now present via `campaign_daily_metrics`.
- ROI calculation is still not implemented.
- Forecasting is still not implemented as a runtime feature.

The platform is now schema-ready for financial facts (`cost`, `revenue`) but not functionally ROI-ready because those fields are not populated by any production ingestion path yet.

## What Exists Today
Implemented:
- canonical nullable financial columns on `campaign_daily_metrics` in `backend/app/models/campaign_daily_metric.py`
- deterministic daily storage and replay-safe upsert in `backend/app/services/analytics_service.py`
- portfolio allocation helper in `backend/app/services/portfolio/allocator.py`
- weighted momentum helper in `backend/app/services/portfolio/portfolio_momentum.py`
- temporal strategy momentum in `backend/app/services/strategy_engine/temporal_integration.py`

These are readiness components, not a complete ROI or forecast engine.

## What Is Missing
Not implemented today:
- revenue ingestion pipeline into `campaign_daily_metrics.revenue`
- spend ingestion pipeline into `campaign_daily_metrics.cost`
- attribution models
- cost allocation models
- LTV models
- budget pacing logic
- forecast persistence models
- forecast APIs
- reporting views that expose ROI or capital projections

## Required Data for ROI
Minimum required inputs:
- daily campaign cost
- daily recognized revenue or attributed revenue
- attribution rules (first touch, last touch, weighted, or custom)
- explicit cost-allocation logic for shared spend
- optional customer value extensions (gross margin, retention, LTV)

Current repository status:
- `cost` and `revenue` columns exist but are not populated by `analytics_service.rollup_campaign_daily_metrics_for_date()`
- no service currently computes ROI from stored facts

## Required Data for Pacing
Minimum pacing inputs:
- planned budget
- actual spend by day and by intra-period checkpoint
- pacing target window
- alert thresholds and recommendation rules

Current status:
- there is no persisted budget model in the reporting path
- there is no spend ingestion into the analytics fact layer
- there is no pacing service in `backend/app/services/`

## Required Data for Forecasting
Minimum forecasting inputs:
- normalized historical daily performance series
- normalized financial facts
- forecast horizon definitions
- model selection (heuristic, moving average, regression, or other)
- confidence intervals or bounded assumptions

Current status:
- the platform now has a canonical daily table that can serve as the historical base layer
- the populated metrics are still incomplete for revenue-grade forecasting because traffic and financial facts are not yet fully stored

## Capital Allocation Integration Path
Current code that can be reused:
- `backend/app/services/portfolio/allocator.py`
- `backend/app/services/portfolio/portfolio_momentum.py`

Recommended extension path:
1. Populate `cost` and `revenue` in `campaign_daily_metrics` from real ingestion pipelines.
2. Add a dedicated ROI service that consumes only stored daily facts.
3. Add a separate forecast service and storage model layered above `campaign_daily_metrics`.
4. Feed forecast outputs into portfolio allocation rather than expanding the base fact schema.

## Implemented vs Planned
Implemented:
- decimal-safe financial storage fields
- canonical daily analytics foundation

Planned:
- actual ROI math
- pacing logic
- forecasting math
- report/API integration for capital planning
