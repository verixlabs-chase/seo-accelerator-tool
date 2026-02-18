# OBSERVABILITY_AND_SLOS.md
Generated: 2026-02-18T17:29:02.381145

## INTENT
Define reliability targets and alerting thresholds.

---

## SLO TARGETS
API Availability: 99.5%
Worker Success Rate: 98%
Queue Latency: < 60s
Crawl Success: 95%

---

## ALERTS
Queue lag > 5m
DB CPU > 80%
Crawl failure spike > 10%

---

## CODED THRESHOLDS
- `queue_lag_minutes`: 5
- `db_cpu_percent`: 80
- `crawl_failure_spike_percent`: 10

Implemented in backend alert threshold constants and surfaced through `/api/v1/health/metrics`.
