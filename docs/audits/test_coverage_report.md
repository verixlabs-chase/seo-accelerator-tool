# Test Coverage Report

Date: 2026-03-10

## Test Suite Size

- Backend test files: 178
- Collected backend test functions by static scan: 480
- Frontend test framework: not configured

## Coverage by Area

### Strongly Covered

- API authentication and campaign endpoints
- Execution lifecycle and governance
- Recommendation outcomes and intelligence metrics
- Knowledge graph, causal learning, mechanism learning
- Strategy evolution and experiment engine
- Worker queue dispatch, failure isolation, idempotency
- Event outbox atomicity
- Reference library path resolution

### Moderately Covered

- Full platform lifecycle smoke path
- Replay governance
- Provider infrastructure
- Reporting and dashboard APIs

### Weakly Covered

- Frontend rendering and route behavior
- Production Celery retry/dead-letter semantics
- True load and concurrency behavior
- Multi-worker operational recovery under real Redis/Postgres load

## New Coverage Added In This Audit

### Integration

- `backend/tests/integration/test_platform_event_chain.py`
  - outcome tracking to portfolio/experiment persistence
  - experiment event to knowledge graph and strategy evolution

### Load profiles

- `backend/tests/load/test_platform_load_profiles.py`
  - manual load scenarios for API, queue, worker, and report bursts

## Coverage Gaps

1. No frontend component or browser test stack.
2. No automatic load/performance suite in standard CI.
3. No end-to-end Docker integration job for the full platform lifecycle beyond existing compose test jobs.
4. No formal coverage percentage report was generated in this audit run.

## Recommendation

Adopt a staged coverage model:

1. fast unit/API/intelligence checks on every push
2. backend integration slice on every PR
3. nightly load and worker-recovery jobs
4. frontend route tests once a test runner is added
