# Claude Next Build Brief

> **Active roadmap status (2026-08-03):** Release R1 is production-verified, and
> the TR1 security/recovery implementation is published. Tenant isolation,
> Windows-native recovery tooling, bounded key rotation, sanitized evidence
> capture, and deployment rollback controls are in place. The production
> frontend/API rollback-and-restore drill passed. TR1 remains a continuous
> release gate until the platform-owner operational capture, isolated Supabase
> restore drill, and live secret-rotation drills are completed and reviewed.
> **G1.3: Usage Economics and Margin Guardrails** is production-released;
> **I1.1: Live Website Performance and CWV Experience** is production-released;
> **I1.3: Governed AI Runtime API** is active and its first vertical slice is
> production-verified. It adds a
> Mistral-first, explain-only runtime over deterministic intelligence, strict
> structured-output validation, tenant-scoped audit history, and hard cost
> controls. **I1.5: Pluggable and Local Model Gateway** now preserves a future
> path for approved hosted, customer-owned, and local-model APIs without making
> the product depend on one vendor or weakening the intelligence contract. The
> **UX10-UX12, I1.4/T27, and I1.2/T28 are complete.** Supported website-speed
> action plans now store reproducible conservative, expected, and optimistic
> direct-metric forecasts and compare them with a genuinely new result after
> the observation window. Unsupported ranking, visit, lead, and revenue effects
> remain unknown. The bounded **I1.3 daily action brief is now implemented**:
> each location can receive up to three engine-approved actions with current
> checklist context and plain-language AI wording. The next I1.3 slice is
> evidence-based questions and answers.
> remaining roadmap
> targets a focused Semrush and BrightLocal replacement for local service
> businesses: provider truth and local operations in G1.2-G1.7 and DT1,
> evidence-backed intelligence in I1, research/content/AI visibility in
> MKT1-CNT1-AUTH1-AIV1, multi-location intelligence in ML1, commerce in COM1, and
> Enterprise/reporting in ENT1. Where Sections 7-10 conflict with Sections
> 1A-1C, Sections 1A-1C take precedence.

## 1. Executive Summary

This repo is in the phase where Codex should stop adding destinations and make the existing product easy to understand and operate.

The current truth from the audits and codebase:
- The platform is backend-heavy and product-thin.
- The tenant UI is no longer a raw scaffold. It now has working routes for dashboard, rankings, organic value, reports, opportunities, locations, local visibility, site health, competitors, and citations.
- Multi-location data and provider-backed ranking checks work, but active-location context is too subtle and portfolio data is mixed with location detail.
- Recent workflow-closure work already produced execution, reporting, competitors, and citations surfaces. Route existence is no longer the primary problem.
- The navigation exposes too many destinations at the same level, and page controls do not make the next action obvious.
- Local Visibility has a truthful base map but lacks a real rank-grid/heat-map layer, and Site Health still exposes too much technical language before explaining what matters.
- The backend already exposes a lot more than the frontend surfaces.
- The safest next phase is information-architecture and comprehension work on top of the existing routes, not new architecture.

Recommended build direction:
1. Make the current organization/location scope persistent, prominent, and consistent across every product page.
2. Separate portfolio comparison from individual-location detail on Rankings and make switching obvious.
3. Simplify the navigation into a small set of primary workflows with secondary tools grouped under More.
4. Rewrite Site Health around plain-language priorities and next actions.
5. Build a real location map before attempting a premium geo-grid layer.
6. Normalize DataForSEO locations from structured city/state/country data so customers never enter provider-specific strings.

This brief is optimized for safe execution. Codex should work sprint-by-sprint, preserve working behavior, avoid backend architecture rewrites, and keep truth states explicit.

## 1A. Active Customer UX Sprint Sequence

> **Execution status (2026-08-03):** UX5-UX9 established the working customer
> baseline, UX10 established the shared plain-language and visual system, and
> UX11-UX12 completed the owner-journey and cross-page rollout. The next
> customer product phase is I1.2 improvement forecasting and scenario modeling.
> Recommendation-only
> intelligence remains enabled; autonomous customer-site mutations and
> automatic policy updates remain disabled.

### Sprint 5 - Location Context and Navigation Clarity

Goal: a user always knows which location they are viewing and where to go next.

Scope:
- Add one persistent selector to the authenticated shell: `Viewing: All locations / [location name]`.
- Use the same selected-location state on Dashboard, Rankings, Local Visibility, Site Health, Competitors, Citations, Opportunities, and Reports.
- Persist the selection across navigation and make scope visible in page headings.
- Define two explicit modes:
  - **All locations** for portfolio comparison and rollups.
  - **One location** for detailed metrics, actions, and provider runs.
- Make portfolio rows clickable and switch directly into the chosen location.
- Simplify primary navigation to:
  - Overview
  - Rankings
  - Local Visibility
  - Site Health
  - Opportunities
  - Reports
- Group Locations, Organic Value, Competitors, and Citations under a clearly labeled secondary menu.
- Replace ambiguous `Refresh` labels with scoped labels such as `Reload saved data`, `Check for updates`, or `Run live check`.

Acceptance criteria:
- A first-time user can switch Reno/Lexington without discovering an unlabeled campaign control.
- The selected location remains active when moving between core pages.
- Every page states `All locations` or the selected location near its title.
- Reloading data never appears to be the way to switch locations.
- Desktop and mobile navigation expose the same hierarchy.

### Sprint 6 - Rankings and Site Health Comprehension

Goal: make two working data modules immediately understandable to a non-technical owner.

Rankings scope:
- Show the portfolio comparison only in **All locations** mode.
- Show individual rankings, tracked phrases, latest check time, and run controls only in **Location** mode.
- Add obvious `All locations`, `Reno`, and `Lexington` switching at the top of the workspace.
- Keep `Run live check` visually distinct from `Reload saved data`.
- Add plain-language summaries for page-one status, strongest phrase, and the next ranking opportunity.
- Add a portfolio location-comparison chart, current-position distribution, and per-phrase history using stored ranking snapshots.
- Add honest sparse-data states when there are not enough live checks to establish a trend.

Site Health scope:
- Lead with `Fix this first`, not raw issue groups.
- For every issue show:
  - What is wrong
  - Why it matters
  - What to do next
  - Priority
- Keep raw crawl terminology and affected-URL detail behind an expandable `Technical details` control.
- Add a clear next action for rescanning, reviewing affected pages, or creating an opportunity.
- Visualize current priority, affected-page concentration, and issue-count history without inventing an unsupported health score.
- Keep visual severity semantics consistent: urgent, next, monitor, and insufficient data.

Acceptance criteria:
- A business owner can identify the strongest and weakest phrase for one location without reading the portfolio table.
- A business owner can explain the top technical issue and next action without knowing crawl terminology.
- Every chart includes a plain-language interpretation and remains truthful with zero, one, or multiple stored checks.

### Sprint 7 - Intelligence Activation and Safety

Goal: turn the existing deep intelligence architecture into a safe, durable
recommendation system before presenting it as autonomous intelligence.

> **Completed and production-verified 2026-07-29:** Reno and Lexington each completed a serverless-safe stored-data cycle that generated two orchestrator recommendations and produced three active recommendations total per location. Repeat runs reused the same daily job without duplication. Both execution inboxes remained at zero, provider checks stayed off, both campaigns are Active, and the production API health check returned `ok`.

Scope:
- Add an explicit production activation mode that defaults to
  **recommendation only**.
- Run campaign intelligence from stored crawl, ranking, content, and local
  signals without triggering paid provider checks.
- Keep mutation scheduling and execution disabled during recommendation-only
  cycles.
- Tenant-scope every intelligence score, recommendation, simulation, metric,
  execution, and outcome query.
- Add a durable serverless cadence for active campaigns using the existing
  Vercel cron and database-backed job system.
- Persist idempotent signals, recommendations, simulations, and metrics so the
  engine can build history without duplicating work.
- Clearly distinguish the simple heuristic score/recommendation service from
  the deeper orchestrator pipeline in API truth metadata and the Opportunities
  UI.
- Capture recommendation-score checkpoints and run learning in
  **observation-only** mode until enough real outcomes exist to review
  recommendation quality.
- Do not update policies or make causal claims from observation-only outcomes.
- Require an explicit governance policy and human approval before any future
  execution mode can deliver a customer-site mutation.

Acceptance criteria:
- Reno and Lexington can complete a stored-data intelligence cycle through the
  serverless job runner.
- Recommendation-only cycles create no scheduled or completed mutations.
- Cross-tenant intelligence reads return `404`.
- Repeating the same scheduled cycle is idempotent.
- Every surfaced recommendation includes evidence, confidence, freshness, and
  an honest model/runtime label.
- Chosen recommendations can record deduplicated before/after score
  checkpoints with tenant-scoped history.
- Outcome history explicitly disables policy updates and causal claims.
- The test suite proves the safe activation mode, tenant isolation, durable
  scheduling, and unchanged Opportunities lifecycle behavior.

### Sprint 8 - Local Visibility Map and Provider Location Normalization

Goal: make Local Visibility a real location product rather than another summary page.

> **Completed and production-verified (2026-07-29):** Business locations now store structured geography, coordinates, coordinate precision/source, and DataForSEO location metadata. Reno resolves to DataForSEO location `1022653`; Lexington resolves to `1017818`. Both locations open an interactive OpenStreetMap reference map, switch independently, and clearly separate the base map from unavailable paid geo-grid coverage. Address misses fall back to a rate-limited, cached city-center lookup rather than presenting a false exact pin.

Scope:
- Store structured city, state/region, country, and coordinates on business locations.
- Resolve and store the DataForSEO location code/name automatically; never require a customer to enter an exact provider string.
- Add a working map centered on the selected business location.
- Show the business pin, address, and service-area context.
- Add honest empty and setup states when coordinates or local-provider data are missing.
- Add a provider-backed geo-grid/map-rank layer only after the base map and location normalization are reliable.
- Label base-map presence separately from paid map-ranking coverage.

Acceptance criteria:
- Reno opens on Reno and Lexington opens on Lexington without manual provider formatting.
- The map is interactive and location-specific.
- The UI never presents a decorative map as map-ranking intelligence.
- Paid geo-grid requests are explicit and budget-aware.

### Sprint 9 - Cross-Page UX and Visual Polish

Goal: remove remaining convolution after the core information architecture is stable, with the
primary reader defined as a service-business owner rather than an SEO operator.

> **Closing slice started 2026-07-29:** the Overview lead-in no longer reserves a
> tall empty column before the Search Console charts. Repeated `Good to know`
> panels are being replaced by at most one dismissible `InsightOS guide` per
> page. Reports remain outside this closing slice except for the shared guidance
> treatment.
>
> **Historical comparison slice completed 2026-07-30:** Overview Search Console
> visualizations now support 28-day, 3-month, 6-month, 12-month, and custom
> ranges, with previous-period, prior-year, custom-period, or no comparison.
> The stored-history target is now 480 days, and every chart reports actual
> coverage instead of presenting a partial comparison as complete.
>
> **Plain-language hierarchy completed and production-verified 2026-07-30:**
> all 11 customer routes now lead with a compact, route-specific `Start here`
> instruction and exactly one dismissible daily guide. The guide uses the
> governed AI brief, is cached once per location and day across the workspace,
> and falls back safely when AI is unavailable. Internal labels such as
> `Deterministic summary`, `Data status`, and `Live source` were removed from
> the customer reading flow. Next Steps now leads with one recommended action,
> while its explanation and progress details are collapsed until requested.
> The same progressive-disclosure treatment is applied to detailed report,
> settings, website-health, and workflow controls.

Scope:
- Rewrite customer-facing copy for a person who runs a local or multi-location service business.
- Lead every page with three owner questions:
  - What is happening?
  - Why does it matter to calls, leads, customers, or trust?
  - What should I do next?
- Prefer familiar labels such as `Search Rankings`, `Local Search`, `Website Health`,
  `Next Steps`, and `Directory Listings`.
- Keep terms such as provider, runtime, heuristic, crawl, geo-grid, citation, and execution
  inside optional setup or technical-detail areas unless the term is immediately explained.
- Never expose a provider name, internal state, or data classification as the main explanation.
- Standardize page introductions, scope labels, loading states, empty states, error messages, and action placement.
- Put the first useful chart, decision, or action directly under each page introduction; do not reserve empty grid space for a taller adjacent card.
- Limit proactive guidance to one dismissible guide per page. Do not stack repeated `Good to know`, freshness, or provider-explanation panels in the main reading flow.
- Keep source freshness in the shared trust/status surface and put troubleshooting detail behind an optional control.
- Reduce Website Health to one `Fix this first` decision, one plain-language next action, a compact visual summary, and expandable technical details.
- Remove duplicated provider setup panels from pages where setup is already complete.
- Consolidate repeated controls into shared components.
- Let owners change the date range directly above historical charts and compare
  against the previous period, the same dates last year, or independently chosen
  dates without leaving the page.
- Verify the full journey on desktop, tablet, and mobile.
- Run task-based usability checks:
  - switch locations
  - find one location's rankings
  - identify the first technical fix
  - open the local map
  - find the next recommended action

Acceptance criteria:
- Each task is discoverable without prior instruction.
- Primary navigation contains no dead ends or equally weighted low-priority tools.
- The interface uses plain language before technical detail.
- A service-business owner can explain the purpose of every primary navigation item without
  knowing SEO terminology.
- Every core page presents an owner-level explanation before data-source or system-state detail.
- Button labels describe the result the owner expects, not the internal process being triggered.
- No page renders more than one proactive guidance widget, and the user can dismiss it without losing the page's primary data or controls.
- Overview begins with live performance data when it exists and has no empty desktop column under the daily briefing.
- Website Health exposes the first fix and its next action before issue counts or technical terminology.
- Overview supports more than 14 days of Search Console history, labels both
  comparison periods, and discloses incomplete historical coverage.
- Visual polish follows the finalized hierarchy rather than masking an unclear workflow.

### Sprint 10 - Plain-Language and Visual Product System

Goal: give every customer-facing page one reusable visual and writing system
designed for a service-business owner, not an SEO technician.

> **Completed 2026-08-03:** the shared customer visual system now provides an
> original accessible SVG icon family for every product route, compact icon-led
> page headings and navigation, semantic trend arrows with words and color,
> compact metric strips, chart scope and legends, optional measurement details,
> and honest loading/empty/one-point/partial/stale/unsupported/error states. The
> service-business language guide is now v2 and is mirrored by the browser-side
> filter used for AI guidance and customer labels. Automated tests cover banned
> labels, route icon coverage, shared hierarchy, trend meaning, and chart-state
> support. The rollout flag is
> `NEXT_PUBLIC_CUSTOMER_VISUAL_SYSTEM_V2_ENABLED` and defaults on.

> **Customer review added 2026-08-03:** the working Next Steps page still uses
> too many equally weighted boxes, repeated actions, internal status labels,
> and phrases such as `governed location target`, `possible benefit`, and
> `deeper review`. The reference Ahrefs screenshot is useful for information
> hierarchy, compact icon navigation, and data visualization only. InsightOS
> must use its own icons, components, copy, and visual identity rather than
> reproducing Ahrefs.

Scope:
- Create a customer-language dictionary and prohibited-jargon list used by
  static UI copy, deterministic summaries, and AI-generated explanations.
- Target short sentences and a sixth-to-eighth-grade reading level. Explain the
  business result before naming an SEO method, provider, system state, or data
  limitation.
- Replace internal phrases with direct owner language. For example, prefer
  `Get more reviews from recent customers` over `Reach more eligible completed
  customers`, and `We need more information before estimating the result` over
  `Possible benefit — more evidence needed`.
- Add automated copy tests that reject banned internal labels in the primary
  customer reading flow and validate AI output against the service-business
  language guide.
- Define one shared page hierarchy: purpose and location, key result, primary
  visual, recommended action, supporting details, then optional technical data.
- Define an original, accessible icon family for navigation, page headings,
  metric types, actions, status, and empty states. Icons always have a text
  label or accessible name and are never the only carrier of meaning.
- Define shared metric, trend, chart, filter, comparison, details-drawer,
  tooltip, empty-state, and error-state components.
- Reduce decorative containers and badges. A box, divider, label, or status
  chip must communicate grouping, hierarchy, state, or an available action.
- Use green plus an up arrow for a beneficial increase, red plus a down arrow
  for a harmful decrease, and neutral treatment when direction is not good or
  bad. Never rely on color alone.
- Provide truthful chart states for no data, one point, partial history, stale
  data, and unsupported comparisons. Do not fabricate scores or trends.

Acceptance criteria:
- A shared language and component inventory covers every authenticated customer
  route before page-specific redesign begins.
- Primary customer copy contains no unexplained internal terms, provider names,
  model labels, policy labels, or evidence classifications.
- Every customer-visible AI message passes the same language checks as static
  UI copy and has a deterministic fallback.
- Navigation and page headings use original, consistent icons without copying
  Ahrefs artwork or layout.
- Shared chart components support location, date range, comparison period,
  source freshness, accessible legend, tooltip, loading, and sparse-data states.
- Removing a card, badge, or paragraph does not remove a customer decision,
  result, warning, or action.

### Sprint 11 - Overview and Next Steps Journey Redesign

Goal: make the two most important pages understandable above the fold and
remove the duplicated, console-like action experience shown in customer QA.

Scope:
- Redesign Overview as a daily business briefing: what changed, whether the
  change is good or bad, why it matters, and the one best next action.
- Put useful charts before secondary explanation. Show Google visits,
  visibility, ranking movement, and other supported business signals across a
  selectable date range with an honest comparison period.
- Use compact KPI rows with icons and directional arrows rather than placing
  every value inside a large card.
- Remove data-source, live-status, and freshness labels from the primary flow;
  keep them in one shared trust/details control.
- Redesign Next Steps around `Today`, `This week`, and `This month`, with a
  visible checklist and progress. Do not repeat the same recommendation in a
  spotlight, card row, full list, and detail panel at the same time.
- Replace `Recommended`, `Reviewed`, `Already handled`, `Deeper review`, and
  evidence-quality labels with owner-facing progress and decision language.
- Show action details in a focused drawer or progressive disclosure region:
  why it matters, what to do, effort, owner, proof, and expected review date.
- Show no unsupported overall score or oversized empty status card.

Acceptance criteria:
- At 1440×900, Overview shows the main results, first meaningful chart, and one
  next action without scrolling.
- At 1440×900, Next Steps shows cadence, checklist progress, and the next
  required step without the same action appearing in multiple competing areas.
- A service-business owner can describe what changed and what to do next after
  a five-second glance at either page.
- Every displayed metric answers a business question or supports a decision;
  internal status and diagnostic metadata remain optional.
- Desktop, tablet, and mobile task tests pass with keyboard and screen-reader
  labels intact.

Completion record (2026-08-03):
- Overview is now an owner briefing: what changed, why it matters, one action,
  compact Google results, and decision-useful comparison charts appear before
  optional progress, source, and manual-control details.
- Next Steps is now a cadence board plus one working checklist. The previous
  action spotlight and full console remain hidden or progressively disclosed
  instead of repeating the same recommendation across the primary screen.
- `NEXT_PUBLIC_OWNER_JOURNEY_V2_ENABLED` is default-on and preserves a bounded
  rollout control separate from the shared visual-system flag.
- The frontend contract covers responsive hierarchy, accessible checklist
  state, date comparison access, and optional technical details.

### Sprint 12 - Cross-Page Visualization and Usability Rollout

Goal: apply the approved UX10 system and UX11 hierarchy to every remaining
customer page, using visualization only where it helps the owner decide.

Scope by page:
- **Search Rankings:** position distribution, biggest movers, phrase history,
  location comparison, and clear `improving / slipping / unchanged` language.
- **Local Search:** location map or paid rank grid, keyword-specific results,
  coverage trend, and a clear run cost/allowance before a paid check.
- **Website Health:** current Core Web Vitals, issue concentration, history,
  `Fix this first`, and expandable affected-page and technical details.
- **Directory Listings and Reviews:** accuracy/completion progress, mismatches,
  review pace, location outliers, and the next correction or response.
- **Competitors and Search Value:** small, readable comparison charts and
  opportunity gaps; no dense SEO tables before the plain-language takeaway.
- **Locations:** portfolio comparison, outlier locations, shared problems, and
  one-click movement into the selected location.
- **Reports:** visual performance story, completed work, next actions, delivery
  status, and optional source/methodology details.
- **Settings and setup:** step-by-step connection health, allowance and usage
  visuals where useful, with no charts added merely for decoration.
- Audit every route for repeated guidance, oversized empty space, dead controls,
  unnecessary badges, duplicated data, and important content below the fold.

Acceptance criteria:
- Every authenticated customer route passes the same five-second comprehension
  test: page purpose, current result, trend or state, and next action are clear.
- Every data-heavy core page has at least one decision-useful visualization or
  a documented reason why a chart would mislead.
- Every visualization supports date and location scope when the underlying data
  supports them and explains partial or missing history honestly.
- No core page requires technical SEO knowledge to understand its first screen.
- Visual regression and task-based tests cover desktop, tablet, and mobile for
  every primary route.

Completion record (2026-08-03):
- Every remaining customer page now uses the compact purpose-and-start pattern
  so the current result appears higher on desktop and mobile.
- Website Health, Directory Listings, Competitors, Search Value, Locations,
  Reports, and Data Connections lead with a shared owner decision panel that
  states the result, business meaning, and real next action.
- Listings, Locations, Reports, and Connections use accessible progress visuals;
  Search Value adds a readable scenario comparison; existing Rankings, Local
  Search, and Website Health charts and maps remain tied to real data.
- Duplicate Website Health and Reports summary panels were removed, Locations
  setup is progressively disclosed, and provider/runtime detail remains
  optional instead of competing with the primary decision.
- Cross-page source contracts cover compact hierarchy, one dismissible guide,
  decision visuals, accessible progress state, and removal of duplicated
  console-style summaries.

## 1B. Roadmap Tracks and Next Product Phase

Sprint numbers in older documents refer to different bodies of work. Use these
names in issues, commits, and status reports so a number is never ambiguous:

- **Platform P1-P10:** the historical platform-foundation sequence in
  [product_overview/sprint_roadmap.md](./product_overview/sprint_roadmap.md).
- **Customer UX UX1-UX12:** the active usability and productization sequence in
  Section 1A and [ui-ux-productization-plan.md](./ui-ux-productization-plan.md).
- **Production Readiness PR0-PR6:** cross-cutting deployment, security, provider,
  and release gates in
  [production-readiness-roadmap.md](./production-readiness-roadmap.md).
- **Growth G1+:** customer data and outcome product phases that begin after UX9
  meets its acceptance criteria.

### Recommended Execution Order From The Current State

This is the default delivery order as of 2026-08-03. Track identifiers below
remain stable even if a release needs to split one scope into smaller tickets.

| Order | Sprint | Customer result |
| ---: | --- | --- |
| 1 | **Release R1 - UX9 and I1.0 production closeout** | The current UX polish and canonical intelligence lexicon are migrated, configured, activated, and verified in production. |
| 2 | **TR1 - Security, Reliability, and Recovery Gate** | Tenant isolation, durable execution, monitoring, backups, restore drills, and safe release controls are proven before paid automation expands. |
| 3 | **G1.3 - Usage Economics and Margin Guardrails** | Paid provider and AI work cannot overspend the organization's allowance or silently damage gross margin. |
| 4 | **I1.1 - Live Website Performance and CWV Experience — released** | Customers see their actual field and lab website measurements, Google thresholds, history, source, freshness, and plain-language meaning. |
| 5 | **I1.3 - Governed AI Runtime API — active** | Mistral-first AI becomes standard across plans and can explain, prioritize, draft, and answer questions from the deterministic evidence packet without inventing facts or actions. |
| 6 | **I1.4 - Expanded Action Plans, Guided Checklists, and Work Routines** | Customers receive multiple prioritized action plans, plain-language checklists, and clear Daily, Weekly, and Monthly work routines. |
| 7 | **UX10 - Plain-Language and Visual Product System** | Every page and AI explanation uses service-owner language, original icons, consistent hierarchy, and shared accessible visualization components. |
| 8 | **UX11 - Overview and Next Steps Journey Redesign** | The two highest-traffic pages become glanceable, action-oriented, visual, and free of duplicated console-style panels. |
| 9 | **UX12 - Cross-Page Visualization and Usability Rollout** | Rankings, Local Search, Website Health, Listings, Reviews, Competitors, Locations, Reports, Settings, and setup states receive the same understandable hierarchy. |
| 10 | **I1.4/T27 - Action Measurement Readiness — completed** | Starting measurements, completed-work proof, success measurements, and honest waiting periods make a checked box different from a proven result. |
| 11 | **I1.2/T28 - Improvement Forecasting and Scenario Modeling — completed** | Supported action plans add conservative improvement ranges and compare them with the eventual measured result. |
| 12 | **I1.3 remaining slices - Governed AI Utility Expansion — daily brief completed** | Evidence-based questions and answers and governed drafting make AI useful beyond the completed three-action daily brief while the deterministic engine keeps authority. |
| 13 | **MKT1.1 - Automated Local Keyword Discovery** | Each location receives useful keyword ideas, demand data, intent, and tracking recommendations without recurring manual entry. |
| 14 | **G1.2 - Local Search Rank Grid** | Each location can run and view its own paid, allowance-controlled local ranking heat map. |
| 15 | **G1.4 - Google Business Profile Intelligence** | Owners can audit and improve the correct profile, categories, services, content, and local competitor position for each location. |
| 16 | **G1.5 - Listings and Citation Intelligence** | Missing and inconsistent listings become a verified correction workflow rather than a static score. |
| 17 | **G1.6 - Reputation Management** | Review monitoring, response work, request routines, and multi-location comparisons replace the core BrightLocal reputation workflow. |
| 18 | **DT1 - Data Trust and Connection Health Center** | Every provider connection exposes freshness, last success, failures, affected locations, and a plain recovery action in one place. |
| 19 | **ML1 - Portfolio Intelligence** | The $699 multi-location experience identifies outliers, shared problems, reusable wins, and bulk work before that plan is sold broadly. |
| 20 | **PA1 first slice - Activation and Value Measurement** | The team measures onboarding, first verified value, action completion, AI usefulness, and forecast trust before expanding further. |
| 21 | **RPT1 - Premium Reporting and Delivery** | Owners receive polished, visual, scheduled reports that explain progress, completed work, measured results, risks, and next actions. |
| 22 | **ALT1 - Alerts, Notifications, and Digests** | Customers learn about meaningful changes and failures without repeatedly checking every page. |
| 23 | **CX1 - Guided Onboarding, Education, and Support** | A non-technical owner can connect data, reach first value, understand the product, and recover from setup problems without operator help. |
| 24 | **COM1 paid-beta slice - Checkout and Plan Enforcement** | Invite-only customers can subscribe, understand allowances, recover payment, and cancel without operator database work. |
| 25 | **G1.7 - Website Analytics and Form Events** | Website visits and form outcomes connect to the location without adding CRM or call-tracking scope. |
| 26 | **MKT1.2 - Competitor and Content-Gap Research** | Owners can find real local competitors, keyword gaps, and content opportunities without moving between tools. |
| 27 | **CNT1 - Content and On-Page Workspace** | Research and intelligence produce governed page, content, metadata, schema, and internal-link work. |
| 28 | **AUTH1 - Backlink and Local Authority Intelligence** | New and lost referring domains, competitor link gaps, local authority opportunities, and outreach work close a major Semrush replacement gap. |
| 29 | **WP1.1 - WordPress Connection and Safe Site Control** | The existing WordPress path becomes a hardened, observable, reversible production integration. |
| 30 | **WP1.2 - WordPress Managed Autopilot** | Approved policies can safely implement bounded content and on-page changes without routine customer editing. |
| 31 | **MIG1 - Semrush/BrightLocal Migration** | New customers can bring supported locations, phrases, competitors, listing facts, and historical files into the platform without starting over. |
| 32 | **GOV1 - Data Privacy, Retention, and Portability** | Customers can understand, export, retain, disconnect, and delete their data through governed workflows. |
| 33 | **SEO2 - Advanced Search and Site Integrity** | The product closes additional Semrush-class gaps in indexation, SERP features, entities, content decay, cannibalization, and technical integrity. |
| 34 | **I2 - Outcome Learning and Controlled Experiments** | Forecasts and recommendations improve from verified outcomes under minimum-sample, calibration, approval, and rollback controls. |
| 35 | **AIV1 - AI Search and Entity Visibility** | The product measures visibility across supported AI-answer surfaces. |
| 36 | **COM1 full release - Billing, Entitlements, and Self-Service Accounts** | The commercial plans, roles, active-location allowances, and subscription lifecycle become fully self-service. |
| 37 | **OPS1 - Customer Support and Launch Operations** | Support, demos, status communication, escalation, onboarding playbooks, and release evidence are ready for a paid launch. |
| 38 | **I1.5 and ENT1 - Enterprise Model Gateway, API, White Label, and Reporting** | Enterprise customers receive customer-owned/local-model connectivity, advanced roles, API/export, white label, custom limits, and durable reporting. |

Release R1 is complete as of 2026-07-30. The I1.0 migration is applied, hosted
CrUX configuration is active, the API is deployed, the first standards check
is stored as `current`, and CI plus production health verification passed.

TR1 is a continuous release gate as well as an ordered sprint. Its controls
must remain green while later sprints add provider calls, AI, customer data, or
website mutations.

### Trust TR1 - Security, Reliability, and Recovery Gate

Goal: prove that the hosted Supabase and Vercel system can protect customer
data, recover safely, and run durable work before paid automation expands.

> **Implementation status (2026-07-30):** TR1 is in closeout. PostgreSQL RLS,
> transaction-local tenant context, rotating and revocable sessions, durable
> database-backed job health, and the PostgreSQL isolation gate are active.
> The closeout slice adds zero-downtime JWT and credential-key transitions,
> atomic credential rewrapping, a rollback-only behavioral RLS restore probe,
> sanitized operational evidence capture, Windows-native drill commands, and a
> manual GitHub drill workflow. Revision `20260730_0077` is applied in
> Supabase, RLS enforcement is active in Vercel, the production API health and
> two-location customer journey are green, and the local backend regression is
> 602 passed with 16 environment-specific skips. The closeout slice still
> requires published CI plus isolated Supabase restore, live secret-rotation,
> and Vercel deployment-rollback evidence before TR1 is marked complete.

Scope:

- Complete least-privilege database access, tenant context, explicit RLS
  policies, and cross-organization read/write tests.
- Replace weak privileged browser-token handling with the approved safer
  session model; add invitations, password recovery, session revocation, and
  organization switching.
- Require idempotency, retry classification, dead-letter state, visible job
  status, and duplicate-invocation tests for scheduled and paid work.
- Add server-side rate limits, secret rotation procedures, audit coverage,
  input/output safety, dependency and secret scanning, and privileged-action
  alerts.
- Configure production metrics, structured logs, traces, provider and delivery
  health, stale-data detection, and actionable alert routing.
- Prove Supabase backup/PITR behavior with a documented restore drill and
  post-recovery tenant-integrity checks.
- Add PostgreSQL integration CI, critical Playwright journeys, Vercel smoke
  tests, compatible migration sequencing, load checks, and release rollback.

Acceptance criteria:

- Automated tests prove one tenant cannot read, write, execute, export, or
  receive another tenant's data.
- A duplicate job or provider callback cannot duplicate a paid or mutating
  operation.
- Backup restoration, deployment rollback, secret rotation, and incident
  response have current evidence from a production-like environment.
- A critical provider, queue, delivery, authentication, or data-freshness
  failure alerts an operator and produces an honest customer-visible state.
- TR1 failures block the release of later paid, AI, or WordPress automation.

### Growth G1 - Automated Data Connections

Goal: replace recurring manual data entry with trustworthy, tenant-safe, and
location-aware connections for the signals the current product can use.

> **Implementation status (2026-07-29):** Slice G1.1 is implemented and
> production-connected: a customer Data Connections page, signed Google OAuth
> return flow, per-location Search Console property mappings, initial backfill,
> durable scheduled synchronization, and owner-facing charts are live. Google
> Business Profile, local rank-grid collection, website analytics/form-event
> synchronization, and generalized spend controls remain later G1 slices.

In scope:

- Google Search Console connection and scheduled synchronization.
- Google Business Profile connection and scheduled profile, review, and local
  signal synchronization.
- Website analytics and website form-conversion events, using an approved
  analytics/event source selected during technical design.
- An organization-owner connection flow with truthful connected, syncing,
  current, stale, failed, and reconnect-required states.
- Explicit mapping from each external property/profile to its organization,
  subaccount, business location, website, and campaign.
- Initial backfill followed by durable, idempotent scheduled synchronization
  through the Supabase-backed job runner.
- Retry classification, deduplication, freshness timestamps, source labels,
  audit history, tenant isolation, and user-visible sync health.
- Customer-facing summaries that work without asking the business owner to
  create recurring rows or copy provider data manually.

Explicitly deferred from G1:

- Call-tracking providers, call recordings, call transcripts, and call
  attribution.
- CRM connections or synchronization.
- Field-service and job-management systems.
- Booked-job, estimate, pipeline, payment, or revenue imports.
- Sales and revenue attribution models.
- Autonomous execution, automatic policy updates, or causal claims based on the
  new signals.

G1 acceptance criteria:

- An organization owner connects each approved source once and subsequent
  synchronization runs automatically.
- Reno and Lexington can be mapped and viewed independently without blended
  location data.
- Backfill and scheduled jobs are safe to retry and do not create duplicate
  events or snapshots.
- Every customer-visible metric identifies its source and freshness, and failed
  or stale connections provide a clear recovery action.
- Cross-organization connection metadata and synchronized data remain
  inaccessible.
- No call-tracking, CRM, job-management, booked-job, payment, revenue, or sales
  attribution connector, endpoint, job, or schema is added in this phase.

### Growth G1.2 - Local Search Rank Grid

Goal: let an owner run a truthful heat map for one location and one or more
tracked search phrases without exposing provider mechanics or allowing
unbounded paid checks.

Scope:

- Use the selected business location's stored coordinates and DataForSEO
  location metadata; never blend grid points between locations.
- Let the owner choose tracked phrases, grid size, and search radius, with a
  safe default of a small grid and the standard queued provider method.
- Create one durable, idempotent job per grid run and persist the run, phrase,
  point coordinates, rank, matched business, source, freshness, and provider
  task identifiers.
- Render an interactive map whose point colors have one stable meaning:
  positions 1-3, 4-10, 11-20, 21+, and not found.
- Show the exact number of checks and estimated platform cost before the owner
  confirms a run.
- Reserve estimated usage before dispatch, reconcile it against the
  provider-reported cost, and release the reservation on terminal failure.
- Apply organization, tier, location, monthly-usage, and credential-owner
  checks before any paid provider call.
- Use the organization's own DataForSEO credentials without charging platform
  provider spend, while still recording task volume and enforcing safety-rate
  limits.
- Keep the current base map visually and semantically separate from rank-grid
  results.
- Do not add report automation, call tracking, CRM, job-management, payment, or
  revenue work in this slice.

Acceptance criteria:

- Reno and Lexington can run and view independent maps for the same phrase.
- A 5x5 grid for two phrases produces 50 location-specific points and no
  duplicate provider work when the same idempotency key is retried.
- The confirmation screen states the grid dimensions, phrase count, total
  checks, estimated cost, remaining allowance, and expected completion mode.
- Platform-paid checks stop before dispatch when the organization's hard
  allowance would be exceeded.
- Failed provider tasks do not remain charged as completed spend.
- Sparse, pending, stale, and not-found points are visually distinct and
  explained in owner language.

### Growth G1.3 - Usage Economics and Margin Guardrails

Goal: know the true variable cost of each organization and prevent platform-paid
providers or future AI models from pushing the service below its target margin.

> **Implementation status (2026-07-30):** G1.3 is production-released. Revision
> `20260730_0078` adds versioned provider price cards, an
> append-only and tenant-isolated reservation/reconciliation ledger, versioned
> non-provider cost allocations, canonical Solo/Multi-location/Enterprise plan
> economics, and generic model/token fields before a paid LLM is enabled. The
> current platform-paid DataForSEO rank path reserves its depth- and
> operator-adjusted maximum before dispatch, reconciles the provider-reported
> task cost, and releases failed reservations. Paid-capable rank backends
> without an active price card fail closed. Organization-owned credentials are
> recorded but excluded from platform COGS. Customer Settings shows only paid
> data allowance and recovery guidance; the platform organization view shows
> revenue, API spend, allocated COGS, gross profit, gross margin, and the 85%
> heavy-use publication test. Local migration validation, focused backend
> tests, the uncapped suite tail, Ruff, frontend tests/lint, and the production
> frontend build are green. Supabase migration run `#10` applied the revision;
> Backend run `#151` and CI run `#291` passed; Vercel API deployment
> `FoHtmCxKrpwRP3w8ToMuE676VWKx` and frontend deployment
> `9knRiaDgyRVQFDx9gWzJXUzNxYC9` reached Production/Ready; and the production
> API health endpoint returned HTTP 200. The only deferred observation is an
> authenticated visual smoke of the customer allowance card: the existing
> browser session expired, so this requires a fresh customer login and does not
> block the deployed server-side allowance enforcement.

Current truth:

- Production intelligence is heuristic/orchestrator code and does not currently
  call a paid LLM, so there is no production AI-token cost to meter today.
- The repository already counts entitlements, provider executions, portfolio
  usage, and provider quota state, but it does not record provider-reported
  currency cost, credential ownership, reservations, or realized margin.
- Queue `tokens_per_minute` are rate-limit tokens, not billable AI tokens.

Scope:

- Add an append-only cost ledger with organization, location, campaign,
  provider, capability, operation, credential owner (`platform` or
  `organization`), quantity, unit, estimated cost, provider-reported cost,
  currency, status, idempotency key, and reconciliation timestamps.
- Add generic AI usage fields before any paid LLM is enabled: provider, model,
  input tokens, cached-input tokens, output tokens, and price-card version.
- Version provider/model price cards so historical margin does not change when
  vendor prices change.
- Add soft warnings at 50%, 75%, and 90% of the platform-paid allowance and a
  hard pre-dispatch stop at 100%.
- Count organization-owned credentials for operational safety and product-tier
  limits, but exclude their vendor cost from platform COGS.
- Add an internal margin view showing revenue, platform-paid API cost, hosting,
  storage, email, other allocated COGS, gross profit, and gross margin by
  organization and tier.
- Cap the platform-paid API budget at 5% of plan revenue while reserving 10%
  for hosting, storage, email, and other software COGS. Payroll, human support,
  marketing, taxes, and general overhead are outside this product-usage margin
  calculation. The 85% software-usage margin floor is a hard publication gate.
- Keep these controls internal; customer-facing UI shows allowance and recovery
  actions, not internal margin.

Margin guardrail:

`maximum total COGS = monthly revenue × (1 - target gross margin)`

| Plan | Monthly revenue | Total software COGS ceiling at 85% margin | 5% platform-API budget |
| --- | ---: | ---: | ---: |
| Solo | $299 | $44.85 | $14.95 |
| Multi-location | $699 | $104.85 | $34.95 |
| Enterprise starting point | $1,999 | $299.85 | $99.95 |

Pricing decision:

- Solo is `$299/month` and includes one active location.
- Multi-location is `$699/month` and includes up to ten active locations.
- Enterprise starts at `$1,999/month`, includes 11-20 active locations by
  default, and uses custom per-location pricing above 20 or when its approved
  user, provider, data-volume, or support allowance is exceeded.
- An active location is one that receives scheduled scans, rankings, local
  maps, reports, AI actions, or connected-data synchronization. Stored
  inactive locations do not consume the active-location allowance.
- Agency workflows are packaged inside Enterprise rather than maintained as a
  separate fourth public tier.

Acceptance criteria:

- Every platform-paid provider operation has an estimated, reserved, and
  reconciled currency cost.
- Every organization-owned provider operation is distinguishable and excluded
  from platform vendor COGS.
- No provider or future LLM task can dispatch after the applicable hard
  allowance is exhausted.
- Internal reporting calculates realized gross margin from versioned price
  cards and provider-reported cost without retroactively changing prior months.
- A tier cannot be published unless its modeled software and provider usage
  remains at or above the 85% margin floor under the approved heavy-use
  scenario.

### Growth G1.4 - Google Business Profile Intelligence

Goal: replace manual GBP audits with a connected, location-aware profile
workspace that explains what is incomplete, what changed, and what to improve.

Scope:

- Map one Google Business Profile to the correct organization, subaccount,
  business location, website, and campaign.
- Synchronize the profile identity, primary and secondary categories, services,
  hours, special hours, address/service area, phone, website, attributes,
  description, photos, posts, and supported performance metrics.
- Audit profile completeness, category fit, NAP consistency, service-area
  coverage, hour accuracy, photo freshness, and posting cadence.
- Compare supported profile attributes with the businesses that repeatedly
  outrank the location in local rank-grid results.
- Turn audit findings into evidence-backed recommended actions.
- Allow profile edits, posts, and other supported mutations only through an
  explicit review and approval workflow. No automatic profile mutation is
  enabled by default.
- Preserve profile snapshots so the customer can see what changed and whether
  visibility improved afterward.

Acceptance criteria:

- Each location is mapped to one verified profile without cross-location
  blending.
- Missing or unsupported fields are labeled honestly rather than scored as
  failures.
- Every audit recommendation identifies the profile field, evidence, expected
  benefit, and owner action.
- A profile mutation cannot run without an authorized connection, explicit
  approval, audit history, and rollback/recovery guidance where the provider
  supports it.

### Growth G1.5 - Listings and Citation Intelligence

Goal: replace BrightLocal-style citation tracking and listing management with a
truthful inventory, consistency audit, and approval-driven correction workflow.

Scope:

- Connect an approved production listings/citation provider; synthetic authority
  data remains test-only.
- Discover listings for each physical location and normalize business name,
  address, phone, website, categories, hours, and status.
- Classify listings as correct, inconsistent, missing, duplicate, submitted,
  live, verified, or unavailable without treating submission as publication.
- Show directory importance, confidence, last verification time, source link,
  and the exact field differences that need correction.
- Prioritize listing work by business impact instead of presenting one flat
  directory checklist.
- Support approval-driven listing creation, correction, suppression, and
  verification when the selected provider or directory allows it.
- Track provider cost and per-location allowance for paid submission or
  correction work.
- Keep citation building pay-as-you-go or explicitly allowance-backed; never
  hide third-party directory fees inside an unlimited action.

Acceptance criteria:

- A user can see which listings are actually live, which are only submitted,
  and which contain conflicting business details.
- A correction is tenant- and location-scoped, idempotent, auditable, and
  cost-confirmed before dispatch.
- Portfolio views identify consistency problems shared across locations without
  merging the underlying listing records.

### Growth G1.6 - Reputation Management

Goal: replace BrightLocal-style review monitoring, response, generation, and
multi-location reputation reporting while adding an intelligence layer.

Scope:

- Ingest reviews from Google and other approved sources with source, rating,
  text, author metadata allowed by the provider, response status, and freshness.
- Provide one review inbox with location, source, rating, theme, sentiment,
  response status, and date filters.
- Allow approved direct replies where provider APIs permit them; otherwise
  provide a direct source link and track completion.
- Generate response drafts and reusable templates, but require human review by
  default and clearly label AI-generated text.
- Detect recurring customer themes, urgent negative-review patterns, unanswered
  reviews, rating changes, and review-velocity gaps against local competitors.
- Add compliant email, SMS, link, QR, and kiosk review-request campaigns with
  consent, suppression, delivery, and cost controls.
- Do not implement review gating, selective suppression of negative customers,
  fabricated reviews, or other platform-policy violations.
- Add optional brand-controlled website widgets for selected reviews.
- Add a multi-location reputation overview with leaderboards, outlier alerts,
  campaign performance, recent-review velocity, response time, and average
  rating.

Acceptance criteria:

- New reviews are synchronized durably and cannot duplicate on retry.
- A user can find and respond to an unanswered review without leaving the
  active location context when direct response is supported.
- Review-request campaigns show audience, channel cost, consent state,
  delivery, feedback, and resulting public-review activity.
- Intelligence recommendations cite the review evidence and never infer a
  customer outcome that has not been observed.

### Growth G1.7 - Website Analytics and Form Events

Goal: connect website behavior to search visibility without introducing the
deferred CRM, call-tracking, job-management, payment, or revenue scope.

Scope:

- Complete Google Analytics connection and per-location property/stream mapping.
- Ingest sessions, engaged sessions, landing pages, source/medium, and approved
  conversion events.
- Add a first-party website form event contract with tenant, location, website,
  page, event name, and deduplication identifiers.
- Join Search Console, ranking, crawl, local, and website-event facts at the
  location and date level without claiming sales attribution.
- Surface search-to-visit and visit-to-form trends, data freshness, and broken
  tracking alerts.

Acceptance criteria:

- Reno and Lexington remain independently mapped through Search Console,
  Analytics, and form-event facts.
- Duplicate backfills and retries do not duplicate daily metrics or form events.
- Customer-visible language says `website forms` or `inquiries`, not revenue or
  booked jobs.
- No call-tracking, CRM, field-service, payment, or revenue connector is added.

### Trust DT1 - Data Trust and Connection Health Center

Goal: make source freshness and connection recovery obvious without filling
every customer page with provider and runtime badges.

Scope:

- Add one tenant- and location-scoped connection inventory for Search Console,
  Analytics, GBP, rankings, local grid, listings, reviews, website performance,
  forms, WordPress, and approved AI providers.
- Show the last successful update, newest usable data date, current failure,
  affected locations/features, allowance state, and one plain recovery action.
- Keep healthy details compact; elevate only stale, broken, unmapped, or
  allowance-blocked sources into the owner's primary workflow.
- Feed connection failures into ALT1 and exclude stale or failed sources from
  forecasts, AI evidence, reports, and outcome claims according to policy.

Acceptance criteria:

- An owner can identify and begin fixing every broken customer data connection
  from one page without reading logs or provider terminology.
- Every customer metric can link back to the relevant source status and newest
  usable evidence date.
- A disconnected or stale provider cannot silently produce a current-looking
  recommendation, forecast, report, or measured result.

## 1C. Competitive Replacement Product Sprint Sequence

The following sprints begin after the applicable G1 provider truth is reliable.
Their purpose is to replace the useful local-business workflows of Semrush and
BrightLocal without copying their tool sprawl.

### Intelligence I1.0 - Canonical Lexicon and Standards Governance

Goal: make one deterministic, versioned knowledge system the source of truth
for diagnostics, actions, standards, evidence, and bounded AI explanations.

Implementation status:

- Foundation implemented 2026-07-29.
- The built-in `verix.seo.intelligence` v1 bundle now governs 40+ signals,
  current Core Web Vitals and supporting metrics, 15 diagnoses, 35+ actions,
  source provenance, plain-language terms, and the existing policy mappings.
- Tenant-active Reference Library artifacts can persist and supply the
  intelligence lexicon; the built-in validated pack remains the last-known-good
  fallback.
- The orchestrator records lexicon identity/version with recommendations and
  resolves legacy diagnostic language from the lexicon.
- A Vercel-compatible durable standards job compares the active built-in CWV
  thresholds with official CrUX histogram boundaries. Drift requires review
  and a new explicit activation; it never changes production rules silently.
- A provider-neutral AI decision contract limits models to verified facts,
  deterministic assessments, known diagnoses, and allowed actions.

Remaining productization:

- Connect production CrUX URL/origin and form-factor collection to Website
  Health with explicit URL/origin fallback labels.
- Add Lighthouse/PSI lab diagnostics with Lighthouse version and environment
  metadata, while keeping CrUX as field truth.
- Expand the lexicon as G1.2-G1.7 providers land for geo-grid, GBP, listings,
  reviews, analytics, and form-event evidence.
- Add a platform evidence/lexicon viewer, proposed-version diff, replay report,
  approval, activation, and rollback UI.
- Calibrate internal heuristics only after minimum sample and governance gates;
  never relabel them as Google standards.

Acceptance criteria:

- Unknown or duplicate signal, metric, diagnostic, policy, action, or source
  references fail validation.
- LCP, INP, and CLS are evaluated at p75 with exact boundary semantics; all
  three must be good to pass and missing data stays unknown.
- TTFB remains supporting evidence and is never labeled a Core Web Vital.
- Every generated recommendation records its lexicon version.
- AI cannot select an action outside the deterministic allow-list or overwrite
  evidence, risk, approval, and insufficient-data states.
- Official threshold drift creates `review_required`, never automatic
  production activation.

Reference:

- [platform/intelligence_lexicon.md](platform/intelligence_lexicon.md)

### Intelligence I1.1 - Live Website Performance and CWV Experience

Goal: turn the canonical Core Web Vitals rules into a clear, continuously
measured customer experience instead of another technical scorecard.

Scope:

- Collect production Chrome UX Report field data by URL or origin and form
  factor, using explicit URL-to-origin fallback labels.
- Collect PageSpeed Insights/Lighthouse lab diagnostics separately with tool
  version, test environment, run timestamp, source, and freshness.
- Persist measured LCP, INP, CLS, supporting TTFB, distribution, sample
  availability, measurement window, threshold version, and pass state.
- Compare every value with the active lexicon standard and show `good`,
  `needs work`, `poor`, or `not enough real-user data`; never convert missing
  field data into a passing result.
- Replace dense Website Health text with an accessible visual experience:
  current value, target band, distance from target, historical trend,
  mobile/desktop control, affected URL group, and plain-language explanation.
- Separate real-user field data from one-time lab diagnostics visually and in
  copy.
- Turn deterministic failures into lexicon-backed recommendations with
  evidence, likely technical cause, owner-friendly meaning, effort, risk, and
  validation steps.
- Schedule collection through the durable job runner with tenant-safe
  deduplication, retry handling, provider allowance checks, and visible sync
  health.

Acceptance criteria:

- A business owner can tell in under 30 seconds whether the site passes each
  Core Web Vital, what the current value is, what Google considers good, and
  what to do next.
- The page clearly distinguishes field data, lab data, URL data, origin
  fallback, mobile, desktop, freshness, and insufficient-data states.
- Every threshold is supplied by the active versioned lexicon and every stored
  result records that version.
- Charts remain usable on mobile, do not rely on color alone, and provide
  exact accessible values.
- No UI claims that passing Core Web Vitals guarantees a ranking improvement.

Production evidence (2026-07-30):

- Database revision `20260730_0079` is applied in Supabase with tenant-scoped
  RLS for persisted field and lab measurements.
- Commits `4d7ddff` and `04b226c` are deployed to the Vercel frontend and API.
- The production Reno desktop test returned Lighthouse `96/100` using version
  `13.4.1`; the largest reported opportunity was unused CSS.
- Google Chrome UX Report did not have enough Reno traffic for a field result.
  The product correctly shows `not enough real-user data`, the origin fallback,
  and the active lexicon thresholds instead of reporting a false pass.
- The Google key is restricted to the Chrome UX Report and PageSpeed Insights
  APIs. Manual retries are safely deduplicated while allowing a new test after
  provider configuration changes.

### Intelligence I1.2 - Improvement Forecasting and Scenario Modeling

> **Completed 2026-08-03:** T28 adds the tenant-scoped
> `action_plan_forecasts` artifact with database-enforced immutable model inputs,
> RLS, model and lexicon versions, hashes, assumptions, data quality, and outcome
> comparisons. Approved deterministic models cover render-blocking work, LCP
> resource priority, server response, browser main-thread and interaction work,
> layout-space reservation, and dynamic-content stability when a real CrUX
> field baseline and defined scope exist. The Next Steps visual compares the
> saved starting point, active target, conservative, expected, optimistic, and
> eventual observed values while explicitly withholding ranking, visits, leads,
> and revenue claims. Unsupported or insufficient plans persist an honest
> `not available` artifact instead of a number.

Goal: show what could reasonably improve if recommended work is completed,
without presenting a guess as a guaranteed Google or business outcome.

Scheduling decision:

- Build this after the I1.4 action-plan portfolio, checklist, and baseline slices.
  A forecast belongs to a defined action plan with known scope, success metrics,
  and an observation window; it must not be generated beside a vague one-line
  recommendation.
- Start with directly measurable outcomes such as Core Web Vitals, crawl issue
  counts, listing completeness, review-response coverage, and tracked keyword
  visibility. Do not estimate rankings, visits, leads, or revenue without a
  separately validated model and sufficient customer evidence.

Scope:

- Capture an immutable baseline for the affected URLs, metrics, device class,
  traffic segment, evidence window, action-plan version, and lexicon version.
- Add deterministic intervention models for supported actions such as image
  optimization, render-blocking resource reduction, server-response
  improvement, layout-shift correction, and JavaScript interaction work.
- Produce conservative, expected, and optimistic metric ranges rather than one
  false-precision number.
- Display `current`, `target`, and `forecast range` on the same chart with the
  assumptions, confidence, data coverage, and expected observation window.
- Forecast the directly affected technical measurement first. Ranking, traffic,
  inquiry, or revenue impact remains `unknown` unless separately supported by
  sufficient observed evidence.
- Recalculate scenarios when the baseline, recommendation, active standard, or
  implementation scope changes.
- Compare forecast with post-change measurements and record `within range`,
  `outside range`, or `insufficient data` so future models can be calibrated
  under governance.
- Store forecasts as versioned plan artifacts with the metric, baseline, target,
  conservative/expected/optimistic ranges, assumptions, data quality, model
  version, generated time, and observation window.
- Show `forecast not available yet` when a plan lacks a supported model,
  sufficient baseline, defined scope, or observation window.

Acceptance criteria:

- Every forecast is reproducible from stored inputs, model version, assumption
  set, action-plan version, and lexicon version.
- The UI never labels a scenario as a promise, guaranteed ranking increase, or
  guaranteed lead result.
- A customer can visually compare the current measurement, accepted target,
  forecast range, and eventual observed result.
- Unsupported recommendation types show no numeric forecast rather than a
  fabricated estimate.
- Forecast generation cannot begin until the action plan identifies its
  success metric, baseline, implementation scope, and observation window.
- Learned coefficients cannot enter production until minimum-sample,
  calibration, replay, review, and rollback gates pass.

### Intelligence I1.3 - Governed AI Runtime API

Goal: add a real, metered AI provider layer that makes the deterministic
intelligence useful in conversation and content workflows while the lexicon and
policy engine retain decision authority.

> **First vertical slice production-verified 2026-07-30:** the Opportunities
> workspace can request a plain-language explanation of the current
> engine-selected action. The provider-neutral gateway uses Mistral Small 4,
> strict JSON-schema output, evidence and action allow-list validation,
> deterministic fallback, idempotency, per-plan monthly and concurrency limits,
> bounded input/output tokens, and reserve/reconcile cost accounting. Every run
> persists organization, campaign, location, lexicon, prompt template, hashes,
> evidence references, model, tokens, cost, validation state, and rejection
> reason under database RLS. Mistral has no database, Google, WordPress, or tool
> access and cannot execute changes. The production migration, provider key,
> restricted-role pricing access, deterministic control-field enforcement, and
> live validated-output/cost audit have passed. Evidence Q&A and governed
> drafting remain later I1.3 slices.
>
> **Service-business language contract completed 2026-07-30:** the live AI
> prompt now loads the versioned
> `backend/app/intelligence/lexicon/service_business_language_guide.md` writing
> standard. Customer summaries must start with a clear action, stay at or below
> 32 words and two sentences, and avoid internal SEO, analytics, and software
> terms. `why now` is limited to 24 words and one sentence. The server rejects
> noncompliant model output and uses a plain-language fallback, while the client
> retains a final translation layer for older cached responses.
>
> **Bounded daily action brief implemented 2026-08-03:** the runtime now ranks
> active, non-archived recommendations with the same deterministic priority
> rules used by Next Steps, admits no more than three lexicon-approved actions,
> and includes each action's saved cadence, due state, checklist progress, and
> next unfinished step in the bounded AI context. The provider cannot add,
> remove, or reorder those action IDs. The API hydrates the saved IDs from the
> versioned lexicon, the daily guide reports the ready-action count, and Next
> Steps presents the result as a numbered owner-friendly plan. Provider failure
> keeps the exact deterministic plan available. Automated tests cover archived
> action exclusion, the three-action ceiling, checklist context, invalid action
> rejection, tenant scope, cost accounting, fallback behavior, and UI wording.

Runtime sequence:

1. Gather tenant- and location-scoped facts with source and freshness.
2. Run the deterministic evaluator and policy engine.
3. Build the bounded AI decision context from verified facts, diagnoses, and
   allowed actions.
4. Call the configured model through one server-side provider-neutral gateway.
5. Validate the structured response against the contract and action allow-list.
6. Persist prompt template version, model, token usage, cost, evidence
   references, validated output, and rejection reason when invalid.
7. Present the result for the appropriate approval or execution policy.

Scope:

- Add a provider-neutral server-side AI gateway with structured inputs and
  outputs, timeouts, retries, model routing, and feature-level model allow-lists.
- Use Mistral Small 4 as the first production model because the required
  structured output and tool-contract behavior fit the bounded daily/weekly
  action workload at a low unit cost. Keep a benchmarked Gemini adapter as an
  optional fallback; no product workflow depends on one vendor-specific SDK.
- Preserve a stable adapter boundary for future OpenAI-compatible hosted or
  local-model APIs. I1.3 does not add arbitrary endpoint connectivity or a
  customer-side relay; that operational and security scope belongs to I1.5.
- Include governed AI actions in every paid plan. Plan differences are monthly
  action/token allowances, concurrency, history, bulk scope, and model-routing
  policy rather than whether the intelligence explanation works at all.
- Support bounded uses first: plain-language explanations, daily brief,
  recommendation ordering within the deterministic candidate set, question
  answering from supplied evidence, and draft content or metadata.
- Reject invented measurements, sources, diagnoses, actions, causal claims, or
  execution authority.
- Add prompt-template versioning, evaluation fixtures, hallucination and
  unsupported-claim checks, personally identifiable information minimization,
  tenant isolation, audit history, and model-response retention controls.
- Connect all calls to the G1.3 cost ledger, plan entitlement, soft warnings,
  hard allowance, concurrency, token, and per-feature rate limits.
- Provide a deterministic fallback when the AI provider is unavailable, over
  budget, times out, or fails validation.
- Do not give the model credentials or direct access to WordPress, Google, the
  database, or arbitrary tools. Execution uses typed platform actions after
  policy and approval checks.

Acceptance criteria:

- An AI response cannot create an action outside the deterministic allow-list.
- Every customer-visible claim can be traced to supplied evidence or is
  explicitly labeled as a suggestion.
- Invalid, unsupported, over-budget, and timed-out calls fail closed and leave
  the deterministic experience usable.
- Model and token cost is reserved and reconciled before another call can
  exceed the organization's hard allowance.
- A replayable evaluation suite proves schema compliance, tenant isolation,
  stable fallback behavior, and supported-claim accuracy before a model or
  prompt version is activated.

### Intelligence I1.4 - Expanded Action Plans and Guided Checklists

Goal: make the intelligence layer the reason a service business pays for the
product by turning evidence into a practical body of work, not one isolated
recommendation.

> **T25 implementation completed 2026-08-03:** the location-specific Next Steps
> experience now keeps one stable `Do this first` action and surfaces up to four
> additional useful actions immediately below it. Active recommendations are
> ordered, deduplicated by canonical action, and separated from archived build
> artifacts. Recognized actions receive their governed lexicon title, reason,
> effort, owner, steps, success metrics, and observation window from the API.
> The UI does not generate filler when only one action is supported. Persistent
> checklist progress and Daily/Weekly/Monthly routines remain T26.
>
> **T26 implementation completed 2026-08-03:** lexicon-backed plans now create
> versioned, dated work occurrences and persistent checklist rows. Each step
> stores order, required state, progress, blocker/evidence fields, completion
> actor, and completion time. Deterministic cadence and due state drive Today,
> This week, This month, and Later groups in Next Steps. Progress survives
> sessions and devices, required-step completion moves work to
> `waiting_for_results`, and no AI call is made for rendering or checklist
> updates. Forecasting and verified outcome proof remain T27-T28.

Product decision:

- Keep one `Do this first` item as the fastest entry point, but never present it
  as the entire recommendation experience. Show the next two or more useful
  actions immediately below it whenever the evidence supports them.
- Add a customer-facing `Your action plan` area with `Daily`, `Weekly`, and
  `Monthly` views. Order every view by current value and keep a separate
  `Later / watch` backlog for blocked, lower-priority, or waiting-for-data work.
  Prefer three to seven active plans per location when the evidence supports
  them; do not invent filler to reach a quota.
- Each action opens a persistent checklist. The deterministic lexicon supplies
  the action, dependencies, success metrics, and canonical steps. AI may make
  that approved material easier to read, but it cannot create a new action,
  required step, measurement, or claim.
- Finish the action-plan and measurement-readiness slices before I1.2 adds
  customer-visible forecasting.

Scope:

- Replace unsupported overall scores and duplicate recommendations with a
  deduplicated action-plan portfolio scoped to the selected location.
- Give every action a location, evidence set, freshness, confidence, expected
  benefit, estimated effort, dependency, success metric, observation window,
  and plain-language `why now`.
- Give every plan both a priority and a work cadence so `what matters first`
  and `when should I do this` remain separate:
  - `Daily`: one to three short, time-sensitive actions such as responding to a
    new issue, checking a material change, or completing the next step in an
    active plan.
  - `Weekly`: the larger improvements and reviews that move active SEO work
    forward, ordered to fit the owner's configured weekly capacity.
  - `Monthly`: recurring health, visibility, listings, review, content, and
    outcome reviews that should not consume attention every day.
  - `Later / watch`: lower-priority, blocked, or waiting-for-data items that do
    not belong in the current routine.
- Generate cadence, due windows, and recurrence deterministically from the
  canonical action definition, signal urgency, data freshness, dependencies,
  location timezone, and plan capacity. AI can explain the schedule but cannot
  choose a different cadence or silently move work.
- Materialize a versioned customer-facing action plan rather than overloading a
  one-line `StrategyRecommendation`. Each plan records its canonical action,
  source recommendations, priority, owner, dependencies, success metric,
  baseline, observation window, status, lexicon version, and content hash.
- Add three to eight ordered checklist steps for normal multi-step work. Each
  item records a stable step key, required/optional state, status
  (`not started`, `in progress`, `done`, `skipped`, or `blocked`), blocker
  reason, completion actor/time, and supporting evidence. Legitimate
  single-step actions remain single-step.
- Persist checklist progress across navigation, sessions, and devices. Show
  progress as completed required steps out of total required steps, with the
  next unblocked step visible without opening every detail panel.
- Persist each recurring action occurrence separately so completing today's or
  this month's checklist does not erase history. Show `due now`, `upcoming`,
  `completed`, `overdue`, and `snoozed` states in the location's timezone.
- Prevent the same required work from appearing as separate duplicate actions
  across Daily, Weekly, and Monthly views. A single plan may be surfaced in the
  appropriate view while retaining one checklist and one progress record.
- Add plan-level statuses for `ready`, `in progress`, `blocked`, `waiting for
  results`, `completed`, and `dismissed`. A plan cannot become completed while
  required steps remain unresolved.
- Capture the pre-action baseline before work begins. When required work is
  complete, start the defined observation window and later attach
  `helped / did not help / insufficient data` evidence.
- Connect safe automated steps to the existing approval/execution/rollback
  system without treating a checked box as proof that an external mutation
  succeeded.
- Add a compact Daily Intelligence Brief after the first useful Overview charts:
  what changed, likely explanation, strongest evidence, and the next action.
- Add cross-signal diagnoses across Search Console, rankings, geo-grid, GBP,
  reviews, listings, crawl, competitors, analytics, and form events.
- Record a pre-action baseline, action event, observation window, post-action
  measurement, and `helped / did not help / insufficient data` outcome.
- Keep policy learning and causal claims disabled until minimum sample,
  calibration, and governance gates pass.
- Use an LLM only as a cost-capped narrative layer over verified facts; the LLM
  does not invent scores, evidence, or actions.

AI usage and margin controls:

- Build the complete plan and checklist deterministically before any AI call.
- Make at most one `action_plan_explanation` call per plan content hash,
  location, language-guide version, and prompt version; cache and reuse the
  validated result.
- Do not call AI on page load, checklist clicks, progress updates, sorting, or
  repeated views.
- Regenerate only when evidence, canonical action, checklist scope, lexicon
  version, or language-guide version materially changes.
- Reserve and reconcile the call through the existing plan allowance and cost
  ledger. If AI is unavailable or over budget, show the deterministic
  plain-language plan and checklist with no loss of core functionality.

Acceptance criteria:

- No active recommendation is duplicated for the same location, evidence, and
  observation window.
- No recommendation is shown without supporting evidence or an explicit
  insufficient-evidence state.
- A user can see the full action portfolio, the top action, each plan's
  progress, and the next unblocked step without hunting through the page.
- The Next Steps experience shows multiple actions when supported and gives the
  user clear Daily, Weekly, and Monthly lists without requiring a scroll past
  explanatory content.
- Every supported multi-step plan has a deterministic, ordered checklist in
  plain language, and progress survives sign-out and another-device access.
- Recurring actions reset only by creating a new dated occurrence; the prior
  checklist, completion actor, result, and evidence remain auditable.
- AI output cannot add or remove a required action, checklist step, dependency,
  baseline, success metric, or execution authority.
- Completing a UI checkbox cannot falsely mark an automated or externally
  verified action as successfully executed.
- A plan with missing evidence, baseline, or measurement rules clearly explains
  what is needed before forecasting or outcome measurement can begin.
- Every completed action returns to the user with a measured outcome.
- A service-business owner can explain the top action without SEO terminology.

### Intelligence I1.5 - Pluggable and Local Model Gateway

Goal: let the platform route between approved managed models and let an
authorized Enterprise owner connect a customer-controlled model API without
changing the deterministic intelligence engine, weakening validation, or
exposing model credentials to the browser.

Scheduling note:

- This sprint follows the I1.4 action-plan/checklist work and I1.2 forecasting
  work and does not block the current Mistral-first rollout.
- Customer-supplied endpoints and local-model relays are Enterprise-only.
  Solo and Multi-location use the platform-managed governed AI route and cannot
  add arbitrary model endpoints.
- A Vercel deployment cannot call `localhost` on a customer's computer. A local
  model must be exposed through an approved reachable HTTPS endpoint or a
  separately installed, outbound-only customer relay.

Scope:

- Add a versioned model-provider registry with adapter type, endpoint, model
  identifier, supported capabilities, ownership, enabled features, health,
  latency, last validation, and active/standby state.
- Support the existing Mistral adapter plus a constrained OpenAI-compatible API
  adapter suitable for approved services such as Ollama, LM Studio, vLLM, or
  another compatible runtime.
- Add platform-level provider selection and feature-level routing with a safe
  default and one-click rollback. Expose customer-controlled provider selection,
  test connection, and benchmark results only to authorized Enterprise owners
  and platform administrators.
- Store credentials server-side as encrypted secrets. Never return API keys or
  local endpoint credentials to customer JavaScript, logs, prompts, or model
  output.
- Protect custom endpoints with HTTPS requirements, DNS/IP validation,
  private-network and metadata-service blocking, redirect limits, timeouts,
  response-size limits, egress allow-lists, and auditable administrator
  approval to prevent server-side request forgery.
- Define an optional customer-side relay for truly local models. It makes only
  outbound authenticated connections, receives bounded decision packets, and
  cannot query the InsightOS database or execute website changes.
- Run the same structured-output contract, evidence/action allow-lists,
  hallucination checks, retention rules, deterministic fallback, concurrency,
  and entitlement controls for every provider.
- Record provider, model, endpoint identity hash, credential ownership, tokens
  when reported, duration, estimated platform cost, validation result, and
  fallback reason in the existing AI audit and cost ledgers.
- Add an owner-friendly Settings screen that shows provider name, model,
  connection status, supported actions, privacy boundary, last test, and a
  plain-language warning when a selected local model is too weak or
  incompatible.

Acceptance criteria:

- Switching providers never changes the deterministic facts, diagnoses,
  allowed actions, approval policy, or tenant boundary supplied to the model.
- A provider cannot become active until health, schema-conformance,
  supported-claim, latency, and bounded-output tests pass.
- Solo and Multi-location users cannot create, edit, select, or supply
  credentials for a custom or local-model endpoint.
- A failed or unreachable customer endpoint falls back to the approved platform
  route or deterministic narrative according to organization policy.
- Custom endpoints cannot reach loopback, link-local, cloud metadata, or
  unapproved private-network targets from the hosted backend.
- The local relay can be revoked and disconnected without redeploying InsightOS
  or leaving an active credential.
- An organization can prove which provider and model produced every narrative
  while platform margin reporting excludes customer-owned compute cost and
  still counts usage against product safety limits.

### Reporting RPT1 - Premium Reporting and Delivery

Goal: give every paid customer a polished, trustworthy progress story instead
of a metric export; Enterprise later adds deeper white-label and API controls.

Scope:

- Create audience-aware owner, multi-location, and client-safe report
  templates with executive summary, wins, losses, local visibility, rankings,
  website health, actions completed, measured outcomes, risks, and next
  priorities.
- Use consistent visual definitions and the same source, freshness, location,
  date range, and lexicon version as the product screens.
- Add durable artifact storage, scheduled generation, recipient management,
  delivery verification, retry state, failure recovery, history, and secure
  expiring share links.
- Let I1.3 write bounded narrative only from the report's verified facts and
  deterministic conclusions; retain a deterministic narrative fallback.
- Provide accessible web and PDF output with a summary-first presentation and
  technical evidence in an appendix.

Acceptance criteria:

- A report can be regenerated from its stored input snapshot and produces
  internally consistent numbers across screen, export, and delivery.
- Generated, delivered, failed, retried, opened when supported, and expired
  states remain distinct and visible.
- Reports never merge locations silently or claim outcomes not present in the
  evidence.
- Solo receives polished owner reporting; Multi-location receives location
  comparison; Enterprise adds brand, client, API, and custom-distribution
  controls rather than owning basic report quality.

### Customer Experience ALT1 - Alerts, Notifications, and Digests

Goal: notify the right person about meaningful SEO changes, completed work,
connection failures, and required decisions without creating alert noise.

Scope:

- Add an in-product notification center plus configurable email delivery and
  weekly digest.
- Cover ranking and geo-grid movement, CWV regression, crawl/indexability
  problems, new review and reputation risk, provider reconnect, stale data,
  report delivery, pending approval, WordPress execution, verification
  failure, rollback, and allowance warnings.
- Use lexicon severity, confidence, freshness, location scope, deduplication,
  cooldown, and owner preferences to determine delivery.
- Group repeated symptoms into one incident or recommendation when they share
  evidence and observation window.
- Provide direct recovery or action links and record delivery, read,
  dismissal, snooze, and resolution state.

Acceptance criteria:

- The same underlying event cannot create repeated customer notifications
  inside its cooldown window.
- Every alert identifies the affected organization/location, source,
  freshness, meaning, and required action.
- Customers can choose immediate, digest, in-product-only, or disabled delivery
  for eligible categories; mandatory security notices cannot be disabled.
- Provider or notification failure is retried durably and visible to
  operators.

### Customer Experience CX1 - Guided Onboarding, Education, and Support

Goal: let a service-business owner reach the first trustworthy insight and know
what to do next without SEO expertise or operator database work.

Scope:

- Add one guided setup path for account, location, website, Search Console,
  provider connections, tracked phrases, first crawl, first measurement, and
  first recommendation.
- Show progress, blockers, time expectations, data requirements, freshness,
  insufficient-data states, and the next available step.
- Add a customer glossary, contextual explanations, task checklists,
  short product tours, troubleshooting, reconnect guidance, and searchable
  help content in plain service-business language.
- Provide a clear support contact, diagnostic bundle, consented operator-access
  path, response expectation, and escalation state.
- Create persona-aware guidance for a solo owner, multi-location manager, and
  agency operator without creating separate products.

Acceptance criteria:

- A new owner can create a location, connect supported data, run the first
  checks, understand the first recommendation, and request help without
  operator intervention.
- Every blocked onboarding state explains what is missing, who must act, and
  how to recover.
- The system measures completion, abandonment, time to first verified insight,
  and support escalation without recording sensitive page content
  unnecessarily.
- Help copy uses the same governed terms as the active lexicon.

### Market MKT1.1 - Automated Local Keyword Discovery

Goal: replace the Semrush research workflows a local service business actually
needs.

Scope:

- Add local keyword discovery using services, city/service area, Search Console
  queries, related searches, and an approved keyword-data provider.
- Show search volume, intent, CPC, trend, difficulty/competition proxy, current
  position, map visibility, and business relevance with source/freshness.
- Cluster phrases by service, problem, location, funnel stage, and target page.
- Convert research findings directly into tracked phrases, content briefs,
  profile actions, or approved opportunities.

Acceptance criteria:

- A customer can move from `What should I target?` to a location-specific
  tracked phrase or action without copying data between tools.
- Provider-derived volume or difficulty is never mixed with platform estimates
  without a source label.
- The default suggestions are generated from connected data and location facts;
  the owner is not required to build the starting keyword list manually.

### Market MKT1.2 - Competitor and Content-Gap Research

Goal: add the deeper competitive research needed to replace the local-service
parts of Semrush without delaying automated keyword discovery.

Scope:

- Discover real organic and map competitors automatically rather than requiring
  a manually maintained list.
- Add competitor keyword gaps, page/content gaps, local-grid overlap, GBP
  attribute comparisons, authority gaps, and competitor-movement alerts.
- Identify the exact competing URL, phrase, location, source, freshness, and
  supporting evidence for every suggested gap.

Acceptance criteria:

- Competitor recommendations identify the exact gap and supporting data.
- A discovered gap can become a tracked phrase, governed content brief, local
  profile action, or approved opportunity without copying data between tools.

### Content CNT1 - Content and On-Page Workspace

Goal: replace the most useful Semrush content and on-page workflows for local
service businesses.

Scope:

- Productize the existing content-plan, content-asset, internal-link, entity,
  and execution foundations.
- Add page inventory, service/location page coverage, content briefs, intent
  match, title/meta suggestions, schema recommendations, and internal-link plans.
- Compare target pages with ranking competitors and local customer questions.
- Require approval for publishing or website mutations and preserve before/after
  evidence.

Acceptance criteria:

- Every content recommendation identifies the target phrase, target page,
  missing coverage, competitor evidence, and completion state.
- A user can turn a research gap into a governed content or on-page action.

### Authority AUTH1 - Backlink and Local Authority Intelligence

Goal: close the major Semrush authority gap with evidence-backed local link
work rather than an unexplained domain score.

Scope:

- Connect an approved production backlink source for referring domains,
  referring pages, anchors, destinations, link attributes, first/last seen,
  new/lost state, and provider freshness.
- Add competitor link-gap analysis, lost-link recovery, unlinked local mentions,
  chamber/sponsorship/association opportunities, supplier/partner links, and
  locally relevant outreach candidates.
- Keep directory/listing citations distinct from editorial backlinks while
  combining both in plain owner-level authority recommendations.
- Route selected opportunities into governed outreach and action checklists;
  do not label a link as toxic or safe without explicit evidence and policy.
- Apply G1.3 provider-cost allowances and DT1 connection/freshness controls.

Acceptance criteria:

- Every link fact identifies its production source, observed URL, destination,
  first/last seen dates, freshness, and location/campaign scope.
- A user can move from competitor gap or lost link to a deduplicated, assigned,
  measurable authority action.
- No unexplained authority score is presented as proof of ranking ability or a
  guaranteed benefit.

### WordPress WP1.1 - Connection and Safe Site Control

Goal: harden the existing WordPress execution path into a production-safe
connection that can read, preview, apply, verify, and reverse supported site
changes.

Scope:

- Package and version the WordPress plugin with an owner-friendly installation
  and pairing flow.
- Use revocable site-scoped credentials, signed requests, replay protection,
  least-privilege capabilities, rotation, disconnect, and audit history.
- Synchronize posts, pages, custom post types in scope, titles, meta
  descriptions, headings, canonical tags, supported schema, internal links,
  publication state, revision identifier, and compatible SEO-plugin metadata.
- Detect supported WordPress and SEO-plugin versions and fail safely when a
  mutation target is unsupported.
- Require a dry-run change set that shows the exact before/after values,
  affected URLs, validation checks, conflicts, approval requirement, and
  rollback plan.
- Store or reference a recoverable pre-change revision before every mutation,
  use idempotency keys, and verify the public page after execution.
- Add connection health, last sync, plugin version, permission state, execution
  status, verification result, error, and rollback visibility.

Acceptance criteria:

- A site can connect and synchronize without sharing a WordPress administrator
  password with the platform.
- Every supported change has an exact preview, immutable audit record,
  recoverable prior state, and post-change verification.
- Retrying the same operation cannot duplicate content or apply the same
  mutation twice.
- Unsupported versions, permission loss, content conflicts, and public-page
  verification failures stop safely and provide a recovery action.

### WordPress WP1.2 - Managed Autopilot

Goal: let a customer opt into bounded policies that implement routine,
low-risk content and on-page improvements without manually editing WordPress.

Scope:

- Add per-site and per-location automation policies for allowed action types,
  URL scopes, schedules, monthly limits, risk ceilings, blackout windows, and
  required approvals.
- Support governed updates for content sections, title tags, meta descriptions,
  selected headings, internal links, supported schema fields, image alt text,
  and other explicitly implemented action types.
- Generate drafts through I1.3 only from the deterministic brief, lexicon,
  business facts, target phrase, existing page, and evidence packet.
- Validate factual claims, required business details, duplication, length,
  prohibited language, link targets, schema shape, and action allow-list before
  execution.
- Allow genuinely low-risk actions to run automatically only after the owner
  explicitly enables that action category. High-risk page replacement,
  deletion, redirect, canonical, robots, template, theme, code, and sitewide
  mutations require review unless a later governed policy explicitly proves
  them safe.
- Schedule post-change crawl, indexability, CWV, ranking, and content checks;
  surface the measured result and automatically pause the applicable policy
  after repeated failure or regression.
- Provide one-click rollback and an emergency site-level automation stop.

Acceptance criteria:

- An owner can enable a bounded policy once and have eligible routine changes
  drafted, validated, applied, verified, measured, and reported without opening
  WordPress.
- No action executes unless its type, site, URL scope, risk, allowance, and
  approval state satisfy the saved policy.
- Every generated claim and changed field is traceable to its inputs, model,
  prompt, lexicon, recommendation, and execution record.
- A failed verification, material regression, unexpected content conflict, or
  exhausted allowance pauses automation before further work.
- Every mutation remains reversible and visible in the Action Center.

### Migration MIG1 - Semrush and BrightLocal Switching Tools

Goal: let a replacement-product customer preserve useful setup and supported
history instead of rebuilding the account by hand.

Scope:

- Import supported locations, websites, tracked phrases, keyword groups,
  competitors, ranking snapshots, citation/listing facts, and report recipient
  configuration from documented CSV formats and approved provider APIs where
  contractually available.
- Provide downloadable templates, field mapping, location matching, dry-run
  validation, duplicate detection, unsupported-field warnings, and row-level
  error recovery.
- Preserve source, original identifier, original timestamp, import batch,
  confidence, and transformation history; never present imported data as
  freshly collected platform data.
- Keep imports tenant-scoped, idempotent, resumable, allowance-aware, and
  reversible before dependent platform activity begins.
- Add a guided switching checklist that clearly distinguishes imported
  history, newly connected data, and measurements that must be recollected.

Acceptance criteria:

- Retrying an import cannot duplicate a location, phrase, competitor, or
  historical fact.
- Every imported record can be traced to its source file/API, batch, original
  value, normalized value, and location mapping.
- Invalid or ambiguous rows do not block valid rows and can be corrected and
  retried.
- No unsupported Semrush or BrightLocal field is silently discarded or
  relabeled as an equivalent platform metric.

### Product PA1 - Product Analytics and Customer Feedback

Goal: measure whether customers reach value, trust recommendations, complete
work, and remain engaged so roadmap decisions use evidence.

Scope:

- Define a privacy-minimized product event taxonomy for onboarding,
  connections, first verified insight, location switching, report use,
  recommendation views, approval/rejection, execution, rollback, notification,
  help, and support escalation.
- Measure activation, time to first value, weekly useful activity, connection
  health, recommendation acceptance, completion, outcome availability,
  WordPress automation success, report engagement, retention, and churn-risk
  indicators by plan and non-identifying cohort.
- Add short contextual feedback for recommendation usefulness, explanation
  clarity, forecast trust, automation confidence, and report quality.
- Build internal funnels and cohort views without exposing one customer's
  identifiable behavior to another.
- Connect roadmap experiments to explicit success metrics and stop conditions.

Acceptance criteria:

- Every tracked event has an owner, purpose, schema version, retention period,
  and prohibited sensitive fields.
- Product metrics exclude synthetic/demo activity and identify missing or
  partial instrumentation.
- Feedback changes recommendation outcome evidence only through a reviewed,
  auditable path.
- The team can quantify first value, repeated value, failure points, and
  adoption for each paid plan.

### Governance GOV1 - Data Privacy, Retention, and Portability

Goal: give customers and operators clear, enforceable control over collected
data, credentials, generated artifacts, AI records, and deletion.

Scope:

- Inventory data classes and define purpose, owner, sensitivity, residency
  where applicable, retention, deletion, backup behavior, and audit
  requirements.
- Add customer export for account, location, measurement, recommendation,
  execution, report, and supported imported data in documented formats.
- Add provider disconnect, credential deletion/rotation, AI retention controls,
  user deletion, organization closure, legal hold, and verified deletion
  workflows.
- Record consent and delivery suppression for review requests, notifications,
  support access, and other user-data workflows.
- Document subprocessors and customer-facing privacy behavior without claiming
  certifications that have not been completed.

Acceptance criteria:

- A verified owner can request an export or deletion and see its durable,
  auditable status.
- Tenant data, credentials, generated artifacts, queues, caches, backups, and
  provider mappings follow the approved retention/deletion contract.
- Legal hold and security evidence cannot be bypassed by a normal deletion
  request, and the limitation is explained.
- A restore cannot silently resurrect data beyond its approved lifecycle.

### Search Intelligence SEO2 - Advanced Search and Site Integrity

Goal: close the most valuable remaining Semrush-class search and technical
coverage gaps without adding disconnected tool clutter.

Scope:

- Add Search Console indexation and sitemap monitoring with crawl-derived
  robots, canonical, redirect-chain, status, duplicate, orphan, broken-link,
  and supported structured-data validation.
- Add keyword cannibalization, content decay, page-query mismatch, internal-link
  opportunities, and service/location coverage gaps.
- Track SERP features such as local pack, featured result, video, image, and
  other supported result types with provider source and freshness.
- Add entity and topical coverage comparisons against relevant competitors,
  with evidence rather than an unexplained authority score.
- Route every finding through the lexicon, Action Center, and supported
  WordPress action types rather than creating independent recommendation lists.

Acceptance criteria:

- Every issue identifies the affected URL, observed evidence, source,
  freshness, severity, confidence, and supported next action.
- Indexation, crawlability, canonical selection, structured-data validity, and
  ranking presence remain distinct concepts in UI and reports.
- Provider-derived SERP features and platform-derived estimates are never
  blended without labels.
- The default owner experience prioritizes a few consequential issues while
  preserving an expert evidence view.

### Intelligence I2 - Outcome Learning and Controlled Experiments

Goal: improve forecasts and recommendations from verified outcomes while
preventing premature causal claims or uncontrolled self-modification.

Scope:

- Join pre-action baseline, intervention, execution verification, observation
  window, confounders, post-action measurement, and outcome classification.
- Calibrate I1.2 forecast ranges and record accuracy by action type, site
  context, evidence quality, and model version.
- Add governed content, metadata, internal-link, and other supported A/B or
  staggered-rollout experiments with consent, eligibility, stop rules, and
  rollback.
- Maintain champion/challenger policy versions with minimum samples,
  confidence calibration, replay, review, activation, monitoring, and
  rollback.
- Allow privacy-safe cross-location or cohort learning only after minimum
  sample, de-identification, tenant-isolation, and governance review.
- Keep policy mutation and autonomous expansion disabled until explicit
  production gates are met.

Acceptance criteria:

- The system distinguishes correlation, experiment result, and approved causal
  evidence in storage, API, UI, and AI context.
- A policy or forecast model cannot activate itself.
- Experiments stop on safety, regression, data-quality, allowance, or
  statistical guardrails and preserve the prior state.
- Learned changes are reproducible, reviewable, reversible, and never expose
  another tenant's identifiable data.

### AI Visibility AIV1 - AI Search and Entity Visibility

Goal: turn the existing deterministic AI Visibility specification into a real
upper-tier product rather than a documentation-only promise.

Scope:

- Connect an approved provider or governed collection path for prompts,
  responses, mentions, citations, competitors, and platform metadata across
  supported AI-search surfaces.
- Track prompt clusters by service, location, customer question, and buying
  intent.
- Surface inclusion frequency, citation presence, position/prominence,
  competitor share, entity consistency, and volatility over time.
- Tie AI visibility findings to content, schema, entity, review, and authority
  actions without guaranteeing inclusion.
- Add per-plan prompt/check allowances, provider cost reconciliation, and
  customer-owned credential support where available.

Acceptance criteria:

- Every AI visibility metric identifies platform, prompt set, source, date,
  model/collection version when available, and known limitations.
- No static readiness score is presented as proof that an AI system recommends
  the business.
- Recommended actions are evidence-backed and flow into the same governed
  Action Center.

### Multi-Location ML1 - Portfolio Intelligence

Goal: make the $699 plan materially better than repeating a single-location
dashboard ten times.

Scope:

- Add portfolio scorecards, maps, leaderboards, trends, alerts, and sortable
  location matrices across rankings, geo-grid coverage, GBP, reviews, listings,
  website health, search traffic, and action backlog.
- Detect outliers, shared template problems, regional patterns, and sudden
  changes.
- Identify repeatable winning patterns from stronger locations and propose them
  to weaker locations with human review.
- Add bulk checks, bulk scheduling, bulk action assignment, location groups,
  delegated access, and pooled provider allowances.
- Never expose or transfer one tenant's identifiable data to another tenant.
  Any future cohort benchmark must be privacy-safe, minimum-sample gated, and
  governance approved.

Acceptance criteria:

- A multi-location operator can identify the three locations needing attention
  and why in one minute.
- Shared issues are grouped without erasing location-specific evidence.
- Bulk work remains idempotent, approval-gated, cost-confirmed, and auditable.

### Commerce COM1 - Billing, Entitlements, and Self-Service Accounts

Goal: make the $299, $699, and $1,999+ plans enforceable and supportable.

Scope:

- Add checkout, subscription lifecycle, trials, invoices, payment-failure
  recovery, upgrade/downgrade, cancellation, and plan-change audit history.
- Enforce location, user, keyword, grid, prompt, crawl, provider, storage, and
  export allowances through the existing entitlement system.
- Add invitations, password recovery, session revocation, organization
  switching, roles, and delegated location access.
- Show customer-friendly usage and recovery actions without exposing internal
  margin.
- Model normal and heavy-use COGS before a tier can be published.

Acceptance criteria:

- A customer can subscribe, onboard, understand usage, recover access, change
  plans, and resolve payment failure without operator database work.
- Heavy-use simulations preserve at least the approved 85% software-usage
  margin floor.
- Platform-paid provider calls stop before dispatch when allowance is exhausted.

### Operations OPS1 - Customer Support and Launch Operations

Goal: make the paid product supportable, demonstrable, and honest on launch
day—not merely deployable.

Scope:

- Define support channels, ownership, hours, response targets, severity,
  escalation, customer communication, and handoff between product, provider,
  billing, security, and WordPress incidents.
- Add a safe operator diagnostic bundle with customer consent, tenant scope,
  data freshness, connection health, relevant job IDs, recent errors, and
  redacted configuration.
- Maintain a seeded demo environment and repeatable Solo, Multi-location, and
  Enterprise demo paths whose claims match production capability.
- Add customer-facing status communication for incidents, degraded providers,
  delayed data, maintenance, and resolution.
- Create launch, onboarding, provider setup, WordPress recovery, billing
  recovery, incident, rollback, and account closure playbooks.
- Require a go/no-go scorecard covering product truth, critical journeys,
  security, recovery, provider health, data freshness, support readiness,
  pricing, and known limitations.

Acceptance criteria:

- Support can reproduce and diagnose a customer problem without requesting
  passwords or crossing tenant boundaries.
- Every critical incident has an owner, customer communication path, recovery
  procedure, evidence timeline, and corrective-action record.
- Demo and sales claims are generated from a maintained capability matrix and
  cannot describe synthetic, fixture-only, or disabled functionality as live.
- A paid launch cannot proceed while critical TR1, billing, provider,
  WordPress, data-integrity, or support-readiness gates are red.

### Enterprise ENT1 - Agency, API, White Label, and Reporting

Goal: justify the $1,499+ starting price after the core product is proven.

Scope:

- Add advanced roles, client access, organization audit views, custom limits,
  bulk export, API access, and priority-support workflows.
- Add white-label brand settings and client-safe surfaces.
- Finish durable report storage, scheduling, delivery verification, executive
  narratives, portfolio reporting, and branded templates.
- Add reliability/status communication, data export, retention controls, and
  enterprise onboarding runbooks.
- Keep dedicated capacity, custom provider contracts, SSO, and contractual SLA
  commitments quote-based rather than assumed in the base tier.

Acceptance criteria:

- Enterprise customers can operate multiple teams or clients without
  cross-account leakage.
- Reports and exports are durable, reproducible, and source/freshness labeled.
- Custom limits, provider ownership, support commitments, and overages are
  explicit before purchase.

### BrightLocal Replacement Coverage Map

| BrightLocal-class capability | InsightOS sprint |
| --- | --- |
| Local rank tracker and neighborhood geo-grid | G1.2 |
| GBP audit, profile history, competitor benchmarks, and approved management | G1.4 |
| Citation audit, listing consistency, creation/correction workflow | G1.5 |
| Review monitoring, inbox, response, generation, and showcase | G1.6 |
| Multi-location reputation and local visibility overview | G1.6 and ML1 |
| AI-prioritized local SEO actions | I1.3 and I1.4 |
| Local keyword and competitor research | MKT1.1 and MKT1.2 |
| Website audit, current CWV visualization, and improvement scenarios | I1.1 and I1.2 |
| WordPress content and on-page implementation | WP1.1 and WP1.2 |
| Backlink monitoring, competitor link gaps, and local authority work | AUTH1 |
| Historical switching/import workflow | MIG1 |
| Alerts, scheduled digests, and action notifications | ALT1 |
| Owner, portfolio, and client-safe reporting | RPT1 and ENT1 |
| White-label reports and client access | ENT1 |
| API and custom-scale access | ENT1 |

### Commercial Readiness Gates

| Public plan | Price | Minimum completed sprints before general sale |
| --- | ---: | --- |
| Solo | $299/month · 1 active location | R1, TR1, G1.2-G1.7, DT1, I1.0-I1.4 with a standard governed-AI allowance, RPT1, ALT1, CX1, MKT1.1-MKT1.2, baseline CNT1 and AUTH1, WP1.1-WP1.2, MIG1, PA1, GOV1, baseline SEO2, limited AIV1, COM1 self-service billing/account recovery, and OPS1 launch readiness |
| Multi-location | $699/month · up to 10 active locations | All Solo gates plus ML1 portfolio intelligence, pooled AI/provider allowances, team roles, delegated location access, and bulk workflows |
| Enterprise | From $1,999/month · 11-20 active locations | All Multi-location gates plus ENT1 API/export, white label, advanced roles, custom limits and per-location pricing above 20, durable reporting, onboarding, priority-support workflows, and I1.5 customer-owned or local-model API access |

An invite-only paid beta may start earlier with explicit limits and known-feature
disclosures. The public plans above must not be marketed as Semrush or
BrightLocal replacements until their listed gates pass production QA.

### Later Growth Phases

- **G2 - Business Results and Attribution:** define lead and outcome reporting
  only after G1 data quality is proven. Any call-tracking, CRM, job-management,
  or revenue connection requires a new explicit scope decision before work
  starts.
- **G3 - Revenue-Linked Recommendation Validation:** compare recommendations
  with approved outcome data while retaining evidence, confidence, human
  approval, and observation-only learning controls.
- **Later reporting phase:** premium report redesign and expanded report
  automation remain deferred until local rank-grid truth, connection health,
  and usage economics are reliable.

## 2. What The Platform Is Today

Today the platform is:
- A usable tenant-facing local SEO operations workbench.
- A FastAPI backend with broad route coverage for campaigns, crawl, rankings, reports, intelligence, executions, competitors, citations, platform control, and provider health.
- A Next.js tenant UI with:
  - `/dashboard`
  - `/rankings`
  - `/reports`
  - `/opportunities`
  - `/local-visibility`
  - `/site-health`
- A thin but working platform control surface:
  - `/platform`
  - `/platform/orgs`
  - `/platform/orgs/[id]`
  - `/platform/providers`
  - `/platform/audit`

Current reality of key user flows:
- Onboarding exists and is one of the stronger productized flows.
- The dashboard still carries operator DNA and some manual controls, but the tenant shell is materially better than earlier audit states.
- The opportunities page already includes execution list/filter/detail/action behavior.
- The reports page already supports report list, detail, generation, and delivery.
- Competitors and citations have tenant-facing pages, but their production data
  collection and customer workflows remain shallow.

## 3. What The Platform Is Not Yet

It is not yet:
- A launch-ready non-technical-user product.
- A complete execution operations console.
- A finished reporting automation center.
- A real competitors product.
- A real citations product.
- A mature content/authority workspace.
- An agency-ready white-label platform.

Claude should not treat backend coverage as shipped product.

Specific non-truths to avoid reinforcing:
- Do not imply competitors are already shipped in the tenant UI.
- Do not imply citations are already a buyer workflow.
- Do not imply execution automation is fully trustable or autonomous.
- Do not imply report scheduling/delivery visibility is already complete in the tenant UI.
- Do not imply agency/portfolio workflows are ready for productization in this phase.

## 4. Current Stable Surfaces

These surfaces are currently stable enough that Claude should build on them, not redesign them:

- Tenant app shell and shared product components in `frontend/app/(product)/components/`
- Dashboard shell and onboarding flow in `frontend/app/(product)/dashboard/page.tsx`
- Rankings page in `frontend/app/(product)/rankings/page.tsx`
- Reports page in `frontend/app/(product)/reports/page.tsx`
- Opportunities page in `frontend/app/(product)/opportunities/page.tsx`
- Local visibility page in `frontend/app/(product)/local-visibility/page.tsx`
- Site health page in `frontend/app/(product)/site-health/page.tsx`
- Shared nav config in `frontend/app/(product)/nav.config.ts`
- Auth flow and API helper in:
  - `frontend/app/login/page.jsx`
  - `frontend/app/platform/api.js`

Stable backend surfaces Claude can rely on:
- Execution APIs in `backend/app/api/v1/executions.py`
- Reports APIs in `backend/app/api/v1/reports.py`
- Competitors APIs in `backend/app/api/v1/competitors.py`
- Citations APIs in `backend/app/api/v1/authority.py`
- Platform/provider health APIs already used by opportunities

## 5. Current Fragile Surfaces

These areas are fragile and should be extended carefully:

- `frontend/app/(product)/dashboard/page.tsx`
  - Still mixes briefing, setup, and manual operator actions.
- `frontend/app/platform/*`
  - Internal/admin tooling is functional but visually and structurally separate from the tenant product.
- Execution automation paths
  - Backed by real endpoints, but trust and safety UX is still incomplete.
- Reporting quality
  - Reports work, but output and automation visibility are still underbuilt.
- Provider-backed features
  - Backend breadth exceeds tenant UX and provider reality in several domains.
- Hidden future routes in nav config
  - `/settings`, `/locations`, `/competitors` are hidden stubs or incomplete surfaces.

Backend/runtime fragility Claude should respect:
- Avoid touching recommendation execution engine internals unless a UI slice cannot be completed without it.
- Avoid changing execution lifecycle semantics without proving no regression in existing opportunities behavior.
- Avoid changing report generation/delivery behavior unless the work is strictly needed for visibility/status surfacing.
- Avoid broad auth/session changes.

## 6. What Claude Must Preserve

Claude must preserve:
- Current working tenant routes and navigation behavior.
- Current onboarding flow and dashboard setup behavior.
- Current opportunities page behavior:
  - recommendation loading
  - execution loading/filtering
  - dry-run preview behavior
  - execution action buttons already in place
  - WordPress execution setup visibility
- Current reports page behavior:
  - report list/detail loading
  - generate report
  - deliver report
- Current local visibility and site health pages.
- Current platform admin pages.
- Existing backend API contracts wherever possible.
- Current build health and CI-green assumptions.

Preservation rules:
- Prefer additive UI slices over route rewrites.
- Prefer extension of current pages over creating replacement pages.
- Do not refactor shared shell/components unless the ticket requires a small local extension.
- Do not reorganize the backend architecture during this phase.

## 7. Historical Workflow Closure Phase (Substantially Shipped)

This sequence is retained as implementation history. Its routes and major UI slices are now substantially present, so it is no longer the active next phase.

### Phase target
**Workflow Closure Phase: Execution + Reporting + Competitors + Citations**

### Why this phase
- It uses existing backend leverage.
- It strengthens current user-visible surfaces instead of inventing new ones.
- It closes the gap between recommendation, execution, reporting, and audit.
- It adds commercially meaningful tenant workflows before broader surfaces like content/authority/agency.

### Concrete next-build goals

1. Execution inbox and audit completion inside the opportunities surface
- Make the opportunities page a complete human-in-the-loop action center.
- Improve visibility of approval state, mutation count, errors, result summaries, and rollback history.
- Add clearer audit/timeline visibility using existing execution and automation data.

2. Report scheduling and delivery visibility inside the reports surface
- Surface schedule state, cadence, next run, retry count, failure state, and delivery history.
- Make reporting feel operationally managed, not just manually generated.

3. Competitors workflow as the next tenant product page
- Add nav exposure only when the page is usable.
- Support add/list/snapshot/gaps with clear empty/error/provider-thin states.

4. Citations workflow as the next tenant product page or subordinate local SEO workflow
- Support submission and status visibility.
- Keep scope tight and local-SEO-centered.

Only after those are complete:
- content / topical authority
- backlinks / outreach
- broader WordPress provisioning UX
- agency / portfolio productization

## 8. Historical Guardrails For Workflow Closure

The active sprints in Section 1A explicitly authorize scoped shared-shell, navigation, location-context, and multi-location UX changes. The remaining guardrails below still apply: do not use UX work as a reason to rewrite backend architecture or unrelated platform surfaces.

Claude must not touch these areas in this phase unless a ticket explicitly requires a minimal local change:

- Auth architecture and token strategy
- Dashboard rewrite
- Platform/admin app rewrite
- Execution engine internals in `backend/app/intelligence/recommendation_execution_engine.py`
- WordPress execution transport/plugin behavior
- Core provider credentials architecture
- Report rendering engine internals beyond exposing status/visibility data
- Org/tenant/role model
- Broad CSS/design system rewrite

Do not start:
- content workspace
- authority/backlinks workspace
- agency console
- major dashboard simplification
- reporting artifact redesign

Those are later phases.

## 9. Historical Recommended Build Phase

Recommended next build phase:

**Phase: Workflow Closure 1**

Definition:
- Complete the current opportunities page into a trustworthy execution inbox.
- Complete the current reports page into a manageable reporting automation center.
- Add the first two backend-rich, UI-missing tenant workflows:
  - competitors
  - citations

Success condition for this phase:
- A tenant user can:
  - review recommendations
  - inspect execution state
  - approve/reject/run/retry/cancel/rollback safely
  - understand execution history and current blockers
  - manage report schedule and see delivery state
  - use a competitors page
  - use a citations page

Non-goals:
- Do not broaden into content, authority, outreach, or agency productization.
- Do not attempt major intelligence-quality improvements.
- Do not attempt broad automation hardening beyond UI-safe visibility and gating.

## 10. Historical Workflow Closure Ticket Order

These tickets document the prior Workflow Closure order. Use Section 1A for the active next-sprint order.

### T1. Execution Inbox Completion
Scope:
- Extend `frontend/app/(product)/opportunities/page.tsx`
- Improve execution list/detail visibility
- Expose approval state, mutation count, last error, result summary, rollback state more clearly

Why first:
- This page already has real execution behavior.
- This is the shortest path to workflow closure without introducing new routes.

Backend changes allowed:
- Small additive response-field exposure only if needed.

Stop condition:
- If the ticket requires changing execution state-machine behavior, stop and document the blocker.

### T2. Execution Audit / Timeline Visibility
Scope:
- Add visible execution-history / recommendation-history timeline in opportunities
- Reuse existing execution detail plus automation timeline data if possible

Why second:
- Users need trust and traceability after actions are exposed.

Backend changes allowed:
- Small additive read endpoints or payload enrichment only.

Stop condition:
- If timeline assembly requires event model redesign, stop.

### T3. Report Schedule Editor
Scope:
- Extend `frontend/app/(product)/reports/page.tsx`
- Add schedule fetch/edit/save UI using `/reports/schedule`
- Show enabled state, cadence, timezone, next run, retry count

Why third:
- Existing backend exists and current page is already a natural host.

### T4. Report Delivery Visibility
Scope:
- Extend reports page with status summary and delivery history visibility
- Clarify generated vs delivered vs failed

Why fourth:
- Makes reports operationally trustworthy.

Backend changes allowed:
- Add read-only delivery-history exposure if not already returned.

Stop condition:
- If it requires report artifact model rewrite, stop.

### T5. Competitors Page
Scope:
- Add `frontend/app/(product)/competitors/page.tsx`
- Make competitors nav item visible only when page is shipped
- Support add/list/snapshots/gaps

Why fifth:
- High commercial value, backend already exists, no current tenant page.

Rules:
- Keep the page consistent with current product shell/components.
- Handle empty/provider-thin states honestly.

### T6. Citations Page or Local SEO Extension
Scope:
- Add `frontend/app/(product)/citations/page.tsx` or a tightly scoped citations workflow linked from local visibility
- Support submission and status tracking

Why sixth:
- Strong local SEO value with existing backend support.

Rules:
- Keep the workflow small and legible.
- Do not broaden into backlinks/outreach.

### T7. Integration Polish
Scope:
- Link opportunities, reports, competitors, and citations workflows together where needed
- Add minimal cross-page CTAs
- Remove any remaining hidden-nav mismatch introduced by the new pages

Why last:
- Only after core slices are working.

## 11. Safe Implementation Rules

Claude must follow these rules:

1. Work ticket-by-ticket.
2. Make additive changes first.
3. Reuse existing shared components and patterns.
4. Preserve current route structure unless a ticket explicitly adds one new page.
5. Prefer frontend work over backend rewrites.
6. Only make backend changes when:
   - the required data is not currently exposed
   - the change is additive
   - the change does not alter core lifecycle semantics
7. Do not change execution or reporting behavior just to make the UI easier.
8. Do not touch unrelated pages while implementing a ticket.
9. Keep copy honest:
   - do not overstate automation
   - do not pretend provider-thin states are real completion
10. Document before large code changes if a ticket unexpectedly expands.

## 12. Validation Requirements

After each ticket or logical slice, Claude must validate:

- frontend lint passes
- frontend build passes
- affected page loads without runtime crash
- affected user flow works against current local APIs
- no existing tenant route regresses:
  - `/dashboard`
  - `/rankings`
  - `/reports`
  - `/opportunities`
  - `/local-visibility`
  - `/site-health`

Ticket-specific validation:

- Execution tickets:
  - execution list loads
  - pending/completed/failed states render
  - dry-run path still works
  - approve/reject/run/retry/cancel/rollback UI behavior still works

- Report tickets:
  - report list/detail still loads
  - generate still works
  - deliver still works
  - schedule load/save works

- Competitors ticket:
  - add competitor works
  - list works
  - snapshots and gaps render without crash
  - empty state is understandable

- Citations ticket:
  - submission works
  - status list works
  - no-data state is understandable

## 13. Merge / Regression Rules

Claude should only consider a ticket merge-ready if:

- The ticket is scoped and complete.
- Existing working flows still behave the same or better.
- No broad refactor was introduced.
- No backend lifecycle semantics were changed unintentionally.
- New UI follows the existing product shell and design language.
- New routes are only added when they are usable on day one.
- Hidden nav items are only made visible when the corresponding route is actually ready.

Regression red flags that must block merge:
- Dashboard setup flow breaks.
- Opportunities action flow regresses.
- Reports generate/deliver flow regresses.
- New page depends on speculative backend changes.
- New UI exposes backend-only states without clear copy.
- A ticket turns into a rewrite.

## 14. Final Claude Prompt

Use this prompt as the next Claude instruction package:

```text
Work in this WSL project path:
/home/verixlabs/SEO Accelerator Tool

Use these documents as your primary brief:
- docs/claude-next-build-brief.md
- docs/master-system-audit.md
- docs/full-feature-fulfillment-audit.md
- docs/post-ui-feature-fulfillment-ticket-backlog.md
- docs/claude-ui-validation-and-polish-sweep.md

Your assignment:
Implement the next safe build phase: Workflow Closure 1.

Phase goals:
1. Complete the opportunities page into a trustworthy execution inbox and audit surface.
2. Complete the reports page into a report scheduling and delivery visibility center.
3. Add the competitors tenant workflow.
4. Add the citations tenant workflow.

Important constraints:
- Work ticket-by-ticket in the order defined in docs/claude-next-build-brief.md.
- Preserve all currently working behavior.
- Do not do broad rewrites.
- Do not redesign the dashboard or platform admin areas in this phase.
- Prefer additive UI work on top of existing routes and components.
- Avoid risky backend changes unless absolutely necessary.
- If a ticket requires changing execution engine semantics, reporting engine semantics, auth architecture, or provider credential architecture, stop and document the blocker instead of pushing through.
- Keep product copy honest. Do not overstate automation or backend-only capability.
- Reuse existing product shell/components and current visual language.

Validation rules:
- Validate after each ticket or logical slice.
- Run frontend lint and frontend build after each slice.
- Verify affected flows manually against the current local app when possible.
- Confirm no regressions on:
  - /dashboard
  - /rankings
  - /reports
  - /opportunities
  - /local-visibility
  - /site-health

Execution rules:
- Before making large or risky changes, write a short implementation note in docs if needed.
- Keep changes tightly scoped to the active ticket.
- Do not start later-phase work early.

Start with:
T1. Execution Inbox Completion

Then continue ticket-by-ticket only if the current ticket is stable and validated.
```
