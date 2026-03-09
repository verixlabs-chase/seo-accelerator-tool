# ARCHITECTURE.md

## 1) System Mission

TopDog Local SEO Operating System (LSOS) is a production-grade, multi-tenant platform that executes a repeatable 12-month local SEO program across 100+ concurrent campaigns. The system automates technical SEO, geo-rank tracking, competitor intelligence, content operations, internal linking, local SEO health, citation growth, authority outreach, review velocity monitoring, strategic recommendations, and white-label reporting.

Primary design goals:
- Predictable campaign execution at monthly cadence.
- Safe tenant isolation across data, API access, workers, and reports.
- Horizontally scalable ingestion/scraping and async processing.
- Observable workflows with deterministic retries and auditability.
- Modular service boundaries with versioned contracts.

## 2) Architecture Principles

- Multi-tenant by design: every domain record and job is tenant-scoped.
- Async-first: all heavy SEO workflows run through Celery task clusters.
- Idempotent processing: scheduled tasks can re-run without data corruption.
- Contract-driven interfaces: API schemas and task payload schemas are explicit and versioned.
- Storage separation: OLTP in PostgreSQL, transient state/cache in Redis, artifacts in object storage.
- Isolation by queue: scraper-heavy tasks separated from CPU-bound analytics.
- Deterministic campaign orchestration: month-stage workflow engine drives operations.

## 3) High-Level System Topology

```text
                          +--------------------------+
                          |    External Providers    |
                          |--------------------------|
                          | Google SERP/Maps         |
                          | Search Console/Analytics |
                          | GBP APIs (where used)    |
                          | Email SMTP provider      |
                          | Proxy Providers          |
                          +------------+-------------+
                                       |
                                       v
+------------------+        +----------+----------+        +-------------------+
|  Next.js Frontend| <----> | FastAPI API Gateway | <----> | Auth/RBAC Service |
|  (Tenant Portal) |  HTTPS |  /api/v1            |        | JWT + Permissions |
+------------------+        +----------+----------+        +-------------------+
                                       |
             +-------------------------+--------------------------+
             |                         |                          |
             v                         v                          v
  +---------------------+   +-----------------------+   +----------------------+
  | Domain Service Layer|   | Workflow Orchestrator |   | Reporting Composer   |
  | (11 LSOS Modules)   |   | (Campaign Logic)      |   | (HTML/PDF/Email)     |
  +----------+----------+   +-----------+-----------+   +----------+-----------+
             |                          |                          |
             +---------------+----------+--------------------------+
                             |
                             v
                   +---------+---------+
                   |   Celery Broker   |
                   |      Redis        |
                   +----+----+----+----+
                        |    |    |
                        v    v    v
                   +----+----+----+-------------------------------+
                   | Worker Clusters (queue-isolated)             |
                   | crawl | serp | content | local | outreach    |
                   | citation | reviews | intelligence | reporting |
                   +----+----+----+-------------------------------+
                        |    |    |
                        +----+----+-------------------------------+
                             |
                             v
             +---------------+-------------------+----------------+
             |                                   |                |
             v                                   v                v
   +---------------------+             +----------------+  +---------------+
   | PostgreSQL 16+      |             | Redis Cache    |  | Object Storage|
   | tenant data + audit |             | locks, rate,   |  | reports/media |
   | partitioned tables  |             | broker backend |  | exports       |
   +---------------------+             +----------------+  +---------------+
```

## 4) Service Separation Model

LSOS uses a modular backend with clear domain boundaries. It can run as a modular monolith initially and split into microservices as load increases.

Domain modules:
1. Crawl & Technical SEO Engine
2. Rank Tracking Engine
3. Competitor Intelligence Engine
4. Content Automation Engine
5. Internal Linking Intelligence Engine
6. Local SEO Engine
7. Authority & Outreach Engine
8. Citation Engine
9. Review Monitoring Engine
10. Campaign Intelligence Engine
11. Reporting Engine
12. Reference Library Loader Foundation

Boundary rules:
- Each module owns its task definitions and business logic.
- Shared data access only via repository layer and typed models.
- Cross-module writes must be event/task-driven, not direct tight coupling.
- Module contracts are versioned (`v1`) for API and worker payloads.

## 5) Backend Architecture (FastAPI + Celery + PostgreSQL)

### 5.1 Core Backend Components

- API Gateway Layer:
  - FastAPI routers under `/api/v1`.
  - Request validation (Pydantic v2).
  - JWT auth, RBAC, tenant resolution middleware.
  - Idempotency key support for write endpoints that schedule tasks.

- Application Layer:
  - Use-case services per module.
  - Campaign orchestration service (month-stage scheduler).
  - Strategy scoring engine.

- Async Processing Layer:
  - Celery workers per queue family.
  - Retry policies with exponential backoff + dead-letter queue.
  - Task deduplication and tenant-scoped locks.

- Persistence Layer:
  - PostgreSQL for authoritative state.
  - Redis for broker, result backend, cache, lock, rate counters.
  - Object storage for report PDFs and large generated assets.

### 5.2 API Service Decomposition

```text
api/
  auth/
  campaigns/
  crawl/
  ranking/
  competitors/
  content/
  internal_links/
  local_seo/
  authority_outreach/
  citations/
  reviews/
  intelligence/
  reporting/
```

### 5.3 Task Payload Contract (Canonical)

```json
{
  "schema_version": "v1",
  "task_id": "uuid",
  "tenant_id": "uuid",
  "campaign_id": "uuid",
  "module": "rank_tracking",
  "action": "fetch_serp_batch",
  "scheduled_for": "2026-02-16T15:00:00Z",
  "attempt": 1,
  "correlation_id": "uuid",
  "payload": {}
}
```

### 5.4 Idempotency and Consistency

- Every ingestion result table stores source fingerprint/hash.
- Upserts keyed by `(tenant_id, campaign_id, natural_key, snapshot_date)`.
- Task execution guard:
  - Redis distributed lock: `lock:{tenant_id}:{campaign_id}:{job_type}`.
  - DB job execution table with unique `(task_name, schedule_window, campaign_id)`.

## 6) Frontend Architecture (Next.js 14+)

- Framework:
  - Next.js App Router, React Query for API state, TailwindCSS UI system.

- Frontend domains:
  - Campaign workspace dashboard.
  - Technical SEO diagnostics.
  - Rank and competitor visibility analytics.
  - Content pipeline and approval queue.
  - Citation/outreach/reviews operations console.
  - White-label report preview and delivery controls.

- Auth model:
  - JWT-based session handling with refresh flow.
  - Tenant-aware route guards and role-based UI feature gating.

- Data flow:
  - Client requests -> `/api/v1` -> async task scheduling -> status polling/websocket updates -> UI reconciliation.

## 7) Multi-Tenant Isolation Model

Tenant isolation is mandatory across read/write paths.

Isolation controls:
- All tables include `tenant_id` (not nullable).
- Composite indexes begin with `tenant_id`.
- API middleware injects tenant context from JWT and blocks cross-tenant IDs.
- Optional PostgreSQL Row-Level Security (RLS) policies:
  - `USING (tenant_id = current_setting('app.tenant_id')::uuid)`.
- Worker payloads require tenant_id and validate campaign ownership before execution.
- Report generation must resolve branding and data only from tenant scope.

## 8) Data Flow Architecture

### 8.1 Crawl + Audit Flow

```text
Scheduler -> enqueue crawl job -> crawl worker (Playwright/BS4/lxml)
         -> parse technical signals -> persist CrawlRuns/Page snapshots
         -> compute issue severity -> update StrategyRecommendations
         -> emit campaign intelligence event
```

### 8.2 Geo Rank Flow

```text
Rank schedule -> serp queue batches by geo grid/keyword
             -> proxy pool allocation
             -> scrape + normalize
             -> store Rankings + CompetitorRankings snapshots
             -> compute deltas/trends
```

### 8.3 Content + Internal Links Flow

```text
Roadmap trigger -> topic/cluster selection
               -> content draft generation pipeline
               -> QA + approval state
               -> publish metadata ingest
               -> internal link map refresh + recommendation output
```

### 8.4 Reporting Flow

```text
Monthly close window
  -> aggregate module KPIs
  -> strategy recommendation synthesis
  -> render HTML template (tenant branding)
  -> PDF generation
  -> store artifact + email dispatch
```

## 9) Campaign Lifecycle and Automation States

Campaign lifecycle state machine:

```text
[created]
   |
   v
[onboarding] -> baseline crawl/rank setup/competitor baseline
   |
   v
[active_month_n] (n=1..12)
   |  recurring monthly jobs + quality checks
   v
[review_pending] -> monthly report generation + approval
   |
   v
[active_month_n+1] ... until month 12
   |
   v
[completed] or [paused] or [archived]
```

Automation orchestrator rules:
- Month 1: full audit setup, tracking setup, outreach foundation, technical remediation plan.
- Month 2: on-page tuning, GBP optimization, authority placement kickoff.
- Month 3: citation stack buildout, location template rollout, first health check.
- Months 4-12: recurring production cadence, health checks, strategy checkpoints, monthly report.

## 10) Dockerized Deployment Layout

### 10.1 Container Topology

```text
docker-compose / orchestrated cluster

edge:
  - reverse-proxy (nginx/traefik)

app:
  - api (FastAPI, uvicorn/gunicorn)
  - scheduler (Celery beat)

workers:
  - worker-crawl
  - worker-serp
  - worker-content
  - worker-local
  - worker-outreach
  - worker-citation
  - worker-reviews
  - worker-intelligence
  - worker-reporting

data:
  - postgres-primary
  - postgres-replica (optional in compose, required in production)
  - redis
  - object-storage (S3-compatible endpoint external or containerized for local)

monitoring:
  - flower
  - prometheus
  - grafana
  - loki/vector (optional log pipeline)
```

### 10.2 Environment Separation

- Local: docker-compose single-node stack with reduced concurrency.
- Staging: production-like topology with smaller worker replicas.
- Production: orchestrated deployment with autoscaling, separate DB/Redis tiers, managed object storage.

## 11) Celery Worker Model

Queue-separated worker pools:

```text
queue.crawl          -> IO-heavy, browser automation
queue.serp           -> high-volume network scraping + proxy rotation
queue.content        -> CPU+IO mixed (NLP, templating)
queue.local          -> local profile checks and sync jobs
queue.outreach       -> CRM automation + email sequencing
queue.citation       -> directory submission/status monitoring
queue.reviews        -> ingestion + velocity computation
queue.intelligence   -> scoring, anomaly detection, recommendations
queue.reporting      -> aggregation, chart prep, PDF rendering, email send
queue.default        -> light general tasks
queue.deadletter     -> exhausted retries for triage
```

Concurrency model baseline for 100+ campaigns:
- `crawl`: 8-16 concurrency per worker pod, bounded browser sessions.
- `serp`: 20-60 concurrency per worker pod with strict proxy/circuit limits.
- `content/intelligence`: 4-12 concurrency (CPU-aware).
- `reporting`: 2-6 concurrency (PDF generation memory-bound).

Reliability model:
- Retry: exponential backoff with jitter.
- Max retries vary by queue (serp/crawl higher than reporting).
- Timeouts per task type; stuck tasks moved to dead-letter.
- Circuit breakers for failing proxy/provider segments.

## 12) Redis Role Definition

Redis serves four roles:
- Celery broker/result backend.
- Hot cache for dashboard aggregates and recent campaign KPIs.
- Distributed lock manager for idempotent scheduled jobs.
- Rate limiting counters for API and external request pacing.

Key patterns:
- `cache:{tenant_id}:{campaign_id}:{metric}:{window}`
- `lock:{tenant_id}:{campaign_id}:{job_type}`
- `rate:{tenant_id}:{service}:{minute_bucket}`
- `taskstate:{task_id}`

## 13) Reporting Pipeline Architecture

Reporting is deterministic and replayable.

Pipeline stages:
1. Snapshot freeze for reporting window.
2. KPI aggregation across rankings, crawl health, backlinks, citations, reviews, content velocity.
3. Strategy recommendation generation from scoring rules.
4. Tenant branding injection (logo, colors, agency identity).
5. HTML render -> PDF export.
6. Artifact storage + signed access URL.
7. Email scheduling and delivery tracking.

Report contract:
- Input: `tenant_id`, `campaign_id`, `period_start`, `period_end`, `template_version`.
- Output: `report_id`, `artifact_url`, `kpi_summary`, `generated_at`, `delivery_status`.

## 14) Scaling Model (Production)

### 14.1 Horizontal Scaling

- API layer: stateless replicas behind load balancer.
- Workers: independent autoscaling by queue lag and runtime saturation.
- Scheduler: single active leader with failover lock in Redis.

### 14.2 Database Scaling

- PostgreSQL primary + read replicas.
- Partition high-volume snapshot tables by month or campaign hash.
- Use materialized views for heavy report queries.
- Connection pooling via PgBouncer.

### 14.3 Campaign Sharding Strategy

- Assign campaign shards to worker groups for predictable throughput.
- Shard key: `hash(tenant_id, campaign_id) % N`.
- Scheduler emits tasks in shard windows to avoid thundering herd.

### 14.4 Proxy Rotation Infrastructure

- Dedicated proxy manager service/module.
- Per-provider health score, geo affinity, cooldown windows.
- Automatic failover and quarantine for high-failure proxy nodes.

## 15) Observability and Operations

Metrics:
- Queue depth, task latency, task success/failure rates.
- Crawl/rank ingestion freshness by campaign.
- API p95 latency and error rate.
- Report generation duration and delivery success.
- Proxy health and block-rate trends.

Logging and tracing:
- Structured JSON logs with `tenant_id`, `campaign_id`, `correlation_id`.
- Distributed tracing for API -> task -> DB flow.
- Audit logs for privileged operations and report delivery actions.

Alerting:
- Queue backlog threshold breach.
- Repeated dead-letter growth.
- Stale campaign (>48h missing core snapshots).
- Elevated auth failures or cross-tenant access denials.

## 16) Non-Functional Requirements

- Availability target: 99.9% for core API and scheduling operations.
- Data durability: PITR-capable backups for PostgreSQL.
- Throughput target: support 100+ active campaigns with monthly cadence and daily tracking jobs.
- Recovery target:
  - RPO <= 15 minutes.
  - RTO <= 4 hours for major service failure.

## 17) Implementation Directives for Next Documents

This architecture mandates:
- Tenant-scoped schema with partition strategy (`DATABASE_SCHEMA.md`).
- Module-owned service contracts and task definitions (`SERVICE_MODULES.md`).
- Explicit endpoint contracts and background bindings (`API_SPECIFICATION.md`).
- Queue topology, retries, chaining, schedules (`BACKGROUND_TASK_PIPELINE.md`).
- Security controls integrated at API, worker, data layers (`SECURITY_SPEC.md`).
- White-label report rendering and delivery contract (`WHITE_LABEL_REPORTING_SPEC.md`).
- Reliability targets and alert policy (`SRE_SLOS_AND_ALERTING.md`).
- Incident and queue triage procedures (`OPERATIONS_RUNBOOK.md`).
- Config/secret governance (`ENVIRONMENT_AND_CONFIG_SPEC.md`).
- Migration and retention governance (`MIGRATION_AND_DATA_GOVERNANCE.md`).
- Telemetry/logging/tracing standards (`OBSERVABILITY_SPEC.md`).
- Release controls and rollback policy (`RELEASE_AND_CHANGE_MANAGEMENT.md`).
- Verification strategy and quality gates (`TEST_STRATEGY.md`).

This file is the governing implementation architecture baseline for LSOS.
