# PORTFOLIO AUTOMATION EVENT MODEL
## Specification

---

## 1. Purpose

Define the canonical event contract for deterministic portfolio orchestration cycles.

---

## 2. Event Types

- `portfolio_cycle_evaluated`
- `portfolio_phase_transitioned`
- `portfolio_allocation_proposal_generated`
- `portfolio_allocation_proposal_status_changed`

---

## 3. Canonical Event Envelope

```json
{
  "schema_version": "v1",
  "event_type": "portfolio_cycle_evaluated",
  "organization_id": "uuid",
  "portfolio_id": "uuid",
  "evaluation_date": "2026-02-27T00:00:00Z",
  "engine_version": "pcp-engine-v1",
  "assumption_bundle_version": "portfolio-assumptions-v1",
  "threshold_bundle_version": "portfolio-thresholds-v1",
  "payload": {},
  "payload_hash": "sha256hex",
  "version_hash": "sha256hex"
}
```

---

## 4. Payload Contracts

### 4.1 Cycle Evaluated
Required fields:
- `prior_phase`
- `new_phase`
- `triggered_rules[]`
- `stability_index`
- `ranked_interventions[]`

### 4.2 Proposal Generated
Required fields:
- `proposal_id`
- `window_start`
- `window_end`
- `allocations[]`
- `allocation_sum`
- `max_shift`

### 4.3 Proposal Status Changed
Required fields:
- `proposal_id`
- `prior_status`
- `new_status`
- `actor_id`
- `reason_code`

---

## 5. Hashing and Canonicalization

- Payload hash: SHA256 of canonical payload JSON.
- Version hash: SHA256 over version tuple + threshold tuple.
- Rule: no hash computation on non-canonical object forms.

---

## 6. Ordering and Idempotency

Idempotency key dimensions:
- organization_id
- portfolio_id
- event_type
- evaluation_date

Duplicate event processing returns existing event reference.

---

## 7. Event Storage Requirements

Storage table: `portfolio_automation_events`

Minimum indexed paths:
- `(portfolio_id, evaluation_date desc)`
- `(organization_id, created_at desc)`
- `(decision_hash)`

Retention:
- hot: 24 months
- cold archive: policy-driven

---

## 8. Validation Rules

Reject event if:
- missing required identifiers
- hash mismatch
- unknown schema version
- phase outside enum set

---

## 9. Audit Requirements

Every event write records:
- actor source (`system`, `user`, `scheduler`)
- request_id
- policy context
- hash values

---

## 10. Replay Constraints

Replay compares:
- payload hash
- event ordering
- phase transition consistency

Drift in any dimension is gate-failing in CI.

---

END OF DOCUMENT