# Post-UI Feature Fulfillment Ticket Backlog

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

## 5. Tickets Grouped By Area

### Execution inbox / approvals / rollback / audit

- T01 Build buyer-facing execution inbox page
- T02 Add approve / reject actions to execution inbox
- T03 Add execution run / retry / cancel / rollback controls
- T04 Add execution audit timeline to buyer UI
- T14 Add recommendation-to-execution creation action from opportunities
- T15 Add recommendation impact verification panel

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

## 7. Dependencies and Blockers

### Hard dependencies

- T01 before T02, T03, T04, T15
- T03 before T10
- T05 before T17
- T11 before T12
- T13 before T21
- T07 and T08 before T16 is fully worthwhile
- T09 before confident rollout of T03/T10 for WordPress mutation flows

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
