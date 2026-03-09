# PORTFOLIO REPLAY GOVERNANCE V3 PLAN

---

## 1. Objective

Extend deterministic replay governance to portfolio orchestration outputs and enforce zero-drift CI behavior.

---

## 2. Corpus Scope

New corpus: `replay_corpus/v3`

Scenario groups:
1. Stable portfolio, no phase change.
2. Recovery transition due to systemic negative drift.
3. Expand transition under positive momentum.
4. Dominate transition under sustained strength.
5. Allocation cap enforcement edge cases.
6. Proposal status transitions.
7. Multi-campaign tie-break ordering.
8. Assumption-version mismatch rejection.

---

## 3. Replay Artifact Set

Per case includes:
- input snapshot fixture
- assumption bundle version fixture
- expected event payload
- expected hash outputs
- expected ranked intervention order

---

## 4. Drift Dimensions

Validate all:
- output hash equality
- ranking order equality
- phase transition equality
- confidence band categorical equality (if present)

---

## 5. CI Enforcement

Add PCP-sensitive path filters in CI:
- `backend/app/services/portfolio/**`
- `backend/app/services/*control*`
- `backend/app/governance/replay/**`
- `backend/app/testing/fixtures/replay_corpus/v3/**`

Required gate steps:
1. baseline manifest integrity check
2. replay v3 run
3. fail build on non-zero drift events

---

## 6. Baseline Lock Policy

- Baseline manifest immutable in standard PRs.
- Baseline updates require explicit governance PR + approval.
- Each baseline update includes changelog and rationale.

---

## 7. Operational Governance

- Monthly replay integrity review.
- Drift incident runbook for root cause isolation.
- Threshold/assumption update process with replay impact preview.

---

## 8. Migration and Rollout Strategy

- Introduce v3 corpus in shadow mode first.
- Run v2 + v3 in parallel for one release cycle.
- Promote v3 to mandatory gate after parity is proven.

---

## 9. Definition of Done

- v3 corpus complete and validated.
- CI gate active and green.
- Drift triage runbook published.
- Baseline lock policy enforced.

---

END OF DOCUMENT