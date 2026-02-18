# OPERATIONS_RUNBOOK.md
Generated: 2026-02-18T17:29:02.381145

## INTENT
Provide operational recovery steps.

---

## INCIDENT TYPES
Worker crash
Proxy block
Database failover
Queue stall

---

## RESPONSE FLOW
1. Identify
2. Triage
3. Mitigate
4. Log
5. Postmortem

---

## BACKUP / RESTORE

Backup Policy:
- Daily logical database backup
- Weekly full backup validation restore in staging
- Retention aligned with tenant lifecycle policy

Restore Flow:
1. Identify restore point objective (RPO)
2. Restore database snapshot into isolated environment
3. Run integrity checks (tenant counts, campaign counts, recommendation records)
4. Cut over with change approval
5. Validate health endpoints and queue recovery
