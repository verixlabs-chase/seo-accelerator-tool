# SEARCH CAPITAL FORECAST ENGINE
## Enterprise Specification
Platform: SEO Accelerator Tool  
Phase: Portfolio Intelligence (Phase 2.x)  
Status: Specification Draft  
Version: v1.0  
Author: Platform Architecture  
Last Updated: 2026-02-27

---

## 1. Executive Summary

The Search Capital Forecast Engine (SCFE) is a deterministic forecasting subsystem that estimates the economic value of SEO ranking improvements at keyword, cluster, campaign, and portfolio levels.

SCFE is designed to convert search opportunity into capital allocation decisions by quantifying:

- Incremental organic click and conversion potential.
- Revenue uplift bands (low/median/high).
- Paid-media equivalent cost.
- Break-even CPC and efficiency ratios.
- Forecast confidence and assumption sensitivity.

SCFE is **decision support**, not financial guarantee. All outputs are deterministic for identical inputs and assumption versions.

---

## 2. Strategic Purpose

SCFE enables the platform to move from diagnostics to capital planning:

- Executive ROI forecasting for board-level planning.
- Organic vs paid investment comparison.
- Deterministic prioritization for portfolio allocation.
- Tier differentiation for commercialization.
- Better attribution narrative for agencies and enterprise operators.

---

## 3. Scope and Non-Goals

### 3.1 In Scope (v1)

- Keyword-level and cluster-level forecast generation.
- Deterministic CTR-curve based click modeling by rank.
- Conversion/revenue delta modeling with confidence bands.
- Paid-equivalent benchmark model.
- Hash-stamped, replay-safe payloads.
- API and service-level contracts for downstream portfolio engines.

### 3.2 Out of Scope (v1)

- Machine-learned rank prediction.
- Real-time auction bid simulation.
- Cross-channel MMM attribution.
- Vertical-specific CTR tuning via AI.

---

## 4. Core Definitions

- **Forecast Window**: fixed period for volume and value assumptions (typically 30 days).
- **Current Rank**: observed baseline rank at forecast start.
- **Target Rank**: hypothetical or planned rank state for scenario simulation.
- **CTR Curve**: versioned mapping from rank position to click-through rate.
- **Capital Efficiency Index (CEI)**: normalized value-to-cost efficiency signal for ranking opportunity.
- **Paid Equivalent Cost**: estimated spend required to acquire equivalent traffic through ads.
- **Break-even CPC**: CPC threshold where paid cost equals forecasted organic value.
- **Assumption Bundle**: immutable set of model constants (CTR, CVR modifiers, confidence multipliers).

---

## 5. Functional Requirements

### 5.1 Organic Revenue Forecast Model

Inputs:
- `keyword`
- `search_volume_monthly`
- `current_rank`
- `target_rank`
- `ctr_curve_version`
- `conversion_rate`
- `revenue_per_conversion`

Outputs:
- Current projected clicks.
- Target projected clicks.
- Incremental clicks and conversions.
- Incremental revenue delta.
- Confidence band outputs (`low`, `median`, `high`).

### 5.2 Paid Benchmark Comparison

Inputs:
- `cpc` (manual or provider-sourced)
- `paid_conversion_rate` (optional override)
- `paid_ctr` (optional, primarily for advanced paid simulation)

Outputs:
- Paid equivalent cost for projected organic incremental traffic.
- Break-even CPC.
- CEI and related ranking signals.

### 5.3 Portfolio Readiness Outputs

SCFE output schema must include fields consumable by portfolio allocator:
- `opportunity_score`
- `capital_efficiency_index`
- `confidence_weight`
- `forecast_hash`

---

## 6. Deterministic Modeling Requirements

SCFE must satisfy the following non-negotiable deterministic controls:

1. Canonical JSON serialization (`sort_keys=true`, compact separators).
2. Fixed precision rounding (6 decimals).
3. Stable ordering for all list outputs.
4. SHA256 hash of canonical payload.
5. Versioned assumption tables and CTR curves.
6. No randomization, wall-clock dependence, or mutable global state.
7. Replay-safe deterministic behavior in CI.

---

## 7. Mathematical Model (v1)

### 7.1 Click Projection

For a keyword:

- `clicks_current = search_volume_monthly * ctr(current_rank)`
- `clicks_target = search_volume_monthly * ctr(target_rank)`
- `clicks_delta = max(0, clicks_target - clicks_current)`

### 7.2 Conversion and Revenue Projection

- `conversions_delta = clicks_delta * conversion_rate`
- `revenue_delta = conversions_delta * revenue_per_conversion`

### 7.3 Paid Equivalent

- `paid_equivalent_cost = clicks_delta * cpc`
- `break_even_cpc = revenue_delta / max(clicks_delta, epsilon)`

### 7.4 Capital Efficiency (Reference Formula)

- `cei = revenue_delta / max(paid_equivalent_cost, epsilon)`

Where `epsilon` is a deterministic small constant defined in the assumption bundle.

---

## 8. Confidence Band Model

SCFE must emit three deterministic bands:

- **Low**: conservative multipliers on CTR/CVR/value assumptions.
- **Median**: baseline assumptions.
- **High**: optimistic but bounded assumptions.

Band multipliers are part of a versioned assumption bundle and must be hash-locked in output metadata.

Example structure:

```json
{
  "confidence_band": {
    "low": {"revenue_delta": 0.0},
    "median": {"revenue_delta": 0.0},
    "high": {"revenue_delta": 0.0}
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
  "conversion_rate": 0.03,
  "revenue_per_conversion": 850,
  "paid": {
    "cpc": 18.5,
    "paid_conversion_rate": 0.025
  },
  "assumption_bundle_version": "scfe-assumptions-v1"
}
```

### 9.2 Response Contract (Planned)

```json
{
  "keyword": "...",
  "model_version": "scfe-v1",
  "assumption_bundle_version": "scfe-assumptions-v1",
  "current_state": {},
  "projected_state": {},
  "delta": {
    "clicks": 0.0,
    "conversions": 0.0,
    "revenue": 0.0
  },
  "paid_equivalent": {
    "cost": 0.0,
    "break_even_cpc": 0.0
  },
  "capital_efficiency_index": 0.0,
  "confidence_band": {
    "low": {},
    "median": {},
    "high": {}
  },
  "hash": "sha256hex"
}
```

---

## 10. Assumption and Version Governance

SCFE requires versioned assumption artifacts:

- CTR curve tables.
- Confidence band multipliers.
- Numeric constants (`epsilon`, caps/floors).

Governance controls:
- Each artifact version has immutable hash.
- Artifact changes require review + changelog entry.
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
- `forecast_confidence_band_stability`
- `forecast_zero_volume_and_zero_cpc`.

---

## 12. Portfolio Integration Requirements

SCFE outputs must integrate cleanly with:

- Portfolio momentum model.
- Portfolio allocation engine.
- Strategy automation loop.
- Executive reporting and board exports.

Integration contract expectations:
- Deterministic per-keyword opportunity records.
- Aggregatable to campaign and portfolio dimensions.
- Stable IDs/hashes for downstream caching and dedupe.

---

## 13. Security and Compliance Considerations

- Treat revenue assumptions as sensitive commercial metadata.
- Enforce tenant and organization scoping on all forecast endpoints.
- Log access and compute events to audit trail.
- Do not expose cross-tenant assumption artifacts or forecast records.
- Ensure PII is excluded from forecast payloads by design.

---

## 14. Failure Modes and Guardrails

Expected failure classes:

- Invalid rank/volume ranges.
- Missing/invalid assumption bundle version.
- Numerical instability (divide by zero protections).
- Missing paid benchmark inputs.

Guardrails:
- Strong schema validation and bounded numeric ranges.
- Deterministic fallback behavior for optional paid fields.
- Explicit reason codes for rejected requests.

---

## 15. Commercialization Strategy

Suggested packaging:

- **Base**: manual ROI input and keyword-level forecast.
- **Pro**: live rank-linked forecast + cluster aggregation.
- **Enterprise**: portfolio capital forecasting + allocation-ready output.
- **Executive**: board-grade exports and attribution overlays.

Monetizable differentiators:
- Forecast confidence controls.
- Portfolio-level CEI prioritization.
- Decision-ready exports for C-suite reporting.

---

## 16. Roadmap Placement

- **Phase 2.x**: SCFE core model + deterministic contracts + keyword endpoint.
- **Phase 3**: portfolio control plane integration.
- **Phase 4**: executive attribution and capital efficiency dashboards.
- **Phase 6**: commercialization hardening and entitlement enforcement.

---

## 17. Success Metrics

Primary metrics:
- Forecast usefulness adoption (% of active users invoking SCFE).
- Forecast-to-realized directional accuracy.
- % of allocation decisions influenced by SCFE CEI.
- Executive report engagement on forecast sections.

Reliability metrics:
- Replay drift count (target: zero).
- Deterministic hash stability across environments.
- API p95 latency and error rates.

---

## 18. Future Enhancements

- Deterministic rank trajectory modeling from historical slope and volatility.
- SERP volatility adjustment factors.
- Competitive paid overlap modifiers.
- Vertical-specific assumption bundles (still deterministic/versioned).
- Attribution confidence scoring tied to realized outcomes.

---

## 19. Open Questions

- Preferred default CTR curve source and update cadence.
- Minimum data completeness threshold for exposing confidence bands.
- Paid benchmark fallback policy when CPC unavailable.
- How CEI should be normalized across heterogeneous campaign verticals.

---

## 20. Implementation Readiness Checklist

SCFE is build-ready when:

1. Assumption bundle schema and governance policy approved.
2. Deterministic math library and rounding conventions finalized.
3. Replay corpus extension plan accepted.
4. API contract reviewed by platform and reporting teams.
5. Commercial packaging and entitlement mapping approved.

---

## 21. Codex Engineering Directive (Future Build)

When implementing SCFE:

1. Build pure deterministic service first (no side effects).
2. Lock assumption versioning before API release.
3. Add replay corpus and CI drift gate before rollout.
4. Integrate with portfolio allocator only after deterministic stability is verified.
5. Keep paid comparisons explicit as benchmark assumptions, never as guarantees.

---

END OF DOCUMENT