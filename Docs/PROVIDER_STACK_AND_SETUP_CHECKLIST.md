# PROVIDER_STACK_AND_SETUP_CHECKLIST.md

## 1) Recommended Production Stack

Use this exact stack unless you have a strong business reason to change:

- Hosting: Render (simplest managed deployment for this app shape)
- Database: Render PostgreSQL (managed)
- Redis: Render Redis (managed)
- Object storage: Cloudflare R2
- Email delivery: Postmark
- Monitoring:
  - Uptime: Better Stack Uptime
  - Error tracking: Sentry
  - Metrics/infra logs: Better Stack Logs or Datadog

## 2) What You Must Buy/Create

1. A Render account
2. A Cloudflare account (for R2 bucket)
3. A Postmark account
4. A Better Stack account
5. A Sentry account
6. A domain name (if you do not already have one)

## 3) Exact Non-Technical Setup Steps

### A) Render (API, worker, scheduler, frontend, Postgres, Redis)

1. Log into Render.
2. Create a new Render project named `lsos-production`.
3. Add PostgreSQL service and copy its internal connection string.
4. Add Redis service and copy its internal URL.
5. Add Web Service for backend API:
- Root directory: `backend`
- Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`
6. Add Worker service:
- Root directory: `backend`
- Start command: `celery -A app.tasks.celery_app.celery_app worker -Q default -l INFO`
7. Add Worker service (scheduler):
- Root directory: `backend`
- Start command: `celery -A app.tasks.celery_app.celery_app beat -l INFO`
8. Add Web Service for frontend:
- Root directory: `frontend`
- Build command: `npm install && npm run build`
- Start command: `npm run start`

### B) Cloudflare R2 (report artifacts)

1. Create a new bucket named `lsos-reports-prod`.
2. Create an access key pair for that bucket.
3. Copy:
- R2 endpoint URL
- Access key ID
- Secret access key

### C) Postmark (email delivery)

1. Create a server named `lsos-prod`.
2. Verify your sender domain (or sender email).
3. Create a server API token.
4. Keep token for `SMTP_PASSWORD` (Postmark SMTP mode).

### D) Better Stack + Sentry (monitoring)

1. Better Stack: create uptime checks for:
- API health endpoint
- Frontend homepage
2. Better Stack: create alert policy to email/SMS you on downtime.
3. Sentry: create a project for backend and one for frontend.
4. Copy DSN values to your deployment secret settings.

## 4) Production Environment Variables To Fill

Set these in Render for API/worker/scheduler:

- `APP_ENV=production`
- `APP_NAME=LSOS API`
- `POSTGRES_DSN=<render postgres dsn>`
- `REDIS_URL=<render redis url>`
- `CELERY_BROKER_URL=<render redis url>`
- `CELERY_RESULT_BACKEND=<render redis url>`
- `JWT_SECRET=<64+ character random secret>`
- `JWT_ACCESS_TTL_SECONDS=900`
- `JWT_REFRESH_TTL_SECONDS=604800`
- `OBJECT_STORAGE_ENDPOINT=<r2 endpoint>`
- `OBJECT_STORAGE_BUCKET=lsos-reports-prod`
- `OBJECT_STORAGE_ACCESS_KEY=<r2 access key id>`
- `OBJECT_STORAGE_SECRET_KEY=<r2 secret>`
- `SMTP_HOST=smtp.postmarkapp.com`
- `SMTP_PORT=587`
- `SMTP_USERNAME=<postmark server token>`
- `SMTP_PASSWORD=<postmark server token>`
- `SMTP_FROM_EMAIL=<verified sender>`
- `PROXY_PROVIDER_CONFIG_JSON=<provider json from engineer>`
- `LOG_LEVEL=INFO`
- `METRICS_ENABLED=true`
- `OTEL_EXPORTER_ENDPOINT=<monitoring endpoint>`

Set this in Render frontend:

- `NEXT_PUBLIC_API_BASE_URL=<your public api url>/api/v1`

## 5) Go/No-Go Release Rule

You can launch only when all are true:

1. `infra/go-live-preflight.ps1` passes locally.
2. GitHub Actions is green on main branch.
3. Staging smoke test passes all modules.
4. Uptime checks and alerting are active.
5. Rollback contact and owner are named.
