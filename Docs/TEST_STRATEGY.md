# TEST_STRATEGY.md

## 1) Scope

Defines LSOS quality strategy across unit, integration, end-to-end, security, and performance testing.

## 2) Test Pyramid

- Unit tests:
  - business rules, scoring logic, payload validation, serializers.
- Integration tests:
  - API + DB, worker + broker, module boundary contracts.
- End-to-end tests:
  - campaign lifecycle flows from setup to report delivery.
- Non-functional tests:
  - load, resilience, failover, security.

## 3) Mandatory Coverage Areas

- Auth and RBAC permission enforcement.
- Tenant and campaign isolation in reads/writes.
- Celery retry/dead-letter behavior.
- Month-based campaign rule engine (months 1-12).
- Reporting generation and delivery pipeline.

## 4) Test Data and Fixtures

- Tenant-isolated fixtures for at least 3 tenants and 20 campaigns.
- Deterministic HTML fixtures for parser regressions.
- Synthetic ranking/review datasets for trend/scoring validation.
- Snapshot fixtures for reporting sections and PDF regression.

## 5) Environment Strategy

- Local:
  - fast unit + selected integration tests.
- CI:
  - full unit + integration + contract tests.
- Staging:
  - e2e, load, and reliability drills.

## 6) CI Quality Gates

- Lint and static checks must pass.
- Unit test coverage floor: 80% for core services.
- No critical security scan findings.
- Migration tests (up/down) must pass.
- Contract tests for API schemas and task payloads must pass.

## 7) Performance and Load Testing

Targets:
- Validate 100+ concurrent campaigns.
- Validate queue throughput under month-close peak.
- Validate report generation concurrency.

Scenarios:
- Daily rank collection peak.
- Weekly crawl burst.
- Monthly report generation burst.

## 8) Reliability and Chaos Tests

- Broker restart during active queue processing.
- Worker pod eviction with in-flight tasks.
- Replica lag spike and read-routing fallback.
- Proxy provider outage and failover behavior.

## 9) Security Testing

- Auth bypass attempts.
- Cross-tenant access and IDOR tests.
- Input injection tests (SQLi/XSS/SSRF vectors).
- Secret leak scanning in code and logs.

## 10) Release Test Sign-off

Release candidate is valid only when:
- All blocking tests pass.
- No unresolved critical/high defects.
- SLO baseline checks pass in staging.
- Manual smoke suite completed.

This document is the governing quality and test policy for LSOS.
