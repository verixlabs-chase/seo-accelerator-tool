# PORTFOLIO CONTROL PLANE
## Technical Architecture

---

## 1. Architecture Position

Portfolio Control Plane (PCP) sits above campaign strategy services and below executive reporting, orchestrating cross-campaign decisions.

```text
Signal/Strategy Layer
  -> Portfolio Computation Layer (momentum, drift, allocator, SCFE)
  -> Portfolio Control Plane (phase engine, prioritization, proposals)
  -> API + Reporting + Automation Timeline
```

---

## 2. Component Model

### 2.1 `PortfolioStateAssembler`
- Collects current portfolio signals.
- Produces canonical input snapshot.

### 2.2 `PortfolioPhaseEngine`
- Applies deterministic rules for phase transitions.
- Emits trigger reasons and transition confidence metadata.

### 2.3 `PortfolioPrioritizationEngine`
- Produces deterministic ranked interventions.
- Tie-breakers: score desc, campaign_id asc, scenario_id asc.

### 2.4 `AllocationOrchestrator`
- Invokes bounded allocator.
- Validates cap policy.
- Produces allocation proposal payload.

### 2.5 `PortfolioEventWriter`
- Persists automation event, trace payload, and hashes.

### 2.6 `PortfolioQueryService`
- Serves control-plane state, allocation details, timeline.

---

## 3. Phase Engine Rule Skeleton

Inputs:
- portfolio momentum
- systemic drift ratio
- volatility proxy
- acceptance rate trend

Outputs:
- `new_phase`
- `triggered_rules[]`
- `stability_index`

Baseline deterministic transition profile:
- High negative momentum + high drift -> `recovery`
- Low volatility + improving momentum -> `stabilize`
- Positive momentum + acceptable drift -> `expand`
- Sustained strong momentum + high execution confidence -> `dominate`

---

## 4. Storage and Integrity

Every control cycle stores:
- canonical input snapshot hash
- decision hash
- version hash (assumptions + engine version + threshold bundle)

Persistence invariants:
- terminal event records immutable
- proposal payload immutable after approval/rejection
- timeline ordering by `evaluation_date`, then `id`

---

## 5. API Read Model Strategy

### 5.1 Control Plane Snapshot
- Derived from latest automation event + latest proposal + current phase.

### 5.2 Allocation View
- Returns latest active proposal and campaign allocations.

### 5.3 Automation Timeline
- Returns ordered event history with normalized reason codes.

---

## 6. Failure Handling

Failure classes:
- signal assembly failure
- policy violation
- persistence conflict
- hashing mismatch (critical)

Recovery posture:
- fail closed for write path
- keep last known good read model
- emit alert + audit event on critical mismatch

---

## 7. Observability Requirements

Metrics:
- control cycle duration
- phase transition frequency
- proposal generation rate
- proposal approval/rejection ratio
- hash mismatch count

Events:
- `portfolio_control.cycle_started`
- `portfolio_control.cycle_completed`
- `portfolio_control.phase_transition`
- `portfolio_control.proposal_generated`

---

## 8. Security and Tenant Isolation

- All queries scoped by `organization_id` + `portfolio_id`.
- API authorization must enforce organization membership.
- No cross-portfolio joins without explicit policy context.

---

## 9. Dependency Injection and Versioning

PCP services must be version-addressable:
- `pcp-engine-v1`
- `portfolio-assumptions-v1`
- `portfolio-thresholds-v1`

Version fingerprint included in every event.

---

## 10. Build Sequence

1. Data models + migrations.
2. Canonicalization + hashing utility integration.
3. Phase + prioritization engine.
4. Orchestration writer and query service.
5. API layer and policy enforcement.
6. Replay v3 + CI gate.

---

END OF DOCUMENT