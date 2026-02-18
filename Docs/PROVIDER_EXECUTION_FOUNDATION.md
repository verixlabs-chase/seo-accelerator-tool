# PROVIDER_EXECUTION_FOUNDATION.md

## 1) Phase Objective

Establish a production-ready provider execution foundation for LSOS before any external API wiring.

This phase introduces:
1. `ProviderBase` abstraction
2. Canonical provider error taxonomy + mapping
3. Shared `CircuitBreaker` utility
4. Shared `RetryPolicy` utility (capped exponential + jitter)
5. `QuotaState` model
6. `ProviderHealthState` model
7. `CeleryProviderTask` execution wrapper
8. Provider metrics DB schema
9. Provider health dashboard contract
10. Unit/integration coverage for retry, breaker, quota exhaustion paths

## 2) Guardrails (Hard Constraints)

- No schema redesign: additive tables/columns only.
- No lifecycle changes: no modifications to campaign/recommendation state engines.
- No tenant model expansion: keep current tenant scoping pattern.
- No UI implementation: dashboard defined as backend/API contract only.
- No external provider API wiring in this phase.

## 3) Target Placement In Existing Codebase

- `backend/app/providers/base.py`
- `backend/app/providers/errors.py`
- `backend/app/providers/retry.py`
- `backend/app/providers/circuit_breaker.py`
- `backend/app/providers/execution.py`
- `backend/app/models/provider_quota.py`
- `backend/app/models/provider_health.py`
- `backend/app/models/provider_metric.py`
- `backend/app/services/provider_execution_service.py`
- `backend/app/tasks/provider_task.py`
- `backend/app/schemas/provider.py`
- `backend/app/api/v1/provider_health.py` (read-only contract endpoint)
- `backend/alembic/versions/<next>_provider_execution_foundation.py`
- `backend/tests/test_provider_retry_policy.py`
- `backend/tests/test_provider_circuit_breaker.py`
- `backend/tests/test_provider_quota_state.py`
- `backend/tests/test_provider_task_wrapper.py`

## 4) Core Architecture

```text
Domain Service
  -> ProviderBase.execute()
      -> QuotaState.reserve()
      -> CircuitBreaker.before_call()
      -> RetryPolicy.run(call)
          -> provider._execute_impl()
          -> canonical error mapping
      -> CircuitBreaker.after_call()
      -> metrics + health state write

CeleryProviderTask wrapper
  -> timeout budget enforcement
  -> idempotency guard
  -> structured log envelope
  -> retry classification
  -> DLQ publish on retry exhaustion
```

## 5) ProviderBase Contract

`ProviderBase` is an abstract class (not protocol) and is the single execution entrypoint for provider calls.

Required API:
- `provider_name: str`
- `capability: str` (e.g. `rank_snapshot`, `crawl_fetch`)
- `def execute(self, *, tenant_id: str, campaign_id: str | None, operation: str, payload: dict, context: ProviderExecutionContext) -> ProviderExecutionResult`
- `def _execute_impl(...) -> dict` (implemented by concrete provider)

Behavior in `execute`:
- Creates operation correlation metadata.
- Enforces quota reservation.
- Runs breaker pre-check.
- Runs retry policy with canonical classification.
- Emits structured metrics row(s).
- Updates provider health state.
- Returns normalized `ProviderExecutionResult`.

## 6) Error Taxonomy and Canonical Mapping

Canonical error classes:
- `ProviderError` (base)
- `ProviderTimeoutError`
- `ProviderConnectionError`
- `ProviderRateLimitError`
- `ProviderAuthError`
- `ProviderQuotaExceededError`
- `ProviderBadRequestError`
- `ProviderResponseFormatError`
- `ProviderDependencyError`
- `ProviderInternalError`
- `ProviderCircuitOpenError`

Canonical reason codes:
- `timeout`
- `connection_error`
- `rate_limited`
- `auth_failed`
- `quota_exhausted`
- `bad_request`
- `response_invalid`
- `dependency_unavailable`
- `circuit_open`
- `internal_error`

Retry classes:
- Retryable: timeout, connection_error, dependency_unavailable, rate_limited (with cooldown)
- Non-retryable: auth_failed, quota_exhausted, bad_request, response_invalid

## 7) CircuitBreaker Utility

State model:
- `closed`: normal operation
- `open`: fast-fail until cooldown expires
- `half_open`: allow limited probes

Core fields:
- `failure_threshold`
- `open_cooldown_seconds`
- `half_open_max_calls`
- `consecutive_failures`
- `open_until`

Transitions:
- `closed -> open` when failures >= threshold
- `open -> half_open` when cooldown reached
- `half_open -> closed` on probe success threshold
- `half_open -> open` on any probe failure

Persistence note:
- In-memory utility + persisted snapshot in `provider_health_states` for observability and worker restarts.

## 8) RetryPolicy Utility

Inputs:
- `max_attempts`
- `base_delay_seconds`
- `max_delay_seconds`
- `jitter_ratio`

Backoff:
- `delay = min(max_delay, base_delay * 2^(attempt-1))`
- jitter applied as symmetric percentage window on computed delay

Execution behavior:
- retries only for retryable canonical errors
- respect per-task timeout budget remaining
- return attempt metadata for metrics/logging

## 9) New State Models

### 9.1 QuotaState (`provider_quota_states`)

Purpose:
- Track remaining call budget by provider/capability/window for fail-fast quota enforcement.

Columns:
- `id`
- `tenant_id`
- `provider_name`
- `capability`
- `window_start`
- `window_end`
- `limit_count`
- `used_count`
- `remaining_count`
- `last_exhausted_at`
- `updated_at`

Indexes:
- `(tenant_id, provider_name, capability, window_start)` unique
- `(tenant_id, window_end)`

### 9.2 ProviderHealthState (`provider_health_states`)

Purpose:
- Persist operational health snapshot for each provider/capability.

Columns:
- `id`
- `tenant_id`
- `provider_name`
- `capability`
- `breaker_state` (`closed|open|half_open`)
- `consecutive_failures`
- `success_rate_1h`
- `p95_latency_ms_1h`
- `last_error_code`
- `last_error_at`
- `last_success_at`
- `updated_at`

Indexes:
- `(tenant_id, provider_name, capability)` unique
- `(tenant_id, breaker_state)`

## 10) Provider Metrics DB Schema

Table: `provider_execution_metrics`

Purpose:
- Immutable per-attempt execution telemetry for SLO/alerts and health rollups.

Columns:
- `id`
- `tenant_id`
- `task_execution_id` (nullable FK `task_executions.id`)
- `provider_name`
- `capability`
- `operation`
- `idempotency_key`
- `correlation_id`
- `attempt_number`
- `max_attempts`
- `duration_ms`
- `timeout_budget_ms`
- `outcome` (`success|retry|failed|dead_letter`)
- `reason_code`
- `retryable`
- `http_status` (nullable)
- `created_at`

Indexes:
- `(tenant_id, provider_name, capability, created_at)`
- `(tenant_id, outcome, created_at)`
- `(correlation_id)`

## 11) CeleryProviderTask Wrapper

`CeleryProviderTask` extends Celery `Task` and is opt-in for provider-backed tasks.

Responsibilities:
- Enforce timeout budget per task invocation.
- Compute/validate idempotency key.
- Emit structured logs with:
  - `tenant_id`, `campaign_id`, `provider_name`, `capability`, `operation`, `correlation_id`, `idempotency_key`, `attempt`, `reason_code`, `outcome`
- Map raw exceptions to canonical provider errors.
- Apply retry classification via `RetryPolicy`.
- Send terminally failed events to `queue.deadletter` on retry exhaustion.

Dead-letter payload minimum:
- `tenant_id`
- `campaign_id`
- `task_name`
- `provider_name`
- `capability`
- `operation`
- `idempotency_key`
- `correlation_id`
- `reason_code`
- `error_type`
- `error_message`
- `attempts`
- `occurred_at`

## 12) Provider Health Dashboard Contract (Backend/API)

Endpoint (read-only):
- `GET /api/v1/provider-health/summary?tenant_id=<uuid>`

Response contract:
```json
{
  "tenant_id": "uuid",
  "generated_at": "ISO-8601",
  "providers": [
    {
      "provider_name": "rank",
      "capability": "rank_snapshot",
      "breaker_state": "closed",
      "success_rate_1h": 0.99,
      "p95_latency_ms_1h": 210,
      "quota": {
        "limit_count": 10000,
        "used_count": 2450,
        "remaining_count": 7550,
        "window_end": "ISO-8601"
      },
      "last_error_code": null,
      "last_error_at": null,
      "last_success_at": "ISO-8601"
    }
  ]
}
```

## 13) Test Plan (Phase Gate)

Unit tests:
- Retry policy computes capped exponential delays and jitter bounds.
- Retry policy stops on non-retryable errors.
- Circuit breaker transitions: closed/open/half_open semantics.
- Quota state reservation and exhaustion behavior.

Integration tests:
- Provider task retries transient errors and succeeds before exhaustion.
- Provider task exhausts retries and emits dead-letter payload.
- Breaker fast-fails while open and recovers after cooldown/half-open probe success.
- Quota exhaustion fails fast with canonical `quota_exhausted` reason.

## 14) Rollout Sequence

1. Introduce utility modules (`errors`, `retry`, `circuit_breaker`, `execution context/result`).
2. Add ORM models + migration for quota, health, metrics tables.
3. Add `CeleryProviderTask` wrapper and wire one internal synthetic provider path (no external API).
4. Add provider health summary service + API contract endpoint.
5. Add unit/integration tests and run `pytest`, `ruff`, `mypy`.

## 15) Out of Scope For This Phase

- Any live external provider integration.
- UI implementation for provider health.
- Multi-tenant org hierarchy expansion.
- Lifecycle or recommendation engine changes.
- Re-architecting existing domain services.
