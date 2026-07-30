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
  relationships, exact baseline counts, RLS coverage, and rollback-only
  cross-organization read/write behavior on a restored database.
- JWT and credential encryption keys support bounded transition-key windows;
  new material is written only with the active key.
- `rotate_credential_master_key.py` verifies or atomically rewraps all stored
  provider credentials without printing plaintext.
- The Windows operator script and manual GitHub workflow produce sanitized
  operational, restore, and credential-rotation evidence.

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

The Windows evidence collector performs this sequence without writing tokens or
passwords to its output:

```powershell
$env:TR1_API_BASE_URL = 'https://your-api-project.vercel.app'
$env:TR1_PLATFORM_EMAIL = '<platform owner email>'
$env:TR1_PLATFORM_PASSWORD = '<platform owner password>'
.\scripts\windows\Invoke-TR1Drill.ps1 -Drill Operational
```

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
.\.venv\Scripts\python.exe scripts\verify_restore_integrity.py `
  --baseline artifacts\tr1\pre-restore-baseline.json `
  --output artifacts\tr1\restore-evidence.json
```

5. Save the JSON output with the incident/change ticket.
6. Confirm the rollback-only RLS behavior probe passed. Do **not** run the
   normal pytest PostgreSQL fixture against a restored database; that fixture
   intentionally drops and rebuilds `public`.
7. Record restore start/end time, recovery point, exact row-count comparison,
   schema head, RLS result, orphan result, and reviewer.
8. Destroy the isolated recovery target after evidence retention is complete.

The drill passes only when the verifier returns exit code `0`, cross-tenant
tests pass, and the restored row counts are reconciled with the selected
recovery point.

## Secret rotation drill

### JWT signing secret

1. Generate a new secret of at least 32 random characters.
2. In Vercel, set the new value as `JWT_SECRET` and set
   `JWT_PREVIOUS_SECRETS_JSON` to a JSON array containing the old secret.
3. Redeploy and run the operational evidence collector. Existing sessions must
   refresh successfully, and newly issued tokens must use the new key.
4. Revoke remaining sessions or wait through the approved refresh-token grace
   period.
5. Set `JWT_PREVIOUS_SECRETS_JSON=[]`, redeploy, and run the evidence collector
   again.

### Credential encryption master key

1. Generate 32 random bytes encoded as base64.
2. Set the new value as `PLATFORM_MASTER_KEY`, put the old key in
   `PLATFORM_PREVIOUS_MASTER_KEYS_JSON`, and increment
   `CREDENTIAL_MASTER_KEY_VERSION`.
3. Redeploy. Search Console and other stored provider credentials remain
   decryptable through the transition key.
4. Set `CREDENTIAL_ROTATION_DATABASE_URL` to the direct PostgreSQL URL and run:

```powershell
.\scripts\windows\Invoke-TR1Drill.ps1 -Drill CredentialRotationDryRun
.\.venv\Scripts\python.exe scripts\rotate_credential_master_key.py `
  --apply `
  --confirm-version $env:CREDENTIAL_MASTER_KEY_VERSION `
  --output artifacts\tr1\credential-rotation-applied.json
```

5. Verify Google Search Console synchronization, then set
   `PLATFORM_PREVIOUS_MASTER_KEYS_JSON=[]` and redeploy.

The rotation command decrypts and immediately re-encrypts in memory, commits
all credential rows atomically, and never prints credential plaintext.

## Rollback

If RLS causes a production regression:

1. Roll back the API to the prior Vercel deployment.
2. Keep the database migration in place while investigating; the owner
   connection used by the prior deployment bypasses RLS and remains compatible.
3. Do not disable RLS to mask an application-context defect.
4. If a migration rollback is explicitly approved, take a fresh backup first,
   then downgrade one revision and verify tenant integrity.

For the scheduled TR1 deployment drill, use two backward-compatible app
deployments:

1. Record the current frontend and API deployment IDs and health results.
2. Promote the immediately previous successful deployment for each project.
3. Verify API health, login, and one Reno/Lexington location switch.
4. Promote the current deployment again.
5. Repeat health and authenticated smoke checks and retain the deployment IDs,
   timestamps, and results. Do not downgrade the database for this drill.

## Evidence required to close TR1

- PostgreSQL CI isolation job: green on 2026-07-30
- migration workflow: revision `20260730_0077` applied on 2026-07-30
- production API health: HTTP 200 after RLS-enabled redeploy on 2026-07-30
- production authenticated dashboard session: green on 2026-07-30
- production Reno/Lexington location-switch smoke test: green on 2026-07-30
- local Windows regression: 602 passed, 16 environment-specific skips on
  2026-07-30
- closeout implementation: published as commit `45e4ca4` on 2026-07-30
- backend CI workflow run `30564491627`: green on 2026-07-30
- CI workflow run `30564491646`: backend, PostgreSQL security, deterministic
  replay, and frontend jobs all green on 2026-07-30 (21m 19s)
- Vercel API deployment `AiwLSjeNnsQ6MFNvsJWbKoSQe66B` and frontend
  deployment `AAyNtEhCEx46oybyFYt8T2HMLZKu`: ready and assigned to production
  on 2026-07-30
- deployment rollback drill: passed on 2026-07-30. The API was rolled back to
  `4s66LNciaRyaTXDysnxXaRLSso2M`, returned HTTP 200, and was restored to
  `AiwLSjeNnsQ6MFNvsJWbKoSQe66B`, which returned HTTP 200. The frontend was
  rolled back to `5PxaopMQ7JRxcnKktsNLgQEWCaCV`, returned HTTP 200 with the
  login form present, and was restored to
  `AAyNtEhCEx46oybyFYt8T2HMLZKu`, which returned HTTP 200 with the login form
  present
- operational-health durable-job state: **pending** a sanitized capture using
  a platform-owner session
- isolated backup/PITR restore drill: **pending** an approved isolated
  Supabase recovery project or restore branch
- live JWT and credential-master-key rotation drills: **pending** an approved
  maintenance window and production secret access

TR1 remains open until the three pending operator-controlled drills above are
captured and reviewed. The GitHub Actions Node.js 20 deprecation annotations
are non-blocking but should be cleared by upgrading the affected action
versions before GitHub removes forced Node.js 24 compatibility.
