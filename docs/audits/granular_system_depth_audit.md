# Granular System Depth Audit

Date: 2026-03-11

## Summary

This audit goes deeper than the platform-wide feature pass. It looks at each major system in terms of:

- actual implemented depth
- user-facing depth
- missing layers
- blockers to becoming a durable product feature

Scoring uses:

- `surface depth`: how much real functionality exists
- `product depth`: how complete it feels for users
- `architecture depth`: how serious the backend/ops implementation is

Scores are out of 10.

## System-By-System Audit

| System | Surface Depth | Product Depth | Architecture Depth | Current state |
|---|---:|---:|---:|---|
| Campaign lifecycle | 7.5 | 5.8 | 7.8 | real backend, thin user journey |
| Onboarding | 7.8 | 4.8 | 7.9 | strong automation engine, almost invisible UX |
| Rank tracking | 7.3 | 5.2 | 7.4 | functional backend, weak visuals |
| Crawl / technical audit | 7.6 | 5.0 | 7.8 | solid engine, weak presentation layer |
| Competitor intelligence | 6.4 | 4.7 | 6.6 | useful primitives, shallow product depth |
| Local SEO | 6.9 | 4.9 | 6.9 | right category, not yet compelling |
| Content / internal links | 6.7 | 4.5 | 6.8 | backend slice exists, workflow incomplete |
| Authority / citations / outreach | 6.3 | 4.2 | 6.5 | scaffolding more than full operator system |
| Reporting | 6.6 | 4.9 | 6.8 | plumbing exists, narrative/reporting weak |
| Dashboarding | 6.2 | 4.3 | 6.7 | backend aggregate exists, main UI underpowered |
| Recommendations / execution | 7.8 | 4.8 | 8.1 | serious backend control layer, mostly hidden |
| Intelligence / experiments / learning | 8.4 | 4.7 | 8.5 | deepest backend subsystem, limited customer exposure |
| Entity / AI visibility | 6.1 | 4.0 | 6.4 | early differentiator, not productized |
| Provider infrastructure | 8.0 | 6.0 | 8.5 | strong operational layer |
| Hierarchy / subaccounts / locations | 7.4 | 5.0 | 7.7 | good agency foundation, weak portfolio UX |
| Platform control / ops | 8.3 | 7.2 | 8.6 | best-finished admin slice |
| Reference library | 7.0 | 3.8 | 7.6 | powerful governance concept, little visible product value yet |
| Frontend shell | 4.2 | 4.2 | 4.5 | much thinner than backend breadth |

## Detailed Findings

### 1. Campaign lifecycle

What is deep:

- campaign creation
- setup-state transitions
- campaign dashboard/performance/report/strategy endpoints
- organization and subaccount scoping

What lacks depth:

- user journey from campaign creation to first insight
- setup-state meaning and guided progression
- campaign workboard or milestone UX

What should exist but does not:

- campaign workspace home
- first-30-days setup checklist
- cross-feature "next best action" logic

### 2. Onboarding

What is deep:

- `onboarding_service` is a true workflow engine
- it can progress through org readiness, campaign creation, provider connection, crawl start, report generation, and automation enablement

What lacks depth:

- almost no customer UX
- failure recovery is service-level, not user-friendly
- no trust-building status visualization

What should exist but does not:

- a visible onboarding command center
- readiness checklist with blockers
- human-readable milestone summaries

### 3. Rank tracking

What is deep:

- keyword clusters
- snapshot persistence
- trends endpoints
- provider-aware collection
- entitlement-aware collection limits

What lacks depth:

- segmentation by business goal
- location-grid style visualization
- share-of-ranking story
- summary layer for owners

What should exist but does not:

- cluster health view
- movers/losers view
- map-pack correlation to rankings

### 4. Crawl / technical audit

What is deep:

- crawl run scheduling
- frontier batching
- page result persistence
- issue extraction
- metrics and progress

What lacks depth:

- issue classification UI
- page-level diagnosis experience
- workflow from issue to remediation
- business-priority filtering

What should exist but does not:

- issue bucket dashboard
- URL issue explorer
- remediation board with ownership and impact

### 5. Competitor intelligence

What is deep:

- competitor entities and snapshots exist
- ranking/page/signal persistence exists
- gap calculation exists

What lacks depth:

- narrow visible use cases
- weak comparison UX
- unclear link from competitor findings to strategy in product experience

What should exist but does not:

- overlap visualization
- competitor trend dashboards
- market positioning summary
- competitor-informed recommendation explanation

### 6. Local SEO

What is deep:

- local profile model
- health scoring
- reviews and review velocity
- map-pack position capture

What lacks depth:

- geo-grid or service-area visualization
- true local market comparison
- local issue/action guidance
- multi-location local rollups

What should exist but does not:

- local visibility map
- review sentiment story
- listing optimization workspace

### 7. Content / internal links

What is deep:

- content asset lifecycle
- plan retrieval
- internal link recommendation retrieval
- QC hook when publishing

What lacks depth:

- no editorial workflow UI
- no topic cluster planning UX
- no evidence of content performance feedback loop in customer surface

What should exist but does not:

- content board
- topic cluster view
- planned vs published vs performing comparisons

### 8. Authority / citations / outreach

What is deep:

- models and endpoints exist
- Celery tasks exist
- outreach campaigns, contacts, backlinks, citation submissions all exist as primitives

What lacks depth:

- little orchestration UX
- no funnel visibility
- no relationship workflow or execution workspace

What should exist but does not:

- outreach pipeline
- citation completion board
- backlink quality and momentum views

### 9. Reporting

What is deep:

- scheduling
- generation
- artifact storage
- email delivery
- status tracking

What lacks depth:

- report content sophistication
- narrative design
- client-ready storytelling
- white-label polish

What should exist but does not:

- strong executive summary
- progress vs risk framing
- client-ready visual templates

### 10. Dashboarding

What is deep:

- `dashboard_service` combines technical, entity, recommendation, crawl, report, and SLO state

What lacks depth:

- current dashboard page is not really a dashboard
- no hierarchy of insights
- no role-based views

What should exist but does not:

- owner dashboard
- agency dashboard
- portfolio dashboard

### 11. Recommendations / execution

What is deep:

- recommendation transitions
- execution listing and detail
- run/retry/cancel/approve/reject/rollback
- execution mutation persistence

What lacks depth:

- no unified action center
- no plain-language reasoning for business users
- no confidence and tradeoff UX

What should exist but does not:

- action queue with reason, risk, expected upside, and completion tracking

### 12. Intelligence / experiments / learning

What is deep:

- orchestrator
- digital twin
- simulations
- event chain
- graph learning
- evolution
- telemetry
- heavy tests

What lacks depth:

- duplicated learning paths
- limited customer-visible outputs
- weak bridge from intelligence sophistication to perceived customer value

What should exist but does not:

- experiment insight surface
- simulation outcome view
- customer-facing explanation layer

### 13. Entity / AI visibility

What is deep:

- entity extraction across campaign and competitor assets
- entity score and recommendations
- conceptual product positioning docs

What lacks depth:

- no strong UI
- weak differentiation at product surface level
- not yet a must-have day-to-day workflow

What should exist but does not:

- entity coverage dashboard
- AI visibility narrative tied to local search outcomes

### 14. Provider infrastructure

What is deep:

- platform and org credential separation
- policy support
- provider health and quota summaries
- metrics query API

What lacks depth:

- better guided setup for customers/agencies
- richer diagnostics UX

What should exist but does not:

- provider setup wizard
- provider troubleshooting center

### 15. Hierarchy / subaccounts / locations

What is deep:

- org/subaccount/location/business-location APIs
- hierarchy health observability
- subaccount dashboard service

What lacks depth:

- cross-location rollups
- agency command center
- portfolio-wide optimization workflow

What should exist but does not:

- client portfolio dashboard
- location comparison reports

### 16. Platform control / system ops

What is deep:

- this is the cleanest fully surfaced slice
- org controls, provider health, audit, operational health, data freshness all exist
- frontend platform pages are present

What lacks depth:

- richer incident drilldown views
- deeper change history and rollout UX

### 17. Reference library

What is deep:

- versioning
- validation
- activation
- audit trail

What lacks depth:

- visible integration into recommendations and reports
- operator understanding of why it matters

What should exist but does not:

- evidence viewer
- citation-aware report/recommendation rendering

## Cross-Cutting Gaps

### Gap 1: backend depth exceeds product depth

This is the dominant pattern across the repository.

### Gap 2: local-business simplicity is underbuilt

The primary audience still does not have a simple enough experience.

### Gap 3: agency depth exists structurally, not experientially

Hierarchy, provider policy, and platform admin are present, but not yet assembled into a true agency operating layer.

### Gap 4: several systems are deep in isolation but weakly connected in UX

Examples:

- competitor analysis to strategy
- entity analysis to reporting
- recommendations to execution outcomes
- local SEO health to report story

### Gap 5: intelligence is ahead of delivery experience

This is both a strength and a risk.

## Depth Priorities

Highest ROI depth increases:

1. dashboarding
2. reporting
3. local SEO
4. competitor intelligence
5. recommendation/action UX
6. onboarding
7. agency portfolio rollups

Lowest immediate ROI depth increases:

- additional backend-only intelligence complexity
- more architecture expansion without customer surfaces

## Final Read

At a granular level, the system does not suffer from lack of breadth. It suffers from uneven depth distribution:

- operations and backend architecture are deep
- customer product experience is shallow
- agency capability is structurally present but not fully assembled
- moat-capable signals exist, but most are not yet translated into a compelling product layer
