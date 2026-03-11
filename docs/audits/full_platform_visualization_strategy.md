# Full Platform Visualization Strategy

Date: 2026-03-11

## Executive Direction

Visualization is the biggest near-term product lever in this repository.

Why:

- the backend already produces enough structured state to support a compelling product
- many features currently look incomplete only because they are not visualized, narrated, or grouped well
- better visual language would help both local businesses and agencies without requiring major backend redesign

## Visualization Principles

### For local business owners

- default to simple scorecards, trend indicators, and clear "what changed" cards
- avoid dense SEO jargon and tables as the first view
- connect every chart to an action or outcome

### For agencies

- allow deeper drilldowns, filters, cohorts, and exports
- preserve evidence and operational detail
- provide cross-location and cross-account comparisons

### For future LLM summaries

- every major view should have room for:
  - one-line summary
  - risk summary
  - next best action
  - confidence or completeness note

## Feature Visualization Recommendations

### Campaign creation and lifecycle

- Best visualization types:
  - progress timeline
  - stage-based checklist
  - readiness scorecard
- Why it helps:
  - local owners understand setup completion quickly
  - agencies can see blocked states across many campaigns
- Audience mode:
  - simple customer-facing primary
  - advanced agency-facing secondary rollup
- LLM summary use:
  - "You are 3 of 6 setup steps complete"
  - "The only blocker is provider connection"

### Onboarding

- Best visualization types:
  - guided stepper
  - milestone timeline
  - blocker panel
- Why it helps:
  - replaces opaque automation with confidence-building progress
- Audience mode:
  - simple customer-facing primary
- LLM summary use:
  - onboarding summary card
  - blocker explanation card

### Rank tracking

- Best visualization types:
  - line chart by keyword cluster
  - ranking distribution histogram
  - movement table with up/down indicators
  - local pack share trend
- Why it helps:
  - shows progress without forcing users to parse raw positions
- Audience mode:
  - simple trend view for owners
  - advanced keyword/cluster drilldown for agencies
- LLM summary use:
  - "Your core terms improved by 3.2 average positions this month"
  - "Two important terms dropped after the last site change"

### Crawl / site audit

- Best visualization types:
  - severity donut
  - issue bucket stacked bar
  - URL issue matrix
  - technical health trend line
  - remediation board grouped by impact
- Why it helps:
  - turns technical SEO from a raw issue list into a prioritization tool
- Audience mode:
  - simple customer-facing summary plus action groups
  - advanced agency-facing URL matrix and filters
- LLM summary use:
  - "Your biggest technical risk is missing metadata on 18 high-value pages"

### Competitor analysis

- Best visualization types:
  - competitor overlap chart
  - share-of-visibility bar chart
  - keyword gap matrix
  - trend lines per competitor
- Why it helps:
  - competitor features are only compelling when relative positioning is obvious
- Audience mode:
  - advanced agency-facing primary
  - simplified customer-facing highlight cards
- LLM summary use:
  - "Competitor A is outranking you most often in service-intent terms"

### Local SEO / GBP / reviews

- Best visualization types:
  - geo-grid / heat map
  - local pack share map
  - review velocity line chart
  - average rating trend
  - location visibility scorecard
- Why it helps:
  - this is the clearest category where visuals create instant understanding
- Audience mode:
  - simple customer-facing map and scorecards
  - advanced agency-facing location comparisons
- LLM summary use:
  - "Your map visibility is strong downtown but weak in the north service area"

### Content planning / internal links

- Best visualization types:
  - editorial calendar
  - topic cluster tree
  - internal link network graph
  - content status board
- Why it helps:
  - makes content planning feel like a manageable roadmap instead of records
- Audience mode:
  - advanced agency-facing primary
  - simplified customer-facing plan board secondary
- LLM summary use:
  - "Publishing these two pages should support the services cluster most likely to move rankings"

### Authority / outreach / citations

- Best visualization types:
  - outreach funnel
  - citation status board
  - backlink trend line
  - source quality bubble chart
- Why it helps:
  - outreach progress is operational and pipeline-shaped
- Audience mode:
  - advanced agency-facing primary
  - internal/operational for some details
- LLM summary use:
  - "Citation coverage is improving, but outreach pipeline stalled at contact enrichment"

### Dashboarding

- Best visualization types:
  - executive scorecards
  - trend strip with sparklines
  - health summary row
  - prioritized action feed
  - before/after monthly comparison cards
- Why it helps:
  - the dashboard should become the product home, not just an action console
- Audience mode:
  - simple customer-facing primary
  - advanced agency drilldowns beneath
- LLM summary use:
  - dashboard headline summary
  - "best win / biggest risk / next action"

### Reporting

- Best visualization types:
  - monthly story layout
  - before/after scorecards
  - trend lines for rank, traffic proxy, reviews, and technical health
  - action completed timeline
  - risk section with severity bars
- Why it helps:
  - reporting must feel trustworthy, clear, and outcome-oriented
- Audience mode:
  - simple customer-facing report version
  - advanced agency/white-label version with detail appendix
- LLM summary use:
  - executive summary paragraph
  - monthly narrative recap

### Recommendations and execution

- Best visualization types:
  - action queue board
  - recommendation confidence bars
  - execution timeline
  - approval funnel
  - rollback/audit timeline
- Why it helps:
  - this is one of the most differentiated backend capabilities, but it needs a visible control center
- Audience mode:
  - advanced agency-facing primary
  - simplified customer-facing task list with plain language
- LLM summary use:
  - "These 3 actions are highest impact and lowest risk this week"

### Intelligence / experiments / learning

- Best visualization types:
  - control vs treatment experiment view
  - simulation comparison cards
  - cohort comparison
  - policy lineage tree
  - confidence trend line
- Why it helps:
  - intelligence is best shown as decision support, not just internal complexity
- Audience mode:
  - advanced agency/internal primary
  - internal/operational for deeper graph views
- LLM summary use:
  - "The system is increasingly confident that internal link improvements correlate with local service-page gains"

### Entity analysis / AI visibility

- Best visualization types:
  - entity coverage scorecard
  - citation/source coverage table
  - AI visibility trend line
  - competitor entity overlap chart
- Why it helps:
  - this area needs translation into intuitive business meaning
- Audience mode:
  - advanced agency-facing near term
  - simple customer-facing later
- LLM summary use:
  - "Your business is well represented for brand and location terms, but weak for service authority"

### Provider credentials / health / metrics

- Best visualization types:
  - provider health table with status pills
  - latency trend line
  - quota gauge
  - failure reason stacked bar
- Why it helps:
  - ops teams need quick degradation detection
- Audience mode:
  - internal/operational primary
  - advanced agency admin secondary
- LLM summary use:
  - short ops alert summary only

### Tenant / subaccount / hierarchy support

- Best visualization types:
  - organization tree
  - subaccount summary cards
  - cross-location comparison table
  - rollup trend dashboard
- Why it helps:
  - agencies need portfolio awareness, not just account lists
- Audience mode:
  - advanced agency-facing primary
- LLM summary use:
  - "Three locations are improving, one is at risk, and two are missing data"

### Platform control and system operations

- Best visualization types:
  - operational health overview
  - queue backlog chart
  - freshness status board
  - audit timeline
- Why it helps:
  - makes the admin plane actionable during incidents and rollout checks
- Audience mode:
  - internal/operational only
- LLM summary use:
  - ops incident recap, not customer-facing

### Reference library

- Best visualization types:
  - version history timeline
  - validation status table
  - evidence coverage matrix
- Why it helps:
  - helps admins trust the governed evidence base
- Audience mode:
  - internal/operational primary
- LLM summary use:
  - later, surface cited evidence in recommendation/report cards

### White-label / agency workflows

- Best visualization types:
  - multi-client portfolio dashboard
  - branded report templates
  - account health matrix
  - service delivery timeline
- Why it helps:
  - agencies need cross-client clarity and presentation quality
- Audience mode:
  - advanced agency-facing primary
- LLM summary use:
  - portfolio-level weekly account summaries

### Future LLM explanation layer

- Best visualization types:
  - insight cards attached to charts
  - expandable explanation drawers
  - confidence badges
  - "why this matters" sidebars
- Why it helps:
  - LLM value should frame visuals, not replace them
- Audience mode:
  - simple customer-facing and advanced agency-facing
- LLM summary use:
  - primary use case

## Simple vs Advanced View Strategy

### Simple customer-facing view

Use for:

- local business owners
- report recipients
- onboarding and monthly review workflows

Characteristics:

- 3 to 5 top KPIs
- trend direction, not dense diagnostics
- plain-language callouts
- one recommended action per section

### Advanced agency-facing view

Use for:

- agencies
- operators
- power users

Characteristics:

- drilldowns
- filters and comparisons
- per-location and per-keyword detail
- exports and audit history

### Internal/operational only view

Use for:

- provider health
- queue/worker health
- audit logs
- reference library activation and validation

## Reporting And Summary Recommendations

### Local business owner report structure

1. What improved
2. What needs attention
3. What we did
4. What happens next

Chart choices:

- scorecards
- short trend lines
- one map/local visibility visual if available
- one issue severity visual

### Agency report structure

1. Executive summary
2. Performance trend
3. Technical findings
4. Local visibility
5. Competitor position
6. Actions completed
7. Next actions
8. Appendix detail

Chart choices:

- line charts
- grouped bars
- severity buckets
- comparison tables
- per-location views

### White-label report structure

Same as agency, but:

- cleaner branding
- simplified default detail
- optional appendix tabs

## Biggest Visualization Opportunities

1. Replace the current dashboard page with a real campaign intelligence dashboard.
2. Build a local SEO map/geo-grid view.
3. Add a site audit severity and URL issue matrix.
4. Create a competitor comparison workspace.
5. Turn reporting into a monthly story, not just artifact generation.
6. Build an action center for recommendations and execution.
7. Add multi-location rollups for agencies.

## Final Recommendation

If the product team wants the biggest visible leap, the first wave of visual work should focus on:

- campaign dashboard
- local visibility
- technical audit
- reporting
- recommendation/action center

Those five areas will make the existing backend look like a product instead of an API-rich prototype.
