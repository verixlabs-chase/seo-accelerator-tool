# Project System Scan

Date: 2026-03-11

## Scope

This scan covered:

- `docs/`
- `backend/docs/`
- `backend/docs/architecture/`
- `docs/audits/`
- `backend/app`
- `backend/scripts`
- `frontend/app`
- `infra`
- `.github/workflows`
- `backend/tests`

Production code was not modified during this scan.

## 1. System Architecture Map

### Intended architecture from docs

The architecture documents describe a graph-first intelligence system with this canonical learning spine:

```text
campaign cycle
  -> signals
  -> temporal store
  -> features
  -> patterns
  -> policies
  -> recommendations
  -> digital twin selection
  -> execution
  -> outcome
  -> portfolio allocation
  -> experiment attribution
  -> causal learning
  -> knowledge graph update
  -> strategy evolution
  -> new experiments
  -> future portfolio decisions
```

Key architecture contracts from the docs:

- The synchronous runtime is `run_campaign_cycle()`.
- The digital twin selects the winning strategy before execution.
- Portfolio decisions must read policy preferences through `knowledge_graph/query_engine.py`.
- Causal learning must write graph evidence through `knowledge_graph/update_engine.py`.
- Strategy evolution should consume strong causal policies and record parent-child lineage back into the graph.
- Direct `KnowledgeEdge` writes outside the graph layer are forbidden.

### Actual repository system map

#### API layer

- Runtime entrypoint: `backend/app/main.py`
- Route composition: `backend/app/api/v1/router.py`
- Major API surfaces:
  - auth, tenants, campaigns, onboarding
  - intelligence, recommendations, executions
  - dashboard, reports
  - providers, hierarchy, platform control

#### Intelligence engine

- Orchestrator: `backend/app/intelligence/intelligence_orchestrator.py`
- Signal assembly: `signal_assembler.py`
- Temporal persistence: `temporal_ingestion.py`
- Feature computation: `feature_store.py`
- Pattern detection: `pattern_engine.py`
- Policy/recommendation generation: `policy_engine.py`
- Digital twin: `backend/app/intelligence/digital_twin/*`
- Execution: `recommendation_execution_engine.py`
- Outcome tracking: `outcome_tracker.py`

#### Event system

- Outbox writer: `backend/app/events/emitter.py`
- Event bus: `backend/app/events/event_bus.py`
- Redis/in-memory event stream: `backend/app/events/event_stream.py`
- Worker queue shim: `backend/app/events/queue.py`
- Subscriber wiring: `backend/app/events/subscriber_registry.py`

#### Worker system

- Celery app: `backend/app/tasks/celery_app.py`
- Intelligence Celery tasks: `backend/app/tasks/intelligence_tasks.py`
- Campaign worker entry: `backend/app/intelligence/campaign_workers/campaign_task_runner.py`
- Worker dispatch:
  - `learning_worker.py`
  - `experiment_worker.py`
  - `outbox_worker.py`
  - `causal_worker.py`
  - `evolution_worker.py`

#### Knowledge graph

- Active graph layer:
  - reads: `backend/app/intelligence/knowledge_graph/query_engine.py`
  - writes: `backend/app/intelligence/knowledge_graph/update_engine.py`
- Also present and still runtime-active:
  - `backend/app/intelligence/global_graph/*`

#### Experiments

- `backend/app/intelligence/experiments/experiment_engine.py`
- `experiment_registry.py`
- `experiment_assignment.py`
- `experiment_analysis.py`

#### Causal learning

- `backend/app/intelligence/causal/causal_learning_engine.py`
- `causal_query_engine.py`
- `backend/app/intelligence/event_processors/causal_learning_processor.py`
- Mechanism layer:
  - `backend/app/intelligence/causal_mechanisms/*`

#### Evolution engine

- New engine:
  - `backend/app/intelligence/evolution/strategy_evolution_engine.py`
  - `policy_mutation_engine.py`
  - `strategy_generator.py`
- Legacy package still present:
  - `backend/app/intelligence/strategy_evolution/*`

#### Portfolio engine

- `backend/app/intelligence/portfolio/portfolio_engine.py`
- `policy_performance.py`
- `strategy_allocator.py`

#### Metrics / observability

- `backend/app/core/metrics.py`
- `backend/app/observability/*`
- telemetry snapshots/reports:
  - `backend/app/intelligence/telemetry/*`
- go-live checks:
  - `infra/go-live-preflight.ps1`

#### Load testing

- `backend/tests/load/test_concurrency_simulation.py`
- `backend/tests/load/test_intelligence_full_cycle_benchmark.py`
- `backend/tests/load/test_platform_capacity_benchmark.py`
- `backend/tests/load/test_platform_load_profiles.py`

#### CI/CD

- `.github/workflows/ci.yml`
- `.github/workflows/backend-ci.yml`
- `.github/workflows/preflight-pr.yml`
- container parity: `docker-compose.yml`

## 2. Runtime Entry Points

### Primary runtime entrypoints

- API server:
  - `backend/app/main.py`
  - Docker command: `uvicorn app.main:app`
- Celery worker:
  - `backend/app/tasks/celery_app.py`
  - Docker command: `celery -A app.tasks.celery_app.celery_app worker -Q default -l INFO`
- Celery beat:
  - Docker command: `celery -A app.tasks.celery_app.celery_app beat -l INFO`
- Campaign intelligence tasks:
  - `intelligence.run_campaign_cycle`
  - `intelligence.run_system_cycle`
- Campaign worker task:
  - `intelligence.process_campaign`
- Queue consumers:
  - `run_intelligence_worker_task()` for `learning` and `experiment`
- Outbox consumer:
  - `backend/app/intelligence/workers/outbox_worker.py`

### Event processor chain registered at startup

`backend/app/main.py` initializes the event stream and calls `register_default_subscribers()`.

The registered event chain is:

```text
signal.updated -> signal_processor
feature.updated -> pattern_processor
pattern.discovered -> recommendation_processor
recommendation.generated -> simulation_processor
simulation.completed -> execution_processor
execution.completed -> outcome_processor
outcome.recorded -> enqueue_learning_event
experiment.completed -> enqueue_experiment_event
```

## 3. Runtime Pipeline Diagram

### Actual operational flow

```text
campaign creation API
  -> Campaign row persisted
  -> outbox event campaign.created

scheduled or task-triggered intelligence cycle
  -> run_campaign_cycle()
  -> assemble_signals()
  -> write_temporal_signals()
  -> compute_features()
  -> detect_patterns()
  -> discover_cohort_patterns()
  -> legacy adapter merge
  -> generate/persist recommendations
  -> digital twin optimize_strategy()
  -> schedule_execution()
  -> execute_recommendation()
     -> outbox events: execution.scheduled / started / completed / failed
     -> on success: _record_outcome_if_possible()
        -> record_execution_outcome()
           -> record_outcome()
              -> run_portfolio_cycle()
              -> record_experiment_outcome()
              -> commit
              -> publish experiment.completed
              -> publish outcome.recorded

experiment worker
  -> causal_worker
     -> causal_learning_engine
     -> knowledge_graph.update_engine
  -> evolution_worker
     -> strategy_evolution_engine
     -> new experiments
     -> lineage edge via knowledge_graph.update_engine
     -> learning telemetry/report
```

### Parallel runtime path still active

There is also a second live path after `execution.completed` outbox replay:

```text
execution.completed outbox event
  -> outbox_worker publishes to event_bus
  -> outcome_processor.process()
     -> record_execution_result() if payload includes result
     -> fetch latest RecommendationOutcome
     -> global_graph.update_from_outcome()
     -> industry_learning_pipeline.update_from_outcome()
     -> publish outcome.recorded again
```

This second path is the main architecture divergence in the repository.

## 4. Graph-First Learning Architecture Verification

### Verified compliant

- Portfolio reads through the graph query layer:
  - `backend/app/intelligence/portfolio/portfolio_engine.py`
  - imports `get_policy_preference_map` from `knowledge_graph/query_engine.py`
- Causal learning writes through the graph update layer:
  - `backend/app/intelligence/causal/causal_learning_engine.py`
  - calls `update_global_knowledge_graph()`
- Strategy evolution lineage writes through the graph layer:
  - `backend/app/intelligence/evolution/policy_mutation_engine.py`
  - calls `record_policy_evolution()`
- No direct `KnowledgeEdge` inserts were found outside `backend/app/intelligence/knowledge_graph/`

### Violations / divergences

#### Violation 1: active parallel graph system outside the knowledge graph layer

`backend/app/intelligence/event_processors/outcome_processor.py` still writes to:

- `global_graph.update_from_outcome()`
- `industry_learning_pipeline.update_from_outcome()`

This means the active runtime is not exclusively graph-first through the new knowledge graph layer.

#### Violation 2: duplicate outcome publication path

`backend/app/intelligence/outcome_tracker.py` already publishes:

- `experiment.completed`
- `outcome.recorded`

But `outcome_processor.py` can publish `outcome.recorded` again from the `execution.completed` event path. That creates a second learning trigger path and raises duplicate-processing risk.

#### Violation 3: not all learning events are outbox-driven

`record_outcome()` publishes `experiment.completed` and `outcome.recorded` directly via `publish_event()` after commit, not through the outbox table. The docs emphasize post-commit event safety, but runtime event delivery is split between outbox-backed execution events and directly published learning events.

### Contract result

Status: Partial compliance

- `portfolio -> query_engine`: compliant
- `causal -> update_engine`: compliant
- no direct `KnowledgeEdge` writes: compliant
- single graph-first learning spine: not compliant

## 5. Active Subsystems

Active in the runtime path:

- FastAPI app startup and routing
- Redis/in-memory event stream
- outbox-backed execution event publication
- synchronous campaign orchestrator
- digital twin selection
- recommendation execution engine
- outcome tracking
- portfolio engine
- experiment network
- causal learning into knowledge graph
- evolution worker and experiment creation
- telemetry snapshots and learning report persistence
- Celery beat schedules for system cycle and model maintenance

Notable reality check:

The docs say the new evolution package is "implemented but not yet wired into the live event chain." That is no longer true. `experiment_worker.py` invokes `evolution_worker.py`, which invokes `evolution/strategy_evolution_engine.py`. The docs are stale here.

## 6. Inactive or Legacy Systems

### Confirmed inactive / stubbed

- `backend/app/intelligence/event_integration.py`
  - `process_learning_event()` is a no-op
- `backend/app/intelligence/workers/learning_worker.py`
  - returns a noop payload
- `backend/app/events/emitter.py::_process_learning_event`
  - legacy compatibility stub only
- `backend/app/intelligence/event_processors/outcome_processor.py::record_seo_flight`
  - compatibility stub only

### Present but not on the active runtime path

- `backend/app/intelligence/network_learning/*`
- `backend/app/intelligence/strategy_evolution/*` (legacy package)
- `backend/docs/causal_discovery/seo_flight_recorder.md`

### Present and still indirectly relevant

- `backend/app/intelligence/policy_update_engine.py`
  - still bridges to legacy `strategy_evolution` package
  - not referenced by the current worker hooks scanned here

### Conclusion

The named legacy systems are not part of the primary live learning path, but the repository still contains enough legacy graph and strategy infrastructure to create confusion. The larger active legacy risk is not `network_learning`; it is the still-live `global_graph` and industry-learning path in `outcome_processor.py`.

## 7. Scalability Readiness

### Queue capacity

From `backend/app/core/settings.py` and queue controls:

- `max_queue_depth`: `10000`
- `max_worker_inflight`: `2000`
- queue admission critical lag threshold: `180`
- queue admission warning lag threshold: `60`
- token bucket capacity per `(tenant, queue)`: `120`
- token refill rate: `2.0/sec`

### Worker concurrency limits

- API request concurrency:
  - global: `2000`
  - per tenant: `200`
- `run_system_cycle()` local worker pool:
  - `min(8, active_campaigns)`
- Celery worker prefetch multiplier:
  - default/resolved default: `1`
- Celery worker process concurrency:
  - not pinned in repo config or `docker-compose.yml`
  - falls back to Celery default worker concurrency

### Request throttling

`RequestThrottleMiddleware` enforces:

- global semaphore: `max_concurrent_requests`
- per-tenant semaphore: `max_requests_per_tenant`
- rejection timeout window: `0.001s`
- rejection status: `429`

### Event stream batching

`event_stream.consume_event_batches()`:

- effective batch size min/max clamp: `50..200`
- default configured size: `100`
- Redis stream retry cap: `3`

### Graph write batching

The graph layer has a batcher:

- `knowledge_graph_batch_size`: `100`
- `knowledge_graph_flush_interval_ms`: `500`

But the main causal write path calls `update_global_knowledge_graph(... force=True)` via `flush_graph_write_batch()`. In practice, causal graph writes are flushed immediately per update, so configured batching is mostly bypassed on the active causal path.

### Distributed locks

No Redis-based distributed campaign-cycle lock was found for the intelligence runtime.

Current protections are local/in-process:

- campaign cycle lock in `intelligence_orchestrator.py`
- queue state locks in `events/queue.py`
- request throttle semaphores in middleware

This means cross-process duplicate campaign execution protection is weak unless external scheduling discipline prevents overlap.

### Scaling summary

Strengths:

- admission control exists
- queue lag throttling exists
- request concurrency caps exist
- Celery queue routing exists
- event stream has retry/DLQ semantics

Weaknesses:

- core intelligence flow remains synchronous
- campaign execution lock is process-local
- knowledge graph batching is configured but effectively forced to flush
- learning is split across two graph systems
- Celery concurrency is not explicitly pinned

## 8. Test Coverage Status

### Static scan totals

- backend test files: `184`
- integration test files: `1`
- system test files: `1`
- load test files: `4`
- statically counted test functions: `494`
- frontend test stack: not configured

### Architecture contract tests present

- `backend/tests/test_architecture_contract.py`
- `backend/tests/test_event_contract.py`
- `backend/tests/test_intelligence_contract_schema_stability.py`
- `backend/tests/test_intelligence_contracts.py`
- `backend/tests/test_knowledge_graph_contract.py`

### Intelligence / learning coverage present

Representative coverage exists for:

- orchestrator
- causal learning
- knowledge graph
- global graph
- portfolio
- experiment engine
- strategy evolution
- intelligence workers

Representative files:

- `backend/tests/test_intelligence_orchestrator.py`
- `backend/tests/test_causal_learning_engine.py`
- `backend/tests/test_global_knowledge_graph.py`
- `backend/tests/test_global_graph_runtime_integration.py`
- `backend/tests/test_portfolio_engine.py`
- `backend/tests/test_strategy_evolution_engine.py`

### Load tests

Load/performance coverage exists, but most of it is synthetic or monkeypatched:

- `test_platform_capacity_benchmark.py`
- `test_intelligence_full_cycle_benchmark.py`
- `test_platform_load_profiles.py`
- `test_concurrency_simulation.py`

Important limitation:

- `test_platform_load_profiles.py` is skipped unless `RUN_PLATFORM_LOAD_TESTS` is explicitly enabled
- capacity benchmarks monkeypatch major runtime stages, so they validate envelope shape more than production-real throughput

### Coverage gaps

- no frontend unit/integration/browser tests
- very thin true multi-process integration coverage
- no standard CI lane for load tests
- no dedicated contract test asserting the legacy `global_graph` path is off
- no explicit runtime test proving outcome events are emitted only once

## 9. CI/CD Inspection

### `ci.yml`

Runs three lanes:

- backend:
  - Python 3.12
  - Postgres service
  - install deps
  - apply migrations
  - `pytest -q`
- deterministic replay gate:
  - path-filtered
  - baseline hash verification
  - migration validation
  - replay corpus execution
- frontend:
  - `npm install`
  - `npm run lint`
  - `npm run build`
  - `npm audit --audit-level=high`

### `backend-ci.yml`

Docker parity lane:

- `docker compose build`
- `docker compose run --rm test-runner`
- performance envelope test
- `ruff check .`
- production config validation inside container

### `preflight-pr.yml`

Cross-platform preflight:

- Ubuntu and Windows
- Python and Node setup
- runs `infra/go-live-preflight.ps1`
- preflight itself runs:
  - backend dependency install
  - backend `pytest -vv -s`
  - `pip-audit`
  - frontend install/build/audit

### CI/CD summary

Strengths:

- backend tests run with Postgres
- migrations are validated
- replay gate exists
- Docker parity lane exists
- frontend build is enforced
- preflight runs on Linux and Windows

Gaps:

- no frontend functional tests
- no automated load test lane
- no dedicated worker/recovery chaos lane
- no explicit check that docs match runtime wiring

## 10. Operational Risks

### High risk

1. Parallel learning spines are still active.
   - New knowledge graph path is live.
   - Older `global_graph` path is also live via `outcome_processor.py`.

2. Outcome-triggered duplicate learning is possible.
   - `record_outcome()` publishes learning events directly.
   - `execution.completed` processing can publish `outcome.recorded` again.

3. Graph batching is not realized on the hot path.
   - The batcher exists.
   - Active causal writes flush immediately.

4. Campaign-cycle locking is only process-local.
   - Safe inside one process.
   - Not safe as a distributed runtime guard.

### Medium risk

1. Documentation drift.
   - Docs say evolution is not wired.
   - Runtime says it is.

2. Legacy packages remain close to active code.
   - They are mostly inactive, but the repository boundary between active and deprecated systems is still blurry.

3. Worker concurrency is under-specified.
   - Prefetch is set.
   - Process concurrency is not pinned.

### Low risk

1. Direct `KnowledgeEdge` writes outside the graph layer were not found.
2. Contract tests for the graph-first rules already exist.

## 11. Recommended Next Engineering Priorities

1. Remove the active `global_graph` and industry-learning branch from `outcome_processor.py`, or explicitly gate it off behind a dead path.

2. Make the outcome learning path singular and post-commit consistent.
   - One source of `outcome.recorded`
   - one source of `experiment.completed`
   - one worker-driven downstream path

3. Stop forcing immediate graph flushes on the causal hot path so `knowledge_graph_batch_size` and `knowledge_graph_flush_interval_ms` can actually reduce write amplification.

4. Replace the in-process campaign execution lock with a distributed lock or DB-backed lease if overlapping workers are expected in production.

5. Update the architecture docs to match runtime reality, especially:
   - evolution engine live wiring
   - residual `global_graph` runtime path
   - direct event publication versus outbox-backed publication

6. Add tests for:
   - single-publication outcome event behavior
   - absence of `global_graph` writes on the modern runtime path
   - worker recovery and cross-process duplicate prevention

7. Add a real frontend test harness and at least one route/API integration lane in CI.

## 12. Bottom Line

The repository now enforces the intended graph-first architecture through a single active learning spine:

- portfolio reads from the knowledge graph correctly
- causal learning writes through the knowledge graph correctly
- evolution records lineage through the graph correctly
- Legacy global_graph runtime path removed. All learning now flows through the knowledge_graph layer.

Remaining follow-up work is focused on scaling and operational hardening rather than removing a parallel learning branch.
