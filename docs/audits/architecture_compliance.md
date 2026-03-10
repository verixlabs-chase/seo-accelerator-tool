# Architecture Compliance

Date: 2026-03-10

## Documentation Baseline

Primary architecture contract sources used for this audit:

- `backend/docs/architecture/intelligence_system.md`
- `backend/docs/architecture/intelligence_engine.md`
- `backend/docs/architecture/global_knowledge_graph.md`
- `backend/docs/architecture/experiment_network.md`
- `backend/docs/architecture/causal_discovery.md`
- `backend/docs/architecture/strategy_evolution_engine.md`
- `backend/docs/architecture/unified_runtime_design.md`

## Compliant Areas

### Global knowledge graph

- Runtime causal learning writes through `backend/app/intelligence/knowledge_graph/update_engine.py`.
- Portfolio reads graph preferences through `backend/app/intelligence/knowledge_graph/query_engine.py`.
- Strategy evolution writes `policy_policy` lineage edges through the graph update engine.
- Legacy `causal_edges` runtime usage has been removed from active app code.

### Event atomicity

- `backend/app/events/emitter.py` now writes to an outbox instead of publishing immediately.
- `backend/app/intelligence/workers/outbox_worker.py` publishes only committed outbox rows.

### Worker separation

- `backend/app/events/queue.py` routes `OUTCOME_RECORDED` and `EXPERIMENT_COMPLETED` into worker execution.
- Experiment processing now fans into causal learning, evolution, telemetry snapshotting, and learning report persistence.

## Partial Compliance

### Unified learning loop

- The new graph-based runtime is active.
- The legacy learning path still survives in `learning_worker.py` and related legacy modules.
- This means the repository still contains two learning interpretations.

### Queue architecture

- Test-mode inline execution is robust and covered.
- Production queue behavior still depends on Celery defaults rather than a richer application-level retry and dead-letter contract.

### Frontend contract

- Frontend supports dashboard and platform admin views.
- There is no frontend test harness and no `frontend/docs/` contract set.

## Violations and Gaps

### Duplicate learning path

- `backend/app/intelligence/workers/learning_worker.py` still drives:
  - policy weight updates
  - prediction training
  - legacy strategy evolution
  - legacy network learning
- This bypasses the “single graph-first learning spine” implied by the current architecture docs.

### Event-driven recomputation overlap

- `backend/app/intelligence/event_integration.py` still recomputes signals and features after outbox processing.
- That does not match the “campaign runtime fast, learning in workers” goal cleanly.

### Frontend verification gap

- CI runs frontend lint/build only.
- No route, rendering, or API-integration tests exist for the frontend.

## Contract Status

| Area | Status |
|---|---|
| Knowledge graph authoritative reads/writes | Compliant |
| Experiment to causal learning | Compliant |
| Causal learning to evolution | Compliant |
| Evolution to new experiments | Compliant |
| Outbox-based event atomicity | Compliant |
| Single learning spine | Partial |
| Worker retry/recovery contract | Partial |
| Frontend contract enforcement | Weak |

## Required Follow-Up

1. Remove or isolate the legacy `learning_worker` stack.
2. Retire `event_integration.py` once the outbox path no longer needs legacy recomputation.
3. Add a real frontend test runner and route-level integration coverage.
