# AI Visibility Intelligence Engine (AVIE)

## Enterprise Dynamic Architecture Specification

### Modular, Versioned, and Deterministic

------------------------------------------------------------------------

# 1. Executive Overview

The AI Visibility Intelligence Engine (AVIE) is a deterministic,
enterprise-grade intelligence module designed to measure, analyze, and
strategically influence a business's presence inside AI-generated search
ecosystems.

This system is NOT dependent on LLM APIs.

It is architected as:

-   Signal-driven
-   Versioned
-   Configurable
-   Relative-metric based
-   Volatility-aware
-   Decision-tree aligned
-   Campaign-integrated

AVIE transforms AI-generated responses into structured competitive
intelligence and integrates directly into the Campaign Intelligence
Engine.

------------------------------------------------------------------------

# 2. Architectural Philosophy

## Core Principles

1.  Deterministic first. LLM optional.
2.  Signals over surface-specific logic.
3.  Versioned scoring models.
4.  Relative dominance, not absolute metrics.
5.  Volatility-aware weighting.
6.  Modular recommendation bundles.
7.  Feedback reinforcement loop.

------------------------------------------------------------------------

# 3. System Layer Architecture

AI Surface Layer\
↓\
Signal Extraction Layer\
↓\
Signal Registry Layer\
↓\
Versioned Scoring Engine\
↓\
Decision Tree Engine\
↓\
Campaign Intelligence Core\
↓\
Reporting Layer

Each layer is independently maintainable.

------------------------------------------------------------------------

# 4. Signal Abstraction Framework

Signals are categorized, not hardcoded to UI behavior.

## Signal Categories

-   Inclusion Frequency
-   Position Dominance
-   Citation Presence
-   Platform Coverage
-   Sentiment Polarity
-   Entity Stability
-   Competitive Acceleration
-   AI Result Volatility

Signals stored in:

ai_signal_types - id - signal_name - category - description - is_active

New signals can be added without rewriting core logic.

------------------------------------------------------------------------

# 5. Versioned Scoring Models

Scoring is not hardcoded.

## scoring_models

-   id
-   model_name
-   version
-   created_at
-   is_active

## scoring_factors

-   id
-   model_id
-   signal_type_id
-   base_weight
-   threshold_min
-   threshold_max
-   decay_enabled

Each campaign references a scoring_model_id.

This allows: - Model evolution - A/B model testing - Historical
preservation - Tier-based model assignment

------------------------------------------------------------------------

# 6. Relative Metric Computation

AI-SOV is computed as:

AI-SOV = (Target Weighted Mentions ÷ Total Weighted Mentions) × 100

But scoring is based on:

-   Market percentile rank
-   Relative competitor delta
-   Growth velocity comparison

Example:

Dominance Gap = Competitor AI-SOV -- Target AI-SOV

This ensures adaptation as AI ecosystems evolve.

------------------------------------------------------------------------

# 7. Volatility Monitoring System

Track:

-   Mention churn rate
-   First-position turnover rate
-   Citation persistence
-   Platform consistency index

If volatility exceeds threshold:

-   Reduce prominence weight
-   Increase frequency weight
-   Adjust model weight decay

Volatility Index stored per cluster monthly.

------------------------------------------------------------------------

# 8. Weight Decay Logic

Effective Weight = Base Weight × Decay Modifier

Decay Modifier adjusts based on:

-   Signal instability
-   Platform behavior change
-   Historical correlation strength

This prevents obsolete signals from dominating score calculations.

------------------------------------------------------------------------

# 9. AI Visibility Score (Dynamic)

AIVS is computed via active scoring model.

Example structure (configurable):

AIVS = (Platform Coverage × configurable_weight) + (AI-SOV ×
configurable_weight) + (Citation Frequency × configurable_weight) +
(Position Dominance × configurable_weight) + (Entity Stability ×
configurable_weight)

Weights are database-driven.

------------------------------------------------------------------------

# 10. Decision Tree Engine (Deterministic)

Triggers are signal-category driven.

Example:

IF Inclusion Frequency \< Threshold\
AND Competitive Gap \> 20%\
→ Trigger ENTITY_REINFORCEMENT_PROTOCOL

IF Citation Presence = 0\
AND Mentions \> 0\
→ Trigger STRUCTURED_CONTENT_OPTIMIZATION

IF Competitive Acceleration \> Target Growth\
→ Trigger AUTHORITY_SPRINT

Triggers attach modular action bundles.

------------------------------------------------------------------------

# 11. Action Bundle Framework

action_bundles - id - trigger_code - severity - recommended_modules -
priority_weight

Modules may include:

-   Schema Expansion
-   Authority Content Sprint
-   Backlink Acquisition
-   Review Velocity Campaign
-   Comparative Content Development
-   Internal Linking Restructure

Bundles are editable without rewriting decision engine.

------------------------------------------------------------------------

# 12. Feedback Reinforcement Loop

Track correlation between:

-   AI Visibility Score change
-   Organic ranking change
-   Lead volume change
-   Conversion change

If correlation \> threshold:

-   Increase weight confidence

If correlation weak:

-   Reduce signal influence

This allows internal model refinement without AI API dependency.

------------------------------------------------------------------------

# 13. Data Schema (Enterprise Dynamic)

ai_platforms ai_prompt_clusters ai_prompts ai_executions
ai_raw_responses ai_entity_mentions ai_signal_scores ai_cluster_scores
ai_volatility_metrics scoring_models scoring_factors action_bundles

All scoring references model_id for version control.

------------------------------------------------------------------------

# 14. Optional LLM Narrative Layer (Future)

LLM may be used for:

-   Executive summaries
-   Competitive narrative explanation
-   Content brief suggestions

Core intelligence functions independently of LLM APIs.

------------------------------------------------------------------------

# 15. Campaign Intelligence Integration

AI_VISIBILITY_SCORE feeds into:

CAMPAIGN_HEALTH_SCORE = Weighted Sum of Active Module Scores

Relative AI metrics influence:

-   Content roadmap prioritization
-   Authority sprint triggers
-   Review acceleration decisions
-   Technical structured data updates

------------------------------------------------------------------------

# 16. Governance Protocol

Every 6 months:

-   Review signal effectiveness
-   Adjust weights
-   Introduce new signal categories
-   Retire underperforming signals
-   Recompute percentile baselines

System evolution is procedural, not reactive.

------------------------------------------------------------------------

# 17. Enterprise Positioning

This module is:

-   Upper-tier feature
-   Competitive differentiation layer
-   AI-first positioning asset
-   Long-term data moat generator

------------------------------------------------------------------------

# 18. Customer AI Search Visibility Workspace

The customer product is a dedicated `AI Search Visibility` section, not a
general chatbot and not a single unexplained score.

It answers four owner questions:

1.  Where does my business appear in AI search?
2.  Which services, customer questions, and locations cause it to appear?
3.  Which competitors appear when my business does not?
4.  What evidence-backed improvement should I work on next?

The default workspace includes:

-   A location and portfolio selector
-   A supported-engine comparison
-   Mention, recommendation, citation, and link rates as separate facts
-   Question clusters based on confirmed services and service areas
-   Competitor share and cited-source comparisons
-   Historical change, sample size, volatility, and collection gaps
-   Question-level evidence and supported response excerpts
-   A direct path into governed content, entity, review, authority, and website
    actions

Supported engines are controlled by a versioned registry. Candidate surfaces
include Google AI Overviews and AI Mode, ChatGPT Search, Perplexity, Microsoft
Copilot, Gemini, and future material AI-search products. A surface is visible to
customers only after its production collection method, geography, language,
evidence, and historical-comparison behavior pass QA. Unavailable coverage is
never converted into a zero visibility result.

The monitored question set is bounded and reproducible. It is generated from
the confirmed business service catalog, real service areas, owner-approved
customer problems, and buying intent. Owners may add, pause, or reject a
question, but cannot use the feature for open-ended conversation. Each check
stores the exact question and available platform, location, language, device,
model, provider, and collection-version context.

Scheduled sampling is the default. Manual reruns are credit-priced,
rate-limited, and deduplicated so the product can protect margin without
weakening the saved historical record.

------------------------------------------------------------------------

# Conclusion

The Dynamic AI Visibility Intelligence Engine is not a static scoring
tool.

It is a configurable, evolving intelligence framework built to:

-   Adapt to AI ecosystem shifts
-   Maintain deterministic reliability
-   Preserve historical comparability
-   Integrate into campaign strategy
-   Evolve through versioned models

This architecture prevents obsolescence and positions the platform for
long-term competitive dominance.
