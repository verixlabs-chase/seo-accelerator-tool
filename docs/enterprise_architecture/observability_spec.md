# OBSERVABILITY_SPEC.md

## 1) Scope

Defines LSOS observability requirements for metrics, logging, tracing, dashboards, and operational diagnostics.

## 2) Observability Signals

- Metrics:
  - API, workers, queues, DB, proxy health, report pipeline.
- Logs:
  - structured JSON logs across all services.
- Traces:
  - distributed traces from request to async task completion.
- Events:
  - domain events for campaign milestones and recommendation publication.

## 3) Metrics Catalog (Minimum)

API:
- request rate, error rate, latency p50/p95/p99 by endpoint.

Celery:
- queue depth, task runtime, retries, failures, dead-letter count.

Data freshness:
- last successful snapshot age per campaign for crawl/rank/reviews.

Reporting:
- generation duration, success/failure, delivery success rate.

Infrastructure:
- CPU, memory, container restarts, DB connections, replica lag.

## 4) Logging Contract

Required fields:
- `timestamp`
- `level`
- `service`
- `environment`
- `tenant_id` (if available)
- `campaign_id` (if available)
- `correlation_id`
- `request_id` (API)
- `task_id` (workers)
- `message`

Policies:
- No secrets or tokens in logs.
- PII minimized and redacted.
- Retention tiered by log type.

## 5) Tracing Contract

- Trace propagation via W3C trace context.
- API request span includes DB, external provider, and queue publish spans.
- Worker span links to originating request via correlation metadata.

## 6) Dashboard Requirements

- Platform health dashboard.
- Queue/worker performance dashboard.
- Campaign data freshness dashboard.
- Reporting pipeline dashboard.
- Security and auth anomaly dashboard.

## 7) Alert Integration

- Alerts must map to runbook references in `OPERATIONS_RUNBOOK.md`.
- Severity mapping aligned with `SRE_SLOS_AND_ALERTING.md`.

## 8) Data Retention

- High-resolution metrics: 30 days.
- Downsampled metrics: 12+ months.
- Logs: based on sensitivity tier and compliance policy.
- Traces: 7-30 days depending on volume and environment.

This document is the governing observability contract for LSOS.
