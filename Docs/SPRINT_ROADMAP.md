# SPRINT_ROADMAP.md

## 1) Delivery Framework

This roadmap defines 9 implementation sprints for LSOS. Each sprint includes objective, deliverables, acceptance criteria, database changes, API additions, Celery tasks, and testing requirements. All increments are production-oriented and multi-tenant safe.

Cadence assumptions:
- Sprint length: 2 weeks
- Environments: local -> staging -> production
- Release model: trunk-based with feature flags for incomplete modules

## 2) Sprint 1: Project Scaffold

Objective:
- Establish production-ready foundation for API, async workers, tenant isolation, auth, observability, and deployment.

Deliverables:
- FastAPI service scaffold with `/api/v1` routing.
- Next.js frontend shell with tenant-aware auth flow.
- PostgreSQL + Redis + Celery integration.
- Base Docker Compose stack and environment config strategy.
- Logging, metrics, health checks, and CI pipeline.

Acceptance criteria:
- Users can authenticate and access only their tenant context.
- API, scheduler, and worker containers boot cleanly in local/staging.
- Structured logs include correlation and tenant metadata.
- CI runs lint/tests/build and blocks failing merges.

Database changes:
- Create foundational tables: tenants, users, roles, user_roles, campaigns, audit_logs, task_executions.

API endpoints added:
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `POST /api/v1/campaigns`
- `GET /api/v1/campaigns`

Tasks added:
- `ops.healthcheck.snapshot`
- `campaigns.bootstrap_month_plan`
- `audit.write_event`

Testing checklist:
- Auth token issuance and refresh.
- Cross-tenant access denial tests.
- Container startup integration test.
- DB migration rollback/forward validation.

## 3) Sprint 2: Crawl Engine

Objective:
- Build technical crawl and issue extraction pipeline.

Deliverables:
- URL queueing and crawl scheduler.
- Playwright crawler with robots and rate controls.
- Technical parser pipeline (status/indexability/canonicals/meta/headings/internal links).
- Technical issue taxonomy and severity scoring.

Acceptance criteria:
- Deep and delta crawls execute with tenant-safe writes.
- Crawl results persist with snapshot timestamps.
- Technical issue dashboard returns top issues per campaign.

Database changes:
- Add tables: pages, crawl_runs, crawl_page_results, technical_issues.
- Add indexes on `(tenant_id, campaign_id, crawled_at)`.

API endpoints added:
- `POST /api/v1/crawl/schedule`
- `GET /api/v1/crawl/runs`
- `GET /api/v1/crawl/issues`

Tasks added:
- `crawl.schedule_campaign`
- `crawl.fetch_batch`
- `crawl.parse_page`
- `crawl.extract_issues`
- `crawl.finalize_run`

Testing checklist:
- Crawl respects per-tenant rate caps.
- Parser regression suite for HTML fixtures.
- Retry/dead-letter behavior for network failures.
- Performance test for 10k-page campaign cap.

## 4) Sprint 3: Rank Tracking Engine

Objective:
- Deliver geo-specific rank collection and trend reporting.

Deliverables:
- Keyword and location grid management.
- SERP scraping pipeline with proxy rotation.
- Rank normalization and daily snapshots.
- Delta calculations and movement alerts.

Acceptance criteria:
- Daily core keyword collection works at campaign scale.
- Rank snapshots include geo context and confidence metadata.
- Dashboard exposes movement by keyword cluster and location.

Database changes:
- Add tables: keyword_clusters, campaign_keywords, rankings, ranking_snapshots.
- Partition ranking snapshots by month.

API endpoints added:
- `POST /api/v1/rank/keywords`
- `POST /api/v1/rank/schedule`
- `GET /api/v1/rank/snapshots`
- `GET /api/v1/rank/trends`

Tasks added:
- `rank.schedule_window`
- `rank.fetch_serp_batch`
- `rank.normalize_snapshot`
- `rank.compute_deltas`

Testing checklist:
- Proxy failover and cooldown behavior.
- Rank deduplication and idempotency.
- Geolocation batching correctness.
- p95 collection runtime under SLO in staging load test.

## 5) Sprint 4: Competitor Engine

Objective:
- Build competitor discovery, tracking, and comparative intelligence.

Deliverables:
- Competitor list management by campaign and keyword cluster.
- Snapshot capture for competitor positions, pages, and visibility indicators.
- Comparative scorecards and gaps.

Acceptance criteria:
- Competitor data updates weekly without cross-tenant leakage.
- Users can compare top competitor movements over time.
- Recommendations include competitor gap signals.

Database changes:
- Add tables: competitors, competitor_rankings, competitor_pages, competitor_signals.

API endpoints added:
- `POST /api/v1/competitors`
- `GET /api/v1/competitors`
- `GET /api/v1/competitors/snapshots`
- `GET /api/v1/competitors/gaps`

Tasks added:
- `competitor.refresh_baseline`
- `competitor.collect_snapshot`
- `competitor.compute_gap_scores`

Testing checklist:
- Snapshot alignment with ranking windows.
- Competitor merge and dedupe logic.
- Historical comparison query performance.

## 6) Sprint 5: Content Engine

Objective:
- Build content planning, production tracking, and internal linking intelligence.

Deliverables:
- Topic and keyword cluster planner.
- Content asset lifecycle (planned -> draft -> approved -> published).
- Internal link map generation and recommendation engine.

Acceptance criteria:
- Teams can create monthly content plans tied to clusters.
- Internal linking recommendations are generated after publish updates.
- Content production metrics feed reporting aggregates.

Database changes:
- Add tables: content_assets, editorial_calendar, internal_link_map, content_qc_events.

API endpoints added:
- `POST /api/v1/content/assets`
- `PATCH /api/v1/content/assets/{id}`
- `GET /api/v1/content/plan`
- `GET /api/v1/internal-links/recommendations`

Tasks added:
- `content.generate_plan`
- `content.run_qc_checks`
- `content.refresh_internal_link_map`

Testing checklist:
- State transition validation for content lifecycle.
- Link recommendation precision on fixture sites.
- Throughput test for monthly plan generation across 100 campaigns.

## 7) Sprint 6: Local Engine

Objective:
- Implement local SEO monitoring: GBP/local presence/review ingestion hooks.

Deliverables:
- Local profile health checks.
- NAP consistency checks and local pack visibility data integration.
- Review ingestion pipeline and velocity snapshots.

Acceptance criteria:
- Local health scores compute nightly.
- Review velocity trends are visible per campaign.
- Local data contributes to strategy recommendations.

Database changes:
- Add tables: local_profiles, local_health_snapshots, reviews, review_velocity_snapshots.

API endpoints added:
- `GET /api/v1/local/health`
- `GET /api/v1/local/map-pack`
- `GET /api/v1/reviews`
- `GET /api/v1/reviews/velocity`

Tasks added:
- `local.collect_profile_snapshot`
- `local.compute_health_score`
- `reviews.ingest`
- `reviews.compute_velocity`

Testing checklist:
- Review deduplication and sentiment parsing validity.
- Local health score reproducibility.
- Missing-provider graceful degradation tests.

## 8) Sprint 7: Authority & Citation

Objective:
- Deliver outreach CRM automation, backlink tracking, and citation workflows.

Deliverables:
- Outreach campaign and contact sequence management.
- Backlink acquisition tracking and quality metadata.
- Citation stack workflows with submission/status checks.

Acceptance criteria:
- Outreach lifecycle can be executed end-to-end.
- Backlink and citation states are visible and reportable.
- Month-3 citation stack target workflows are automatable.

Database changes:
- Add tables: outreach_campaigns, outreach_contacts, backlink_opportunities, backlinks, citations.

API endpoints added:
- `POST /api/v1/authority/outreach-campaigns`
- `POST /api/v1/authority/contacts`
- `GET /api/v1/authority/backlinks`
- `POST /api/v1/citations/submissions`
- `GET /api/v1/citations/status`

Tasks added:
- `outreach.enrich_contacts`
- `outreach.execute_sequence_step`
- `authority.sync_backlinks`
- `citation.submit_batch`
- `citation.refresh_status`

Testing checklist:
- Sequence scheduling and retry behavior.
- Citation status transition integrity.
- Backlink snapshot conflict resolution.

## 9) Sprint 8: Campaign Intelligence

Objective:
- Implement strategy scoring, anomaly detection, and recommendation engine.

Deliverables:
- Composite campaign health scoring model.
- Month-stage automation triggers aligned to 12-month logic.
- Recommendation records with rationale and confidence.

Acceptance criteria:
- Score computation is deterministic for same input snapshot.
- Rules engine schedules monthly actions according to campaign month.
- Recommendations exposed via API and consumed by reporting.

Database changes:
- Add tables: strategy_recommendations, intelligence_scores, campaign_milestones, anomaly_events.

API endpoints added:
- `GET /api/v1/intelligence/score`
- `GET /api/v1/intelligence/recommendations`
- `POST /api/v1/campaigns/{id}/advance-month`

Tasks added:
- `intelligence.compute_score`
- `intelligence.detect_anomalies`
- `campaigns.evaluate_monthly_rules`
- `campaigns.schedule_monthly_actions`

Testing checklist:
- Rule engine unit suite by month (1-12).
- Recommendation generation consistency tests.
- Snapshot gap handling and fallback logic.

## 10) Sprint 9: Reporting Engine

Objective:
- Deliver white-label monthly reporting with artifact export and scheduled delivery.

Deliverables:
- KPI aggregation across all modules.
- Brandable template renderer (HTML).
- PDF generator and report artifact storage.
- Scheduled email delivery and status tracking.

Acceptance criteria:
- Monthly report generation succeeds for complete campaign snapshots.
- PDF rendering supports tenant branding.
- Report endpoints provide summary and downloadable artifacts.

Database changes:
- Add tables: monthly_reports, report_artifacts, report_delivery_events, report_template_versions.

API endpoints added:
- `POST /api/v1/reports/generate`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{id}`
- `POST /api/v1/reports/{id}/deliver`

Tasks added:
- `reporting.freeze_window`
- `reporting.aggregate_kpis`
- `reporting.render_html`
- `reporting.render_pdf`
- `reporting.send_email`

Testing checklist:
- Report correctness on seeded historical dataset.
- PDF rendering stress test at concurrent load.
- Delivery retry and bounce handling tests.

## 11) Cross-Sprint Quality Gates

- Security: auth/RBAC/tenant isolation regression in every sprint.
- Reliability: no unbounded retries; dead-letter monitored.
- Performance: each sprint defines queue/runtime SLOs for new pipelines.
- Observability: new endpoints/tasks include metrics and structured logs.
- Data: every schema change includes migration, rollback plan, and index review.

## 12) Definition of Done (Global)

A sprint is complete only if:
- Production code merged with tests passing.
- Migrations applied in staging with rollback verified.
- Runbooks updated for new services/tasks.
- API contracts published and backward compatibility validated.
- Monitoring dashboards and alerts updated for shipped components.

Governance artifacts required before production go-live:
- `OPERATIONS_RUNBOOK.md`
- `SRE_SLOS_AND_ALERTING.md`
- `TEST_STRATEGY.md`
- `ENVIRONMENT_AND_CONFIG_SPEC.md`
- `MIGRATION_AND_DATA_GOVERNANCE.md`
- `OBSERVABILITY_SPEC.md`
- `RELEASE_AND_CHANGE_MANAGEMENT.md`

This roadmap is the governing delivery plan for LSOS implementation.
