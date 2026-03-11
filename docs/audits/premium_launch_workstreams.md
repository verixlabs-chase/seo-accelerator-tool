# Premium Launch Workstreams

Date: 2026-03-11

## Workstream Overview

These workstreams focus on what is required to convert the current repo from a strong backend platform into a premium launch-ready product.

## Product Design

- Current repo supports: broad documented architecture, audits, screen candidates, backend feature inventory
- Must build: final information architecture, screen specs, design system, content hierarchy, tier-aware user journeys
- Must refine: product promise and launch bar by tier
- Must remove or delay: low-signal speculative screens that are not launch-critical
- Completion standard: every launch surface has a clear purpose, first-read hierarchy, and action model
- Missing for premium launch: a unified customer product definition across all key workflows

## Frontend UX

- Current repo supports: Next.js shell, auth flow, dashboard page, platform admin pages
- Must build: full navigation, premium dashboard, rankings, local visibility, site health, competitors, opportunities, reports, settings, portfolio
- Must refine: loading states, empty states, trust badges, responsiveness, visual hierarchy
- Must remove or delay: test-console style forms on primary product surfaces
- Completion standard: a customer can complete core flows without internal knowledge
- Missing for premium launch: most customer-facing screens

## Backend Feature Completion

- Current repo supports: broad API coverage and service layer across campaigns, onboarding, crawl, rank, competitors, local, content, authority, reporting, recommendations, executions, hierarchy, control plane
- Must build: product-shaped summary endpoints, richer comparison endpoints, geo-grid/local visibility collection if absent, agency rollup endpoints, stronger recommendation explanation payloads
- Must refine: cross-surface consistency, freshness semantics, error payloads, entitlement handling
- Must remove or delay: backend branches that are not exposed in launch flows
- Completion standard: APIs feed premium product screens cleanly without frontend over-assembly
- Missing for premium launch: screen-oriented aggregation contracts

## Data / Metrics Shaping

- Current repo supports: dashboard aggregation, campaign performance summaries, observability metrics, provider metrics
- Must build: normalized KPI definitions for dashboard, reports, portfolio, and action center
- Must refine: metric consistency across screens and exports
- Must remove or delay: excessive metric density on first-read surfaces
- Completion standard: one trusted definition per KPI family
- Missing for premium launch: consistent presentation-layer metrics model

## Reporting System

- Current repo supports: report generation, scheduling, artifact storage, delivery events
- Must build: audience-specific report templates, narrative sections, strong visual layouts, branded/white-label variants
- Must refine: monthly summary logic, action narrative, risk framing, executive readability
- Must remove or delay: low-value raw-detail-first reports
- Completion standard: reports are shareable premium artifacts without extra explanation
- Missing for premium launch: premium report design and story logic

## Local Visibility System

- Current repo supports: local APIs, review snapshots, map-pack and local health primitives
- Must build: geo-grid or equivalent local-market visualization, share-of-market view, local action guidance
- Must refine: location comparisons, review story, listing optimization narratives
- Must remove or delay: local metrics shown without geographic meaning
- Completion standard: local visibility is a flagship surface buyers remember
- Missing for premium launch: the signature customer experience

## Competitor Intelligence System

- Current repo supports: competitor entities, snapshots, gap primitives
- Must build: overlap comparisons, market positioning view, competitor-informed recommendations
- Must refine: strategy tie-in and prioritization
- Must remove or delay: isolated competitor metrics without decision context
- Completion standard: competitor data changes what the user does next
- Missing for premium launch: strategic workspace

## Recommendation / Action System

- Current repo supports: recommendation generation, execution workflows, approvals, retries, rollback, execution history
- Must build: action center UI, impact/confidence/risk presentation, outcome feedback loop
- Must refine: recommendation explainability and business framing
- Must remove or delay: opaque recommendation categories
- Completion standard: the product answers what to do next clearly
- Missing for premium launch: customer-facing action operating layer

## Agency / Portfolio System

- Current repo supports: orgs, subaccounts, locations, business locations, hierarchy observability, admin control-plane views
- Must build: customer-facing portfolio dashboard, cross-location comparisons, bulk workflows, client-safe report delivery, branding controls
- Must refine: agency workflow fit and alerting
- Must remove or delay: agency claims unsupported by workflow depth
- Completion standard: agencies save real labor and can operate across accounts efficiently
- Missing for premium launch: true agency productization

## Support / Help / Docs

- Current repo supports: extensive internal architecture and audit docs
- Must build: customer help center, onboarding guides, glossary, troubleshooting flows, in-product guidance
- Must refine: support runbooks into customer-facing playbooks where useful
- Must remove or delay: internal jargon in customer surfaces
- Completion standard: users can self-serve common issues and understand outputs
- Missing for premium launch: customer education layer

## Billing / Packaging

- Current repo supports: little explicit commercial packaging in product
- Must build: plans, entitlements, usage enforcement, upgrade paths, billing UX, packaging copy
- Must refine: which features are gated by tier versus universal
- Must remove or delay: tiers unsupported by live experience
- Completion standard: pricing and product behavior match exactly
- Missing for premium launch: most of the commercial system

## Reliability / Observability

- Current repo supports: strong runtime middleware, Redis/Celery assumptions, health endpoints, metrics, provider health, freshness monitoring, CI
- Must build: customer-visible freshness and degraded-state behaviors, incident/status communication, enterprise support playbooks
- Must refine: cross-surface handling of stale data and provider outages
- Must remove or delay: hidden failure states
- Completion standard: failures are contained, visible, and confidence-preserving
- Missing for premium launch: trust-oriented operational presentation

## Launch Website / Sales Enablement

- Current repo supports: almost nothing directly
- Must build: launch site, premium product story, demo environment, live examples, pricing pages, objection handling assets
- Must refine: narrative to match what the product actually does
- Must remove or delay: claims not supported by product evidence
- Completion standard: sales story is credible, repeatable, and aligned to demos
- Missing for premium launch: most commercial GTM assets

## Suggested Execution Order

1. Product design
2. Frontend UX foundation
3. Data/metrics shaping
4. Reporting and dashboard rebuild
5. Local visibility and site health productization
6. Opportunities/action center
7. Competitor intelligence workspace
8. Agency/portfolio layer
9. Billing/packaging
10. Launch website and sales enablement

## Workstreams That Should Not Be Overbuilt Before Launch

- generalized LLM summary layer
- speculative enterprise automation surfaces
- abstract portfolio capital forecasting productization
- niche visualization variants before the core dashboard/report/local surfaces are excellent
