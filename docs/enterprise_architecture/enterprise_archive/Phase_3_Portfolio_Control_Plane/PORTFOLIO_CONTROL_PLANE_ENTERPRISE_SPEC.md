# PORTFOLIO CONTROL PLANE
## Enterprise Specification
Platform: SEO Accelerator Tool
Phase: Phase 3 Portfolio Control Plane
Status: Architecture Initiation Spec
Version: v1.0
Last Updated: 2026-02-27
Owner: Platform Architecture

---

## 1. Executive Summary

The Portfolio Control Plane (PCP) is the capital orchestration layer that elevates the platform from campaign-level intelligence to portfolio-level authority. It coordinates deterministic cross-campaign prioritization, allocation governance, and automation lifecycle control with replay-safe auditability.

PCP is not an analytics add-on. It is a platform governance layer that:
- Turns portfolio signals into deterministic intervention decisions.
- Persists all orchestration decisions as hash-stamped events.
- Enforces tier-aware allocation policy and risk guardrails.
- Serves allocation and automation state through stable API contracts.

---

## 2. Strategic Objective

Primary objective: move system posture from **Campaign Intelligence** to **Portfolio Authority**.

Strategic outcomes:
- Unified portfolio-level decisioning and control.
- Deterministic capital allocation under bounded risk.
- Enterprise-grade governance for multi-campaign operations.
- Executive-grade orchestration visibility.

---

## 3. Functional Scope

### 3.1 Portfolio Automation Events
- Persist every control-plane cycle decision.
- Include deterministic input/output hashes and version fingerprints.
- Support timeline replay and drift diagnostics.

### 3.2 Cross-Campaign Prioritization Engine
- Rank intervention candidates across campaigns.
- Use deterministic weighting from momentum, drift, opportunity, and risk.
- Produce stable ordering under identical input state.

### 3.3 Portfolio Phase Model
Supported phases:
- `recovery`
- `stabilize`
- `expand`
- `dominate`

Phase transitions are rules-driven and event-persisted.

### 3.4 Allocation Proposal Persistence
- Persist all allocation proposals and decision rationale.
- Keep proposal hash immutable after finalization.
- Maintain acceptance/rejection outcomes for learning telemetry.

### 3.5 Deterministic Intervention Ranking
- Stable sort strategy with explicit tie-breakers.
- Bounded weight normalization.
- No stochastic ranking behavior.

---

## 4. Determinism Requirements

Non-negotiable:
1. Canonical JSON serialization (`sort_keys=true`, compact separators).
2. SHA256 hashes for event payloads and proposal payloads.
3. Versioned portfolio assumptions and threshold bundles.
4. Fixed precision rounding for all scored numerics (6 decimals).
5. Replay corpus v3 lock for portfolio control-plane outputs.
6. No wall-clock randomness in scoring/allocation logic.

---

## 5. Data Model Changes (Planned)

### 5.1 `portfolio_automation_events`
Core columns:
- `id`
- `organization_id`
- `portfolio_id`
- `evaluation_date`
- `prior_phase`
- `new_phase`
- `triggered_rules_json`
- `input_snapshot_json`
- `action_summary_json`
- `trace_payload_json`
- `decision_hash`
- `version_hash`
- `created_at`

### 5.2 `portfolio_allocation_proposals`
Core columns:
- `id`
- `organization_id`
- `portfolio_id`
- `proposal_window_start`
- `proposal_window_end`
- `allocation_payload_json`
- `allocation_hash`
- `status` (`generated`, `approved`, `rejected`, `superseded`)
- `created_by`
- `approved_by`
- `created_at`
- `updated_at`

### 5.3 `portfolio_phase_history`
Core columns:
- `id`
- `organization_id`
- `portfolio_id`
- `prior_phase`
- `new_phase`
- `trigger_reason`
- `stability_index`
- `effective_date`
- `version_hash`
- `created_at`

---

## 6. Integration Contracts

PCP must consume:
- `portfolio_momentum`
- `systemic_drift`
- `allocator`
- `SCFE` (future hook, optional in Phase 3 initial rollout)

PCP must expose:
- Ranked intervention list.
- Current phase and phase transition reasons.
- Latest allocation proposal and acceptance state.

---

## 7. Commercialization Alignment

### 7.1 Tier Gating
- Standard: read-only control-plane visibility.
- Pro: allocation proposals and approval workflows.
- Enterprise: automated bounded allocation and phase orchestration.

### 7.2 Allocation Caps by Tier
- Standard: no automated allocation.
- Pro: constrained simulation caps.
- Enterprise: operational caps configurable per portfolio policy.

### 7.3 Differentiation Layer
Enterprise differentiation centered on:
- deterministic cross-campaign governance
- auditable allocation decisions
- portfolio phase automation timeline

---

## 8. Risk Analysis

### 8.1 Over-allocation Instability
Mitigation:
- max shift bounds
- per-cycle cap enforcement
- phase-based conservative mode on volatility spikes

### 8.2 Drift False Positives
Mitigation:
- confidence thresholds
- minimum campaign sample requirements
- drift persistence windows before phase transition

### 8.3 Cross-Tenant Isolation Risk
Mitigation:
- strict organization/portfolio scoping at query layer
- policy checks at API and service layers
- audit alerts on scope mismatch attempts

---

## 9. 60-Day Implementation Plan

### Days 1-10
- Finalize schema designs and migration drafts.
- Define assumption bundle + versioning contracts.
- Implement canonical payload + hashing utilities for PCP.

### Days 11-20
- Implement event persistence (`portfolio_automation_events`).
- Implement phase engine and phase history persistence.
- Add service layer and deterministic ranking primitives.

### Days 21-30
- Implement allocation proposal persistence.
- Integrate existing `portfolio_momentum/systemic_drift/allocator`.
- Create timeline + allocation query services.

### Days 31-40
- Add API endpoints and response contracts.
- Add plan-tier and cap enforcement.
- Add audit and observability events.

### Days 41-50
- Build replay corpus v3 fixtures and expected outputs.
- Add CI drift gate for PCP.
- Run deterministic regression suite and migration validation.

### Days 51-60
- Pilot with enterprise test tenants.
- Tune thresholds under controlled datasets.
- Finalize runbooks and go-live rollout checklist.

---

## 10. Success Metrics

- Portfolio Stability Index trend improvement.
- Allocation acceptance rate.
- Capital efficiency delta across managed portfolios.
- Replay drift count (target zero).
- Phase transition precision under historical backtest.

---

## 11. Decision Gate Criteria (Build Readiness)

Build phase can start when:
1. Data contracts are approved.
2. Replay governance v3 design is approved.
3. Tier-gating and commercialization policy is approved.
4. Migration strategy passes portability review.

---

END OF DOCUMENT