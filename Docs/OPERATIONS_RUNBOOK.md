# OPERATIONS_RUNBOOK.md

## 1) Scope

Operational procedures for running LSOS in production: health checks, incident triage, queue recovery, and escalation.

## 2) Daily Operations Checklist

- Verify API health endpoint and worker heartbeat status.
- Validate queue lag for all Celery queues.
- Check previous 24h failure ratio and dead-letter growth.
- Confirm crawl/rank/review freshness for active campaigns.
- Confirm backup completion and replica lag thresholds.

## 3) Queue Triage Runbook

Trigger:
- Any queue lag > 15 minutes or dead-letter spike > 3x baseline.

Procedure:
1. Identify queue and top failing task names.
2. Inspect task failure class (transient, validation, provider, parser).
3. Apply immediate mitigation:
   - Reduce concurrency if external blocks detected.
   - Increase replicas if backlog-only issue.
   - Pause specific task emissions if failure loop is confirmed.
4. Replay safe dead-letter tasks after fix.
5. Record incident actions in audit trail.

## 4) Reporting Failure Runbook

Trigger:
- Monthly report generation failures exceed 5% in 1-hour window.

Procedure:
1. Validate data completeness for affected campaigns.
2. Re-run `reporting.aggregate_kpis` and verify payload integrity.
3. Re-render HTML and PDF in isolated retry lane.
4. Resume email delivery for successful artifacts.
5. Notify owners for campaigns with irrecoverable data gaps.

## 5) Provider/Proxy Incident Runbook

Trigger:
- SERP failure rate > threshold across multiple campaigns.

Procedure:
1. Check proxy provider health dashboard.
2. Quarantine degraded provider pool.
3. Shift traffic to fallback provider with reduced concurrency.
4. Enable conservative pacing profile.
5. Backfill missed rank windows after stability.

## 6) Database Incident Runbook

Trigger:
- Replica lag breach, failed migrations, or primary degradation.

Procedure:
1. Freeze non-critical write paths.
2. Validate connection pool saturation and blocking queries.
3. Fail over reads to healthy replica set or primary.
4. Restore service and run integrity checks.
5. Schedule post-incident optimization.

## 7) Escalation Matrix

- SEV-1: full service outage or cross-tenant risk.
  - Immediate paging: on-call engineer + security lead.
- SEV-2: major module unavailable, high error rates.
  - Page primary on-call and module owner.
- SEV-3: partial degradation with workaround.
  - Ticket and same-day remediation.

## 8) Recovery and Replay Controls

- Replay requires privileged operator role.
- Every replay action must include reason code.
- Replay only idempotent tasks unless explicit override.
- Preserve original correlation IDs and chain lineage.

## 9) Post-Incident Review Requirements

- Timeline with exact timestamps (UTC).
- Root cause and blast radius.
- Corrective actions with owner and due date.
- Monitoring gap updates and runbook improvements.

This document is the governing operations runbook for LSOS.
