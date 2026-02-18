# BACKGROUND_TASK_PIPELINE.md

## 1) Scope

Defines the production Celery execution model for LSOS: worker clusters, queue separation, retries, task chaining, recurring schedules, batching strategies, concurrency policy, and monitoring for 100+ concurrent campaigns in a multi-tenant environment.

## 2) Runtime Stack

- Queue engine: Celery 5.x
- Broker: Redis 7.x
- Result backend: Redis 7.x
- Scheduler: Celery Beat (single active leader)
- Worker runtime: Python 3.11+
- Browser tasks: Playwright workers with bounded session pools

## 3) Queue Topology

```text
                     +------------------------+
                     | Celery Beat Scheduler  |
                     +-----------+------------+
                                 |
                                 v
                     +-----------+------------+
                     |      Redis Broker      |
                     +-----+---+---+---+------+
                           |   |   |   |
      +--------------------+   |   |   +------------------------+
      |                        |   |                            |
      v                        v   v                            v
 queue.crawl              queue.serp queue.content         queue.reporting
 queue.local              queue.reviews                    queue.intelligence
 queue.outreach           queue.citation                   queue.default
 queue.reference
                                |
                                v
                          queue.deadletter
```

Queue intent:
- `queue.crawl`: crawl orchestration, technical parsing, page-level extraction.
- `queue.serp`: keyword-geo rank scraping, competitor capture.
- `queue.content`: clustering, generation prep, QA transforms, internal-link suggestions.
- `queue.local`: GBP/local profile checks, map-pack snapshots, NAP consistency checks.
- `queue.outreach`: contact discovery enrichment, outreach sequencing, follow-up timers.
- `queue.citation`: citation submissions, status checks, retries for directory workflows.
- `queue.reviews`: review ingestion, sentiment tagging, velocity snapshot generation.
- `queue.intelligence`: strategy scoring, anomaly detection, recommendations.
- `queue.reporting`: monthly report assemble/render/export/delivery.
- `queue.default`: lightweight maintenance and low-latency tasks.
- `queue.reference`: reference library validation, activation, reload, and rollback flows.
- `queue.deadletter`: terminal failure sink for operator triage.

## 4) Worker Cluster Model

```text
worker-crawl        listens: queue.crawl
worker-serp         listens: queue.serp
worker-content      listens: queue.content
worker-local        listens: queue.local
worker-outreach     listens: queue.outreach
worker-citation     listens: queue.citation
worker-reviews      listens: queue.reviews
worker-intelligence listens: queue.intelligence
worker-reporting    listens: queue.reporting
worker-reference    listens: queue.reference
worker-default      listens: queue.default
```

Cluster policy:
- One deployment per queue family to isolate failures and tune concurrency independently.
- Each worker deployment horizontally scales from queue lag and p95 runtime.
- Workers enforce tenant-scoped locks before campaign-mutating operations.

## 5) Task Envelope Contract

Every task payload must include:

```json
{
  "schema_version": "v1",
  "tenant_id": "uuid",
  "campaign_id": "uuid",
  "correlation_id": "uuid",
  "idempotency_key": "string",
  "scheduled_window_start": "ISO-8601",
  "scheduled_window_end": "ISO-8601",
  "payload": {}
}
```

Validation requirements:
- Reject if `tenant_id` or `campaign_id` missing.
- Reject if campaign does not belong to tenant.
- Reject stale schema versions.
- Enforce idempotency via lock and execution ledger.

## 6) Retry and Failure Policy

Retry classes:
- `network_transient`: retries with exponential backoff and jitter.
- `provider_throttle`: retries with dynamic cooldown and reduced concurrency.
- `validation_error`: no retry, immediate failure.
- `parser_error`: limited retries, then dead-letter.
- `dependency_unavailable`: retries with capped exponential backoff.

Default retry matrix:

```text
queue.crawl       max_retries=5  backoff=30s base  max=20m
queue.serp        max_retries=7  backoff=20s base  max=15m
queue.content     max_retries=4  backoff=45s base  max=25m
queue.local       max_retries=5  backoff=30s base  max=20m
queue.outreach    max_retries=6  backoff=60s base  max=30m
queue.citation    max_retries=6  backoff=60s base  max=30m
queue.reviews     max_retries=5  backoff=30s base  max=20m
queue.intelligence max_retries=3 backoff=60s base  max=20m
queue.reporting   max_retries=3  backoff=120s base max=30m
queue.reference   max_retries=3  backoff=60s base  max=20m
```

Dead-letter conditions:
- Exhausted retries.
- Hard validation or auth failure.
- Task exceeds hard timeout twice in same scheduling window.

Dead-letter handling:
- Persist failure metadata with stack trace, provider state, tenant/campaign context.
- Open triage item in operations queue.
- Optional replay endpoint with fixed payload and new correlation_id.

## 7) Task Chaining and Orchestration

Orchestration primitives:
- `chain`: strict ordered flow.
- `group`: parallel fan-out per keyword/geo/page batches.
- `chord`: fan-out + aggregation callback.

Canonical chains:

1. Crawl Pipeline
```text
schedule_crawl
 -> crawl_fetch_pages
 -> crawl_parse_technical
 -> crawl_extract_issues
 -> intelligence_update_tech_score
 -> emit_campaign_event("crawl_completed")
```

2. Rank Pipeline
```text
schedule_rank_window
 -> group(fetch_serp_batch[k,geo])
 -> chord_callback(normalize_rank_snapshots)
 -> competitor_merge
 -> intelligence_update_rank_score
```

3. Reporting Pipeline
```text
freeze_reporting_window
 -> aggregate_kpis
 -> generate_recommendations
 -> render_html
 -> render_pdf
 -> store_artifact
 -> send_report_email
```

4. Reference Library Pipeline
```text
reference_library.validate_artifact
 -> reference_library.activate_version
 -> reference_library.reload_cache
 -> emit_campaign_event("reference_library_updated")
```

## 8) Scheduled Jobs

Scheduler responsibilities:
- Emit campaign jobs by timezone-aware windows.
- Prevent duplicate emissions by unique `(job_type, campaign_id, window)`.
- Spread start times with shard jitter to avoid thundering herd.

Recurring schedule baseline:
- Crawl health checks: weekly per campaign; monthly deep crawl.
- Rank collection: daily core keywords; weekly extended keyword set.
- Competitor snapshots: weekly.
- Citation status checks: weekly.
- Review ingestion: daily.
- Intelligence scoring: nightly and after major pipeline completion.
- Monthly reporting: first business day + on-demand rerun.

## 9) SERP Scraping Batching

Batch model:
- Partition by `(campaign_id, location_grid, keyword_cluster)`.
- Max keywords per task: 25.
- Max geos per task: 10.
- Task runtime target: <= 180 seconds.

Proxy-aware execution:
- Assign provider + endpoint per batch.
- Apply geo affinity to endpoint selection.
- Circuit-breaker trips on repeated status failures.
- Quarantine failed endpoints for cooldown window.

## 10) Crawl Scheduling Model

Crawl windows:
- `deep_crawl_monthly`: full site scan up to campaign cap.
- `delta_crawl_weekly`: changed/new pages and critical templates.
- `hotfix_crawl_on_demand`: targeted URL list from user or event.

Resource controls:
- Global max concurrent browser sessions.
- Per-tenant crawl token bucket.
- Robots directives respected unless explicit override policy set.

## 11) Rank Scheduling Model

Rank job frequencies:
- Core terms: daily collection.
- Secondary terms: every 3 days.
- Long-tail terms: weekly.
- Triggered rerun: after significant on-page deployment events.

Geo strategy:
- Primary city centroid + predefined grid points.
- Optional zip/postal overlays for local visibility analysis.

## 12) Monthly Recurring Jobs

Month-end pipeline:
1. Freeze data window.
2. Validate required snapshots exist.
3. Backfill missing data if gap is recoverable.
4. Compute KPI deltas and confidence.
5. Generate strategy recommendations.
6. Render and deliver white-label report.
7. Mark campaign month checkpoint complete.

SLA targets:
- 95% of campaign monthly reports generated within 6 hours of schedule.
- 99% within 24 hours.

## 13) Concurrency and Capacity Baseline

Initial baseline for 100+ active campaigns:

```text
worker-crawl:        replicas=3  concurrency=10  prefetch=1
worker-serp:         replicas=5  concurrency=40  prefetch=4
worker-content:      replicas=2  concurrency=8   prefetch=2
worker-local:        replicas=2  concurrency=12  prefetch=2
worker-outreach:     replicas=2  concurrency=10  prefetch=2
worker-citation:     replicas=2  concurrency=10  prefetch=2
worker-reviews:      replicas=2  concurrency=12  prefetch=2
worker-intelligence: replicas=2  concurrency=6   prefetch=1
worker-reporting:    replicas=2  concurrency=4   prefetch=1
worker-reference:    replicas=1  concurrency=2   prefetch=1
```

Autoscaling triggers:
- Queue lag > threshold for 5 minutes.
- Worker CPU > 75% sustained.
- Task p95 runtime exceeds SLO.

## 14) Monitoring and Alerting

Required metrics:
- Queue depth by queue.
- Task success/failure/retry rates.
- Task runtime p50/p95/p99.
- Dead-letter growth rate.
- Scheduling lag and missed windows.
- Provider/proxy failure rates.

Required alerts:
- Any queue lag > 15 minutes.
- Dead-letter volume spike > 3x baseline.
- Report generation failure ratio > 5% in a 1-hour window.
- Missing daily rank snapshots for any active campaign > 24 hours.

Operational views:
- Flower for live Celery state.
- Prometheus + Grafana dashboards for KPIs.
- Structured log search keyed by `correlation_id`, `tenant_id`, `campaign_id`.

## 15) Operational Safeguards

- Idempotent task handlers required for all scheduled tasks.
- Hard timeout per queue family to prevent hung workers.
- Graceful worker shutdown drains running tasks.
- Versioned task names to support rolling upgrades.
- Backward-compatible payload parsing for one previous schema version.
- Alert thresholds and paging are governed by `SRE_SLOS_AND_ALERTING.md`.
- Triage and replay procedures are governed by `OPERATIONS_RUNBOOK.md`.

This document is the governing execution pipeline contract for all background automation in LSOS.
