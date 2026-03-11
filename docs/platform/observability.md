# Observability

## Observability layers

The platform implements observability through four mechanisms:

1. Prometheus metrics in `backend/app/core/metrics.py`
2. operational telemetry snapshots in `backend/app/services/operational_telemetry_service.py`
3. health and operational APIs in `backend/app/api/v1/health.py` and `backend/app/api/v1/system_operational.py`
4. optional OpenTelemetry tracing in `backend/app/core/tracing.py`

## Metrics

Prometheus metrics exposed in code include:

- HTTP request totals and durations
- provider call totals and durations
- replay execution totals and durations
- slow query totals
- Celery task durations
- queue depth and active worker gauges
- worker queue depth and inflight jobs
- graph write batch size
- event batch latency
- campaign execution lock wait

`/metrics` is conditionally enabled and can be protected by source IP or token.

## Internal metrics

`/internal/metrics` returns a narrow JSON snapshot from `internal_metrics_snapshot()`, including:

- active API requests
- worker queue depth
- worker inflight jobs
- graph batch size
- campaign execution lock state

## Operational health model

`snapshot_operational_health()` computes rolling health windows for:

- API latency and error rates
- provider latency and failure rates
- replay drift/failure rates
- slow query counts
- queue depth

The platform compares recent samples to in-code SLO targets such as:

- non-provider API p95: 250 ms
- provider p95: 900 ms
- DB slow query threshold: 200 ms
- queue soft ceiling: 100
- queue hard ceiling: 250

## Tracing

Tracing is opt-in through `OTEL_EXPORTER_ENDPOINT`.

When enabled, `setup_tracing()`:

- configures an OTLP HTTP exporter
- instruments FastAPI
- instruments outbound `requests`

If dependencies are missing, tracing bootstrap logs a warning and the app continues.

## Health topology

```mermaid
flowchart LR
    API[FastAPI] --> M[Prometheus metrics]
    API --> IH[/internal/metrics]
    API --> OH[/system/operational-health]
    API --> DF[/system/data-freshness]
    API --> OT[OpenTelemetry exporter]
    DB[(PostgreSQL)] --> QT[Query timing hooks]
    R[(Redis)] --> INF[infra_service probes]
```

## Probe sources

`backend/app/services/infra_service.py` probes:

- DB connectivity
- Redis connectivity
- worker heartbeat presence
- scheduler heartbeat presence
- active Celery queues
- queue depths

`backend/app/services/freshness_monitor_service.py` evaluates campaign data freshness using:

- `SearchConsoleDailyMetric`
- `AnalyticsDailyMetric`
- `CampaignDailyMetric`

## Operational logging

Operational telemetry emits structured log events for:

- provider calls
- replay executions
- queue depth snapshots
- slow queries
- stale traffic fact detection

These logs should be treated as first-class observability signals, not just debug output.
