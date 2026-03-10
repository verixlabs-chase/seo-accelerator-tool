# Dead Code Report

Date: 2026-03-10

## Method

This report is based on code search, import/reference sampling, and architecture reconciliation against the current documentation set. These findings are candidates, not blind deletions.

## High-Confidence Candidates

### Legacy learning stack overlap

- `backend/app/intelligence/event_integration.py`
  - Still reachable through the outbox worker.
  - Recomputes signals and features after committed learning events.
  - Duplicates the newer worker-based learning path rather than extending it.

- `backend/app/intelligence/strategy_evolution/`
  - Legacy strategy evolution package still exists beside `backend/app/intelligence/evolution/`.
  - Architecture docs now center the new evolution package and global knowledge graph.

- `backend/app/intelligence/network_learning/`
  - Remains referenced by `learning_worker.py`.
  - Functionally overlaps the newer knowledge-graph and experiment/causal runtime.

- `backend/app/intelligence/causal_discovery/`
  - Historical causal discovery stack remains alongside `backend/app/intelligence/causal` and `backend/app/intelligence/causal_mechanisms`.

### Repository artifacts

- `backend/tests/conftest.py.bak`
  - Backup file in the test tree.
  - Not part of normal runtime or test execution.

## Medium-Confidence Candidates

### Modules with low runtime reachability

- `backend/app/intelligence/event_processors/policy_learning_processor.py`
  - Currently acts as a compatibility adapter into the older learning worker path.
  - May become removable once the old network-learning spine is retired.

- `backend/app/intelligence/feature_aggregator.py`
  - Actively imported, but much of its work is duplicated by direct feature recomputation elsewhere.
  - Candidate for narrowing rather than deletion.

### Frontend gaps

- `frontend/components/` and `frontend/lib/`
  - Directories do not exist.
  - The frontend is page-centric and thin; reusable component structure is still absent.

## Meaningless or Weak Validation Patterns

- Manual load tests were not previously present.
- Several existing “system” tests are closer to smoke flows than realistic concurrency or backlog validation.
- Frontend has lint/build verification, but no component, route, or browser tests.

## Recommended Cleanup Order

1. Retire `event_integration.py` or reduce it to outbox-only compatibility hooks.
2. Choose one learning spine:
   - keep `knowledge_graph + experiments + evolution`
   - retire `network_learning + legacy strategy_evolution`
3. Remove `backend/tests/conftest.py.bak`.
4. Collapse duplicate feature recomputation paths after the learning spine is unified.
