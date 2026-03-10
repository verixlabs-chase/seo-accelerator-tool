# SEARCH CAPITAL FORECAST ENGINE
## Enterprise Specification
Platform: SEO Accelerator Tool
Phase: Portfolio Intelligence (Phase 2.x)
Status: Specification Draft
Version: v1.1
Author: Platform Architecture
Last Updated: 2026-03-02

---

## 1. Executive Summary

The Search Capital Forecast Engine (SCFE) v1 is the platform's **Organic Media Value Engine**.

SCFE v1 is a deterministic replacement-cost valuation subsystem that estimates the paid-media equivalent value of organic rankings at keyword, cluster, campaign, and portfolio levels.

SCFE v1 answers:
- What is the current paid-equivalent value of the traffic represented by this ranking?
- What would that value become if rank improves?
- Which keywords have the highest economic upside based on paid replacement cost?

SCFE v1 is **not** accounting ROI, revenue attribution, or financial performance reporting. Those concerns belong to the separate ROI Attribution Engine.

---

## 2. Strategic Purpose

SCFE v1 enables the platform to move from diagnostics to asset valuation and capital planning:

- Organic vs paid replacement-cost comparison.
- Deterministic prioritization for portfolio allocation.
- Opportunity modeling for keyword ownership scenarios.
- Sales and executive narrative around owned organic media value.
- Tier differentiation for commercialization.

---

## 3. Scope and Non-Goals

### 3.1 In Scope (v1)

- Keyword-level and cluster-level paid-equivalent valuation.
- Deterministic CTR-curve based click modeling by rank.
- Rank-improvement forecasting based on CTR change.
- Keyword simulation for hypothetical target positions.
- Paid-equivalent benchmark model.
- Hash-stamped, replay-safe payloads.
- API and service-level contracts for downstream portfolio engines.

### 3.2 Out of Scope (v1)

- Revenue forecasting.
- Conversion delta modeling.
- Break-even CPC calculations.
- Accounting ROI, CAC, or LTV analysis.
- Machine-learned rank prediction.
- Real-time auction bid simulation.
- Cross-channel MMM attribution.
- Vertical-specific CTR tuning via AI.

Revenue attribution, ROI accounting, and related commercial metrics are reserved for the separate ROI Attribution Engine.

---

## 4. Core Definitions

- **Forecast Window**: fixed period for search demand and valuation assumptions (typically 30 days).
- **Current Rank**: observed baseline rank at forecast start.
- **Target Rank**: hypothetical or planned rank state for scenario simulation.
- **CTR Curve**: versioned mapping from rank position to click-through rate.
- **Estimated Clicks**: `search_volume * ctr(position)` under the active CTR curve.
- **Paid Equivalent Value**: estimated spend required to acquire equivalent traffic through ads.
- **Assumption Bundle**: immutable set of model constants (CTR curve, confidence multipliers, local market modifiers).

---

## 5. Functional Requirements

### 5.1 Organic Media Value Model

Inputs:
- `keyword`
- `search_volume_monthly`
- `current_rank`
- `target_rank`
- `ctr_curve_version`
- `cpc`

Outputs:
- Current estimated clicks.
- Target estimated clicks.
- Current paid-equivalent value.
- Target paid-equivalent value.
- Value delta.
- Confidence outputs for the valuation estimate.

### 5.2 Simulation Mode

SCFE v1 must support pure deterministic simulation for questions such as:
- If this keyword ranked at position `1`, what would it be worth?
- If this keyword moved from `5` to `2`, what is the projected value gain?

Simulation requirements:
- No persistence required for ad hoc scenario calls.
- No provider calls.
- Identical inputs must produce identical outputs.

### 5.3 Portfolio Readiness Outputs

SCFE v1 output schema must include fields consumable by portfolio allocation:
- `opportunity_score`
- `value_delta`
- `confidence_weight`
- `forecast_hash`

Capital allocation is a downstream consumer of SCFE v1. It does not redefine SCFE as ROI.

---

## 6. Deterministic Modeling Requirements

SCFE v1 must satisfy the following non-negotiable deterministic controls:

1. Canonical JSON serialization (`sort_keys=true`, compact separators).
2. Fixed precision rounding (6 decimals).
3. Stable ordering for all list outputs.
4. SHA256 hash of canonical payload.
5. Versioned assumption tables and CTR curves.
6. No randomization, wall-clock dependence, or mutable global state in output computation.
7. Replay-safe deterministic behavior in CI.

---

## 7. Mathematical Model (v1)

### 7.1 Click Projection

For a keyword:

- `clicks_current = search_volume_monthly * ctr(current_rank)`
- `clicks_target = search_volume_monthly * ctr(target_rank)`
- `clicks_delta = max(0, clicks_target - clicks_current)`

### 7.2 Paid Equivalent Valuation

- `value_current = clicks_current * cpc`
- `value_target = clicks_target * cpc`
- `value_delta = max(0, value_target - value_current)`

### 7.3 Opportunity Scoring

SCFE v1 may emit a deterministic opportunity score derived from:
- rank gap
- value delta
- confidence weight

The exact formula must be versioned in the assumption bundle and hash-locked in the output.

---

## 8. Confidence Model

SCFE v1 should emit deterministic confidence signals based on input quality.

Examples:
- lower confidence when search volume is missing or inferred
- lower confidence when CPC is inferred
- higher confidence when stored click data supports the estimate

Confidence multipliers are part of a versioned assumption bundle and must be hash-locked in output metadata.

Example structure:

```json
{
  "confidence": {
    "score": 0.0,
    "weight": 0.0,
    "inputs_complete": false
  }
}
```

---

## 9. Data Contracts

### 9.1 Request Contract (Planned)

`POST /api/v1/forecast/keyword`

```json
{
  "keyword": "local seo agency austin",
  "search_volume_monthly": 1200,
  "current_rank": 9,
  "target_rank": 3,
  "cpc": 18.5,
  "assumption_bundle_version": "scfe-assumptions-v1"
}
```

### 9.2 Response Contract (Planned)

```json
{
  "keyword": "...",
  "model_version": "scfe-v1",
  "engine_name": "organic-media-value-engine",
  "assumption_bundle_version": "scfe-assumptions-v1",
  "current_state": {
    "estimated_clicks": 0.0,
    "paid_equivalent_value": 0.0
  },
  "projected_state": {
    "estimated_clicks": 0.0,
    "paid_equivalent_value": 0.0
  },
  "delta": {
    "clicks": 0.0,
    "paid_equivalent_value": 0.0
  },
  "opportunity_score": 0.0,
  "confidence": {
    "score": 0.0,
    "weight": 0.0
  },
  "hash": "sha256hex"
}
```

---

## 10. Assumption and Version Governance

SCFE v1 requires versioned assumption artifacts:

- CTR curve tables.
- Confidence multipliers.
- Numeric constants and local market modifiers.

Governance controls:
- Each artifact version has immutable hash.
- Artifact changes require review and changelog entry.
- Replay corpus includes artifact version pins.

---

## 11. Replay, CI, and Drift Control

Required CI controls:

1. SCFE deterministic unit tests.
2. Replay corpus cases for representative forecast scenarios.
3. Drift gate that fails build on hash mismatch.
4. Manifest hash lock for baseline assumptions.

Replay additions:
- `forecast_keyword_baseline`
- `forecast_paid_equivalent_edge_cases`
- `forecast_confidence_stability`
- `forecast_zero_volume_and_zero_cpc`

---

## 12. Security and Data Handling

- Treat CPC assumptions and market modifiers as sensitive commercial metadata.
- Enforce tenant and organization scoping on all future forecast endpoints.
- Do not expose cross-tenant assumption artifacts or forecast records.
- Ensure PII is excluded from forecast payloads by design.

---

## 13. Relationship to ROI Attribution

SCFE v1 is not the ROI Attribution Engine.

SCFE v1 owns:
- CTR-based click estimation
- paid-equivalent valuation
- rank-improvement value forecasting
- deterministic keyword simulations

ROI Attribution Engine owns:
- conversion attribution
- revenue attribution
- accounting ROI
- CAC/LTV style business metrics
- other finance-grade outcome models built from revenue assumptions

If future SCFE versions add revenue overlays, those overlays must remain explicitly separated from SCFE v1's replacement-cost valuation core.
