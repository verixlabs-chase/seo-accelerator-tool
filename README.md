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

```powershell
cd backend
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Run Tests

```powershell
cd backend
pytest
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

## Run Full Stack via Docker

```powershell
docker compose up --build
```
