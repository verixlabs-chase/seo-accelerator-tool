# Deterministic SEO Strategy & Intelligence Engine (DSSIE)
## Enterprise Whitepaper — Roadmap-Generating, Data-Driven Strategic Decision System (AI-Free, Deterministic)

**Version:** 3.0 (Enterprise Whitepaper Edition)  
**Generated:** 2026-02-23  
**System Scope:** Local SEO Operating System (LSOS)  
**Layer Type:** Deterministic, Read-Only Intelligence Engine  
**Design Principles:** Modular, testable, auditable, explainable, multi-tenant safe  
**Non-Goals:** No external API calls from this layer, no probabilistic/ML reasoning, no write-path mutation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)  
2. [Problem Statement and Market Context](#2-problem-statement-and-market-context)  
3. [Definitions and Core Concepts](#3-definitions-and-core-concepts)  
4. [System Goals, Guardrails, and Non-Goals](#4-system-goals-guardrails-and-non-goals)  
5. [Architecture Overview](#5-architecture-overview)  
6. [Signal Model Specification (Enterprise)](#6-signal-model-specification-enterprise)  
7. [Temporal Intelligence Layer](#7-temporal-intelligence-layer)  
8. [Diagnostic Modules Framework](#8-diagnostic-modules-framework)  
9. [Scenario Registry and Knowledge Base](#9-scenario-registry-and-knowledge-base)  
10. [Opportunity Modeling (Uplift + Gap Indices)](#10-opportunity-modeling-uplift--gap-indices)  
11. [Priority Engine Evolution (ROI + Constraints)](#11-priority-engine-evolution-roi--constraints)  
12. [Roadmap Generation Engine](#12-roadmap-generation-engine)  
13. [Strategic Decision Framework](#13-strategic-decision-framework)  
14. [Portfolio Allocator (Multi-Campaign Planning)](#14-portfolio-allocator-multi-campaign-planning)  
15. [Execution Feedback Loop (Deterministic Learning)](#15-execution-feedback-loop-deterministic-learning)  
16. [Explainability and Evidence Graph](#16-explainability-and-evidence-graph)  
17. [Output Contracts and API Integration](#17-output-contracts-and-api-integration)  
18. [Multi-Tenant Isolation and Security](#18-multi-tenant-isolation-and-security)  
19. [Testing, Validation, and Regression Strategy](#19-testing-validation-and-regression-strategy)  
20. [Operationalization and Release Governance](#20-operationalization-and-release-governance)  
21. [Scaling Model and Performance Considerations](#21-scaling-model-and-performance-considerations)  
22. [Implementation Roadmap (24-Month Maturity Plan)](#22-implementation-roadmap-24-month-maturity-plan)  
23. [Appendices](#23-appendices)

---

# 1. Executive Summary

The **Deterministic SEO Strategy & Intelligence Engine (DSSIE)** is the monetizable intelligence core of the Local SEO Operating System (LSOS). DSSIE transforms normalized multi-source SEO and Local signals into **structured scenarios**, **data-backed recommendations**, and—crucially—**a scalable execution roadmap** that operates as a strategic decision system.

Unlike “SEO dashboards” that aggregate data, DSSIE enforces a **deterministic strategy contract**:

- **Inputs** are normalized numeric/boolean signals (plus metadata).
- **Processing** uses modular threshold rules and deterministic transforms.
- **Outputs** are structured scenario objects, scored and ranked, with evidence.
- **Roadmaps** are generated with phased sequencing, resource estimates, ROI logic, and risk posture.
- **Explainability** is mandatory: every recommendation is backed by explicit signals, thresholds, and (optional) competitor baselines.
- **Read-only**: DSSIE never mutates provider execution, OAuth, or telemetry write paths.

The enterprise objective is to evolve DSSIE from a **diagnostic engine** into a **strategic allocator** that prioritizes SEO actions under constraints and improves over time through a deterministic feedback loop.

---

# 2. Problem Statement and Market Context

## 2.1 Why “More Data” Is Not Strategy

Most SEO software provides:

- data aggregation
- charts and dashboards
- keyword tracking
- audits with generic checklists

These are useful but do not solve the core operational problem:

> **Which actions should be taken next, in what order, and why—under real execution constraints?**

## 2.2 The Operational Reality of SEO (Local + Organic)

SEO execution is constrained by:

- team bandwidth (hours available)
- content velocity (publishing capacity)
- technical change windows
- vendor and provider rate limits
- competitive volatility (SERP + Maps)
- review velocity and reputation management

Without a deterministic strategy engine, teams default to:

- reactive changes
- generic playbooks
- prioritization by opinion rather than evidence

## 2.3 DSSIE’s Value Proposition

DSSIE provides:

- **consistent** decision-making across campaigns
- **scalable** roadmaps (not one-off audits)
- **data-driven** prioritization with ROI and risk
- **enterprise governance** (auditable, testable, versioned)

---

# 3. Definitions and Core Concepts

## 3.1 Signals

A **signal** is a normalized numeric or boolean metric representing measurable reality within a given window.

Examples:
- CTR, impressions, avg_position
- LCP, INP, CLS, TTFB
- GBP views, calls, directions
- review_velocity_90d, negative_review_ratio
- map_avg_position, map_position_delta

**Signals are never free-form text.**

## 3.2 Scenario

A **scenario** is a deterministic classification representing a diagnosable condition that warrants action. It has:

- a unique ID
- category and impact type
- deterministic trigger logic (in module)
- recommendation mapping (in registry)
- evidence payload (signals + thresholds)

## 3.3 Recommendation

A **recommendation** is a pre-authored action set tied to a scenario, with safe numeric placeholder injection and required evidence references.

## 3.4 Roadmap

A **roadmap** is an ordered set of recommendations sequenced into execution phases with:

- time windows (e.g., 30/60/90 days)
- effort estimates and cost classes
- risk posture and dependencies
- expected uplift ranges (deterministic modeling)
- guardrails for execution feasibility

## 3.5 Deterministic

Deterministic means:
- same inputs → same outputs
- versioned thresholds → reproducible results
- no stochastic functions
- no LLM inference or probabilistic scoring

## 3.6 Read-Only Intelligence Layer

DSSIE **consumes** data but does not **create side effects** (no writes to provider execution, OAuth, telemetry pipelines). DSSIE may write its own outputs to a reporting store only if explicitly permitted by platform design; the **strategy computation itself** remains read-only.

---

# 4. System Goals, Guardrails, and Non-Goals

## 4.1 Goals

1. Produce deterministic strategy outputs for Organic + Local + GBP + Maps.
2. Produce a phased roadmap that scales from single campaign to multi-campaign portfolios.
3. Provide evidence-backed recommendations with explicit signals and thresholds.
4. Remain modular: diagnostic logic lives in modules; narrative mapping lives in registry.
5. Remain testable: 90–95%+ rule coverage through unit tests and golden snapshots.
6. Support competitor-optional operation (no hard dependency on competitor data).

## 4.2 Guardrails (Hard Requirements)

- No AI, no ML, no probabilistic logic.
- No external API calls.
- No cross-module imports.
- No mutation of provider framework, OAuth, or telemetry write paths.
- Must maintain org isolation and tenant-safe access patterns.
- Must tolerate partial signal availability.
- Must be forward compatible through versioned schema and scenario thresholds.

## 4.3 Non-Goals

- No automated execution actions from DSSIE.
- No content generation within DSSIE.
- No backlink outreach automation within DSSIE.
- No SERP scraping inside DSSIE (signals must come from other engines).

---

# 5. Architecture Overview

## 5.1 Directory Structure (V2 Baseline)

`backend/app/services/strategy_engine/`

- `signal_models.py`
- `scenario_registry.py`
- `priority_engine.py`
- `engine.py`
- `schemas.py`
- `exceptions.py`
- `modules/`
  - `ctr_diagnostics.py`
  - `ranking_diagnostics.py`
  - `core_web_vitals_diagnostics.py`
  - `content_diagnostics.py`
  - `competitor_diagnostics.py`
  - `indexation_diagnostics.py`
  - `gbp_diagnostics.py`
  - `review_diagnostics.py`
  - `local_pack_diagnostics.py`

## 5.2 Enterprise Architecture (V3 Whitepaper)

Additive layers:

- `temporal_derivation.py` (derived signals)
- `opportunity_modeling.py` (uplift + gap indices)
- `roadmap_generator.py` (phasing + sequencing)
- `portfolio_allocator.py` (optional)
- `feedback_adapter.py` (optional; deterministic learning)
- `explainability.py` (evidence graph builder)

## 5.3 High-Level Data Flow

```text
Normalized Signal Repos (read-only)
        |
        v
SignalModel (validated, numeric/boolean only)
        |
        v
Temporal Derivation Layer (deterministic transforms)
        |
        v
Diagnostic Modules (scenario matches only)
        |
        v
Scenario Registry (pre-authored mapping)
        |
        v
Opportunity Modeling (uplift + indices)
        |
        v
Priority Engine (impact + confidence + ROI + constraints)
        |
        v
Roadmap Generator (phases + dependencies + output contract)
        |
        v
CampaignStrategyOut / CampaignRoadmapOut
```

---

# 6. Signal Model Specification (Enterprise)

## 6.1 Signal Model Principles

- All numeric or boolean fields.
- Missing values allowed if explicitly modeled as optional.
- All units defined and consistent.
- All windows are explicit (7d, 30d, 90d).
- Signal provenance is tracked in metadata (not within the numeric field itself).

## 6.2 Canonical SignalModel (V3)

### 6.2.1 Organic Performance

- `clicks: int`
- `impressions: int`
- `ctr: float` (0–1)
- `avg_position: float`
- `position_delta: float` (positive = improved)
- `traffic_growth_percent: float`
- `sessions: int`
- `conversions: int`

### 6.2.2 Technical SEO

- `lcp_ms: int`
- `cls: float`
- `inp_ms: int`
- `ttfb_ms: int`
- `mobile_usability_errors: int`
- `index_coverage_errors: int`
- `crawl_errors: int`

### 6.2.3 Content Signals

- `word_count: int`
- `title_length: int`
- `title_keyword_position: int` (0-based or 1-based, must be defined)
- `meta_description_length: int`
- `structured_data_present: bool`
- `duplicate_title_flag: bool`
- `cannibalization_flag: bool`

### 6.2.4 GBP Signals

- `gbp_views_search: int`
- `gbp_views_maps: int`
- `gbp_total_views: int`
- `gbp_calls: int`
- `gbp_website_clicks: int`
- `gbp_direction_requests: int`
- `gbp_photo_views: int`
- `gbp_photo_count: int`
- `gbp_posts_last_30_days: int`
- `gbp_qna_count: int`
- `gbp_services_count: int`
- `gbp_products_count: int`
- `gbp_primary_category_match_flag: bool`
- `gbp_secondary_category_count: int`
- `gbp_completeness_score: float` (0–1)

### 6.2.5 Reviews & Reputation

- `total_reviews: int`
- `review_growth_30d: int`
- `review_velocity_90d: float` (reviews/day)
- `average_rating: float` (0–5)
- `rating_delta_90d: float`
- `negative_review_ratio: float` (0–1)
- `review_response_rate: float` (0–1)
- `avg_review_response_time_hours: float`

### 6.2.6 Map Pack

- `map_avg_position: float`
- `map_position_delta: float`
- `map_impressions: int`
- `map_actions: int`

### 6.2.7 Competitor Signals (Optional)

All optional fields:

- `competitor_avg_position: float | None`
- `competitor_ctr_estimate: float | None`
- `competitor_lcp_ms: int | None`
- `competitor_word_count: int | None`
- `competitor_schema_presence: bool | None`
- `competitor_backlink_count: int | None`
- `competitor_map_avg_position: float | None`
- `competitor_review_count: int | None`
- `competitor_review_velocity: float | None`
- `competitor_average_rating: float | None`

## 6.3 Signal Metadata (Separate Model)

- `org_id`
- `campaign_id`
- `window_start`
- `window_end`
- `window_type`
- `signal_version`
- `source_versions` (dict of provider engine versions)
- `data_freshness_seconds`

---

# 7. Temporal Intelligence Layer

## 7.1 Why Temporal Intelligence Matters

Snapshot rules fail when:
- metrics are noisy
- performance is volatile
- competitor actions cause displacement
- seasonal shifts exist

Temporal intelligence adds deterministic characterization:
- trend slope
- volatility index
- momentum vs regression
- structural vs transient classification

## 7.2 Time-Series Storage Schema

### 7.2.1 `signal_timeseries`

- `id: uuid`
- `org_id: uuid`
- `campaign_id: uuid`
- `signal_name: str`
- `signal_value: float`
- `recorded_at: datetime`
- `window_type: str` (7d, 30d, 90d)
- `source_provider: str`
- `schema_version: str`

### 7.2.2 Deterministic Derivation Functions

- `slope(values, timestamps)` → normalized trend [-1..1]
- `volatility(values)` → normalized 0..1 via stddev/mean guardrails
- `acceleration(slope_30d - slope_90d)` → momentum classifier
- `stability_index` → 1 - volatility (bounded)

## 7.3 Derived Temporal Signals (V3)

- `ctr_trend_slope`
- `ranking_trend_slope`
- `ranking_volatility_index`
- `review_velocity_acceleration`
- `gbp_engagement_trend_slope`
- `core_web_vitals_stability_index`
- `map_visibility_trend_slope`
- `competitor_displacement_rate` (if competitor snapshots exist)

## 7.4 Temporal Scenario Extensions

Examples:

- `ctr_decline_with_stable_position`
- `ranking_volatility_spike_detected`
- `review_velocity_decay_detected`
- `gbp_engagement_decline_detected`

These are deterministic, derived from temporal signals, not ML.

---

# 8. Diagnostic Modules Framework

## 8.1 Module Contract

Each module:

- Accepts `SignalModel` + `TemporalSignals` + metadata
- Returns `list[ScenarioMatch]`
- Must not call other modules
- Must not import other modules
- Must not mutate state

### 8.1.1 `ScenarioMatch` Schema

- `scenario_id: str`
- `confidence: float` (0–1)
- `signal_magnitude: float` (0–1)
- `evidence: list[EvidenceItem]`

### 8.1.2 `EvidenceItem` Schema

- `signal_name: str`
- `signal_value: float | bool`
- `threshold: float | bool | None`
- `comparator: str` (`<`, `>`, `==`, `between`, `delta`)
- `reference_value: float | None` (competitor or baseline)
- `notes: str` (short, pre-authored codes, not free narrative)

## 8.2 Deterministic Confidence Rules

Confidence is not “probability.” It is a deterministic proxy for:
- strength of evidence
- number of corroborating signals
- stability of temporal pattern
- competitor confirmation (if available)

Example deterministic mapping:

- 1 signal triggered: confidence 0.55
- 2 corroborating signals: confidence 0.70
- + competitor delta present: confidence +0.10 (capped at 0.90)

## 8.3 Signal Magnitude Normalization

Magnitude expresses “severity” 0–1.

Example for CTR shortfall:

```text
magnitude = clamp((expected_ctr - ctr) / expected_ctr, 0, 1)
```

Magnitude must be deterministic and bounded.

---

# 9. Scenario Registry and Knowledge Base

## 9.1 Registry Responsibilities

- Stores canonical scenario definitions
- Stores pre-authored diagnosis/root cause
- Stores recommended action list (pre-authored)
- Stores expected outcome template (pre-authored)
- Stores authoritative sources list
- Stores weights and constraints metadata

## 9.2 Scenario Definition Schema (Enterprise)

- `scenario_id`
- `category`
- `diagnosis`
- `root_cause`
- `recommended_actions[]`
- `expected_outcome`
- `impact_type`
- `authoritative_sources[]`
- `confidence_weight`
- `impact_weight`
- `effort_hours_estimate`
- `cost_class`
- `execution_complexity`
- `dependencies[]` (scenario_ids or capability flags)
- `phase_preference` (quick_win / structural / competitive / defensive)
- `risk_class` (low/med/high)
- `threshold_version`

## 9.3 Threshold Versioning

All thresholds must be versioned to support:
- reproducibility
- audit trails
- regression prevention

Registry maintains:

- `scenario_id`
- `threshold_version`
- `effective_date`
- `change_reason`
- `prior_version_reference`

---

# 10. Opportunity Modeling (Uplift + Gap Indices)

## 10.1 Purpose

Diagnostics answer: “what is wrong?”  
Opportunity modeling answers: “what is it worth?”

This is the bridge to roadmap ROI.

## 10.2 CTR Uplift Model

Inputs:
- impressions
- current_ctr
- expected_ctr_curve(position)

Output:
- projected_click_uplift

Deterministic CTR curves can be:
- global default
- vertical-specific
- campaign-specific (future) — but still deterministic mappings

## 10.3 Ranking Uplift Model (Deterministic)

If ranking improves from position A to B, expected CTR increases. Use CTR curve delta.

## 10.4 GBP Engagement Uplift Model

Examples:
- improved completeness → increased actions rate
- increased photos/posts → improved conversion actions

These remain heuristic until deep integration; still deterministic.

## 10.5 Structural Gap Indices

Gap indices normalize advantage vs competitor baseline.

Example: review gap index

```text
gap = competitor_review_count - total_reviews
magnitude = clamp(gap / max(competitor_review_count, 1), 0, 1)
```

## 10.6 Opportunity Score

An enterprise-friendly deterministic composite:

```text
opportunity_score =
  w1 * projected_click_uplift_norm +
  w2 * local_visibility_uplift_norm +
  w3 * reputation_uplift_norm
```

Where each component is deterministic and scaled 0–1.

Weights are static (V3), but can be versioned.

---

# 11. Priority Engine Evolution (ROI + Constraints)

## 11.1 V2 Priority Formula

```text
priority_score = impact_weight * signal_magnitude * confidence
```

## 11.2 V3 Priority with ROI

Introduce:
- `estimated_effort_hours`
- `projected_value_score` (0–1)

```text
priority_score =
  (projected_value_score * impact_weight * confidence) / max(effort_hours_estimate, 1)
```

This produces:
- high-value/low-effort items rising to the top
- “structural but expensive” items ranked appropriately

## 11.3 Constraint-Aware Filtering

Roadmaps must respect constraints:
- `max_hours_per_week`
- `max_content_pieces_per_month`
- `max_provider_calls_per_day` (future)
- risk posture

Constraints do not change scoring, but gate roadmap allocation.

---

# 12. Roadmap Generation Engine

## 12.1 Objective

Convert a ranked scenario list into an actionable plan:
- phased
- budget-aware
- dependency-aware
- output-contract compliant

## 12.2 Roadmap Horizon

Default horizons:
- 30 days (tactical)
- 90 days (standard)
- 180 days (strategic)

## 12.3 Roadmap Phases (Deterministic)

**Phase 1 — Quick Wins**
- low effort, high ROI
- frictionless fixes (CTR, metadata, GBP completeness)
- high confidence

**Phase 2 — Structural Improvements**
- technical and content foundation
- indexation, CWV stabilization, content depth gaps

**Phase 3 — Competitive Advantage**
- competitor structural gaps (authority, reviews, map positioning)
- requires sustained effort

**Phase 4 — Defensive Stabilization**
- monitoring scenarios
- volatility and risk posture controls

## 12.4 Sequencing Rules

Sequencing uses deterministic rules:
- dependencies first
- high ROI first within phase
- risk-lowering before expansion if technical debt high
- competitor pressure escalations prioritized if displacement rate high

## 12.5 Roadmap Output Schema

`CampaignRoadmapOut`:

- `campaign_id`
- `window_start`, `window_end`
- `phases: list[RoadmapPhaseOut]`
- `total_effort_hours`
- `projected_uplift_summary`
- `risk_posture`
- `meta`

`RoadmapPhaseOut`:

- `phase_id`
- `phase_name`
- `items: list[RoadmapItemOut]`
- `phase_effort_hours`
- `phase_projected_uplift`

`RoadmapItemOut`:

- `scenario_id`
- `priority_score`
- `action_plan[]`
- `dependencies[]`
- `effort_hours_estimate`
- `expected_outcome`
- `evidence`
- `confidence`
- `impact_type`
- `opportunity_score`
- `risk_class`

No narrative text outside pre-authored registry strings.

---

# 13. Strategic Decision Framework

## 13.1 Decision Dimensions (Enterprise)

- **Impact Type**: traffic, conversions, local_visibility, reputation, technical_risk, competitive_pressure
- **Structural Severity**: 0–1
- **Competitive Pressure**: 0–1
- **ROI Efficiency**: value per effort hour
- **Execution Complexity**: 1–5
- **Confidence Stability**: temporal stability factor
- **Risk Class**: low/med/high

## 13.2 Decision Classes

Each roadmap item is classified into:

- `execute_now`
- `execute_next`
- `build_foundation`
- `monitor_only`
- `deprioritize`

Deterministic rules map:
- high ROI + high confidence → execute_now
- medium ROI + dependency on foundation → build_foundation
- low ROI or low confidence → monitor_only

---

# 14. Portfolio Allocator (Multi-Campaign Planning)

## 14.1 Purpose

For multi-location businesses or agencies, DSSIE must prioritize across campaigns.

## 14.2 Portfolio Constraints

- total hours/month
- max campaigns touched/week
- provider quotas
- strategic emphasis (local vs organic)

## 14.3 Portfolio Allocation Output

`PortfolioRoadmapOut`:

- `org_id`
- `window`
- `campaign_plans[]`
- `portfolio_allocation_summary`
- `resource_budget`
- `risk_posture`

Allocation is deterministic and auditable.

---

# 15. Execution Feedback Loop (Deterministic Learning)

## 15.1 Why Feedback Is the Maturity Hinge

Without feedback:
- weights never improve
- opportunity modeling is uncalibrated
- prioritization drifts from ROI reality

## 15.2 Outcome Log Schema

`execution_outcome_log` captures:
- action executed
- before/after signals
- realized deltas
- time-to-impact

## 15.3 Deterministic Weight Calibration

Bounded adjustment example:
- if realized uplift < expected by threshold → decrease confidence_weight by 0.05 (floor 0.2)
- if realized uplift > expected → increase confidence_weight by 0.05 (cap 1.0)

All adjustments are:
- versioned
- auditable
- bounded

No black-box learning.

---

# 16. Explainability and Evidence Graph

## 16.1 Explainability Requirements

Every scenario output must answer:
- which signals triggered?
- which thresholds were crossed?
- how severe is it?
- what competitor baseline is relevant (if any)?
- why this is prioritized above others?

## 16.2 Evidence Graph

Represent evidence as nodes/edges:

Nodes:
- signals
- thresholds
- competitor comparators
- derived temporal signals

Edges:
- “triggered_by”
- “corroborated_by”
- “worsened_by_competitor_gap”

This supports future UI explainers without narrative generation.

---

# 17. Output Contracts and API Integration

## 17.1 Public Interface

`build_campaign_strategy(campaign_id, date_from, date_to)`

## 17.2 Output Types

- `CampaignStrategyOut` (scenarios + recommendations)
- `CampaignRoadmapOut` (phased execution plan)

## 17.3 Feature Gating

- Engine is gated behind Pro+ tier.
- Lower tiers return: `reason_code="feature_not_available"`

No changes to gating middleware required.

---

# 18. Multi-Tenant Isolation and Security

## 18.1 Access Requirements

- All reads must enforce `org_id` and `campaign_id` boundaries.
- No cross-tenant signal joins.
- No logging of secrets or tenant data in plaintext.

## 18.2 Deterministic Inputs Only

Inputs are restricted to:
- numeric/boolean signals
- safe metadata

No arbitrary text is allowed to influence logic.

---

# 19. Testing, Validation, and Regression Strategy

## 19.1 Test Categories

1. Scenario trigger tests (positive)
2. Scenario non-trigger tests (negative)
3. Competitor-missing stability tests
4. Priority ordering tests (golden sets)
5. Roadmap sequencing tests
6. Injection safety tests
7. Deterministic repeatability tests

## 19.2 Golden Snapshot Testing

Store canonical input-output fixtures:
- input signals json
- expected scenario list
- expected roadmap phases + ordering

Re-run in CI to detect regressions.

Target coverage: 95%+ deterministic paths.

---

# 20. Operationalization and Release Governance

## 20.1 Versioning

- Strategy engine version (semantic)
- Threshold version per scenario
- Signal schema version
- Registry content version

## 20.2 Release Controls

- Feature flag for engine enablement per org
- Canary orgs for threshold updates
- Automated regression suite gate
- Rollback supported via version pinning

---

# 21. Scaling Model and Performance Considerations

## 21.1 Primary Scaling Costs

- signal ingestion volume
- time-series storage size
- strategy build frequency
- portfolio allocation compute

## 21.2 Compute Profile

DSSIE is:
- CPU-bound in scoring + transforms
- memory-light if inputs are bounded
- safe to run in background tasks

---

# 22. Implementation Roadmap (24-Month Maturity Plan)

## Phase 12 (Immediate)
- Global idempotency layer (platform-wide prerequisite)

## Phase 13 (0–3 months)
- Temporal time-series schema
- Derived signal computation service
- Temporal scenarios added

## Phase 14 (3–6 months)
- Opportunity modeling
- ROI priority engine
- Roadmap generator v1

## Phase 15 (6–12 months)
- Execution outcome logging
- Deterministic weight calibration
- Portfolio allocator v1

## Phase 16 (12–18 months)
- Simulation layer v1 (curve-based)
- Evidence graph explainability

## Phase 17 (18–24 months)
- Threshold governance automation
- Advanced portfolio optimization
- SLA-based roadmap planning

---

# 23. Appendices

## A. Deterministic CTR Curve Example

Define static CTR curves by position bands, versioned.

## B. Scenario Template Example

A canonical YAML/JSON representation of a scenario in registry.

## C. Roadmap Example Output (Abbreviated)

Demonstrates phases and item ordering.

---

## End of Whitepaper
