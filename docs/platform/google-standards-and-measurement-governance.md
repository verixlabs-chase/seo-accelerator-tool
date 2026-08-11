# Google Standards and Measurement Governance

## Purpose

This document defines sprint **I1.6 - Google Standards and Measurement
Governance**. The sprint keeps InsightOS measurements aligned with published
Google Search and Google Business Profile guidance while protecting customers
from silent rule changes, broken provider schemas, and unsupported ranking
claims.

> **Implementation status (2026-08-09):** I1.6A through I1.6E are
> implemented locally. The platform has a code-owned allow-list of ten official
> Google sources, immutable snapshots, conditional retrieval, raw and normalized
> content digests, visible source failures, and durable source scheduling. A
> second governed layer now creates typed change candidates, deterministic
> diffs, affected-contract and product impact links, platform-admin review
> endpoints, and fail-closed Search Console and Business Profile adapters for
> unresolved provider-contract changes. Migrations `20260805_0100`,
> `20260809_0101`, `20260809_0102`, `20260809_0103`, and `20260809_0104`
> remain production release work. I1.6C
> adds 51 versioned objective contracts covering CrUX, PageSpeed diagnostics,
> Search Console performance, indexing and structured-data gaps, crawl health,
> Business Profile performance and search terms, geo-grid visibility,
> reputation, and profile configuration. Supported collectors now save the
> contract version and exact comparable scope. Missing URL Inspection,
> structured-data, review-response coverage, and response-time collection are
> explicitly recorded as `not_collected`; the product does not invent those
> results. I1.6D now creates inactive metric-contract candidates from reviewed
> official changes and replays metric contracts or validated lexicon versions
> against deterministic fixtures and minimized, explicitly approved evidence.
> Reports preserve exact diffs, changed product surfaces, newly unknown
> results, invalidated comparisons, and new-baseline requirements. Candidate
> versions cannot activate themselves. I1.6E adds sealed replay decisions,
> platform-owner-only approval and rejection, immediate or scheduled rollout,
> audited activation, rollback to the previous last-known-good version, and a
> platform Standards workspace for source health, exact replay evidence,
> active versions, decisions, rollouts, and audit history. Runtime collectors
> resolve the active database contract version, so an approved rollout changes
> newly collected evidence without rewriting historical records. I1.6F now
> implements Search Console cohort monitoring with a five-organization minimum,
> equal organization weighting, same-contract/scope comparison, incomplete-data
> and onboarding exclusions, known incident/provider-change suppression,
> privacy-minimized evidence, and platform-owner investigation states. It never
> activates a standard or customer action. Production proof and the Business
> Profile metric families remain pending.

The intelligence engine remains the decision authority. AI may summarize an
approved change or explain measured evidence, but it cannot change a standard,
select a replacement metric, or claim that it knows Google's private ranking
algorithm.

## The three truth layers

InsightOS must keep three different kinds of truth separate:

1. **Published standard:** a threshold, metric definition, API contract,
   ranking-system description, or policy that Google publicly documents.
2. **Observed measurement:** a value returned for the customer's exact site,
   page, query, device, country, profile, location, or map coordinate.
3. **Observed outcome:** a same-scope before-and-after result recorded after an
   action and its waiting period.

A published standard does not prove a customer's result. A customer trend does
not prove that Google changed its algorithm. A completed checklist does not
prove that the target metric improved.

## Sprint goal

Give the platform owner one governed place to answer:

- Are our Google definitions, thresholds, and API fields still current?
- Which product rules and customer measurements would a published change
  affect?
- Did a provider definition change make an old comparison invalid?
- Are many comparable locations moving unusually at the same time?
- Has a proposed standards update passed review and replay testing before it is
  activated?

The customer-facing result is simpler: measurements remain current, historical
comparisons stay honest, and the product explains any important definition
change in plain language.

## Objective website measurements

### Real-user page experience

- CrUX p75 **LCP**, **INP**, and **CLS**, separated by URL or origin and by form
  factor. The active lexicon owns the threshold values and boundary semantics.
- CrUX sample availability, collection window, URL-to-origin fallback, and
  source freshness.
- **TTFB** as supporting diagnostic evidence only. It is not labeled a Core Web
  Vital and cannot independently pass page experience.
- PageSpeed Insights/Lighthouse lab measurements as diagnostic evidence, with
  tool version, run environment, and timestamp. Lab data never replaces CrUX
  field truth.

### Search performance

- Search Console **clicks** as the primary observed search outcome when the
  action is intended to earn visits.
- Impressions, CTR, and average position as distinct supporting or primary
  measurements only when they match the action contract.
- Exact page, query, device, country, search type/appearance, property, and date
  window scope. Aggregates with different scopes cannot be compared as if they
  were identical.

### Discoverability and site integrity

- Search Console URL Inspection and Sitemap evidence for indexing state,
  selected canonical, robots eligibility, discovery, and sitemap coverage.
- Structured-data eligibility and validation against Google's currently
  supported Search appearance documentation.
- Crawl measures such as indexable-page count, broken-link count, redirect
  defects, missing or duplicate titles and descriptions, internal-link
  coverage, and affected-page ratio.
- Later G1.7 outcomes such as approved form submissions may be shown as
  separate business outcomes. They do not replace the direct SEO measurement.

## Objective Google Business Profile measurements

### Customer discovery and actions

- Supported Business Profile Performance metrics for Search and Maps
  appearances, website clicks, call clicks, direction requests, bookings, and
  other provider-supported actions when applicable.
- Monthly customer search terms and impressions, tied to the mapped profile and
  reporting month.
- Provider metric ID, definition version, date window, mapped location, source
  account, and freshness on every saved measurement.

### Local visibility

- Geo-grid position by keyword and coordinate.
- Share of points in the top 3 and top 10, median position, unranked share, and
  useful ranking radius.
- Grid size, spacing, center, search language, device/provider method, and run
  timestamp. Different grid definitions begin a new baseline.

### Reputation and profile upkeep

- New-review count and pace, average rating, response coverage, and response
  time as separate measurements.
- Name, address, phone, website, primary/secondary categories, hours, services,
  attributes, photos, and posts as configuration or freshness evidence.
- A profile-completeness check may identify missing work, but it is not treated
  as a ranking score or proof that visibility improved.
- Citation accuracy and coverage remain G1.5 evidence and are not relabeled as
  direct Google Business Profile performance.

## Official source registry

The watcher stores a versioned registry entry for every monitored source,
including source owner, URL, scope, retrieval schedule, last successful check,
content hash, parser version, and last reviewed snapshot.

Initial authoritative sources:

- [Google Search Core Web Vitals](https://developers.google.com/search/docs/appearance/core-web-vitals)
- [Google Search ranking systems guide](https://developers.google.com/search/docs/appearance/ranking-systems-guide)
- [Google Search documentation updates](https://developers.google.com/search/updates)
  and its published RSS feed
- [Google Search Status Dashboard guide](https://developers.google.com/search/help/status-dashboard)
- [Search Console performance metric definitions](https://support.google.com/webmasters/answer/7042828)
- [Google structured-data documentation](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data)
- [Google local ranking guidance](https://support.google.com/business/answer/7091)
- [Business Profile Performance API reference](https://developers.google.com/my-business/reference/performance/rpc/google.mybusiness.performance.v1)
- [Google Business Profile API change log](https://developers.google.com/my-business/content/change-log)
- [Business Information API change log](https://developers.google.com/my-business/content/businessinformation/change-log)

Third-party articles, social posts, search-industry commentary, and AI answers
may create a research lead. They can never directly change an active standard.

## Published-change workflow

1. A durable scheduled job retrieves registered sources and stores an immutable
   snapshot plus normalized content hash.
2. A deterministic comparison identifies added, removed, or changed sections.
3. The classifier labels the candidate as a threshold change, metric
   definition change, API field/deprecation change, ranking-system guidance,
   policy change, incident/status event, or editorial-only change.
4. The system identifies affected lexicon metrics, action contracts, provider
   adapters, UI labels, forecasts, reports, and historical comparisons.
5. A candidate lexicon or provider-contract version is created. Production
   behavior remains on the last-known-good active version.
6. Replay tests run against fixed regression fixtures and an approved,
   tenant-safe sample of saved evidence. The report shows classification and
   recommendation differences, newly unknown results, and invalidated
   comparisons.
7. A platform owner reviews the official source, diff, replay report, effective
   date, rollout plan, and rollback plan.
8. Explicit approval activates the new version. Activation is audited and
   reversible; it never rewrites the original meaning of historical evidence.

## Provider contract drift

Provider schemas are part of measurement truth even when Google has not
changed a ranking standard.

- Unknown, removed, or redefined metric IDs fail closed and create an operator
  alert.
- A renamed field may be mapped only after its meaning and units are verified.
- If a metric definition, unit, aggregation, or entity scope changes, the
  system starts a new baseline or records a version boundary. It does not draw
  one continuous before-and-after line across incompatible definitions.
- Deprecated fields remain readable for historical evidence but cannot be used
  for a new action contract after their supported end date.

## Empirical performance-drift monitor

Published documentation will never reveal every ranking adjustment. InsightOS
may therefore look for unusual movement across comparable, permissioned
customer measurements, with strict wording and privacy controls.

- Compare like with like: same metric version, provider, market type, device,
  date treatment, and sufficient sample size.
- Exclude known outages, missing collection days, onboarding changes, large
  site migrations, and provider-contract changes before evaluating a cohort.
- Detect broad movement in Search Console clicks/impressions/position, rank-grid
  coverage, indexing state, and profile discovery metrics.
- Store the detector version, cohort rules, sample size, confidence band, known
  confounders, and affected metric families.
- Label the result **possible ecosystem change** or **unusual shared movement**.
  Never display `Google changed its algorithm` from correlation alone.
- Drift may open a review task or recommend investigation. It cannot activate a
  new standard or automatically change customer websites or profiles.

## Data records

The implementation should introduce durable, tenant-safe records equivalent to:

- `standards_source_registry`
- `standards_source_snapshots`
- `standards_change_candidates`
- `standards_impact_links`
- `standards_replay_reports`
- `standards_approvals`
- `standards_rollouts`
- `provider_metric_contract_versions`
- `performance_drift_events`

Source snapshots and global published standards are platform-owned. Customer
measurements used in replay or drift analysis remain row-secured, minimized,
and never exposed across tenants.

## Platform-owner experience

Add a platform-only **Standards status** workspace showing:

- monitored source health and last successful check;
- the active lexicon and provider-contract versions;
- new published changes requiring review;
- the exact official-source diff and affected product rules;
- replay results and historical-comparison impact;
- possible ecosystem drift, sample sufficiency, and known confounders;
- approve, reject, schedule, rollback, and audit history controls.

Customer pages should show only what helps the owner act, for example:
`Google changed how this measurement is defined on July 15. We started a new
baseline so your comparison stays accurate.` Do not expose internal labels such
as `deterministic summary`, parser names, or raw policy objects.

## Implementation slices

1. **I1.6A - Source registry and immutable snapshots:** monitor official Search,
   Search Console, CrUX, and Business Profile sources with freshness and hash
   evidence. **Implemented locally; production proof pending.**
2. **I1.6B - Deterministic change classification:** create typed changes,
   affected-rule links, operator alerts, and provider fail-closed behavior.
   **Implemented locally; production migration and review proof pending.**
3. **I1.6C - Objective metric contract expansion:** add the missing exact
   Search Console, indexing, structured-data, geo-grid, monthly-profile-search,
   reputation, and profile-configuration scopes described above. **Implemented
   locally; production migration and live provider proof pending.**
4. **I1.6D - Candidate versions and replay:** produce lexicon/provider-contract
   diffs, fixed-fixture replay, approved evidence replay, and impact reports.
   **Implemented locally; production migration and replay proof pending.**
5. **I1.6E - Approval, rollout, and rollback:** build the platform Standards
   status workspace and audited activation controls. **Implemented locally;
   production migration and operator proof pending.**
6. **I1.6F - Empirical drift:** add minimum-sample cohort monitoring, confounder
   filtering, plain-language alerts, and investigation tasks. **Search Console
   slice implemented locally; production migration and live proof pending.
   Business Profile drift remains gated by G1.4 and T29C.**

I1.6A, I1.6B, and the website portion of I1.6C may begin immediately after
I1.4/T29. Live Google Business Profile validation in I1.6C and I1.6F depends on
G1.4 production approval and T29C proof.

## Acceptance criteria

- Every active Google-derived standard and provider metric has a version,
  authoritative source, checked date, effective date when known, and owner.
- An official-source change creates a reviewable candidate and impact report;
  it cannot alter production rules automatically.
- Unknown or redefined provider fields fail closed instead of producing a
  current-looking value.
- Replay proves the proposed version against regression fixtures and reports
  all changed diagnoses, actions, forecasts, and result classifications.
- Historical evidence keeps the definition active when it was collected.
- Incompatible definition or scope changes create a visible version boundary
  or new baseline.
- Website and profile measurements remain organization-, location-, entity-,
  provider-, and time-window-scoped.
- Empirical drift requires a governed minimum sample and is described as a
  possible shared change, never proof of a secret Google update.
- AI is explain-only for this workflow and cannot approve, activate, or rewrite
  standards.
- Automated tests cover source failure, parser drift, duplicate snapshots,
  threshold changes, API deprecations, replay regression, rejected approvals,
  rollback, stale data, insufficient cohorts, and cross-tenant isolation.

## Out of scope

- Discovering, reverse-engineering, or claiming knowledge of Google's private
  algorithm weights.
- Treating correlation as causation or promising a ranking result.
- Automatically activating a changed standard.
- Automatically changing a customer website or Google Business Profile.
- Adding a general-purpose chatbot or allowing customer prompts to alter this
  governance workflow.
