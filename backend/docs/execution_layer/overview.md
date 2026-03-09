# Execution Layer Overview

## Current scope
The execution layer is implemented and production-oriented in governance shape, but still narrow in execution breadth.

## What is implemented
- Recommendation scheduling through `app/intelligence/recommendation_execution_engine.py`
- Risk scoring, daily caps, idempotency, retry limits, cancel/reject/approve flows
- Manual approval support via `intelligence_governance_policies`
- Safety breaker gating via `app/intelligence/safety_monitor.py`
- Concrete executor adapters for content briefs, internal links, titles, GBP, and schema
- Execution APIs in `app/api/v1/executions.py`

## Current maturity
- Real persistence exists for executions and outcomes.
- Governance is stronger than the executor implementations.
- Most executors still produce controlled deterministic action payloads rather than deep provider-native website mutation workflows.

## Not implemented
- A distributed execution fabric with queue-level isolation beyond Celery queue routing
- Rich rollback orchestration beyond stored rollback plans
- Full provider-backed write surfaces for every execution type

## Runtime flow
```text
recommendation
  -> digital twin winner selection
  -> execution scheduling
  -> governance + risk checks
  -> optional manual approval
  -> executor run
  -> outcome recording
  -> policy/model updates
```
