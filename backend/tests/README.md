# Backend test modes on Windows

Run commands from Windows PowerShell at the repository root.

## Normal suite

The default test harness creates isolated SQLite databases and does not require
PostgreSQL, Docker, or WSL.

```powershell
.\scripts\windows\Initialize-Development.ps1
.\backend\.venv312\Scripts\python.exe -m pytest -q backend\tests
```

Run only unit tests:

```powershell
cd backend
.\.venv312\Scripts\python.exe -m pytest -m unit
```

## PostgreSQL integration tests

Use a dedicated Supabase test project or disposable Postgres database. Never
run destructive integration or load tests against production.

```powershell
cd backend
$env:DATABASE_URL = "postgresql://postgres.<project-ref>:<encoded-password>@<pooler-host>:5432/postgres?sslmode=require"
$env:POSTGRES_DSN = $env:DATABASE_URL
.\.venv312\Scripts\python.exe -m pytest -m "integration or postgres_required"
```

## Load benchmarks

Load tests are intentionally skipped on SQLite because it does not represent a
client/server database.

```powershell
cd backend
$env:DATABASE_URL = "<dedicated-test-database-url>"
$env:POSTGRES_DSN = $env:DATABASE_URL
.\.venv312\Scripts\python.exe -m pytest -m load
```

## Complete validation

```powershell
.\scripts\windows\Invoke-Tests.ps1
```

This runs backend tests, migration validation, Ruff, dependency audits,
frontend tests, lint, and the production frontend build.
