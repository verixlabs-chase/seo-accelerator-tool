# Post-UI Feature Fulfillment Ticket Backlog

> **Status update (2026-08-03):** This remains the workflow-fulfillment backlog,
> but it is no longer the master next-sprint sequence. The working routes are in
> place. Customer review now prioritizes T26 followed by UX10-UX12 / T29-T31:
> plain-language checklists, the shared visual system, the Overview and Next
> Steps redesign, and the cross-page visualization rollout. See
> [claude-next-build-brief.md](./claude-next-build-brief.md#1a-active-customer-ux-sprint-sequence).
> Remaining feature tickets should be scheduled behind or alongside that
> customer-comprehension work, not used to add more dense top-level surfaces.

## 1. Executive Summary

This backlog turns the feature audit into the next execution phase.

Primary principle:

- prioritize workflow closure over new surface area
- prioritize recommendation -> approval -> execution -> audit -> reporting
- do not treat backend-only capability as shipped product
- prefer additive slices that expose existing backend depth safely

Execution priority for this phase:

1. execution inbox / approvals / rollback / audit
2. competitors
3. citations
4. content / topical authority
5. reports scheduling / summaries
6. WordPress execution provisioning / safety UX
7. backlinks / outreach
8. agency / portfolio support

## 2. P0 Ticket List

### T01. Build buyer-facing execution inbox page

- Goal: expose pending/scheduled/completed/failed recommendation executions in a usable operator workflow.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `frontend/app/(product)/components/AppShell.tsx`
  - `frontend/app/(product)/components/ActionDrawer.tsx`
  - `frontend/app/platform/api.js`
  - `backend/app/api/v1/executions.py`
  - `backend/app/schemas/executions.py`
- Backend dependency: existing execution list/detail APIs.
- Frontend dependency: opportunities page and shared authenticated API helper.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - user can view execution list filtered by status for a selected campaign
  - each execution row shows status, execution type, risk, created time, approval state, and latest error
  - execution detail drawer shows result summary and mutation count if present
  - no page crash when no executions exist
- Recommended order: 1

### T02. Add approve / reject actions to execution inbox

- Goal: give operators a real approval workflow instead of recommendation-state-only progression.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `frontend/app/platform/api.js`
  - `backend/app/api/v1/executions.py`
  - `backend/app/intelligence/recommendation_execution_engine.py`
- Backend dependency: approve/reject endpoints already exist.
- Frontend dependency: T01
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - operator can approve and reject pending/scheduled executions from UI
  - approved execution status updates in-page without full reload
  - rejected execution shows rejection result and is removed from pending queue
  - failures are shown as actionable error messages
- Recommended order: 2

### T03. Add execution run / retry / cancel / rollback controls

- Goal: close the main execution loop from approval to delivery to rollback.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `frontend/app/(product)/components/ActionDrawer.tsx`
  - `backend/app/api/v1/executions.py`
  - `backend/app/intelligence/recommendation_execution_engine.py`
  - `backend/app/models/recommendation_execution.py`
  - `backend/app/models/execution_mutation.py`
- Backend dependency: run/retry/cancel/rollback endpoints and mutation persistence.
- Frontend dependency: T01
- Risk level: High
- Feature flag needed or not: Yes, `execution_console_enabled`
- Acceptance criteria:
  - operator can run dry-run and real execution
  - completed executions with persisted mutations can be rolled back
  - scheduled/pending executions can be canceled
  - retry is available only for failed executions
  - each action refreshes execution detail and status
- Recommended order: 3

### T04. Add execution audit timeline to buyer UI

- Goal: expose recommendation status changes, approval events, execution events, rollback events, and mutation outcomes in one timeline.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `backend/app/api/v1/automation.py`
  - `backend/app/api/v1/executions.py`
  - `backend/app/services/audit_service.py`
- Backend dependency: automation timeline export and execution events.
- Frontend dependency: T01
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - selected recommendation or execution shows timeline entries in chronological order
  - approval, execution, rollback, and failure events are visible
  - empty state clearly explains when no history exists
- Recommended order: 4

### T05. Add competitors page and nav exposure

- Goal: turn competitor APIs into a buyer-facing page with add/list/snapshot/gaps workflow.
- Files likely affected:
  - `frontend/app/(product)/nav.config.ts`
  - `frontend/app/(product)/competitors/page.tsx`
  - `frontend/app/(product)/components/ComparisonTable.tsx`
  - `frontend/app/platform/api.js`
  - `backend/app/api/v1/competitors.py`
- Backend dependency: competitors APIs already exist.
- Frontend dependency: new product page.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - competitors nav item is visible
  - user can add competitors to a campaign
  - user can fetch snapshots and see gap table
  - page handles `no_competitors` and `provider_unavailable` states clearly
- Recommended order: 5

### T06. Add citations workflow page

- Goal: expose citation submission and status tracking as a buyer-facing local SEO workflow.
- Files likely affected:
  - `frontend/app/(product)/local-visibility/page.tsx`
  - `frontend/app/(product)/citations/page.tsx`
  - `frontend/app/(product)/nav.config.ts`
  - `backend/app/api/v1/authority.py`
- Backend dependency: citation submission and status endpoints.
- Frontend dependency: new page or Local SEO expansion.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - user can submit citation targets
  - user can view current citation statuses and listing URLs
  - job status and empty states are visible
  - local SEO page links into citation workflow
- Recommended order: 6

### T07. Add report schedule editor to reports page

- Goal: make recurring reporting user-manageable instead of backend-only.
- Files likely affected:
  - `frontend/app/(product)/reports/page.tsx`
  - `backend/app/api/v1/reports.py`
  - `backend/app/services/reporting_service.py`
- Backend dependency: report schedule get/put APIs already exist.
- Frontend dependency: reports page.
- Risk level: Low
- Feature flag needed or not: No
- Acceptance criteria:
  - user can set cadence, timezone, enabled state, and next run
  - current schedule status and retry count are visible
  - reports page shows schedule failure state when retries are exhausted
- Recommended order: 7

### T08. Add report summary cards and delivery history

- Goal: make reporting automation operationally visible and easier to trust.
- Files likely affected:
  - `frontend/app/(product)/reports/page.tsx`
  - `backend/app/api/v1/reports.py`
  - `backend/app/services/reporting_service.py`
  - `backend/app/models/reporting.py`
- Backend dependency: report detail and delivery event persistence.
- Frontend dependency: reports page.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - reports page shows latest generated, latest delivered, schedule state, and delivery history
  - failed delivery attempts are visible
  - user can distinguish generated vs delivered reports without opening detail
- Recommended order: 8

### T09. Add WordPress execution setup status panel

- Goal: stop WordPress execution from being invisible/operator-only by surfacing provisioning state and blockers.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `frontend/app/platform/providers/page.jsx`
  - `backend/app/intelligence/executors/wordpress_plugin.py`
  - `backend/app/services/provider_credentials_service.py`
  - `backend/app/api/v1/provider_health.py`
- Backend dependency: provider credentials and plugin health telemetry.
- Frontend dependency: opportunities page and/or platform provider page.
- Risk level: Medium
- Feature flag needed or not: Yes, `wordpress_execution_setup_ui`
- Acceptance criteria:
  - UI shows whether WordPress execution is configured, test mode, blocked, or unhealthy
  - missing token/shared-secret/base-url states are explained
  - execution actions are disabled with reason when provisioning is incomplete
- Recommended order: 9

### T10. Add execution safety confirmation UX for website mutations

- Goal: require explicit operator confirmation for mutation-producing runs before execution.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `frontend/app/(product)/components/ActionDrawer.tsx`
  - `backend/app/api/v1/executions.py`
  - `backend/app/intelligence/recommendation_execution_engine.py`
- Backend dependency: execution type detection and mutation payload visibility.
- Frontend dependency: T01 and T03
- Risk level: High
- Feature flag needed or not: Yes, `website_mutation_confirmation_enabled`
- Acceptance criteria:
  - mutation-producing executions show explicit warning and rollback note before run
  - user must confirm before non-dry-run website execution
  - dry-run remains available without destructive confirmation
- Recommended order: 10

## 3. P1 Ticket List

### T11. Build content authority workspace page

- Goal: expose content plan, lifecycle state, and internal link recommendations in a buyer-facing workflow.
- Files likely affected:
  - `frontend/app/(product)/content/page.tsx`
  - `frontend/app/(product)/nav.config.ts`
  - `backend/app/api/v1/content.py`
  - `backend/app/services/content_service.py`
- Backend dependency: content plan/assets/QC/internal links.
- Frontend dependency: new page.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - user can view content assets by month and status
  - user can progress assets through lifecycle states
  - internal link recommendations are visible
  - empty state explains how content plan is created
- Recommended order: 11

### T12. Add content QC and publish-readiness badges

- Goal: make content lifecycle operationally meaningful rather than just status fields.
- Files likely affected:
  - `frontend/app/(product)/content/page.tsx`
  - `backend/app/services/content_service.py`
  - `backend/app/api/v1/content.py`
- Backend dependency: QC events.
- Frontend dependency: T11
- Risk level: Low
- Feature flag needed or not: No
- Acceptance criteria:
  - each content asset shows QC summary
  - published assets show target URL and link-map refresh state
  - invalid lifecycle transitions are clearly handled in UI
- Recommended order: 12

### T13. Add backlinks / outreach workspace page

- Goal: expose backlinks, outreach campaigns, and outreach contacts in a usable operational UI.
- Files likely affected:
  - `frontend/app/(product)/authority/page.tsx`
  - `frontend/app/(product)/nav.config.ts`
  - `backend/app/api/v1/authority.py`
  - `backend/app/services/authority_service.py`
- Backend dependency: outreach/backlinks APIs.
- Frontend dependency: new page.
- Risk level: Medium
- Feature flag needed or not: Yes, `authority_workspace_enabled`
- Acceptance criteria:
  - user can create outreach campaign
  - user can create contacts and see statuses
  - user can view synced backlinks
  - clear messaging exists for no data and synthetic/provider-thin states
- Recommended order: 13

### T14. Add recommendation-to-execution creation action from opportunities

- Goal: make approved recommendations actually enter execution flow from the main product page.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `backend/app/api/v1/executions.py`
  - `backend/app/intelligence/recommendation_execution_engine.py`
- Backend dependency: schedule/create execution path.
- Frontend dependency: opportunities page.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - approved recommendation can create/schedule an execution from UI
  - resulting execution appears in execution inbox immediately
  - blocked governance states are shown to the user
- Recommended order: 14

### T15. Add recommendation impact verification panel

- Goal: close the loop after execution by showing outcome metrics and whether the recommendation helped.
- Files likely affected:
  - `frontend/app/(product)/opportunities/page.tsx`
  - `backend/app/intelligence/outcome_tracker.py`
  - `backend/app/intelligence/telemetry/execution_metrics.py`
  - `backend/app/api/v1/executions.py`
- Backend dependency: execution outcome tracking.
- Frontend dependency: T01
- Risk level: Medium
- Feature flag needed or not: Yes, `execution_outcome_panel_enabled`
- Acceptance criteria:
  - completed executions show outcome summary or “awaiting outcome data”
  - failed/rolled-back executions show reason and mutation counts
  - panel distinguishes dry-run from real execution
- Recommended order: 15

### T16. Add report summary narrative generation improvements

- Goal: make report previews and delivered reports feel less placeholder-like.
- Files likely affected:
  - `backend/app/services/reporting_service.py`
  - `frontend/app/(product)/components/ReportPreview.tsx`
  - `frontend/app/(product)/reports/page.tsx`
- Backend dependency: KPI aggregation and report summary payloads.
- Frontend dependency: reports page and preview component.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - report preview includes clearer executive summary blocks
  - technical, ranking, review, and recommendation sections feel distinct
  - missing-data cases render explicit reasons instead of silent thin output
- Recommended order: 16

### T17. Add competitor comparison cards to rankings and reports

- Goal: connect the new competitor workflow back into the core buyer pages.
- Files likely affected:
  - `frontend/app/(product)/rankings/page.tsx`
  - `frontend/app/(product)/reports/page.tsx`
  - `backend/app/api/v1/competitors.py`
- Backend dependency: competitors snapshots/gaps.
- Frontend dependency: T05
- Risk level: Low
- Feature flag needed or not: No
- Acceptance criteria:
  - rankings page can show competitor gap summary when competitor data exists
  - reports page can summarize competitor comparison in preview
  - no regressions when competitor data is absent
- Recommended order: 17

### T18. Add provider credential and policy management polish

- Goal: make admin/provider setup less fragile for real operations.
- Files likely affected:
  - `frontend/app/platform/orgs/[id]/page.jsx`
  - `frontend/app/platform/providers/page.jsx`
  - `backend/app/api/v1/provider_credentials.py`
  - `backend/app/api/v1/provider_health.py`
- Backend dependency: existing provider credential and policy APIs.
- Frontend dependency: platform admin pages.
- Risk level: Low
- Feature flag needed or not: No
- Acceptance criteria:
  - platform org detail explains credential mode impact
  - provider health page links issues to likely setup gaps
  - errors and missing-policy states are understandable
- Recommended order: 18

## 4. P2 Ticket List

### T19. Add portfolio overview page for organization operators

- Goal: expose subaccounts, business locations, and locations as an agency/multi-entity operating surface.
- Files likely affected:
  - `frontend/app/platform/portfolio/page.jsx`
  - `backend/app/api/v1/subaccounts.py`
  - `backend/app/api/v1/business_locations.py`
  - `backend/app/api/v1/locations.py`
  - `backend/app/services/hierarchy_observability_service.py`
- Backend dependency: subaccount/location/business-location APIs.
- Frontend dependency: new platform page.
- Risk level: Medium
- Feature flag needed or not: Yes, `portfolio_admin_ui_enabled`
- Acceptance criteria:
  - operator can see hierarchy summary for subaccounts, business locations, and locations
  - operator can create business locations and locations in one coherent flow
  - missing subaccount dependency is explained clearly
- Recommended order: 19

### T20. Add report branding profile editor

- Goal: begin turning white-label reporting from spec into real admin capability.
- Files likely affected:
  - `frontend/app/platform/orgs/[id]/page.jsx`
  - `backend/app/api/v1/platform_control.py`
  - `backend/app/models/organization.py`
  - `backend/app/services/reporting_service.py`
- Backend dependency: likely new persistence for brand fields.
- Frontend dependency: platform org detail page.
- Risk level: Medium
- Feature flag needed or not: Yes, `report_branding_profile_enabled`
- Acceptance criteria:
  - platform user can save brand name and basic color palette
  - report preview can consume saved brand profile
  - defaults remain intact when no brand profile exists
- Recommended order: 20

### T21. Add outreach workflow stages and operator tasks

- Goal: make outreach more than status mutation by adding explicit next-step visibility.
- Files likely affected:
  - `frontend/app/(product)/authority/page.tsx`
  - `backend/app/services/authority_service.py`
  - `backend/app/api/v1/authority.py`
- Backend dependency: outreach contacts and campaigns.
- Frontend dependency: T13
- Risk level: Medium
- Feature flag needed or not: Yes, `outreach_workflow_v2_enabled`
- Acceptance criteria:
  - contacts show pending/enriched/queued/sent progression
  - page includes next-step counts by stage
  - operator can trigger enrichment/sequence step without raw API access
- Recommended order: 21

### T22. Add execution-safe environment diagnostics page for WordPress plugin

- Goal: give operators a reliable way to verify plugin connectivity, version, token, secret, and test mode before using live execution.
- Files likely affected:
  - `frontend/app/platform/providers/page.jsx`
  - `backend/app/intelligence/executors/plugin_telemetry.py`
  - `backend/app/intelligence/executors/wordpress_plugin.py`
  - `backend/app/api/v1/provider_health.py`
- Backend dependency: plugin health telemetry.
- Frontend dependency: provider page.
- Risk level: Medium
- Feature flag needed or not: Yes, `wordpress_plugin_diagnostics_enabled`
- Acceptance criteria:
  - diagnostics show plugin health and version status
  - blocked conditions are visible before execution attempts
  - test mode vs live mode is explicit
- Recommended order: 22

### T23. Add daily briefing layer on top of dashboard

- Goal: turn dashboard from a page into a repeatable “what changed, what needs action today” product loop.
- Files likely affected:
  - `frontend/app/(product)/dashboard/page.tsx`
  - `backend/app/api/v1/dashboard.py`
  - `backend/app/services/dashboard_service.py`
- Backend dependency: dashboard summary endpoint.
- Frontend dependency: dashboard page.
- Risk level: Low
- Feature flag needed or not: No
- Acceptance criteria:
  - dashboard shows daily change summary
  - it highlights new recommendations, failed schedules, latest crawl/rank/report events
  - it is understandable even when data is sparse
- Recommended order: 23

### T24. Add report-driven execution summary section

- Goal: make reports reflect operational actions taken, not just KPI output.
- Files likely affected:
  - `backend/app/services/reporting_service.py`
  - `frontend/app/(product)/components/ReportPreview.tsx`
  - `backend/app/intelligence/telemetry/execution_metrics.py`
- Backend dependency: execution metrics and audit data.
- Frontend dependency: reports preview.
- Risk level: Medium
- Feature flag needed or not: No
- Acceptance criteria:
  - report preview includes actions taken / queued / rolled back
  - delivered reports can show operational summary where data exists
  - absent execution data shows explicit fallback
- Recommended order: 24

### T25. Build the expanded location action portfolio

> **Implemented 2026-08-03:** API action enrichment, canonical-action
> deduplication, stable first priority, immediate multi-action cards, honest
> sparse-data behavior, and the complete active action list are in place.
> Production verification follows deployment; recurring checklist state remains
> T26.

- Goal: replace the appearance of one isolated recommendation with a
  location-scoped portfolio that keeps one clear first action while exposing
  multiple useful next actions.
- Files likely affected:
  - `backend/app/models/intelligence.py`
  - `backend/app/services/intelligence_service.py`
  - `backend/app/services/strategy_build_service.py`
  - `backend/app/api/v1/recommendations.py`
  - `frontend/app/(product)/opportunities/page.tsx`
- Backend dependency: canonical action definitions and recommendation evidence.
- Frontend dependency: current opportunities page.
- Risk level: Medium
- Feature flag needed or not: Yes, `expanded_action_plans_enabled`
- Acceptance criteria:
  - selected location shows one `Do this first` spotlight plus the next two or
    more useful actions when evidence supports them
  - the full action area provides `Daily`, `Weekly`, `Monthly`, and
    `Later / watch` sections
  - one to three highest-value unblocked plans appear first, while lower
    priorities remain accessible
  - the service creates no filler plan merely to reach a fixed count
  - duplicate recommendations for the same canonical action, location,
    evidence, and observation window merge into one plan
  - every plan shows plain-language reason, effort, owner, evidence freshness,
    dependency state, success metric, and next step
- Recommended order: 25

### T26. Add deterministic checklists, work routines, and persistent progress

> **Implemented 2026-08-03:** canonical lexicon steps now materialize as
> tenant-scoped, dated action occurrences with persistent per-step state,
> completion actor/time, evidence storage, due state, deterministic cadence,
> and saved progress. Next Steps groups supported work into Today, This week,
> and This month; dependency-blocked or unsupported work remains in Later.
> Checklist updates persist through the API and a completed required checklist
> enters `waiting_for_results` instead of claiming that the SEO result is proven.

- Goal: turn each action plan into a resumable set of concrete steps and give a
  non-technical service-business owner a clear Daily, Weekly, and Monthly work
  routine.
- Files likely affected:
  - `backend/app/models/intelligence.py`
  - `backend/app/intelligence/lexicon/schema.py`
  - `backend/app/services/strategy_build_service.py`
  - `backend/app/api/v1/recommendations.py`
  - `frontend/app/(product)/opportunities/page.tsx`
  - new Alembic migration and backend/frontend tests
- Backend dependency: T25 and the active lexicon's canonical action steps.
- Frontend dependency: T25.
- Risk level: Medium
- Feature flag needed or not: Yes, `action_plan_checklists_enabled`
- Acceptance criteria:
  - normal multi-step plans contain three to eight ordered lexicon-backed steps;
    legitimate single-step actions remain single-step
  - each item persists required/optional state, order, status, blocker reason,
    completion actor/time, and evidence
  - progress survives navigation, sign-out, and another-device access
  - the page shows completed required steps out of total required steps and the
    next unblocked step
  - every plan has a deterministic cadence, due window, and location timezone;
    priority and cadence remain separate fields
  - Daily shows one to three short or time-sensitive actions, Weekly holds the
    larger active improvements, and Monthly holds recurring reviews and upkeep
  - recurring work creates a new dated occurrence instead of resetting or
    overwriting the previously completed checklist
  - the same required work is not duplicated across Daily, Weekly, and Monthly
    views, and users can see due, upcoming, completed, overdue, and snoozed work
  - AI can simplify wording but cannot add, remove, or change a required action,
    step, cadence, due window, dependency, metric, or execution permission
  - no AI request occurs for page loads, item checks, sorting, or repeated views
- Recommended order: 26

### T27. Add action baselines, completion proof, and measurement readiness

- Goal: make plan completion meaningful by recording what existed before the
  work, what was actually done, and when results can be judged.
- Files likely affected:
  - `backend/app/models/recommendation_outcome.py`
  - `backend/app/models/recommendation_execution.py`
  - `backend/app/services/recommendation_outcome_service.py`
  - `backend/app/api/v1/recommendations.py`
  - `backend/app/api/v1/executions.py`
  - `frontend/app/(product)/opportunities/page.tsx`
- Backend dependency: T25-T26 and current execution/outcome records.
- Frontend dependency: T26.
- Risk level: High
- Feature flag needed or not: Yes, `action_measurement_readiness_enabled`
- Acceptance criteria:
  - starting a plan captures an immutable baseline, evidence window, success
    metric, implementation scope, and observation window
  - a plan cannot be completed while required checklist items remain unresolved
  - checked UI steps do not falsely prove that an external or automated change
    succeeded
  - completed work enters `waiting for results` until its observation window can
    be evaluated
  - every measurable plan later records `helped`, `did not help`, or
    `insufficient data` with the supporting before/after evidence
- Recommended order: 27

### T28. Add action-linked forecast scenarios and outcome comparison

- Goal: show a conservative view of what a supported action plan could improve,
  then compare that range with the observed result.
- Files likely affected:
  - `backend/app/models/recommendation_outcome.py`
  - `backend/app/api/v1/intelligence_simulations.py`
  - `backend/app/services/recommendation_outcome_service.py`
  - `backend/app/services/website_performance_service.py`
  - `frontend/app/(product)/opportunities/page.tsx`
  - shared chart components and new migration/tests
- Backend dependency: T25-T27 and versioned deterministic forecast models.
- Frontend dependency: T27.
- Risk level: High
- Feature flag needed or not: Yes, `action_plan_forecasting_enabled`
- Acceptance criteria:
  - forecasts exist only for plans with a supported model, sufficient baseline,
    defined scope, success metric, and observation window
  - the UI compares current, target, conservative, expected, optimistic, and
    observed values without presenting a promise
  - each forecast stores model, assumptions, inputs, data quality, plan version,
    lexicon version, and generated time for replay
  - unsupported ranking, traffic, lead, and revenue effects remain unknown
    rather than receiving fabricated numbers
  - post-window outcomes are labeled `within range`, `outside range`, or
    `insufficient data`
- Recommended order: 28

### T29. Build the plain-language and visual product system

- Goal: replace page-by-page improvisation with one service-owner language,
  icon, hierarchy, metric, and visualization system.
- Files likely affected:
  - `backend/app/intelligence/lexicon/service_business_language_guide.md`
  - `frontend/app/(product)/components/`
  - `frontend/app/(product)/nav.config.ts`
  - shared customer-copy and visual-regression tests
- Backend dependency: current AI language guide and deterministic fallbacks.
- Frontend dependency: current authenticated shell and design tokens.
- Risk level: Medium
- Feature flag needed or not: Yes, `customer_visual_system_v2_enabled`
- Acceptance criteria:
  - customer copy uses short service-owner language and explains business meaning
    before SEO, provider, model, policy, or evidence terminology
  - static and AI-generated customer copy share a dictionary, prohibited-jargon
    rules, readability target, and deterministic fallback
  - an original accessible icon family covers navigation, page types, metrics,
    actions, status, and empty states without copying Ahrefs artwork or layout
  - shared metric, trend, comparison, chart, filter, tooltip, details, loading,
    error, and sparse-data components are documented and tested
  - positive, negative, and neutral changes use consistent words, arrows, and
    accessible color semantics; color is never the only signal
  - cards, badges, borders, and labels exist only when they communicate useful
    grouping, state, warning, or action
- Recommended order: immediately after T26 and before customer-visible T27/T28

### T30. Redesign Overview and Next Steps around owner decisions

- Goal: make the two highest-traffic customer pages glanceable, visual, and
  action-oriented while removing the duplicated console-like experience found
  in the 2026-08-03 customer screenshots.
- Files likely affected:
  - `frontend/app/(product)/dashboard/page.tsx`
  - `frontend/app/(product)/opportunities/page.tsx`
  - shared metric, chart, action-list, checklist, and details components
  - focused frontend tests and visual baselines
- Backend dependency: dashboard summaries, T25-T26 action plans, and current
  Search Console/ranking history.
- Frontend dependency: T29.
- Risk level: Medium
- Feature flag needed or not: Yes, `owner_journey_v2_enabled`
- Acceptance criteria:
  - Overview shows its key result, first meaningful chart, directional change,
    and one next action above the fold at 1440×900
  - Next Steps leads with Today, This week, and This month plus persistent
    checklist progress and the next unblocked step
  - the same recommendation is not repeated in a spotlight, horizontal cards,
    full list, and detail panel at the same time
  - technical proof opens in one focused details drawer or expandable region
  - recommendation-engine labels such as `governed target`, `deeper review`,
    and `possible benefit — more evidence needed` do not appear in the primary
    customer reading flow
  - five-second comprehension and desktop/tablet/mobile task tests pass
- Recommended order: after T29; may close the visible portion of T26

### T31. Apply decision-useful visualization and simplified UX to every page

- Goal: bring Search Rankings, Local Search, Website Health, Directory Listings,
  Reviews, Competitors, Search Value, Locations, Reports, Settings, and setup
  states up to the same owner-friendly standard as Overview and Next Steps.
- Files likely affected:
  - all routes under `frontend/app/(product)/`
  - shared charts, maps, tables, filters, trust details, and page-shell components
  - route-by-route visual and accessibility tests
- Backend dependency: existing route data; provider-specific visuals remain
  gated until their real data is available.
- Frontend dependency: T29 and the approved UX from T30.
- Risk level: Medium
- Feature flag needed or not: Yes, route-scoped rollout under
  `customer_visual_system_v2_enabled`
- Acceptance criteria:
  - every route's first screen makes page purpose, location scope, current
    result, trend/state, and next action clear without technical SEO knowledge
  - Rankings shows distribution, movers, phrase history, and location comparison
  - Local Search shows the real location map or allowance-controlled rank grid
    with keyword-specific results and never substitutes a decorative heat map
  - Website Health shows current Core Web Vitals, issue concentration, history,
    and `Fix this first` before technical issue tables
  - Listings, Reviews, Competitors, Search Value, Locations, and Reports use
    small readable progress, comparison, outlier, and history visuals where the
    underlying data supports them
  - Settings and setup use step-by-step connection and usage status without
    decorative graphs
  - every chart exposes location/date scope, honest comparison coverage,
    accessible legend/tooltip, and truthful no-data or partial-data behavior
  - route audit removes repeated guidance, duplicated data, oversized empty
    space, dead controls, unnecessary badges, and priority content below fold
- Recommended order: after T30 and before final forecasting/report polish

## 5. Tickets Grouped By Area

### Execution inbox / approvals / rollback / audit

- T01 Build buyer-facing execution inbox page
- T02 Add approve / reject actions to execution inbox
- T03 Add execution run / retry / cancel / rollback controls
- T04 Add execution audit timeline to buyer UI
- T14 Add recommendation-to-execution creation action from opportunities
- T15 Add recommendation impact verification panel

### Expanded action plans / checklists / forecasting

- T25 Build the expanded location action portfolio
- T26 Add deterministic checklists, work routines, and persistent progress
- T27 Add action baselines, completion proof, and measurement readiness
- T28 Add action-linked forecast scenarios and outcome comparison

### Plain-language and visual experience

- T29 Build the plain-language and visual product system
- T30 Redesign Overview and Next Steps around owner decisions
- T31 Apply decision-useful visualization and simplified UX to every page

### Competitors

- T05 Add competitors page and nav exposure
- T17 Add competitor comparison cards to rankings and reports

### Citations

- T06 Add citations workflow page

### Content / topical authority

- T11 Build content authority workspace page
- T12 Add content QC and publish-readiness badges

### Reports scheduling / summaries

- T07 Add report schedule editor to reports page
- T08 Add report summary cards and delivery history
- T16 Add report summary narrative generation improvements
- T24 Add report-driven execution summary section

### WordPress execution provisioning / safety UX

- T09 Add WordPress execution setup status panel
- T10 Add execution safety confirmation UX for website mutations
- T22 Add execution-safe environment diagnostics page for WordPress plugin

### Backlinks / outreach

- T13 Add backlinks / outreach workspace page
- T21 Add outreach workflow stages and operator tasks

### Agency / portfolio support

- T18 Add provider credential and policy management polish
- T19 Add portfolio overview page for organization operators
- T20 Add report branding profile editor

## 6. Ticket Details Summary Matrix

| Ticket | Backend Dependency | Frontend Dependency | Risk | Feature Flag | Recommended Order |
|---|---|---|---|---|---:|
| T01 | executions APIs | opportunities page | Medium | No | 1 |
| T02 | approve/reject execution | T01 | Medium | No | 2 |
| T03 | run/retry/cancel/rollback execution | T01 | High | Yes | 3 |
| T04 | automation timeline + execution events | T01 | Medium | No | 4 |
| T05 | competitors APIs | new competitors page | Medium | No | 5 |
| T06 | citations APIs | new/expanded local SEO UI | Medium | No | 6 |
| T07 | report schedule APIs | reports page | Low | No | 7 |
| T08 | report detail + delivery data | reports page | Medium | No | 8 |
| T09 | provider credentials + plugin health | opportunities/platform pages | Medium | Yes | 9 |
| T10 | mutation-producing execution metadata | T01/T03 | High | Yes | 10 |
| T11 | content APIs | new content page | Medium | No | 11 |
| T12 | content QC events | T11 | Low | No | 12 |
| T13 | authority APIs | new authority page | Medium | Yes | 13 |
| T14 | execution creation path | opportunities page | Medium | No | 14 |
| T15 | execution outcome telemetry | T01 | Medium | Yes | 15 |
| T16 | reporting service enrichment | reports preview | Medium | No | 16 |
| T17 | competitor snapshots/gaps | rankings/reports pages | Low | No | 17 |
| T18 | provider credential/policy APIs | platform pages | Low | No | 18 |
| T19 | subaccount/location/business-location APIs | new platform page | Medium | Yes | 19 |
| T20 | new branding persistence | platform org detail + reports | Medium | Yes | 20 |
| T21 | outreach services | T13 | Medium | Yes | 21 |
| T22 | plugin telemetry | platform provider page | Medium | Yes | 22 |
| T23 | dashboard summary service | dashboard page | Low | No | 23 |
| T24 | execution telemetry | reports preview | Medium | No | 24 |
| T25 | canonical actions + recommendation evidence | opportunities page | Medium | Yes | 25 |
| T26 | T25 + lexicon action steps | T25 | Medium | Yes | 26 |
| T27 | T25-T26 + execution/outcome records | T26 | High | Yes | 27 |
| T28 | T25-T27 + forecast models | T27 | High | Yes | 28 |
| T29 | language guide + current shell | shared product components | Medium | Yes | after T26 |
| T30 | dashboard summaries + T25-T26 | T29 | Medium | Yes | after T29 |
| T31 | current route data | T29-T30 | Medium | Yes | after T30 |

## 7. Dependencies and Blockers

### Hard dependencies

- T01 before T02, T03, T04, T15
- T03 before T10
- T05 before T17
- T11 before T12
- T13 before T21
- T07 and T08 before T16 is fully worthwhile
- T09 before confident rollout of T03/T10 for WordPress mutation flows
- T25 before T26, T27, and T28
- T26 before T27
- T27 before T28; forecasts must attach to measurable action plans rather than
  standalone recommendations
- T26 before T30 so the redesigned Next Steps page is built on persistent work,
  not another temporary action-card layout
- T29 before T30 and T31 so language, icons, hierarchy, and chart behavior do
  not diverge by route
- T30 before T31 so the highest-traffic journey validates the system before a
  full cross-page rollout
- T31 before final T28 customer visualization and RPT1 polish so forecasts and
  reports reuse the same approved chart and explanation patterns

### Likely blockers

- WordPress provisioning and plugin credential state may be incomplete in many environments.
- Execution engine may need clearer API responses for UI-safe messaging in governance-blocked cases.
- Reporting persistence may not yet expose enough delivery-history detail for rich UI without minor backend additions.
- White-label branding requires new persisted brand profile fields if it is to go beyond documentation.
- Competitor/content/authority outputs may remain thin in low-data or synthetic-provider environments; UI must handle that honestly.

### Cross-cutting concerns

- all execution-related UI should be additive and gated where destructive actions exist
- recommendation status flow and execution status flow must remain distinct in copy and UI
- empty-state design matters because many campaigns will have sparse data early

## 8. Best First 10 Tickets To Execute

1. T01 Build buyer-facing execution inbox page
2. T02 Add approve / reject actions to execution inbox
3. T03 Add execution run / retry / cancel / rollback controls
4. T04 Add execution audit timeline to buyer UI
5. T14 Add recommendation-to-execution creation action from opportunities
6. T09 Add WordPress execution setup status panel
7. T10 Add execution safety confirmation UX for website mutations
8. T07 Add report schedule editor to reports page
9. T08 Add report summary cards and delivery history
10. T05 Add competitors page and nav exposure

Why this top 10:

- it closes the core operational loop first
- it makes automation safer before promoting it
- it adds reporting visibility after execution visibility
- it opens the next highest-value missing product area, competitors, immediately after the loop is closed
