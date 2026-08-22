# SEO Accelerator Tool

Windows-native FastAPI and Next.js application hosted with Supabase and Vercel.

The supported development workflow requires:

- Windows 10 or 11
- PowerShell 5.1 or PowerShell 7
- Python 3.12 with the Windows `py` launcher
- Node.js 22 with npm
- a Supabase Postgres project
- a Vercel account for hosted deployments

Docker, WSL, Bash, Make, Redis, and a locally installed PostgreSQL server are
not required.

## First-time Windows setup

Open PowerShell in the repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Initialize-Development.ps1
```

The script creates:

- `backend\.venv312`
- `backend\.env` from the Windows/Supabase template
- `frontend\.env.local`
- frontend dependencies from `package-lock.json`

Edit `backend\.env` and replace `[URL-ENCODED-PASSWORD]`. Reserved password
characters must be percent-encoded, such as `@` to `%40` and `#` to `%23`.

Apply the Supabase schema:

```powershell
.\scripts\windows\Invoke-Migrations.ps1
```

Start both applications in separate PowerShell windows:

```powershell
.\scripts\windows\Start-Development.ps1
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/v1/health`

## Windows commands

```powershell
# Backend only
.\scripts\windows\Start-Backend.ps1

# Frontend only
.\scripts\windows\Start-Frontend.ps1

# Complete backend/frontend validation
.\scripts\windows\Invoke-Tests.ps1

# Faster repeat validation after dependencies are installed
.\scripts\windows\Invoke-Tests.ps1 -SkipDependencyInstall

# Reset and recreate the development environment
.\scripts\reset_dev_env.ps1
```

## Browser launch smoke

The frontend includes a Playwright smoke suite for the real customer-facing
browser path. The public sign-in check runs locally without credentials:

```powershell
Set-Location frontend
npx playwright install chromium
npm run build
npm run start
# In a second PowerShell window:
npm run test:e2e -- --project=chromium
```

The authenticated test is deliberately read-only: it signs in, confirms the
active location, opens Overview and Reports, and checks the categorized mobile
navigation without creating or changing customer data. Configure
`E2E_SMOKE_EMAIL` and `E2E_SMOKE_PASSWORD` as protected secrets in the GitHub
`production` environment. If that account can open more than one workspace,
set the environment variable `E2E_SMOKE_WORKSPACE` to the exact dedicated smoke
workspace name. The account must be limited to a synthetic tenant with no real
customer records and use only the minimum role needed to read this journey. Seed
that tenant with at least two locations, one comparable saved report for each,
and the normal Overview metrics; these are deliberate fixture requirements so a
green run proves real APIs and portfolio reporting loaded instead of only static
page copy.
Restrict the environment to the `main` deployment branch and require an
independent reviewer, then manually run the `Production browser smoke`
workflow. The workflow is fixed to `https://insightos.verixlabs.com`, exposes
credentials only to the test step, verifies that its server session was revoked,
and does not retain production screenshots, traces, video, or raw console text.

## Hosting

The repository deploys as two Vercel projects:

- `backend` to the FastAPI project
- `frontend` to the Next.js project

Both use the same Supabase database. GitHub Actions applies Alembic migrations
from a Windows runner using the `SUPABASE_MIGRATION_DATABASE_URL` repository
secret. See [Windows development](docs/windows-development.md) and
[Supabase/Vercel deployment](docs/supabase-vercel-deployment.md).

## Hosted-mode boundary

Vercel functions are short-lived. In the current hosted mode:

- Celery executes eagerly inside API requests
- Redis durability and Celery Beat are disabled
- scheduled reports can use the Supabase-backed durable job queue and Vercel Cron
- crawl and automation limits remain conservative
- remaining task types must be migrated to bounded durable jobs before their
  production limits are increased

The developer and operator workflow is Windows-only. Supabase and Vercel are
managed services; their internal infrastructure is controlled by those
providers and does not require Linux access from the user.

See [Production readiness roadmap](docs/production-readiness-roadmap.md) for the
current capability matrix and implementation order.

## Multi-location structure

The `/locations` workspace organizes a main organization into account groups
and physical business locations. Creating a scoped business location
automatically provisions its hidden portfolio and execution record; campaigns
created from the workspace inherit that location scope. Migration
`20260728_0072` is required before deploying this route.
