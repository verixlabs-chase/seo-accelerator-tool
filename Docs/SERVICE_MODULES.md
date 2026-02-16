# SERVICE_MODULES.md

## 1) Scope

Defines LSOS service modules and their implementation contracts: purpose, internal services, Celery tasks, API endpoints, database dependencies, and failure handling.

Module list (authoritative):
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

## 2) Module 1: Crawl & Technical SEO Engine

Purpose:
- Execute recurring and on-demand site crawls and extract technical SEO diagnostics.

Internal services:
- `CrawlSchedulerService`
- `PageFetchService` (Playwright)
- `TechnicalParserService` (BeautifulSoup/lxml)
- `IssueClassifierService`

Celery tasks:
- `crawl.schedule_campaign`
- `crawl.fetch_batch`
- `crawl.parse_page`
- `crawl.extract_issues`
- `crawl.finalize_run`

API endpoints:
- `POST /api/v1/crawl/schedule`
- `GET /api/v1/crawl/runs`
- `GET /api/v1/crawl/issues`

Database dependencies:
- `campaigns`, `pages`, `crawl_runs`, `crawl_page_results`, `strategy_recommendations`

Failure handling:
- Retries for transient fetch failures.
- Per-domain rate backoff and browser session reset on repeated failures.
- Dead-letter escalation for parser regressions with fixture replay.

## 3) Module 2: Rank Tracking Engine

Purpose:
- Collect geo-specific keyword rankings and maintain trend history.

Internal services:
- `KeywordSetService`
- `GeoGridService`
- `SERPCollectionService`
- `RankNormalizationService`

Celery tasks:
- `rank.schedule_window`
- `rank.fetch_serp_batch`
- `rank.normalize_snapshot`
- `rank.compute_deltas`

API endpoints:
- `POST /api/v1/rank/keywords`
- `POST /api/v1/rank/schedule`
- `GET /api/v1/rank/snapshots`
- `GET /api/v1/rank/trends`

Database dependencies:
- `keyword_clusters`, `campaign_keywords`, `rankings`, `campaigns`

Failure handling:
- Proxy circuit breakers and endpoint quarantine.
- Idempotent upsert by `(tenant_id,campaign_id,keyword,location,snapshot_date)`.
- Backfill jobs for partial window failures.

## 4) Module 3: Competitor Intelligence Engine

Purpose:
- Capture competitor SERP behavior and derive comparative insights.

Internal services:
- `CompetitorRegistryService`
- `CompetitorSnapshotService`
- `GapAnalysisService`

Celery tasks:
- `competitor.refresh_baseline`
- `competitor.collect_snapshot`
- `competitor.compute_gap_scores`

API endpoints:
- `POST /api/v1/competitors`
- `GET /api/v1/competitors`
- `GET /api/v1/competitors/snapshots`
- `GET /api/v1/competitors/gaps`

Database dependencies:
- `competitors`, `competitor_rankings`, `campaign_keywords`, `rankings`

Failure handling:
- Partial competitor capture tolerated with confidence flags.
- Retry only transient fetch errors.
- Gap score computation blocked when minimum data completeness threshold not met.

## 5) Module 4: Content Automation Engine

Purpose:
- Manage content planning and execution tied to cluster strategy.

Internal services:
- `ContentPlanService`
- `AssetLifecycleService`
- `ContentQARulesService`

Celery tasks:
- `content.generate_plan`
- `content.run_qc_checks`
- `content.update_publish_state`

API endpoints:
- `POST /api/v1/content/assets`
- `PATCH /api/v1/content/assets/{id}`
- `GET /api/v1/content/plan`
- `GET /api/v1/content/assets`

Database dependencies:
- `content_assets`, `keyword_clusters`, `campaign_keywords`, `campaign_milestones`

Failure handling:
- Validation failure blocks state transition.
- QC failures create remediation recommendations, not silent rejection.
- Publish sync retries with bounded attempts.

## 6) Module 5: Internal Linking Intelligence Engine

Purpose:
- Generate and maintain internal linking opportunities from crawl/content data.

Internal services:
- `LinkGraphBuilderService`
- `AnchorRecommendationService`
- `LinkValidationService`

Celery tasks:
- `links.refresh_graph`
- `links.generate_recommendations`
- `links.validate_existing_links`

API endpoints:
- `GET /api/v1/internal-links/map`
- `GET /api/v1/internal-links/recommendations`
- `POST /api/v1/internal-links/refresh`

Database dependencies:
- `pages`, `content_assets`, `internal_link_map`, `crawl_page_results`

Failure handling:
- On graph build failure, retain previous valid graph snapshot.
- Recommendation generation requires minimum crawl freshness threshold.

## 7) Module 6: Local SEO Engine

Purpose:
- Monitor local profile health and map/local visibility signals.

Internal services:
- `LocalProfileSyncService`
- `LocalHealthScoringService`
- `NAPConsistencyService`

Celery tasks:
- `local.collect_profile_snapshot`
- `local.compute_health_score`
- `local.run_nap_consistency_check`

API endpoints:
- `GET /api/v1/local/health`
- `GET /api/v1/local/map-pack`
- `POST /api/v1/local/refresh`

Database dependencies:
- `campaigns`, `strategy_recommendations`, `reviews`, `review_velocity_snapshots`

Failure handling:
- Provider outage fallback: stale-last-good snapshot with warning status.
- NAP inconsistencies trigger actionable recommendation records.

## 8) Module 7: Authority & Outreach Engine

Purpose:
- Operate authority-building outreach CRM and backlink growth tracking.

Internal services:
- `OutreachCampaignService`
- `ContactEnrichmentService`
- `SequenceExecutionService`
- `BacklinkSyncService`

Celery tasks:
- `outreach.enrich_contacts`
- `outreach.execute_sequence_step`
- `authority.sync_backlinks`

API endpoints:
- `POST /api/v1/authority/outreach-campaigns`
- `POST /api/v1/authority/contacts`
- `GET /api/v1/authority/backlinks`
- `GET /api/v1/authority/outreach-campaigns`

Database dependencies:
- `outreach_campaigns`, `outreach_contacts`, `backlinks`, `campaign_milestones`

Failure handling:
- Email/provider failures retried with provider fallback.
- Duplicate contact detection by email/domain within tenant/campaign.
- Sequence steps idempotent per contact-step key.

## 9) Module 8: Citation Engine

Purpose:
- Build and maintain citation listings and directory consistency.

Internal services:
- `CitationDirectoryCatalogService`
- `CitationSubmissionService`
- `CitationVerificationService`

Celery tasks:
- `citation.submit_batch`
- `citation.refresh_status`
- `citation.audit_nap_consistency`

API endpoints:
- `POST /api/v1/citations/submissions`
- `GET /api/v1/citations/status`
- `GET /api/v1/citations`

Database dependencies:
- `citations`, `campaigns`, `strategy_recommendations`

Failure handling:
- Directory-specific retry and cooldown policies.
- Escalate unresolved pending citations beyond SLA threshold.

## 10) Module 9: Review Monitoring Engine

Purpose:
- Ingest review data, compute velocity/sentiment trends, and detect anomalies.

Internal services:
- `ReviewIngestionService`
- `SentimentScoringService`
- `VelocityComputationService`

Celery tasks:
- `reviews.ingest`
- `reviews.compute_velocity`
- `reviews.detect_anomalies`

API endpoints:
- `GET /api/v1/reviews`
- `GET /api/v1/reviews/velocity`
- `POST /api/v1/reviews/refresh`

Database dependencies:
- `reviews`, `review_velocity_snapshots`, `campaigns`

Failure handling:
- Dedup by external review ID.
- Low-confidence sentiment scores flagged, not dropped.
- Backfill on ingestion gaps.

## 11) Module 10: Campaign Intelligence Engine

Purpose:
- Apply month-based logic rules, score campaign momentum, and publish recommendations.

Internal services:
- `RuleEvaluationService`
- `ScoreAggregationService`
- `RecommendationService`

Celery tasks:
- `campaigns.evaluate_monthly_rules`
- `campaigns.schedule_monthly_actions`
- `intelligence.compute_score`
- `intelligence.detect_anomalies`

API endpoints:
- `GET /api/v1/intelligence/score`
- `GET /api/v1/intelligence/recommendations`
- `POST /api/v1/campaigns/{id}/advance-month`

Database dependencies:
- `campaigns`, `campaign_milestones`, `strategy_recommendations`, `monthly_reports`

Failure handling:
- If required source snapshots missing, emit backfill tasks and mark score confidence reduced.
- Month advancement blocked when mandatory milestones incomplete.

## 12) Module 11: Reporting Engine

Purpose:
- Produce white-label monthly reports, artifacts, and scheduled delivery.

Internal services:
- `KPIAggregationService`
- `TemplateRenderService`
- `PDFExportService`
- `DeliveryService`

Celery tasks:
- `reporting.freeze_window`
- `reporting.aggregate_kpis`
- `reporting.render_html`
- `reporting.render_pdf`
- `reporting.send_email`

API endpoints:
- `POST /api/v1/reports/generate`
- `GET /api/v1/reports`
- `GET /api/v1/reports/{id}`
- `POST /api/v1/reports/{id}/deliver`

Database dependencies:
- `monthly_reports`, `strategy_recommendations`, `rankings`, `crawl_page_results`, `backlinks`, `citations`, `reviews`, `content_assets`

Failure handling:
- Validation gate before rendering (required snapshot completeness).
- Retry render on transient browser/PDF failures.
- Delivery retries with SMTP/provider fallback and delivery event logging.

## 13) Inter-Module Communication Rules

- No module writes directly into another module's aggregate tables unless explicitly allowed by contract.
- Cross-module actions use:
  - Celery task events
  - shared campaign IDs and correlation IDs
  - versioned payload schemas
- Shared recommendation publication path is `strategy_recommendations`.

## 14) Common Reliability Policies

- Idempotency key required for task handlers with side effects.
- Tenant and campaign ownership validated at module entry.
- All modules emit structured logs with `tenant_id`, `campaign_id`, `correlation_id`.
- Dead-letter replay requires privileged permission and audit trail.

This document is the governing service-module contract for LSOS.
