# 📘 Deterministic SEO Strategy Engine -- Full Implementation Specification

**Version:** 1.0\
**Generated:** 2026-02-20T21:42:12.510116 UTC\
**System Scope:** Local SEO Operating System\
**Layer Type:** Deterministic Read-Only Intelligence Module

------------------------------------------------------------------------

# Executive Overview

This document defines the architecture, constraints, and implementation
requirements for the **Deterministic SEO Strategy & Recommendation
Engine**.

This engine:

-   Is fully rule-based
-   Is cross-signal driven
-   Is deterministic and explainable
-   Is fully unit testable
-   Is modular and extensible
-   Produces structured output only
-   Does NOT use AI
-   Does NOT modify provider infrastructure

This engine is the intelligence core of the platform.

It consumes normalized SEO signals and produces:

-   Diagnosed scenarios
-   Structured recommendations
-   Priority scoring
-   Evidence-backed output
-   Authoritative citations

It must remain fully compatible with the existing:

-   Provider execution framework
-   OAuth layer
-   Telemetry write path
-   Feature gating middleware
-   Multi-tenant org isolation model

This is a read-only strategic intelligence system.

------------------------------------------------------------------------

# Core Architectural Principles

1.  Deterministic Logic Only\
2.  No AI / No probabilistic reasoning\
3.  No narrative generation\
4.  No external service calls\
5.  No provider write-path interaction\
6.  No OAuth changes\
7.  No control-plane modification\
8.  Full test coverage enforcement\
9.  Modular design with registry-driven scenarios\
10. Future-compatible with AI presentation layer

------------------------------------------------------------------------

# Directory Structure

    backend/app/services/strategy_engine/

    strategy_engine/
        __init__.py
        signal_models.py
        scenario_registry.py
        priority_engine.py
        engine.py
        schemas.py
        exceptions.py
        modules/
            __init__.py
            ctr_diagnostics.py
            ranking_diagnostics.py
            core_web_vitals_diagnostics.py
            content_diagnostics.py
            competitor_diagnostics.py
            indexation_diagnostics.py

------------------------------------------------------------------------

# Signal Model Layer

File: `signal_models.py`

Signals must:

-   Be numeric or boolean
-   Be strongly typed (Pydantic)
-   Contain no text interpretation
-   Avoid computed narrative logic

## Performance Signals

-   clicks
-   impressions
-   ctr
-   avg_position
-   position_delta
-   traffic_growth_percent
-   sessions
-   conversions

## Technical Signals

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

## Competitor Signals (Optional)

-   competitor_avg_position
-   competitor_ctr_estimate
-   competitor_lcp
-   competitor_word_count
-   competitor_schema_presence
-   competitor_backlink_count

Engine must tolerate missing competitor signals.

------------------------------------------------------------------------

# Scenario Classification Framework

Each diagnostic module:

-   Accepts SignalModel
-   Returns list of ScenarioMatch objects
-   Must be deterministic
-   Must be independently testable
-   Must not depend on other modules

## ScenarioMatch Object

-   scenario_id
-   confidence (0--1)
-   signal_magnitude (0--1)
-   evidence (list of measurable signal references)

------------------------------------------------------------------------

# Cross-Signal Diagnostic Example

If:

-   impressions \> threshold_high\
-   ctr \< threshold_low\
-   avg_position between 3 and 8

Emit:

    scenario_id = "high_visibility_low_ctr"

If competitor_ctr \> ctr and positions similar:

    scenario_id = "competitive_snippet_disadvantage"

------------------------------------------------------------------------

# Scenario Registry

File: `scenario_registry.py`

Each scenario must define:

-   scenario_id
-   category
-   diagnosis
-   root_cause
-   recommended_actions
-   expected_outcome
-   impact_type
-   authoritative_sources
-   confidence_weight
-   impact_weight

All phrasing must be pre-authored.

------------------------------------------------------------------------

# Variable Injection Rules

Support placeholders:

-   {ctr}
-   {lcp}
-   {competitor_ctr}

Rules:

-   Only numeric/boolean substitution
-   Safe escaping
-   No string execution
-   Deterministic substitution

------------------------------------------------------------------------

# Priority Engine

File: `priority_engine.py`

Formula:

    priority_score = impact_weight * signal_magnitude * confidence

Sort descending.

Top N configurable.

------------------------------------------------------------------------

# Engine Orchestrator

File: `engine.py`

Public Interface:

    build_campaign_strategy(campaign_id, date_from, date_to)

Execution Flow:

1.  Fetch normalized signals (read-only repositories)
2.  Construct SignalModel
3.  Execute all diagnostic modules
4.  Collect scenarios
5.  Map to registry definitions
6.  Inject values
7.  Score priority
8.  Return structured output

------------------------------------------------------------------------

# Output Contract

Schema: `CampaignStrategyOut`

Fields:

-   campaign_id
-   window (date_from, date_to)
-   detected_scenarios
-   recommendations
-   meta (total_scenarios_detected, generated_at)

Each recommendation contains:

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

# Competitor Structural Scenario Example

If:

-   competitor_avg_position \< avg_position
-   competitor_lcp \< lcp
-   competitor_word_count \> word_count

Emit:

    competitive_structural_disadvantage

Actions:

-   Improve LCP \< 2.5s
-   Expand content depth
-   Implement structured data

------------------------------------------------------------------------

# Guardrails

Must NOT:

-   Use AI
-   Modify provider layer
-   Modify OAuth
-   Modify telemetry writes
-   Introduce non-deterministic logic

Must:

-   Achieve 90%+ test coverage
-   Preserve org isolation
-   Remain read-only
-   Remain deterministic across runs

------------------------------------------------------------------------

# Testing Requirements

Create:

-   tests/test_strategy_engine.py
-   tests/test_strategy_modules.py
-   tests/test_priority_engine.py
-   tests/test_registry.py

Validate:

-   Scenario fires correctly
-   Scenario does not fire when unmet
-   Cross-signal logic works
-   Missing competitor data tolerated
-   Priority scoring correct
-   Deterministic output stable
-   Variable injection safe

------------------------------------------------------------------------

# Feature Gating

Gate endpoint behind:

    Pro+ tier

Return:

    reason_code = "feature_not_available"

For lower tiers.

------------------------------------------------------------------------

# Integration Directives

-   Use existing DB session management
-   Use existing dependency injection
-   Respect org_id scoping
-   No cross-tenant joins
-   No new telemetry writers
-   No provider execution hooks

------------------------------------------------------------------------

# Final Validation Checklist

-   pytest full suite passes
-   ruff passes
-   mypy passes
-   Docker build passes
-   No regressions in provider layer
-   No regressions in OAuth layer
-   No telemetry path changes

------------------------------------------------------------------------

# Strategic Outcome

This engine becomes:

-   The deterministic intelligence core
-   The measurable strategy backbone
-   The structured output layer
-   The foundation for future AI presentation
-   The monetizable Pro+ feature

------------------------------------------------------------------------

End of Specification
