# LSOS Sprint 1 Scaffold

Initial implementation of Sprint 1 from `Docs/SPRINT_ROADMAP.md`.

## Included

- FastAPI backend under `backend/` with `/api/v1` routes.
- Auth endpoints:
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/refresh`
  - `GET /api/v1/auth/me`
- Campaign endpoints:
  - `POST /api/v1/campaigns`
  - `GET /api/v1/campaigns`
- Celery task scaffold:
  - `ops.healthcheck.snapshot`
  - `campaigns.bootstrap_month_plan`
  - `audit.write_event`
- Alembic migration for foundational tables.
- Next.js frontend shell with tenant-aware login flow.
- Docker Compose stack for local API + worker + scheduler + Postgres + Redis + frontend.
- GitHub Actions CI workflow.

## Run Backend Locally

WSL-friendly local backend flow:

1. Start infrastructure:

```bash
cp .env.example .env
docker compose up -d postgres redis mailhog
```

2. Configure backend env and run the API from the workspace:

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If an older local Postgres volume was created from an incompatible branch and Alembic or auth behaves inconsistently, reset only the local Docker data and migrate again:

```bash
docker compose down -v
docker compose up -d postgres redis mailhog
cd backend
alembic upgrade head
```

## Run Tests

```powershell
cd backend
pytest
```

Go-live preflight (runs backend + frontend checks end-to-end):

```powershell
cd infra
powershell -ExecutionPolicy Bypass -File .\go-live-preflight.ps1
```

If your local network/proxy blocks `pip-audit`, run:

```powershell
cd infra
powershell -ExecutionPolicy Bypass -File .\go-live-preflight.ps1 -SkipSecurityAudit
```

Optional JS-rendered crawling:

```powershell
pip install playwright
python -m playwright install chromium
```

Then set `CRAWL_USE_PLAYWRIGHT=true` in `backend/.env`.

Default local seeded user after migrations/startup:
- `admin@local.dev`
- `admin123!`

## Run Frontend Locally

The frontend is separate from Docker Compose in this repo.

```bash
cd frontend
npm install
npm run dev
```

It defaults to `http://localhost:8000/api/v1`.

## Run Backend Services via Docker Compose

Compose manages backend infrastructure and backend runtime services. It does not start the Next.js frontend.

```bash
cp .env.example .env
docker compose up --build
```

## Local Troubleshooting

If Docker services look healthy but `http://localhost:8000` still behaves unexpectedly, a stale host-run `uvicorn` process may still be bound to port `8000`. During Docker-based validation, `localhost:8000` should point to the Compose `api` service.

Check what is bound to `8000`:

```bash
lsof -i :8000
ss -ltnp | grep 8000
```

Stop the stale host process, then recreate the Compose API cleanly:

```bash
kill <PID>
docker compose up -d --force-recreate api
```

Go-live execution docs:
- `Docs/GO_LIVE_HARDENING_AND_RELEASE_EXECUTION.md`
- `Docs/PROVIDER_STACK_AND_SETUP_CHECKLIST.md`
