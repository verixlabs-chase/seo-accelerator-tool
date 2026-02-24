# Deterministic SEO Strategy & Intelligence Engine (DSSIE)
## Version 4.1 — Enterprise Whitepaper (V3 Expansion + Agency-Replacement + AI Search Readiness + LLM Enhancements Roadmap)

**Version:** 4.1 (Superset of V3, expanded for Agency Replacement + AI Search)  
**Generated:** 2026-02-23  
**System Scope:** Local SEO Operating System (LSOS)  
**Layer Type:** Deterministic, Read-Only Intelligence + Planning Core  
**Primary Objective:** Replace the strategy + planning portion of SEO agencies for non-experts via plain-language, action-native roadmaps.  
**Secondary Objective:** Future-proof decision-making for AI Search Engines (AI Overviews, AI answers, LLM search assistants) and unlock a controlled “LLM augmentation layer” later—without compromising determinism.

---

## How to Read This Document

This whitepaper is intentionally **V3-expanded**, not a replacement.  
- **Sections 1–12** preserve and deepen the deterministic intelligence architecture described in V3.  
- **Sections 13–18** add the agency-replacement layers: task mapping, SOP library, sprint cadence, verification.  
- **Sections 19–21** address **AI Search Engines** (how the model adapts) and **LLM augmentations** (how to add safely later).  
- **Sections 22–26** cover governance, security, testing, scaling, and a phased implementation plan.

Where content does not fit V4’s modeling, it is **integrated as a constraint** or moved into **appendices**, not deleted arbitrarily.

---

# Table of Contents

1. [Executive Summary](#1-executive-summary)  
2. [Problem Statement](#2-problem-statement)  
3. [Definitions](#3-definitions)  
4. [System Goals, Guardrails, Non-Goals](#4-system-goals-guardrails-non-goals)  
5. [Architecture Overview (V3 → V4.1)](#5-architecture-overview-v3--v41)  
6. [Data Inputs: How DSSIE Gets Data](#6-data-inputs-how-dssie-gets-data)  
7. [Interpretation Pipeline: Deterministic Intelligence Flow](#7-interpretation-pipeline-deterministic-intelligence-flow)  
8. [Signal Model (Enterprise Spec)](#8-signal-model-enterprise-spec)  
9. [Temporal Intelligence Layer](#9-temporal-intelligence-layer)  
10. [Diagnostic Modules Framework](#10-diagnostic-modules-framework)  
11. [Scenario Registry + Knowledge Base](#11-scenario-registry--knowledge-base)  
12. [Opportunity Modeling + Priority Engine](#12-opportunity-modeling--priority-engine)  
13. [Roadmap Generation Engine (Scalable Roadmaps)](#13-roadmap-generation-engine-scalable-roadmaps)  
14. [Agency-Replacement Output Contract (Plain Language)](#14-agency-replacement-output-contract-plain-language)  
15. [Task Library Framework (TaskTypes + SOPs + DoD)](#15-task-library-framework-tasktypes--sops--dod)  
16. [Beginner vs Advanced Modes (Safety Levels)](#16-beginner-vs-advanced-modes-safety-levels)  
17. [Verification Loop (Did It Work?)](#17-verification-loop-did-it-work)  
18. [Portfolio Allocation (Multi-Location + Agency Mode)](#18-portfolio-allocation-multi-location--agency-mode)  
19. [AI Search Engines: How DSSIE Adapts](#19-ai-search-engines-how-dssie-adapts)  
20. [LLM Enhancements Roadmap (Controlled Augmentation)](#20-llm-enhancements-roadmap-controlled-augmentation)  
21. [Human-in-the-Loop and “Escalation to Expert” Design](#21-human-in-the-loop-and-escalation-to-expert-design)  
22. [Governance: Versioning, Threshold Controls, Release Safety](#22-governance-versioning-threshold-controls-release-safety)  
23. [Security + Isolation](#23-security--isolation)  
24. [Testing + Validation Framework](#24-testing--validation-framework)  
25. [Scaling Model + Cost Controls](#25-scaling-model--cost-controls)  
26. [Implementation Roadmap (Phases 12–20)](#26-implementation-roadmap-phases-12--20)  
27. [Appendices (Schematics, Templates, Examples)](#27-appendices-schematics-templates-examples)

---

# 1. Executive Summary

The **Deterministic SEO Strategy & Intelligence Engine (DSSIE)** is the intelligence core of the Local SEO Operating System (LSOS).  
DSSIE’s purpose is to convert normalized signals (organic, technical, content, local, GBP, reviews, maps, competitor baselines) into:

- deterministic scenario classifications  
- evidence-backed recommendations  
- ROI-aware prioritization  
- **phased roadmaps**  
- **weekly sprint plans**  
- plain-language step-by-step tasks (agency replacement)

DSSIE remains **AI-free** and deterministic at its core, enabling:

- auditability (why was this recommended?)  
- repeatability (same inputs → same outputs)  
- regression testing (threshold changes don’t silently break results)

**V4.1 adds:**
- Action-native TaskTypes with SOPs, templates, definition-of-done (DoD), and verification metrics
- Beginner/Advanced safety modes to protect non-experts
- An explicit **AI Search readiness layer**: entity coverage, citation readiness, structured evidence, and “AI visibility signals”
- A controlled **LLM augmentation roadmap** that improves communication and workflows without compromising determinism

---

# 2. Problem Statement

## 2.1 Why SEO Tools Fail Non-Experts
Most tools provide data and generic recommendations, but non-experts need:
- a clear next action
- plain-language instructions
- sequencing and constraints
- confidence and expected outcomes
- verification (“did it work?”)

## 2.2 What Agencies Actually Sell
Agencies deliver (mostly):
- prioritization and sequencing
- playbooks and SOPs
- accountability and reporting
- expertise escalation when needed

DSSIE targets agency replacement for **strategy + planning + guided execution**, while allowing escalation for high-risk work.

---

# 3. Definitions

**Signal:** numeric/boolean metric with explicit window and provenance.  
**Scenario:** deterministic diagnosis classification triggered by rules + evidence.  
**Recommendation:** pre-authored action bundle mapped from scenario.  
**TaskType:** action-native unit for non-experts with SOP + DoD + verification.  
**Roadmap:** phased plan allocating TaskTypes under constraints.  
**Verification:** deterministic checks comparing before/after windows to classify success.  
**AI Search Engine:** systems that produce AI-generated answers or summaries based on web content and citations.

---

# 4. System Goals, Guardrails, Non-Goals

## 4.1 Goals
1. Deterministic, cross-signal scenario detection.
2. Opportunity modeling (uplift + gap indices).
3. Priority scoring under constraints.
4. Roadmap generation and sprint planning.
5. Task-level plain-language guidance with DoD and verification.
6. AI Search readiness signals and roadmap integration.
7. Multi-tenant safe operation.

## 4.2 Guardrails (Hard Requirements)
- No probabilistic/ML reasoning in the core engine.
- No external API calls from DSSIE.
- No mutation of provider execution, OAuth, telemetry write paths.
- No cross-module imports.
- Strict org_id isolation and read-only behavior.
- Competitor signals optional; must degrade gracefully.

## 4.3 Non-Goals
- DSSIE does not execute tasks (it plans).
- DSSIE does not scrape SERPs or pull providers (upstream engines do).
- DSSIE does not write content (but may generate briefs/templates later via LLM layer—optional).
- DSSIE is not a billing engine (but provides effort/cost estimates used by billing later).

---

# 5. Architecture Overview (V3 → V4.1)

## 5.1 V3 Baseline Pipeline
```text
SignalModel → Temporal Derivation → Diagnostic Modules → Scenario Registry
→ Opportunity Modeling → Priority Engine → StrategyOut
```

## 5.2 V4.1 Expanded Planning Pipeline
```text
SignalModel
→ Temporal Derivation (trend/volatility)
→ Diagnostic Modules (ScenarioMatches)
→ Scenario Registry (pre-authored mapping)
→ Opportunity Modeling (uplift + indices)
→ Priority Engine (ROI + effort + risk)
→ Task Mapper (Scenario → TaskTypes)
→ Roadmap Generator (Phases + sequencing + constraints)
→ Sprint Planner (Weekly plan for non-experts)
→ Verification Planner (metrics + timeframes)
→ StrategyOut + RoadmapOut + SprintOut
```

## 5.3 Directory Additions (Recommended)
`backend/app/services/strategy_engine/`
- `temporal_derivation.py`
- `opportunity_modeling.py`
- `task_mapper.py`
- `roadmap_generator.py`
- `sprint_planner.py`
- `verification_planner.py`
- `ai_visibility_diagnostics.py` (new module group)
- `llm_augmentation/` (future; optional and isolated)

---

# 6. Data Inputs: How DSSIE Gets Data

DSSIE is **read-only** and consumes normalized outputs from upstream engines.

## 6.1 Upstream Engines (Typical)
- Technical SEO Engine (crawl, indexation, CWV)
- Rank Tracking Engine (organic + maps positions)
- Content Analyzer (structure, depth, schema, duplication)
- GBP Engine (views, actions, completeness, content cadence)
- Reviews Engine (velocity, rating, response time)
- Competitor Engine (optional baselines)
- (Future) AI Visibility Engine (citation presence, entity coverage scoring, structured data validation for AI)

## 6.2 Data Retrieval Contract
`build_campaign_strategy(campaign_id, date_from, date_to)`
1. Resolve org + campaign scope
2. Fetch aggregated snapshot signals (typically 30d)
3. Fetch time-series points (7/30/90) if enabled
4. Fetch competitor baselines if available
5. Validate/normalize inputs into SignalModel + Meta

## 6.3 Freshness Metadata
Every build includes:
- last_updated timestamps
- freshness seconds
- upstream engine versions

If freshness is stale beyond threshold, DSSIE emits:
- `data_stale_warning` (monitor-only) and deprioritizes recommendations that depend on stale signals.

---

# 7. Interpretation Pipeline: Deterministic Intelligence Flow

## Stage A — Validation
- numeric/boolean enforcement
- clamping (CTR 0–1, rating 0–5)
- unit normalization (ms)
- optional competitor tolerance

## Stage B — Temporal Derivation
- slope, volatility, acceleration, stability indices
- distinguishes structural vs transient issues

## Stage C — Diagnostic Modules
Each module returns ScenarioMatches only:
- scenario_id
- confidence (deterministic)
- signal_magnitude (deterministic)
- evidence list

## Stage D — Registry Mapping
Scenario registry supplies:
- diagnosis
- root cause
- recommended actions
- expected outcomes
- sources
- weights, effort, risk, dependencies

## Stage E — Opportunity Modeling
Compute:
- CTR uplift estimate
- local action uplift proxies
- competitor gap indices
- opportunity_score (0–1)

## Stage F — Priority Engine
Compute ROI-adjusted priority:
- projected value × weights × confidence ÷ effort

## Stage G — Task Mapping
Translate scenario → TaskTypes (action-native units):
- SOP steps
- templates
- DoD
- verification plan
- safety level

## Stage H — Roadmap + Sprint Planning
Generate:
- phased roadmap (30/60/90)
- weekly sprint tasks (3–7/week)
- dependencies + constraints enforced

---

# 8. Signal Model (Enterprise Spec)

This section retains V3’s signal model. Only additions are AI Search readiness signals (Section 19).

## 8.1 Organic Performance
- clicks, impressions, ctr, avg_position, position_delta, sessions, conversions, traffic_growth_percent

## 8.2 Technical SEO
- lcp_ms, inp_ms, cls, ttfb_ms, mobile_usability_errors, index_coverage_errors, crawl_errors

## 8.3 Content Signals
- word_count, title_length, title_keyword_position, meta_description_length, structured_data_present, duplicate_title_flag, cannibalization_flag

## 8.4 GBP Signals
- gbp_views_search, gbp_views_maps, gbp_total_views, calls, website_clicks, direction_requests, photo_views, photo_count, posts_last_30_days, qna_count, services_count, products_count, category_match_flag, secondary_category_count, completeness_score

## 8.5 Reviews
- total_reviews, review_growth_30d, review_velocity_90d, average_rating, rating_delta_90d, negative_review_ratio, review_response_rate, avg_review_response_time_hours

## 8.6 Map Pack
- map_avg_position, map_position_delta, map_impressions, map_actions

## 8.7 Competitor Signals (Optional)
- competitor_* equivalents per V3

---

# 9. Temporal Intelligence Layer

Retains V3 but expanded with “stability weighting” used for non-expert roadmaps.

## 9.1 Derived Temporal Signals
- ctr_trend_slope
- ranking_trend_slope
- ranking_volatility_index
- review_velocity_acceleration
- gbp_engagement_trend_slope
- core_web_vitals_stability_index
- map_visibility_trend_slope

## 9.2 Stability Weighting
Introduce:
- `confidence_stability_factor` (0–1)
Used to:
- reduce priority for volatile signals unless defensive scenario triggered
- avoid whiplash roadmaps for non-experts

---

# 10. Diagnostic Modules Framework

## 10.1 Module Contract (unchanged)
No cross-imports, scenario matches only.

## 10.2 Deterministic Confidence
Confidence is a deterministic proxy for “strength of corroboration”:
- corroborating signals increase confidence
- temporal stability increases confidence
- competitor baseline increases confidence (if available)

## 10.3 Evidence Requirements
Evidence must include:
- signal_name
- current_value
- threshold/comparator
- optional baseline
- severity/magnitude

This is essential for both:
- trust (non-experts)
- auditability (enterprise)

---

# 11. Scenario Registry + Knowledge Base

Retains V3 schema plus agency-replacement metadata.

## 11.1 Scenario Definition Schema (V4.1)
Additions to V3:
- `task_types[]` (recommended TaskTypes for this scenario)
- `beginner_safe: bool`
- `verification_ruleset_id`
- `plain_language_why` (pre-authored)
- `plain_language_risk_warning` (pre-authored, optional)

## 11.2 Threshold Versioning (Mandatory)
All thresholds versioned:
- prevents silent strategy drift
- enables safe rollouts and rollback

---

# 12. Opportunity Modeling + Priority Engine

## 12.1 Opportunity Modeling (Deterministic)
- CTR uplift modeling via CTR curve
- review gap indices vs competitor
- map visibility uplift proxies
- GBP engagement uplift proxies

Outputs:
- `opportunity_score`
- `projected_click_uplift_range`
- `projected_local_actions_uplift_range`

## 12.2 ROI-Based Priority (Deterministic)
```text
priority_score =
  (projected_value_score * impact_weight * confidence * stability_factor)
  / max(effort_hours_estimate, 1)
```
- stability_factor reduces “chase noise” behavior for beginners

---

# 13. Roadmap Generation Engine (Scalable Roadmaps)

## 13.1 Roadmap Objectives
Roadmaps must be:
- phased (quick wins → foundation → competitive → defensive)
- capacity-aware (hours/week)
- dependency-aware
- safety-aware (beginner vs advanced)

## 13.2 Roadmap Artifacts (Outputs)
- `CampaignRoadmapOut` (30/60/90 days)
- `SprintPlanOut` (week 1..N tasks)
- `BacklogOut` (deprioritized tasks)

## 13.3 Sequencing Rules (Deterministic)
1. If technical risk high → prioritize foundation tasks first.
2. If CTR opportunity high and safe → quick wins first.
3. If map pack decline + competitor pressure high → review + GBP + local tasks prioritized.
4. Do not schedule multiple high-risk tasks in same sprint.
5. Respect content production cap.

---

# 14. Agency-Replacement Output Contract (Plain Language)

For each roadmap item, the system must output:

- **Do this next** (one sentence)
- **Why it matters** (one sentence, non-jargon)
- **How to do it** (SOP steps)
- **Time estimate** (minutes/hours)
- **Difficulty** (1–5)
- **Safety level** (beginner/advanced)
- **Definition of done** (objective checklist)
- **Verification** (metric + timeframe + success thresholds)
- **Escalation note** (when to hire expert)

This is the key “agency replacement” product contract.

---

# 15. Task Library Framework (TaskTypes + SOPs + DoD)

## 15.1 TaskType Schema
A TaskType is a reusable execution primitive.

Fields:
- task_type_id
- title_plain
- objective_plain
- prerequisites[]
- steps[] (SOP)
- templates[] (copy/paste)
- definition_of_done[]
- verification[]
- rollback_guidance
- estimated_time_minutes
- difficulty (1–5)
- safety_level (beginner/advanced)
- applicable_scenarios[]

## 15.2 TaskType Categories (Minimum Viable)
- CTR (titles/meta/snippets)
- GBP (completeness/posts/photos/services/products)
- Reviews (requests/responses/playbook)
- Technical (CWV/indexation/crawl errors) — advanced mode mostly
- Content structure (depth/internal linking) — beginner-safe subsets
- Local (map pack position hygiene actions)

---

# 16. Beginner vs Advanced Modes (Safety Levels)

## 16.1 Beginner Mode
Allowed:
- GBP completeness/cadence
- review workflows
- titles/meta updates
- safe content edits (non-structural)
- internal linking suggestions (guarded)

Blocked:
- URL changes
- noindex/canonical changes
- architecture rewrites
- advanced schema rewrites

## 16.2 Advanced Mode
Unlocks:
- technical remediation playbooks
- structural content architecture changes
- deeper schema/technical tasks with warnings

---

# 17. Verification Loop (Did It Work?)

## 17.1 Verification States
- not_started
- in_progress
- completed_unverified
- validated_success
- validated_no_change
- validated_negative_change

## 17.2 Verification Rules (Deterministic)
Each task references a ruleset:
- metric
- window
- threshold
- stability constraints

Example (CTR task):
- success if CTR +15% over 28 days while impressions stable (±10%).

---

# 18. Portfolio Allocation (Multi-Location + Agency Mode)

Portfolio allocator ranks tasks across campaigns under a shared budget:
- hours/month
- max campaigns/week
- risk posture
- strategic focus (local vs organic)

Outputs:
- PortfolioRoadmapOut
- campaign allocations
- resource usage

---

# 19. AI Search Engines: How DSSIE Adapts

## 19.1 What “AI Search” Changes
AI Search Engines (AI overviews, assistant answers) shift discovery toward:
- entity-based retrieval
- semantic coverage
- citation quality (sources chosen for authority and clarity)
- structured information extraction
- trust and reputation signals

Classic SEO signals still matter, but “ranking a blue link” isn’t the only goal.

## 19.2 AI Visibility Objectives (Deterministic)
DSSIE adds an **AI Visibility Diagnostics Module** that scores readiness via deterministic checks:

### A) Entity Coverage Signals
- entity_coverage_score (0–1)
- primary_service_entity_present_flag
- location_entity_present_flag
- faq_coverage_flag
- policy_trust_page_present_flag (contact/about/privacy/returns depending on vertical)

### B) Citation Readiness Signals
- authoritativeness_proxy_score (0–1) (non-ML: based on structured signals like citations count, schema completeness, external mention count from upstream engine)
- page_clarity_score (0–1) (deterministic: heading structure, summary blocks, FAQ presence)
- source_consistency_score (NAP + canonical consistency)

### C) Structured Data & Extraction Signals
- structured_data_present_flag
- schema_type_coverage_score
- faq_schema_present_flag (where appropriate)
- organization_schema_present_flag
- local_business_schema_present_flag

### D) Trust/Experience Signals (Non-ML)
- review_volume_index
- rating_stability_index
- response_rate_index
- content_freshness_index (posts/updates cadence)

## 19.3 AI Search Scenarios (Examples)
- ai_citation_readiness_low
- entity_coverage_gap_detected
- structured_data_extraction_gap
- trust_signal_deficit_for_ai

## 19.4 AI Search Roadmap Integration
AI visibility tasks are placed into phases:
- Quick wins: add structured “summary blocks,” FAQ sections, schema completeness
- Foundation: entity coverage across service/location pages, trust pages
- Competitive: authoritative citations and mentions (from upstream authority engine), consistent brand footprint
- Defensive: maintain freshness and trust stability

## 19.5 What DSSIE Does NOT Do for AI Search
- It does not “generate AI content” by default.
- It does not claim direct AI overview placement.
- It does not fabricate citations.
It provides **deterministic readiness and coverage planning**, which is the right long-term posture.

---

# 20. LLM Enhancements Roadmap (Controlled Augmentation)

This section defines how to use LLMs later **without corrupting determinism**.

## 20.1 Principle: LLMs Must Not Decide
LLMs may assist with:
- summarization
- rewriting into plain language
- generating SOP-friendly wording
- drafting content briefs
- producing outreach templates

LLMs must **not**:
- determine scenario triggers
- compute scores
- override thresholds
- change prioritization

## 20.2 LLM Augmentation Layer (Isolation Model)
Add a separate layer:
`llm_augmentation/`
Inputs:
- already-determined scenarios + evidence + roadmap
Outputs:
- human-readable explanations
- task instructions variations
- content briefs

This ensures the intelligence engine remains deterministic and testable.

## 20.3 Safe LLM Use Cases (High ROI)
1. **Plain-language translation** of evidence into user-friendly phrasing (bounded templates).
2. **Task SOP personalization**: adjust steps to CMS type (WordPress vs Webflow) using controlled prompt templates.
3. **Content brief generation**: headings, entity checklist, internal links plan (not full articles by default).
4. **Support assistant**: answer “how do I do this step?” using your SOP library as ground truth.
5. **Executive summaries**: narrative layer for reports (separate from core output contract).

## 20.4 Guardrails for LLM Layer
- Must cite source evidence items (structured references).
- Must not invent metrics.
- Must not change priority ordering.
- Must pass “no hallucination” validation checks:
  - every numeric claim must map to a real evidence field.
- Must be fully optional and feature-flagged.

## 20.5 Long-Term “Next Level” (LLM + Deterministic Hybrid)
When mature, LLMs can enhance:
- scenario coverage expansion drafting (humans approve)
- playbook generation from observed outcomes (humans approve)
- multi-vertical language adaptation

But deterministic core remains the arbitration layer.

---

# 21. Human-in-the-Loop and “Escalation to Expert” Design

Agency replacement requires clear boundaries:
- when a non-expert can proceed
- when to escalate

## 21.1 Escalation Triggers (Deterministic)
If task risk high OR requires code changes:
- escalate_to_expert = true
- show a constrained checklist for hiring a dev (what to ask, what success looks like)

Examples:
- CWV deep remediation
- indexation anomalies requiring server logs
- canonical/noindex decisions

This is how you avoid users breaking sites while still replacing agencies for planning.

---

# 22. Governance: Versioning, Threshold Controls, Release Safety

Version everything:
- engine semantic version
- scenario threshold versions
- task library versions
- CTR curve versions
- verification rules versions

Release model:
- canary org rollout
- regression suite gate
- rollback by version pinning

---

# 23. Security + Isolation

- org_id required for all reads
- no secrets in logs
- no uncontrolled text in inputs
- strict output schemas
- feature gating per tier
- audit logs for threshold changes and roadmap generation

---

# 24. Testing + Validation Framework

Add to V3 suite:
- task mapper tests
- roadmap sequencing under constraints tests
- beginner mode restriction tests
- verification rule tests
- AI visibility scenario tests
- LLM augmentation validation tests (if enabled)

Golden snapshots:
- inputs → scenarios → tasks → roadmap → sprint plan

Target: 95%+ deterministic path coverage.

---

# 25. Scaling Model + Cost Controls

DSSIE compute is lightweight; scaling pain comes from upstream data engines.  
Controls:
- per-org schedule for strategy builds
- caching last strategy output if signals unchanged
- strict cardinality on metrics
- quotas on upstream ingestion and SERP tooling later

---

# 26. Implementation Roadmap (Phases 12–20)

**Phase 12:** Global Idempotency Layer (platform prerequisite)  
**Phase 13:** Temporal Intelligence (timeseries + derived signals)  
**Phase 14:** Opportunity modeling + ROI scoring improvements  
**Phase 15:** Task mapper + SOP library + Roadmap generator + Sprint planner  
**Phase 16:** Verification planner + validation states + outcome logging (optional bounded adaptation)  
**Phase 17:** Portfolio allocator + multi-location playbooks  
**Phase 18:** AI visibility diagnostics + entity coverage roadmap features  
**Phase 19:** Controlled LLM augmentation layer (optional, feature-flagged)  
**Phase 20:** Governance automation + advanced explainability graph UI support

---

# 27. Appendices (Schematics, Templates, Examples)

## Appendix A — TaskType Template (YAML)
```yaml
task_type_id: task.optimize_titles_top_pages
title_plain: "Improve the page titles people see in Google"
objective_plain: "Increase clicks without needing better rankings"
safety_level: beginner
estimated_time_minutes: 60
difficulty: 2
prerequisites:
  - "Access to your website CMS"
steps:
  - "Open the list of top pages provided"
  - "Update the title using the template"
templates:
  - "Primary service + city | Brand"
definition_of_done:
  - "Titles updated on the top 5 pages by impressions"
verification:
  - metric: ctr
    window_days: 28
    success_threshold: "ctr +15% with stable impressions (±10%)"
rollback_guidance: "Restore previous titles from history if CTR drops"
applicable_scenarios:
  - high_visibility_low_ctr
```

## Appendix B — Evidence Item Example
```json
{
  "signal_name": "ctr",
  "signal_value": 0.031,
  "comparator": "<",
  "threshold": 0.06,
  "reference_value": 0.08,
  "notes_code": "CTR_BELOW_EXPECTED_FOR_POSITION"
}
```

## Appendix C — AI Visibility Task Examples
- Add FAQ section for core services + locations
- Add Organization/LocalBusiness schema completeness
- Add “trust pages”: About, Contact, Privacy, Refunds (vertical-dependent)
- Add page summary block (“What we do / where we serve / why trust us”)

---

## End of DSSIE V4.1 Whitepaper
