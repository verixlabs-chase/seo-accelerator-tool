# TR1 Security, Reliability, and Recovery Runbook

## Purpose

This runbook governs the production rollout and evidence required for the TR1
tenant-isolation, revocable-session, durable-job, and database-recovery controls.
It is intentionally Windows-friendly and does not require Docker for local use.

## Shipped controls

- PostgreSQL RLS is enabled for every public base table containing
  `tenant_id` or `organization_id`, plus `tenants` and `organizations`.
- Tenant requests switch transaction-locally to the non-login `lsos_app` role
  and set tenant, organization, user, and platform-access context.
- New access and refresh tokens are tied to a durable `auth_sessions` record.
  Refresh tokens rotate on use, replayed refresh tokens fail, logout revokes
  the server-side session, and users can list or revoke their own sessions.
- Platform operations expose database-backed durable-job counts, dead letters,
  expired leases, retry backlog, and oldest-due age.
- CI runs a real PostgreSQL cross-organization read/write isolation test.
- `verify_restore_integrity.py` validates schema head, required tables, tenant
  relationships, RLS coverage, and the application role on a restored database.

## Production rollout order

1. Confirm the migration workflow and backend CI are green.
2. Apply Alembic revision `20260730_0077`.
3. Confirm the `lsos_app` role exists and RLS is enabled.
4. Deploy the API containing the transaction-local database context.
5. Set `DATABASE_RLS_ENABLED=true` in the backend production and preview
   environments, then redeploy the API.
6. Confirm login, refresh, logout, organization switching, and one
   location-scoped read/write journey.
7. Confirm `/api/v1/system/operational-health` reports durable database truth.
8. Retain the previous Vercel deployment until the smoke tests pass.

RLS enforcement defaults off so a Vercel deployment cannot race ahead of the
database migration. Turn it on only after the role and policies are verified.
Once enabled, the API fails closed when it cannot switch to `lsos_app`.

## RLS verification

Run in the Supabase SQL editor:

```sql
select c.relname as table_name, c.relrowsecurity
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and (
    c.relname in ('tenants', 'organizations')
    or exists (
      select 1
      from information_schema.columns col
      where col.table_schema = 'public'
        and col.table_name = c.relname
        and col.column_name in ('tenant_id', 'organization_id')
    )
  )
order by c.relname;
```

Every returned row must have `relrowsecurity = true`.

## Session smoke test

1. Log in and call `GET /api/v1/auth/me`.
2. Call `POST /api/v1/auth/refresh` once.
3. Reuse the old refresh token and confirm HTTP 401.
4. Call `GET /api/v1/auth/sessions` and confirm the current session appears.
5. Log out and confirm both the old access token and current refresh token fail.

Tokens issued before this release remain temporarily compatible. Their first
successful refresh creates a durable session and rotates them into the new
model.

## Durable-job alert checks

The platform-owner endpoint `GET /api/v1/system/operational-health` includes:

- `dead_letter_count`
- `stale_lease_count`
- `retry_backlog_count`
- `oldest_due_seconds`
- explicit alert booleans

Any dead letter, stale lease, or due job older than five minutes requires
operator review before paid or mutating automation is expanded.

## Backup and restore drill

Never restore over the production project for a drill.

1. Create an isolated Supabase recovery project or approved restore branch.
2. Restore the selected backup/PITR point into that isolated target.
3. Put its direct PostgreSQL URL into the current PowerShell session:

```powershell
$env:RESTORED_DATABASE_URL = '<restored database URL>'
```

4. From `backend`, run:

```powershell
.\.venv\Scripts\python.exe scripts\verify_restore_integrity.py
```

5. Save the JSON output with the incident/change ticket.
6. Run the PostgreSQL RLS test suite against the restored target.
7. Record restore start/end time, recovery point, row-count comparison,
   schema head, RLS result, orphan result, and reviewer.
8. Destroy the isolated recovery target after evidence retention is complete.

The drill passes only when the verifier returns exit code `0`, cross-tenant
tests pass, and the restored row counts are reconciled with the selected
recovery point.

## Rollback

If RLS causes a production regression:

1. Roll back the API to the prior Vercel deployment.
2. Keep the database migration in place while investigating; the owner
   connection used by the prior deployment bypasses RLS and remains compatible.
3. Do not disable RLS to mask an application-context defect.
4. If a migration rollback is explicitly approved, take a fresh backup first,
   then downgrade one revision and verify tenant integrity.

## Evidence required to close TR1

- PostgreSQL CI isolation job: green
- migration workflow: green
- production login/session smoke test: green
- production cross-location read/write smoke test: green
- operational-health durable-job state: captured
- isolated backup/PITR restore drill: captured and reviewed
- secret-rotation and deployment-rollback drills: captured and reviewed
