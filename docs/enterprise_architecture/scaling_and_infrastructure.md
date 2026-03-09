# SCALING_AND_INFRASTRUCTURE.md

## 1) Scope

Defines the LSOS production infrastructure and scaling strategy for 100+ concurrent campaigns. Covers horizontal scaling, worker autoscaling, database partitioning, read replicas, proxy rotation, rate limiting, campaign sharding, CDN usage, report/PDF scaling, and cost modeling.

## 2) Target Capacity

Planning baseline:
- Active campaigns: 100-300
- Daily rank collections: 50k-250k keyword-geo checks
- Weekly crawl volume: up to 2M page fetches across tenant mix
- Monthly reports: 100-300 generated PDF artifacts + email delivery
- Concurrent worker tasks: 1k+ during peak windows

SLO targets:
- API p95 latency: < 300 ms for core reads
- Job scheduling lag: < 2 minutes for high-priority queues
- Monthly report completion: 95% within 6 hours

## 3) Infrastructure Topology

```text
                    +---------------------------+
                    | Global DNS + TLS Edge     |
                    +-------------+-------------+
                                  |
                                  v
                      +-----------+-----------+
                      | Load Balancer / Ingress|
                      +-----+-------------+----+
                            |             |
                            v             v
                   +--------+---+     +---+--------+
                   | API Pods    |     | Next.js Pods|
                   +--------+---+     +---+--------+
                            |             |
                            +------+------+ 
                                   |
                                   v
                         +---------+----------+
                         | Redis (broker/cache)|
                         +----+------------+---+
                              |            |
                              v            v
                   +----------+--+    +---+----------------------+
                   | Celery Workers|    | PostgreSQL Primary      |
                   | (queue shards)|    | + Read Replicas         |
                   +----------+----+    +-----------+-------------+
                              |                     |
                              v                     v
                     +--------+---------+   +------+--------------+
                     | Proxy Rotation   |   | Object Storage      |
                     | Pool + Health    |   | reports/assets      |
                     +------------------+   +---------------------+
```

## 4) Horizontal Scaling Strategy

API tier:
- Stateless FastAPI replicas behind ingress.
- Scale out based on CPU, request rate, and p95 latency.
- Separate read-heavy and write-heavy route pools when needed.

Frontend tier:
- Stateless Next.js pods with CDN-backed static asset delivery.
- Horizontal scale by connection and render metrics.

Worker tier:
- Independent deployments per queue class.
- Scale each class by queue depth and runtime saturation.
- Isolate noisy workloads (SERP/crawl) from reporting/intelligence.

Scheduler tier:
- Single active beat leader with lock-based failover.
- Standby schedulers in passive mode for high availability.

## 5) Worker Autoscaling Model

Autoscaling signals:
- Queue lag time (oldest message age).
- Queue depth (absolute and per-campaign shard).
- Worker CPU/memory saturation.
- Task p95 duration drift.

Policy baseline:

```text
queue.serp:       min=3 max=20 replicas
queue.crawl:      min=2 max=12 replicas
queue.content:    min=1 max=8 replicas
queue.local:      min=1 max=8 replicas
queue.outreach:   min=1 max=6 replicas
queue.citation:   min=1 max=6 replicas
queue.reviews:    min=1 max=6 replicas
queue.intelligence:min=1 max=6 replicas
queue.reporting:  min=1 max=6 replicas
```

Safety controls:
- Cooldown windows on scale-in to avoid oscillation.
- Queue-specific max concurrency caps.
- Graceful shutdown with drain semantics.

## 6) Database Partitioning Strategy

Partition high-volume snapshot tables:
- `rankings` partition by month (`snapshot_date`).
- `competitor_rankings` partition by month.
- `crawl_page_results` partition by month or hash(campaign_id) when large tenants dominate.
- `reviews` partition by month for high-ingest tenants.

Indexing standards:
- Composite indexes start with `tenant_id`.
- Time-series tables index `(tenant_id, campaign_id, snapshot_date DESC)`.
- Covering indexes for reporting aggregate paths.

Maintenance:
- Automated partition creation 3 months ahead.
- Retention and archiving policy by table class.
- VACUUM/ANALYZE scheduled by load windows.

## 7) Read Replica Strategy

Replica usage:
- Reporting reads and dashboard aggregates route to replicas.
- Background analytical reads default to replicas unless strict recency required.

Consistency policy:
- Primary for writes and read-after-write critical endpoints.
- Replica lag monitoring with failback to primary for lag breaches.

Connection management:
- PgBouncer for connection pooling.
- Separate pools for API, workers, and reporting workloads.

## 8) Proxy Rotation Infrastructure

Proxy manager responsibilities:
- Maintain provider inventory and endpoint health scoring.
- Assign endpoint by geo affinity and campaign requirements.
- Track block rates, latency, and success ratio.
- Quarantine failing endpoints and reintroduce after cooldown.

Execution safeguards:
- Per-provider concurrency caps.
- Per-target-domain request pacing.
- Circuit breaker for elevated failure rates.
- Fallback route chains across providers.

## 9) Rate Limiting Model

Internal API limits:
- Tenant-level quotas for expensive endpoints.
- User-level burst and sustained limits.

External request limits:
- Domain-scoped token buckets.
- Provider-scoped throttle adaptation.
- Queue backpressure when thresholds are crossed.

Rate limit keys:
- `rate:tenant:{tenant_id}:api:{route}:{minute}`
- `rate:provider:{provider_id}:serp:{minute}`
- `rate:domain:{target_domain}:{minute}`

## 10) Campaign Sharding

Sharding objective:
- Spread campaign load deterministically across workers and schedule windows.

Shard function:
- `shard_id = hash(tenant_id, campaign_id) % N`

Scheduling rules:
- Emit recurring jobs by shard windows.
- Maintain per-shard lag dashboards.
- Rebalance shard counts as campaign volume grows.

## 11) CDN Strategy

Use CDN for:
- Frontend static assets.
- Report artifact distribution through signed URLs.
- Cached chart assets or pre-rendered visual bundles.

Policies:
- Immutable cache headers for versioned assets.
- Short-lived signed URLs for report access.
- Geo-distributed edge delivery for client-facing report downloads.

## 12) PDF Generation Scaling

Pipeline design:
- Dedicated reporting queue and worker pool.
- HTML template render separate from PDF conversion stage.
- Memory-bounded containers for browser-based PDF rendering.

Scaling tactics:
- Horizontal reporting worker scale during month-close windows.
- Prioritized queue for overdue reports.
- Artifact dedupe by `(campaign_id, period, template_version, hash)`.

Failure handling:
- Retry render on transient rendering failure.
- Dead-letter for persistent template or data integrity issues.

## 13) Cost Modeling

Primary cost drivers:
- SERP and crawl compute time.
- Proxy provider usage.
- Database storage and IO.
- PDF rendering bursts at month close.
- Email delivery volume for reports/outreach.

Control levers:
- Tiered crawl/rank frequencies by campaign plan.
- Adaptive sampling for low-volatility keywords.
- Reserved capacity for baseline workloads.
- Spot/preemptible worker pools for non-urgent tasks.
- Data retention/archival policy for historical snapshots.

Budget telemetry:
- Cost per campaign per month.
- Cost per keyword snapshot.
- Cost per crawl page.
- Cost per generated report.

## 14) High Availability and Recovery

Availability controls:
- Multi-AZ API and worker deployment.
- Redis with persistence and failover strategy.
- Postgres primary/replica with PITR backups.
- Object storage durability guarantees.

Recovery targets:
- RPO <= 15 minutes.
- RTO <= 4 hours.

Drills:
- Quarterly failover rehearsal.
- Backup restore verification.
- Queue recovery and replay validation.

## 15) Scaling Readiness Checklist

- Queue lag stable under projected peak.
- Replica lag within operational bounds.
- Partition creation and pruning automated.
- Proxy failure rates below threshold.
- Report generation SLO met at month-close load.
- Per-campaign cost trend within model bounds.

This document is the governing infrastructure and scaling contract for LSOS operations.
