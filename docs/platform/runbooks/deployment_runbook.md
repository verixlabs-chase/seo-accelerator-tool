# Supabase and Vercel Deployment Runbook

## Purpose

Deploy and recover the Windows-managed hosted platform. The production path is
Supabase PostgreSQL plus separate Vercel FastAPI and Next.js projects. It does
not require Docker, WSL, Redis, or Linux shell tooling.

## Primary artifacts

- backend application: `backend/api/index.py`
- backend deployment settings: `backend/vercel.json`
- frontend deployment settings: `frontend/vercel.json`
- migrations: `backend/alembic`
- migration workflow: `.github/workflows/supabase-migrations.yml`
- hosted settings model: `backend/app/core/settings.py`
- TR1 drill workflow: `.github/workflows/tr1-drills.yml`

## Preconditions

- GitHub `main` is protected by the Windows backend/frontend and PostgreSQL
  isolation checks.
- `SUPABASE_MIGRATION_DATABASE_URL` points to the direct migration connection,
  not the transaction pooler.
- Vercel backend uses the Supabase transaction-pooler URL with
  `sslmode=require`.
- `APP_ENV=production`, `HOSTED_SERVERLESS=true`,
  `LOCAL_ADMIN_BOOTSTRAP_ENABLED=false`, and `DATABASE_RLS_ENABLED=true`.
- `JWT_SECRET`, `PLATFORM_MASTER_KEY`, `CRON_SECRET`, `PUBLIC_BASE_URL`, and the
  approved provider secrets are configured in Vercel.
- Existing production and preview deployments remain available for rollback.

## Deployment sequence

1. Run backend tests, frontend tests/build, migration validation, and Ruff on
   Windows.
2. Push the reviewed commit to `main`.
3. If Alembic changed, wait for the Supabase migration workflow to finish
   before treating the API deployment as released.
4. Confirm both Vercel projects deployed the same commit and reached `Ready`.
5. Confirm `GET /api/v1/health` returns HTTP 200.
6. Log in and verify one location-scoped read for Reno and Lexington.
7. Capture platform operational health and verify durable-job alert state.
8. Keep the previous deployments until the observation window passes.

## Post-deploy checks

- backend and frontend point to the same release commit
- API health is HTTP 200
- login, refresh, session inventory, and logout work
- Reno and Lexington remain independently scoped
- Search Console freshness and provider state are truthful
- durable jobs have no unexplained dead letter, expired lease, retry backlog,
  or queue delay over five minutes
- no new browser console errors appear on the critical journey

Use the Windows evidence collector:

```powershell
.\scripts\windows\Invoke-TR1Drill.ps1 -Drill Operational
```

## Application rollback

1. Confirm the previous deployment used a schema-compatible release.
2. Record the current frontend and backend deployment IDs.
3. Promote the previous successful backend deployment.
4. Promote the matching previous frontend deployment.
5. Run API health, login, and Reno/Lexington smoke checks.
6. If recovery is confirmed, keep the rollback and open an incident. For a
   planned drill, promote the original current deployments again and repeat the
   checks.

Do not disable RLS or downgrade Supabase merely to hide an application-context
failure. A database downgrade requires explicit approval and a fresh backup.

## Failure points

- migration failed: stop; do not promote an API that expects the new schema
- API deployment failed: leave the last production deployment promoted
- frontend failed: leave the prior frontend production deployment promoted
- RLS context failed: roll back the API while keeping the migration and RLS
- provider or OAuth regression: keep stored credentials intact, restore the
  prior application deployment, and verify key-transition configuration
- durable-job backlog: stop dispatching paid or mutating work until the queue is
  healthy

## Recovery evidence

Retain commit SHA, deployment IDs, timestamps, health results, authenticated
smoke results, operational-health summary, reviewer, and rollback decision.
Use [tr1_security_recovery.md](./tr1_security_recovery.md) for restore and secret
rotation drills.
