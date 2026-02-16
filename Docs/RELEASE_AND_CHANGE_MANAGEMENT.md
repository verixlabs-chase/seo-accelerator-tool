# RELEASE_AND_CHANGE_MANAGEMENT.md

## 1) Scope

Defines LSOS release governance, rollout strategy, rollback policy, and change approval controls.

## 2) Release Model

- Trunk-based development with protected main branch.
- Continuous delivery to staging; controlled promotion to production.
- Semantic versioning for API and service releases.

## 3) Release Types

- Patch: bug fixes, no contract breaks.
- Minor: additive features and backward-compatible API changes.
- Major: breaking API/task/schema changes requiring migration plan.

## 4) Pre-Release Checklist

- All CI checks and tests pass.
- Migration scripts validated (forward + rollback).
- SLO guardrails healthy in staging.
- Security scan and secret scan clear.
- Release notes and operator runbook deltas prepared.

## 5) Rollout Strategy

- Preferred: progressive/canary rollout.
- Monitor error and latency budgets during rollout windows.
- Pause rollout automatically on SLO threshold breach.

## 6) Rollback Policy

- Trigger rollback on:
  - severe error-rate increase
  - tenant isolation/security regression
  - critical queue instability
- Rollback sequence:
  1. stop new rollout
  2. route traffic to previous stable revision
  3. disable incompatible feature flags
  4. evaluate DB rollback necessity

## 7) Change Approval Matrix

- Standard changes: module owner + reviewer approval.
- High-risk changes (auth, data isolation, migrations): module owner + platform/security approval.
- Emergency changes: expedited approval with mandatory retroactive review.

## 8) Documentation and Communication

- Every release includes:
  - summary of changes
  - impacted modules/endpoints
  - migration requirements
  - rollback notes
- Notify internal stakeholders before and after production releases.

## 9) Post-Release Validation

- Smoke tests across core workflows.
- Queue health and error-rate checks.
- Campaign data freshness sanity checks.
- Report generation sanity test for at least one campaign.

This document is the governing release and change management policy for LSOS.
