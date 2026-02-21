# Deterministic Intelligence Engine Master Specification

Local + Maps + Organic Enterprise Architecture

Version: 1.0 (Consolidated)
Date: 2026-02-21
Status: Implementation-Ready Specification
Scope: Backend deterministic intelligence layer (read-only)

## 1. Purpose and Scope

This document is the unified specification for the Deterministic Intelligence Engine for Local + Maps + Organic performance.

The engine is:
- Rule-based and deterministic
- Signal-driven and citation-backed
- Fully testable and auditable
- Read-only
- Multi-tenant safe
- Compatible with a future LLM presentation layer

The engine is not:
- Generative AI
- Probabilistic scoring
- A write-path component
- A replacement for provider execution or OAuth systems

## 2. Non-Negotiable Constraints

Must not modify:
- Provider execution framework
- OAuth layer
- Telemetry write path
- Control-plane routes

Must preserve:
- Organization isolation guarantees
- Deterministic repeatability
- Read-only data access patterns
- Existing API-layer monetization gating behavior

Must not introduce:
- External API calls from the engine
- ML models or dynamic learned weights
- Narrative freeform output in core responses

## 3. Core Design Principles

### 3.1 Determinism
All outputs are derived from measurable inputs, static thresholds, and static mappings.

### 3.2 Signal Authority
Every recommendation must trace to:
- Explicit input signals
- Threshold evaluation logic
- Authoritative source references

### 3.3 Cross-Signal Diagnostics
Scenarios should evaluate multiple signals when applicable. Single-signal triggers are allowed only when domain-valid (for example hard technical failures).

### 3.4 Auditability
Every emitted recommendation must include:
- Evidence payload
- Scenario version
- Citation references
- Computed priority inputs

### 3.5 LLM Compatibility Boundary
LLM use is optional and presentation-only. LLM layers may summarize outputs but must not alter:
- Scenario detection
- Root cause classification
- Priority scores
- Rule thresholds

## 4. Canonical Processing Flow

Signals -> Diagnostics -> Scenario Classification -> Recommendation Registry -> Priority Engine -> Structured Output

This flow is mandatory and stable.

Tier execution gating:
- Non-Enterprise: competitor diagnostics do not execute
- Enterprise: competitor diagnostics execute when competitor data is available

## 5. Service Architecture

Implementation directory:
`backend/app/services/strategy_engine/`

Expected modules:
- `__init__.py`
- `signal_models.py`
- `scenario_registry.py`
- `priority_engine.py`
- `engine.py`
- `schemas.py`
- `exceptions.py`
- `modules/ctr_diagnostics.py`
- `modules/ranking_diagnostics.py`
- `modules/core_web_vitals_diagnostics.py`
- `modules/content_diagnostics.py`
- `modules/competitor_diagnostics.py`
- `modules/indexation_diagnostics.py`
- `modules/gbp_diagnostics.py`
- `modules/review_diagnostics.py`
- `modules/local_pack_diagnostics.py`

Architecture rules:
- No monolithic rule tree
- Engine orchestrates only
- Diagnostic modules return scenario matches only
- Scenario registry owns recommendation and source mapping
- No circular or cross-diagnostic module imports

## 6. Signal Model (Canonical, Frozen Contract)

Canonical naming standard:
- Lowercase snake_case only
- All downstream diagnostics consume canonical names only
- Signal normalization occurs in `signal_models.py`

All signals are normalized numeric/boolean values.

### 6.1 Organic Signals
- `clicks`
- `impressions`
- `ctr`
- `avg_position`
- `position_delta`
- `traffic_growth_percent`
- `sessions`
- `conversions`

### 6.2 GBP / Local Signals
- `profile_views`
- `direction_requests`
- `phone_calls`
- `photo_views`
- `review_count`
- `review_velocity`
- `avg_rating`
- `review_response_rate`

### 6.3 Core Web Vitals Signals
- `lcp`
- `cls`
- `inp`
- `ttfb`

### 6.4 Technical Signals
- `index_coverage_errors`
- `crawl_errors`
- `mobile_usability_errors`
- `structured_data_present`
- `duplicate_title_flag`
- `cannibalization_flag`

### 6.5 Competitor Signals
- `competitor_avg_position`
- `competitor_ctr_estimate`
- `competitor_lcp`
- `competitor_word_count`
- `competitor_schema_presence`
- `competitor_review_count`
- `competitor_rating`

Competitor behavior:
- Competitor diagnostics are Enterprise-tier only
- If competitor data is missing in Enterprise, emit `competitor_data_unavailable` at low priority
- Non-Enterprise tiers must not execute competitor diagnostics

## 7. Signal Alias and Normalization Policy

To reconcile legacy naming variants, ingestion must normalize aliases into canonical names in `signal_models.py` before diagnostics.

Examples:
- `gbp_total_views` -> `profile_views`
- `gbp_calls` -> `phone_calls`
- `gbp_direction_requests` -> `direction_requests`
- `total_reviews` -> `review_count`
- `average_rating` -> `avg_rating`
- `competitor_average_rating` -> `competitor_rating`
- `LCP` -> `lcp`, `CLS` -> `cls`, `INP` -> `inp`, `TTFB` -> `ttfb`

Alias handling is deterministic and explicit (no fuzzy matching).

## 8. Threshold Ownership and Versioning

All thresholds must be defined only in:
- `backend/app/services/strategy_engine/thresholds.py`

`thresholds.py` requirements:
- Must include `version_id`
- Must include `threshold_source` (example: `Google Search Central 2024-03`)
- Must include inline citation links

Prohibited:
- Hardcoded threshold constants inside diagnostic modules

## 9. Diagnostic Contract

Each diagnostic module:
- Accepts `SignalModel`
- Applies deterministic threshold rules
- Returns `list[ScenarioMatch]`

`ScenarioMatch` fields:
- `scenario_id`
- `confidence` (0.0 to 1.0)
- `signal_magnitude` (0.0 to 1.0)
- `evidence[]`

Evidence schema (audit-grade, required):
- `signal_name`
- `signal_value`
- `threshold_reference`
- `comparator`
- `comparative_value` (optional)
- `window_reference`

Cross-signal rule:
- Technical failure scenarios may be single-signal
- All other diagnostics must use multi-signal conditions

## 10. Scenario Registry Contract

Each scenario definition must include:
- `scenario_id`
- `version_id`
- `created_at`
- `updated_at`
- `deprecated` (boolean)
- `category`
- `diagnosis`
- `root_cause`
- `recommended_actions[]`
- `expected_outcome`
- `impact_type`
- `impact_level`
- `authoritative_sources[]`
- `confidence_weight`
- `impact_weight`
- `citation_reference_version`

Impact types:
- `traffic`
- `conversions`
- `technical_risk`
- `local_visibility`
- `reputation`
- `competitive_pressure`

Registry content standards:
- Pre-authored deterministic phrasing only
- Safe numeric placeholder injection allowed
- No generated prose in core recommendation objects
- Registry stores no runtime evidence payloads
- `impact_level` is categorical and explicitly defined in registry (not derived from score)

Backward compatibility rule:
- Version updates must not change priority semantics without version increment

## 11. Required Scenario Coverage (Minimum)

### 11.1 Organic
- `high_visibility_low_ctr`
- `competitive_snippet_disadvantage`
- `ranking_decline_detected`
- `content_depth_gap`
- `cannibalization_detected`

### 11.2 Technical
- `poor_lcp_detected`
- `core_web_vitals_failure`
- `indexation_errors_present`
- `crawl_error_spike`

### 11.3 GBP / Local Profile
- `gbp_profile_incomplete`
- `gbp_low_engagement_high_views`
- `gbp_category_misalignment`
- `gbp_content_stale`
- `gbp_media_gap_vs_competitors`

### 11.4 Reviews / Reputation
- `low_review_velocity_vs_competitors`
- `rating_decline_detected`
- `negative_review_ratio_high`
- `slow_review_response_time`
- `competitor_reputation_gap`

### 11.5 Map Pack
- `map_pack_visibility_decline`
- `map_pack_competitive_pressure`
- `review_count_structural_disadvantage`
- `proximity_irrelevance_detected`

### 11.6 System / Competitor Availability
- `competitor_data_unavailable` (Enterprise only, low priority)

Scenario IDs are stable API contracts and must be versioned, not silently renamed.

## 12. Priority Engine

Formula:
`priority_score = impact_weight * signal_magnitude * confidence`

Rules:
- Deterministic only
- Descending sort by `priority_score`
- Top N configurable
- No learned or runtime-adaptive weighting

Deterministic tie-break order (required):
1. Higher `priority_score`
2. Higher `impact_weight`
3. Lexicographic `scenario_id`

## 13. Orchestrator Interface and Flow

Primary interface:
`build_campaign_strategy(campaign_id, date_from, date_to)`

Execution steps:
1. Read normalized signals from approved repositories (read-only)
2. Build canonical `SignalModel`
3. Resolve tier gate and execute eligible diagnostic modules
4. Aggregate `ScenarioMatch` results
5. Enrich through scenario registry
6. Inject safe placeholders
7. Compute and sort priorities
8. Return strict structured output

## 14. Output Contract

### 14.1 CampaignStrategyOut
- `campaign_id`
- `window`
- `detected_scenarios[]`
- `recommendations[]`
- `meta`

### 14.2 RecommendationOut
- `scenario_id`
- `priority_score`
- `diagnosis`
- `root_cause`
- `evidence[]`
- `recommended_actions[]`
- `expected_outcome`
- `authoritative_sources[]`
- `confidence`
- `impact_level`
- `version_id`

### 14.3 Meta (minimum)
- `total_scenarios_detected`
- `generated_at`
- `engine_version`

Output requirements:
- Structured payloads only
- No freeform narrative in deterministic layer
- Stable schema for downstream API and LLM presentation adapter

## 15. Governance, Versioning, and Reproducibility

Each scenario and citation set must be versioned for reproducibility.

Required capabilities:
- Historical replay using versioned thresholds and scenario definitions
- Immutable audit trail of scenario definition changes
- Explicit citation reference version binding

## 16. Monetization and Access Rules

- Engine endpoint is Pro+ gated
- Enterprise tier includes competitor cross-reference features
- Lower tiers return `reason_code = "feature_not_available"`
- Gating remains at API layer; no engine-internal entitlement branching
- Competitor diagnostics are disabled for non-Enterprise tiers
- Enterprise missing competitor data must emit `competitor_data_unavailable`

## 17. Testing Requirements

Minimum test suites:
- `test_strategy_engine.py`
- `test_priority_engine.py`
- `test_registry.py`
- `test_gbp_diagnostics.py`
- `test_review_diagnostics.py`
- `test_local_pack_diagnostics.py`

Coverage and behavior requirements:
- At least 90% rule coverage
- Positive and negative trigger tests
- Priority ordering and tie-break tests
- Competitor-optional stability tests
- Enterprise missing-competitor scenario tests (`competitor_data_unavailable`)
- Non-Enterprise competitor-module non-execution tests
- Cross-org isolation tests
- Placeholder injection safety tests
- Deterministic repeatability regression tests

## 18. LLM Presentation Compatibility Layer (Future)

Allowed future responsibilities:
- Executive summaries
- Client narrative formatting
- Tone adaptation
- Roadmap-style presentation formatting

Disallowed responsibilities:
- Altering detected scenarios
- Altering root causes
- Altering thresholds
- Altering scores or priority order

Contract boundary:
- Deterministic engine outputs are source of truth
- LLM receives read-only structured output

## 19. Implementation Readiness Checklist

Before coding begins, confirm:
- Canonical signal dictionary approved
- Threshold table ownership assigned
- Scenario registry versioning strategy approved
- Tie-break and sorting semantics approved
- Output schema frozen for API contracts
- Test matrix accepted by backend team
- Tier-gating behavior for competitor diagnostics approved
- `thresholds.py` version/citation policy approved
- Evidence schema accepted as immutable contract

## 20. Strategic Outcome

This engine becomes the deterministic intelligence core for Local + Maps + Organic strategy, producing auditable diagnostics, prioritized recommendations, and enterprise-ready decision support without AI-dependent reasoning.
