# Deterministic SEO Strategy Engine -- Version 2

Comprehensive Organic + Local + GBP + Map Intelligence Specification

Version: 2.0 Generated: 2026-02-20T21:54:56.887238 UTC System Scope:
Local SEO Operating System Layer Type: Deterministic Read-Only
Intelligence Engine

------------------------------------------------------------------------

# 1. Executive Summary

This document defines Version 2 of the Deterministic SEO Strategy
Engine.

This engine is:

-   Fully rule-based
-   Cross-signal driven
-   Deterministic
-   Fully testable
-   Modular and extensible
-   Read-only
-   AI-free (diagnostic layer only)

This engine consumes normalized signals from:

-   Organic Search performance
-   Technical SEO metrics
-   Content structure
-   Competitor snapshots
-   Google Business Profile metrics
-   Review & reputation signals
-   Map Pack rankings

It produces:

-   Structured scenario classifications
-   Authoritative recommendations
-   Deterministic priority scoring
-   Evidence-backed outputs
-   Competitive gap diagnostics

It must NOT:

-   Modify provider execution framework
-   Modify OAuth layer
-   Modify telemetry write path
-   Modify control-plane routes
-   Introduce AI or probabilistic reasoning

------------------------------------------------------------------------

# 2. Architecture

Directory:

backend/app/services/strategy_engine/

Structure:

strategy_engine/ **init**.py signal_models.py scenario_registry.py
priority_engine.py engine.py schemas.py exceptions.py modules/
ctr_diagnostics.py ranking_diagnostics.py core_web_vitals_diagnostics.py
content_diagnostics.py competitor_diagnostics.py
indexation_diagnostics.py gbp_diagnostics.py review_diagnostics.py
local_pack_diagnostics.py

Rules:

-   No monolithic logic trees
-   No cross-module imports
-   Modules return scenario matches only
-   Registry controls recommendation mapping
-   Engine orchestrates only

------------------------------------------------------------------------

# 3. Signal Model (Expanded)

All signals numeric or boolean only.

## Organic Performance

-   clicks
-   impressions
-   ctr
-   avg_position
-   position_delta
-   traffic_growth_percent
-   sessions
-   conversions

## Technical SEO

-   lcp
-   cls
-   inp
-   ttfb
-   mobile_usability_errors
-   index_coverage_errors
-   crawl_errors

## Content Signals

-   word_count
-   title_length
-   title_keyword_position
-   meta_description_length
-   structured_data_present
-   duplicate_title_flag
-   cannibalization_flag

## Google Business Profile Signals

-   gbp_views_search
-   gbp_views_maps
-   gbp_total_views
-   gbp_calls
-   gbp_website_clicks
-   gbp_direction_requests
-   gbp_photo_views
-   gbp_photo_count
-   gbp_posts_last_30_days
-   gbp_qna_count
-   gbp_services_count
-   gbp_products_count
-   gbp_primary_category_match_flag
-   gbp_secondary_category_count
-   gbp_completeness_score (0--1)

## Review & Reputation Signals

-   total_reviews
-   review_growth_30d
-   review_velocity_90d
-   average_rating
-   rating_delta_90d
-   negative_review_ratio
-   review_response_rate
-   avg_review_response_time_hours

## Map Pack Signals

-   map_avg_position
-   map_position_delta
-   map_impressions
-   map_actions

## Competitor Signals (Optional)

-   competitor_avg_position
-   competitor_ctr_estimate
-   competitor_lcp
-   competitor_word_count
-   competitor_schema_presence
-   competitor_backlink_count
-   competitor_map_avg_position
-   competitor_review_count
-   competitor_review_velocity
-   competitor_average_rating

Engine must tolerate missing competitor signals.

------------------------------------------------------------------------

# 4. Diagnostic Modules

Each module:

-   Accepts SignalModel
-   Returns list of ScenarioMatch
-   Uses threshold-based deterministic rules
-   Returns confidence (0--1)
-   Returns signal_magnitude (0--1)
-   Provides evidence list

ScenarioMatch:

-   scenario_id
-   confidence
-   signal_magnitude
-   evidence\[\]

------------------------------------------------------------------------

# 5. Scenario Registry

Each scenario defines:

-   scenario_id
-   category
-   diagnosis
-   root_cause
-   recommended_actions\[\]
-   expected_outcome
-   impact_type
-   authoritative_sources\[\]
-   confidence_weight
-   impact_weight

Impact Types:

-   traffic
-   conversions
-   technical_risk
-   local_visibility
-   reputation
-   competitive_pressure

All phrasing pre-authored. Supports safe numeric placeholder injection.

------------------------------------------------------------------------

# 6. Required Scenario Coverage

## Organic

-   high_visibility_low_ctr
-   competitive_snippet_disadvantage
-   ranking_decline_detected
-   content_depth_gap
-   cannibalization_detected

## Technical

-   poor_lcp_detected
-   core_web_vitals_failure
-   indexation_errors_present
-   crawl_error_spike

## GBP

-   gbp_profile_incomplete
-   gbp_low_engagement_high_views
-   gbp_category_misalignment
-   gbp_content_stale
-   gbp_media_gap_vs_competitors

## Reviews

-   low_review_velocity_vs_competitors
-   rating_decline_detected
-   negative_review_ratio_high
-   slow_review_response_time
-   competitor_reputation_gap

## Map Pack

-   map_pack_visibility_decline
-   map_pack_competitive_pressure
-   review_count_structural_disadvantage
-   proximity_irrelevance_detected

All scenarios deterministic and threshold-based.

------------------------------------------------------------------------

# 7. Priority Engine

Formula:

priority_score = impact_weight \* signal_magnitude \* confidence

Sorted descending. Top N configurable.

No dynamic weights. No ML scoring.

------------------------------------------------------------------------

# 8. Engine Orchestrator

Public Interface:

build_campaign_strategy(campaign_id, date_from, date_to)

Execution Flow:

1.  Fetch normalized signals (read-only repositories)
2.  Construct SignalModel
3.  Execute all diagnostic modules
4.  Aggregate scenarios
5.  Map via registry
6.  Inject safe values
7.  Score priority
8.  Return structured output

------------------------------------------------------------------------

# 9. Output Contract

CampaignStrategyOut:

-   campaign_id
-   window
-   detected_scenarios
-   recommendations\[\]
-   meta

RecommendationOut:

-   scenario_id
-   priority_score
-   diagnosis
-   evidence
-   recommended_actions
-   expected_outcome
-   authoritative_sources
-   confidence
-   impact_level

No narrative text allowed.

------------------------------------------------------------------------

# 10. Guardrails

Must NOT:

-   Use AI
-   Modify provider layer
-   Modify OAuth
-   Modify telemetry writes
-   Introduce probabilistic logic
-   Perform external API calls

Must:

-   Maintain org_id isolation
-   Remain read-only
-   Achieve 90%+ coverage
-   Produce deterministic output

------------------------------------------------------------------------

# 11. Testing Requirements

Create tests:

-   test_strategy_engine.py
-   test_priority_engine.py
-   test_registry.py
-   test_gbp_diagnostics.py
-   test_review_diagnostics.py
-   test_local_pack_diagnostics.py

Validate:

-   Scenario firing correctness
-   Non-trigger conditions
-   Competitor-optional stability
-   Priority ordering
-   Injection safety
-   Deterministic repeatability

------------------------------------------------------------------------

# 12. Feature Gating

Endpoint gated behind Pro+ tier.

Lower tiers return:

reason_code = "feature_not_available"

No modification to gating middleware.

------------------------------------------------------------------------

# 13. Strategic Outcome

Version 2 delivers a unified intelligence layer diagnosing:

-   Organic search gaps
-   CTR inefficiencies
-   Technical SEO risks
-   Content structural gaps
-   Competitive structural advantages
-   GBP optimization weaknesses
-   Review velocity deficits
-   Map Pack visibility loss
-   Local competitive pressure

This becomes the monetizable intelligence core of the Local SEO
Operating System.

------------------------------------------------------------------------

End of Version 2 Specification
