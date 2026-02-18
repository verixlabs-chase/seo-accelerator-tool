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

## 13) Future Enhancements Roadmap Integration (V7)

Dependency validation gate (required before "Ready for Implementation"):
- Event bus exists: Yes (Celery/Redis queue fabric and domain events are defined in architecture and observability specs).
- Feature flag system exists: Yes (central governance is defined in environment/config spec).
- Audit logging exists: Yes (`audit_logs` schema and `audit.write_event` workflow are defined).
- RBAC enforcement exists: Yes (RBAC controls are defined in security and architecture specs).
- Reference Library loader exists: No (loader contract exists in Future Enhancements specs, but no current loader module/contract is defined in baseline roadmap docs).

Readiness rule:
- Any EPIC depending on the missing Reference Library loader is `Blocked - Missing Dependency`.

### Phase 4.5 (After Content Automation Engine)

#### EPIC_ENTITY_DOMINANCE

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Measure semantic authority against competitors using entity extraction and gap scoring.

Dependencies:
- Crawl Engine outputs
- Rank/SERP snapshot data
- Competitor snapshot data
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `entity_catalog`
- `page_entities`
- `competitor_entities`
- `entity_dominance_scores`
- `entity_gap_reports`

Required background jobs:
- `entity.extract_from_page`
- `entity.build_campaign_graph`
- `entity.compute_dominance_score`
- `entity.generate_gap_report`

Required API endpoints:
- `GET /api/v1/entity/dominance/score`
- `GET /api/v1/entity/dominance/gaps`
- `GET /api/v1/entity/dominance/evidence`

Required feature flags:
- `entity_dominance.enabled`
- `entity_dominance.read_only_mode`

Acceptance criteria:
- Entity extraction runs per URL with tenant-safe writes.
- Competitor entity overlap and gap scoring are generated.
- Outputs include `entity_score`, `missing_entities[]`, `confidence_score`, and `evidence[]`.
- No hardcoded thresholds outside Reference Library.

Risk tier considerations:
- Tier 0 for insight-only scoring views.
- Tier 1 for draft recommendations derived from dominance gaps.
- Tier 2+ blocked until Reference Library loader is implemented and validated.

### Phase 6 (Inside Campaign Intelligence)

#### EPIC_LOCAL_AUTHORITY_SCORE

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Produce a configurable, versioned composite 0-100 local authority score with explainable breakdowns.

Dependencies:
- Campaign Intelligence scoring pipeline
- Technical score signals
- SERP footprint signals
- Link/review/citation velocity signals
- Entity dominance signals
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `local_authority_model_versions`
- `local_authority_weights`
- `local_authority_scores`
- `local_authority_score_components`

Required background jobs:
- `authority.compute_local_score`
- `authority.apply_model_version`
- `authority.compute_local_score_deltas`

Required API endpoints:
- `GET /api/v1/intelligence/local-authority/score`
- `GET /api/v1/intelligence/local-authority/breakdown`
- `GET /api/v1/intelligence/local-authority/history`

Required feature flags:
- `campaign_intelligence.local_authority_score`
- `campaign_intelligence.local_authority_score_v2`

Acceptance criteria:
- Weighted scoring is configurable and versioned.
- Score outputs include value, component breakdown, delta, and confidence.
- Deterministic recomputation for fixed inputs and model version.
- AI-derived recommendations include evidence and risk tier.

Risk tier considerations:
- Tier 0 for score visibility.
- Tier 1 for draft strategy recommendations.
- Tier 2+ only after Reference Library loader and approval workflows are active.

### Phase 6.5 (After Rank Tracking Enhancements)

#### EPIC_SERP_FOOTPRINT

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Quantify SERP occupation across organic, local pack, snippet, video, and image features.

Dependencies:
- Rank tracking snapshots
- SERP HTML capture pipeline
- Competitor tracking signals
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `serp_feature_snapshots`
- `serp_footprint_scores`
- `serp_feature_presence_map`
- `serp_competitor_overlap`

Required background jobs:
- `serp.extract_features`
- `serp.compute_footprint_score`
- `serp.compute_competitor_overlap`

Required API endpoints:
- `GET /api/v1/rank/serp-footprint/score`
- `GET /api/v1/rank/serp-footprint/features`
- `GET /api/v1/rank/serp-footprint/overlap`

Required feature flags:
- `rank_tracking.serp_footprint`
- `rank_tracking.serp_footprint_advanced_features`

Acceptance criteria:
- SERP feature extraction works on captured HTML snapshots.
- Footprint percentages are available by keyword group.
- Outputs include footprint score, presence map, and competitor overlap.
- Evidence and confidence are included in recommendation payloads.

Risk tier considerations:
- Tier 0 for observational analytics.
- Tier 1 for draft prioritization recommendations.
- Tier 2 blocked pending Reference Library loader and signal calibration.

### Phase 7 (Post-Stability / After V1 Release)

#### EPIC_REVENUE_ATTRIBUTION

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Attribute ranking/page performance to revenue outcomes for ROI analysis.

Dependencies:
- Rank tracking history
- Content/page performance history
- Session tracking and call ingestion
- Campaign Intelligence reporting
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `attribution_sessions`
- `attribution_touchpoints`
- `revenue_events`
- `revenue_attribution_models`
- `revenue_attribution_results`

Required background jobs:
- `attribution.ingest_sessions`
- `attribution.ingest_calls`
- `attribution.map_revenue_events`
- `attribution.compute_revenue_by_page`
- `attribution.compute_roi_by_cluster`

Required API endpoints:
- `GET /api/v1/attribution/revenue-by-page`
- `GET /api/v1/attribution/revenue-by-keyword`
- `GET /api/v1/attribution/roi-by-cluster`

Required feature flags:
- `attribution.revenue_engine`
- `attribution.call_ingestion`

Acceptance criteria:
- Revenue-linked datasets are encrypted at rest/in transit.
- Revenue-by-page/keyword/cluster outputs are produced with deltas.
- Attribution model version is tracked for reproducibility.
- Recommendation outputs include confidence and evidence arrays.

Risk tier considerations:
- Tier 0 for reporting-only views.
- Tier 1 for draft optimization suggestions.
- Tier 3 for high-impact budget reallocation recommendations with approval.

#### EPIC_PREDICTIVE_RANK

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Forecast ranking trajectory using probabilistic models and velocity signals.

Dependencies:
- Rank history and deltas
- Competitor movement signals
- Campaign milestone events
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `rank_forecast_models`
- `rank_forecast_runs`
- `rank_forecast_outputs`
- `rank_forecast_evidence`

Required background jobs:
- `predictive_rank.train_model`
- `predictive_rank.generate_forecast`
- `predictive_rank.validate_forecast_accuracy`

Required API endpoints:
- `GET /api/v1/predictive-rank/curve`
- `GET /api/v1/predictive-rank/confidence`
- `GET /api/v1/predictive-rank/time-to-top`

Required feature flags:
- `predictive_rank.enabled`
- `predictive_rank.model_v2`

Acceptance criteria:
- Forecast includes predicted curve, confidence interval, and time-to-top estimate.
- Model outputs are evidence-backed and reproducible by model version.
- No deterministic "guaranteed rank" outputs are exposed.

Risk tier considerations:
- Tier 0 for forecast visibility.
- Tier 1 for draft planning recommendations.
- Tier 2 for recommended execution plans requiring human review.

#### EPIC_AI_CONVERSION_LAYER

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Improve conversion outcomes using behavioral insights and governed A/B experimentation.

Dependencies:
- Reporting and attribution metrics
- UX/event telemetry
- Experimentation framework
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `conversion_experiments`
- `conversion_variants`
- `conversion_events`
- `conversion_experiment_results`
- `conversion_recommendations`

Required background jobs:
- `conversion.evaluate_variant_performance`
- `conversion.compute_conversion_delta`
- `conversion.generate_ux_insights`

Required API endpoints:
- `POST /api/v1/conversion/experiments`
- `GET /api/v1/conversion/experiments/{id}/results`
- `GET /api/v1/conversion/insights`

Required feature flags:
- `conversion.ai_layer`
- `conversion.ab_testing`

Acceptance criteria:
- No automatic layout changes without approval controls.
- All tests and recommendation events are fully logged.
- Outputs include `ux_insights`, `ab_test_results`, and `conversion_delta`.
- Recommendation payloads include confidence, evidence, and risk tier.

Risk tier considerations:
- Tier 1 for draft test plans.
- Tier 2 for low-risk content/CTA experiments.
- Tier 3 for broad UX changes requiring explicit approval.

#### EPIC_AUTONOMOUS_OUTREACH

Implementation status:
- Blocked - Missing Dependency (Reference Library loader)

Objective:
- Semi-automate prospecting and outreach with AI-assisted classification under strict approval controls.

Dependencies:
- Authority/outreach CRM data
- Citation/backlink state
- AI recommendation governance schema
- Reference Library
- Event bus
- Feature flags
- Audit logging
- RBAC

Required DB tables:
- `outreach_prospect_queue`
- `outreach_message_drafts`
- `outreach_reply_classifications`
- `outreach_automation_runs`

Required background jobs:
- `outreach.rank_prospects`
- `outreach.generate_draft_message`
- `outreach.classify_reply`
- `outreach.sync_response_state`

Required API endpoints:
- `GET /api/v1/outreach/autonomous/prospects`
- `GET /api/v1/outreach/autonomous/drafts`
- `POST /api/v1/outreach/autonomous/{id}/approve-send`
- `GET /api/v1/outreach/autonomous/replies`

Required feature flags:
- `outreach.autonomous_agent`
- `outreach.autonomous_send_enabled`

Acceptance criteria:
- Draft-only mode is default.
- Manual approval is required before sends.
- Outputs include prospect queue, drafted messages, and reply classification.
- All agent decisions and send approvals are audit logged.

Risk tier considerations:
- Tier 1 for draft generation/classification.
- Tier 2 for limited, approved sending workflows.
- Tier 3 for scaled automated sending (approval-gated).

## 14) Next Phase Activation: Sprint 10 - Reference Library Foundation

Objective:
- Implement the minimum shared foundation that unlocks all Future Enhancements EPICs without modifying existing Phase 1-9 production behavior.

Scope:
- Deliver a Reference Library loader contract with version pinning, schema validation, and hot-reload safety controls.
- Deliver governance-safe Recommendation payload schema conformance checks.
- Deliver audit and RBAC controls for library management operations.

Deliverables:
- Reference Library artifact contract (`metrics`, `thresholds`, `diagnostics`, `recommendations`, `validation_rules`).
- Loader lifecycle contract (load, validate, activate, rollback to previous version).
- Version manifest and activation state model.
- Admin/API contracts for validation and controlled activation.
- Queue jobs for async validation and publish-safe cache refresh.

Acceptance criteria:
- Loader can resolve active library version per environment and tenant scope policy.
- Library schema validation runs in CI and runtime pre-activation checks.
- Activation/deactivation operations are RBAC-protected and audit logged.
- No hardcoded thresholds are introduced into service modules.
- Existing Phase 1-9 services run unchanged when loader is disabled.

Database changes:
- Add tables: `reference_library_versions`, `reference_library_artifacts`, `reference_library_validation_runs`, `reference_library_activations`.

API endpoints added:
- `POST /api/v1/reference-library/validate`
- `POST /api/v1/reference-library/activate`
- `GET /api/v1/reference-library/versions`
- `GET /api/v1/reference-library/active`

Tasks added:
- `reference_library.validate_artifact`
- `reference_library.activate_version`
- `reference_library.reload_cache`
- `reference_library.rollback_version`

Feature flags:
- `reference_library.loader_enabled`
- `reference_library.hot_reload_enabled`
- `reference_library.enforce_validation`

Risk tier considerations:
- Tier 0 for read-only version visibility.
- Tier 1 for draft validation runs.
- Tier 2 for activation in staging/production with approval and rollback plan.

Post-sprint dependency re-check:
- Event bus exists: required and already present.
- Feature flag system exists: required and already present.
- Audit logging exists: required and already present.
- RBAC enforcement exists: required and already present.
- Reference Library loader exists: must be set to present after Sprint 10 DoD.

Unlock result:
- On Sprint 10 completion, reclassify Future Enhancements EPICs from `Blocked - Missing Dependency` to `Ready for Implementation` (phase order preserved: 4.5 -> 6 -> 6.5 -> 7).
