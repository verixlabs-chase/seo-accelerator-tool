# MIGRATION_AND_DATA_GOVERNANCE.md

## 1) Scope

Defines schema migration standards, data lifecycle governance, retention, archival, and deletion policy for LSOS.

## 2) Migration Standards

- Use versioned migration tooling (Alembic).
- Every migration includes:
  - forward migration
  - rollback path
  - index impact review
  - tenant isolation validation
- No destructive column drops without deprecation window.

## 3) Migration Workflow

1. Design review against `DATABASE_SCHEMA.md`.
2. Generate migration script with explicit DDL.
3. Run local migration tests (up/down).
4. Run staging migration rehearsal on production-like data volume.
5. Deploy during approved maintenance window when needed.

## 4) Backward Compatibility

- Additive schema changes preferred.
- Feature release must tolerate old+new schema during rolling deployments.
- Breaking DB changes gated behind feature flags and phased rollout.

## 5) Data Classification

- Operational data: campaigns, rankings, crawl outputs, reviews.
- Sensitive data: user credentials, email addresses, auth tokens.
- Audit data: security and privileged action logs.
- Artifact data: report files and branding assets.

## 6) Retention Policy

- Hot operational snapshots: 13 months minimum.
- Aggregated reporting summaries: long-term retention (plan/compliance dependent).
- Audit logs: minimum 24 months unless stricter requirement applies.
- Delivery logs: minimum 12 months.

## 7) Archival Strategy

- Monthly partition archival for aged snapshot tables.
- Archive destination: low-cost object storage with index metadata.
- Archived data retrievable for audits and historical reporting.

## 8) Deletion Policy

- Tenant offboarding uses staged deletion:
  - soft-delete
  - export window
  - hard-delete after retention/legal requirements
- Cascading deletes must be controlled and logged.

## 9) Data Integrity Controls

- FK constraints enforced on all critical relationships.
- Unique constraints scoped by tenant.
- Periodic integrity checks for orphaned records and duplicate snapshots.

## 10) Governance and Approval

- Schema change approval required from backend + platform owner.
- Sensitive data model changes require security review.
- Retention/deletion policy changes require legal/compliance review where applicable.

This document is the governing migration and data lifecycle policy for LSOS.
