# CAPITAL ALLOCATION ORCHESTRATION SPEC

---

## 1. Purpose

Define deterministic orchestration for campaign allocation proposals at portfolio level, including cap policies, acceptance workflow, and traceability.

---

## 2. Inputs

Required:
- campaign opportunity set
- current allocation distribution
- portfolio momentum score
- systemic drift metrics
- max shift policy
- tier cap policy

Optional:
- SCFE forecast outputs
- manual strategic overrides (approval-gated)

---

## 3. Orchestration Pipeline

1. Assemble canonical portfolio snapshot.
2. Compute candidate opportunity weights.
3. Apply bounded allocator.
4. Enforce tier caps and policy constraints.
5. Generate proposal payload and hashes.
6. Persist proposal and emit event.
7. Await approval workflow or auto-advance by policy.

---

## 4. Constraint System

### 4.1 Hard Constraints
- Allocation sum must equal 1.0 (fixed precision).
- Per-campaign delta must not exceed `max_shift`.
- Non-negative allocations only.
- Scoped to campaigns in target portfolio.

### 4.2 Policy Constraints
- Tier-based max campaign concentration.
- Tier-based maximum number of adjusted campaigns per cycle.
- Optional freeze if systemic drift severity exceeds threshold.

---

## 5. Proposal Lifecycle

States:
- `generated`
- `approved`
- `rejected`
- `superseded`

Rules:
- Only `generated` can transition to `approved/rejected`.
- New generated proposal supersedes older generated proposals for same window.
- Approved proposals are immutable.

---

## 6. Deterministic Ranking Inputs

Suggested weighted inputs:
- momentum impact component
- opportunity component
- confidence component
- risk penalty component

Tie-breakers:
1. final_score desc
2. campaign_id asc
3. scenario_id asc

---

## 7. SCFE Integration Hook (Future)

When SCFE available:
- replace/augment opportunity component with forecast delta value.
- include `confidence_weight` and value-quality signals in the weighted score.
- include SCFE assumption version in proposal version hash.

---

## 8. Observability and Audit

Metrics:
- proposal generation time
- proposal acceptance rate
- average allocation delta per cycle
- policy rejection count

Audit payload fields:
- proposal hash
- actor
- reason code
- before/after allocation snapshots

---

## 9. Failure Modes

- invalid input snapshot
- policy cap violation
- hash mismatch
- persistence conflict

Failure policy:
- fail closed for writes
- no partial proposal persistence
- emit deterministic reason code

---

## 10. Validation Test Matrix

- deterministic same-input same-output test
- max shift bound enforcement test
- allocation sum and rounding test
- supersede lifecycle test
- policy cap rejection test
- cross-portfolio contamination test

---

## 11. 60-Day Delivery Sequencing

### Sprint A (Weeks 1-2)
- Proposal schema + persistence.
- Lifecycle state machine.

### Sprint B (Weeks 3-4)
- Orchestration service + policy constraints.
- Event emission + hashes.

### Sprint C (Weeks 5-6)
- API exposure + timeline/read model.
- Replay v3 scenario integration.

### Sprint D (Weeks 7-8)
- Enterprise policy hardening.
- Pilot and calibration.

---

## 12. Success Metrics

- allocation acceptance rate
- capital efficiency delta
- proposal-to-execution latency
- replay drift rate (target zero)

---

END OF DOCUMENT