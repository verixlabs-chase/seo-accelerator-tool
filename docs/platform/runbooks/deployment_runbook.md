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
- Migration `20260821_0208` is applied before request limiting is enabled.
- `RATE_LIMIT_ENABLED=true`, `RATE_LIMIT_BACKEND=postgres`,
  `RATE_LIMIT_IDENTITY_SOURCE=vercel`, and the approved coarse request limit
  are configured on the backend project.
- `RATE_LIMIT_HMAC_SECRET` and `CRON_SECRET` are independent random secrets of
  at least 32 characters.
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
5. Through the frontend origin, confirm `GET /api/v1/health` returns HTTP 200
   and reports an enabled PostgreSQL limiter.
6. Through the frontend origin, confirm `GET /api/v1/health/readiness` returns
   HTTP 200, reports `ready`, a connected database and limiter store, and
   includes numeric `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
   `X-RateLimit-Reset` headers.
7. Log in and verify one location-scoped read for Reno and Lexington.
8. Capture platform operational health and verify durable-job alert state.
9. Keep the previous deployments until the observation window passes.

## Post-deploy checks

- backend and frontend point to the same release commit
- proxied API liveness is HTTP 200 and identifies the enabled PostgreSQL
  limiter; exact liveness is deliberately quota-exempt
- proxied API readiness is HTTP 200, confirms the connected limiter store, and
  returns valid quota headers
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

The production browser smoke makes exactly one same-origin liveness request
and one same-origin readiness request. These reads do not change customer data.
Readiness does consume its internal probe and the caller's normal fixed-window
quota, so never turn the production check into a retry loop or attempt to reach
the 600-request ceiling as proof.

## Isolated limiter promotion proof

Run destructive or threshold-oriented checks only in a dedicated preview that
has no customer traffic, uses a preview database, and has its own HMAC secret.
Never perform these checks against production.

### Direct-versus-proxy identity proof

Use a fresh preview-only HMAC secret and the normal coarse request limit. Make
only these three protected requests within one fixed-window minute and retain
only the returned status and quota headers:

1. From test network A, make one readiness request directly to the preview
   backend, followed immediately by one through the preview frontend origin.
2. Require both responses to share the same `X-RateLimit-Reset` value and the
   direct response to report `limit - 1` remaining and the proxied response to
   report `limit - 2`. This proves the frontend hop preserved network A's
   limiter identity.
3. From a genuinely separate test network B, make one readiness request
   through the frontend origin. It must report `limit - 1` remaining, not
   continue network A's counter. This proves different clients do not collapse
   onto a shared frontend or backend proxy identity.
4. If the reset values cross a minute boundary or any unrelated preview
   request occurs, mark the evidence inconclusive and repeat once in a fresh
   minute; do not compensate by generating more traffic.

### Controlled 429 proof

1. Set the preview's `RATE_LIMIT_REQUESTS_PER_MINUTE` to `2`, keep the
   PostgreSQL backend and Vercel identity source, and deploy with a fresh
   preview-only `RATE_LIMIT_HMAC_SECRET`.
2. Make exactly three sequential `GET /api/v1/health/readiness` requests
   through that preview's frontend origin. Do not use a load generator or a
   loop.
3. Confirm the first two responses are HTTP 200 with numeric quota headers and
   the third is HTTP 429 with `reason_code=rate_limit_exceeded`, `Retry-After`,
   `Cache-Control: private, no-store`, and the three quota headers.
4. Restore the approved request limit and normal preview secret, redeploy, and
   confirm readiness returns HTTP 200.

### Fail-closed 503 proof

1. In the same isolated preview only, temporarily set its database URL to a
   syntactically valid but deliberately unreachable test endpoint and redeploy.
2. Make one protected readiness request. Confirm HTTP 503,
   `reason_code=rate_limit_unavailable`, `Retry-After: 5`, and
   `Cache-Control: private, no-store`; quota headers must be absent. The
   response must complete within the five-second admission deadline plus a
   small transport allowance rather than waiting for Vercel's function limit.
3. Confirm exact `GET /api/v1/health` still returns HTTP 200 because liveness is
   deliberately exempt.
4. Restore the preview database URL immediately, redeploy, and require HTTP 200
   readiness before closing the proof.

Retain only sanitized status codes, headers, request IDs, timestamps, commit
SHA, and deployment IDs. Do not retain secrets, database URLs, raw client
addresses, cookies, or tenant payloads.

### Cron cleanup proof

The drain endpoint can process due durable jobs, so use the isolated preview or
inspect an already scheduled production invocation; do not trigger an extra
production drain merely to test cleanup.

1. Confirm one request with missing or incorrect authorization is rejected and
   does not drain work.
2. Send one direct-backend `GET /api/v1/internal/jobs/drain` with the preview
   cron authorization. Never place `CRON_SECRET` in a browser, frontend
   variable, URL, log, or evidence file.
3. Confirm HTTP 200 and
   `data.rate_limit_cleanup.attempted=true`. Its status must be `completed` or
   `batch_limit_reached`, `deleted` must be nonnegative, and no more than one
   batch of 1,000 rows may run.
4. Treat `status=unavailable` as a failed cleanup proof even if the durable-job
   drain itself returned HTTP 200.

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

## Limiter-only availability rollback

If the PostgreSQL limiter or forwarded-identity path causes a production
availability incident, leave migration `20260821_0208` in place and:

1. Record the incident, current backend deployment ID, and limiter evidence.
2. Set backend `RATE_LIMIT_ENABLED=false` and redeploy. Do not weaken RLS,
   expose a database function, reuse another secret, or switch hosted mode to
   process-local Redis.
3. Confirm liveness reports the limiter as disabled and critical customer reads
   recover. Readiness is expected to remain HTTP 503 while protection is
   disabled; do not record the deployment as launch-ready.
4. Keep Vercel Firewall/WAF controls enabled, time-box the exception, repair the
   failed dependency or identity configuration, then restore
   `RATE_LIMIT_ENABLED=true` and rerun the safe production smoke.

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
