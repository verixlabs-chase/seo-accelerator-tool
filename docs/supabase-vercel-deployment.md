# Supabase + Vercel deployment

This is the supported Windows-managed deployment:

- Supabase transaction-pooled Postgres for application data
- one Vercel project for the FastAPI backend
- one Vercel project for the Next.js frontend
- no Docker, WSL, Bash, local Redis, or local PostgreSQL

## What works in this mode

Authentication, tenant data, campaigns, dashboards, and database-backed API
workflows can run on Vercel. Celery tasks execute eagerly inside the API request.

Vercel functions are not persistent workers. The `platform_jobs` table and a
protected Vercel Cron endpoint provide the first durable execution path for
scheduled report generation. Other Celery tasks still execute eagerly. Large
crawls, Playwright crawling, Redis event durability, and high-volume automation
are deliberately not claimed as production-capable yet. Keep crawl limits small
while additional task types are migrated to durable jobs.

## 1. Create Supabase

1. Create a Supabase project.
2. Open **Connect** and copy the transaction pooler connection string (port
   `6543`) for the Vercel backend, not the browser-facing project URL or anon
   key.
3. Also copy the direct connection string for migrations. If the runner cannot
   reach the IPv6 direct endpoint, use the session pooler on port `5432` for
   migrations.
4. Ensure both URLs include `sslmode=require`.
5. Treat the database password as a server-only secret. Do not expose it using
   a `NEXT_PUBLIC_` variable.
6. Percent-encode reserved password characters before inserting the password
   into either URL. For example, encode `@` as `%40`, `#` as `%23`, and `%` as
   `%25`.

The application continues to own authentication and tables through SQLAlchemy;
Supabase Auth is not required for this first deployment.

## 2. Apply the schema

From Windows with Python 3.12:

```powershell
.\scripts\windows\Initialize-Development.ps1
.\scripts\windows\Invoke-Migrations.ps1
```

Alternatively, add `SUPABASE_MIGRATION_DATABASE_URL` as a GitHub Actions
repository secret and manually run the **Supabase migrations** workflow. Use
the direct or session-pooler URL for this secret, not transaction mode. The
Windows workflow also runs when migration files change on `main`.

Never run migrations automatically during a Vercel function cold start.

## 3. Deploy the backend to Vercel

Import the repository as a Vercel project and set:

- Project root: `backend`
- Framework preset: FastAPI
- Production branch: `main`

Vercel detects `backend/api/index.py` as the FastAPI entrypoint. Do not add a
catch-all rewrite to that file: current Vercel backend routing preserves API
paths automatically, while an internal rewrite changes the path received by
FastAPI and makes `/api/v1/*` return `404`.

Copy the variables from `backend/.env.supabase.example` into the Vercel project.
Replace every placeholder. Deploy, then check:

```text
https://your-api-project.vercel.app/api/v1/health
```

`STARTUP_INVARIANTS_ENABLED=false` avoids a large cold-start validation sweep.
Migrations remain the deployment gate.

## 4. Deploy the frontend to Vercel

Import the same repository as a second Vercel project and set:

- Project root: `frontend`
- Framework preset: Next.js

Add the variables from `frontend/.env.vercel.example`. Set
`API_PROXY_TARGET` to the backend project URL. The frontend sends browser calls
to `/api/v1`; Next.js proxies them to FastAPI. This keeps authentication cookies
first-party and avoids cross-site-cookie failures.

Redeploy the frontend whenever `API_PROXY_TARGET` changes.

## 5. OAuth and production settings

If Google OAuth is enabled, register the callback URL produced from the backend
`PUBLIC_BASE_URL`. Add the frontend production URL to `CORS_ORIGINS` for direct
API calls. Preview deployments normally use the same-origin proxy and do not
need wildcard CORS.

Generate secrets locally:

```powershell
# JWT secret
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))

# PLATFORM_MASTER_KEY
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))

# CRON_SECRET
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

Save `CRON_SECRET` in the backend Vercel project for Production, Preview, and
Development. Vercel automatically sends it to configured cron routes as:

```text
Authorization: Bearer <CRON_SECRET>
```

The drain endpoint refuses all requests when the secret is missing and rejects
non-matching authorization headers. The committed daily schedule is compatible
with Vercel Hobby. Paid plans can increase its frequency later.

## Operational boundary

The no-Docker deployment is an intentionally constrained hosted mode:

- database connection pooling is delegated to Supabase
- each Vercel invocation opens no persistent SQLAlchemy pool
- Redis-backed event streams become process-local
- task calls execute eagerly and must finish before the function timeout
- Celery Beat schedules do not run
- scheduled reports use the Supabase-backed `platform_jobs` queue and Vercel Cron
- all other background task types remain eager until migrated explicitly

For production crawling and automation, migrate bounded work units onto the
existing durable queue and protected Vercel Cron drain. Do not increase function
timeouts and crawl sizes blindly; crawlers require leases, retries, and
idempotent continuation.

See [Production readiness roadmap](production-readiness-roadmap.md).
