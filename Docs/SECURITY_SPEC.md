# SECURITY_SPEC.md

## 1) Scope

Defines mandatory security controls for LSOS across authentication, authorization, tenant/campaign isolation, rate limiting, input validation, logging, encryption, backups, and disaster recovery.

## 2) Security Objectives

- Prevent unauthorized access to tenant data.
- Enforce strict campaign isolation in API, worker, and reporting paths.
- Minimize attack surface and abuse risk for public and internal interfaces.
- Preserve confidentiality, integrity, and availability of campaign operations.
- Provide auditable evidence of privileged and sensitive actions.

## 3) JWT Authentication

Token model:
- Access token (short-lived, signed JWT).
- Refresh token (longer-lived, revocable, rotation-enabled).

JWT claims (required):
- `sub` (user_id)
- `tenant_id`
- `role_ids`
- `permissions`
- `iat`
- `exp`
- `jti`

Policy:
- Access token TTL: 15 minutes.
- Refresh token TTL: 7-30 days by environment policy.
- Key rotation supported with key ID (`kid`) in header.
- Revoke compromised refresh tokens by token family.

Transport/storage:
- HTTPS only.
- Refresh token in secure, httpOnly cookie where frontend model allows.
- Access token never logged.

## 4) Role-Based Access Control (RBAC)

Role model:
- `tenant_owner`
- `tenant_admin`
- `campaign_manager`
- `analyst`
- `viewer`
- `service_worker` (non-human service principal)

Authorization controls:
- Endpoint-level permission decorators.
- Resource-level checks enforce tenant and campaign ownership.
- Least-privilege defaults for new roles.

Permission examples:
- `campaign.read`
- `campaign.write`
- `report.generate`
- `outreach.execute`
- `admin.users.manage`

## 5) Campaign and Tenant Isolation

Mandatory controls:
- All domain records include immutable `tenant_id`.
- API middleware resolves tenant from JWT and blocks cross-tenant IDs.
- Campaign lookups always constrained by `tenant_id` + `campaign_id`.
- Worker tasks validate campaign ownership before processing.
- Report generation queries are tenant-scoped by contract.

Database-level controls:
- Composite indexes include `tenant_id`.
- Optional PostgreSQL RLS with session-scoped `app.tenant_id`.
- No shared mutable cross-tenant caches.

## 6) Rate Limiting

Purpose:
- Protect APIs and external automation workflows from abuse and accidental overload.

Limit layers:
- Per-user and per-tenant API limits.
- Endpoint-specific limits for expensive actions.
- Task emission limits per tenant/campaign window.
- External domain/provider pacing controls for crawls/SERP.

Enforcement:
- Redis token bucket/leaky bucket counters.
- `429 Too Many Requests` with retry metadata.
- Burst and sustained limits configurable by plan tier.

## 7) Input Validation and Output Safety

Input controls:
- Pydantic schema validation on all request bodies and query params.
- Strict enum and length constraints for critical fields.
- URL/domain validation and normalization for crawl/rank targets.
- SQL parameters always bound; never string-interpolated queries.

Sanitization:
- Escape user-generated content in HTML templates.
- Strip/deny dangerous payloads in file uploads and templating inputs.
- Guard SSRF vectors in fetch/crawl modules via allow/deny policies.

Output controls:
- Avoid returning internal stack traces in production responses.
- Consistent error envelope with opaque correlation ID.

## 8) Audit Logging

Audit-required actions:
- Authentication events (login, refresh, logout, failures).
- User/role/permission changes.
- Campaign creation/update/archive.
- Manual task replays and overrides.
- Report generation, download, and email delivery actions.

Audit record fields:
- `event_id`
- `tenant_id`
- `actor_id` (or service principal)
- `campaign_id` (if applicable)
- `action`
- `resource_type`
- `resource_id`
- `result`
- `ip_address`
- `user_agent`
- `occurred_at`
- `correlation_id`

Policy:
- Immutable append-only storage pattern.
- Retention by compliance policy.

## 9) Encryption at Rest

Requirements:
- Database storage encryption enabled.
- Object storage encryption enabled (SSE-KMS or equivalent).
- Backups encrypted with managed key policy.
- Sensitive application secrets never stored in plaintext in repo or images.

Secrets management:
- Use secret manager or encrypted environment injection.
- Rotate credentials periodically and on incident.

## 10) Encryption in Transit

Requirements:
- TLS 1.2+ for all client/API traffic.
- TLS for service-to-service communication where supported.
- Secure SMTP/TLS for report and outreach email delivery.
- Certificate renewal automation and expiry alerts.

## 11) Backup Strategy

Database:
- Continuous WAL archiving and point-in-time recovery capability.
- Daily full backup + frequent incremental backups.

Redis:
- Persistence snapshots for recovery where operationally required.
- Broker backlog design assumes some replay tolerance.

Object storage:
- Versioning enabled for report artifacts and critical exports.
- Cross-region replication where required by business continuity targets.

Backup validation:
- Scheduled restore tests in isolated environment.

## 12) Disaster Recovery

Targets:
- RPO <= 15 minutes.
- RTO <= 4 hours.

Recovery plan:
1. Declare incident and freeze non-essential writes.
2. Restore primary data stores from latest valid recovery point.
3. Rehydrate queue state from durable execution ledger and replay policies.
4. Validate tenant isolation and auth services before reopening traffic.
5. Run post-recovery integrity checks and publish incident report.

## 13) Security Monitoring and Incident Response

Monitoring requirements:
- Auth failure spikes and token misuse patterns.
- Cross-tenant access denial attempts.
- Unusual task replay or override volumes.
- Elevated 4xx/5xx from sensitive endpoints.
- WAF and ingress anomaly events.

Incident response:
- Severity classification and paging policy.
- Containment actions by subsystem.
- Credential rotation playbooks.
- Forensic log preservation.
- Post-incident corrective action tracking.

## 14) Secure Development Requirements

- Dependency vulnerability scanning in CI.
- Static analysis and secret scanning in CI.
- Mandatory code review for auth/RBAC/data access changes.
- Migration review for tenant scoping and index safety.
- Penetration tests for API and auth surface on scheduled cadence.

## 15) Compliance and Governance

- Maintain access reviews for privileged roles.
- Enforce least privilege for service accounts and infra credentials.
- Keep data retention and deletion policies explicit per data class.
- Document lawful basis and consent handling where user data is involved.

This document is the governing security baseline for LSOS.
