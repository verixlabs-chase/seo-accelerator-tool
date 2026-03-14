# Backend Test Modes

All commands below assume the WSL project path:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
```

## Default Behavior

- Functional tests default to the existing SQLite-backed temp database setup.
- Load benchmarks are marked `load` and `postgres_required`.
- Any test marked `postgres_required` is skipped unless `DATABASE_URL` or `POSTGRES_DSN` points to PostgreSQL.

## Markers

- `unit`: default fast test coverage under `tests/` outside `integration/` and `load/`
- `integration`: tests under `tests/integration/`
- `load`: tests under `tests/load/`
- `postgres_required`: tests that require a PostgreSQL-backed test database

## 1. Run Normal Test Suite

Uses the default SQLite temp DB path.

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
. .venv/bin/activate
pytest
```

Or:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
make test
```

Run only unit tests:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
. .venv/bin/activate
pytest -m unit
```

## 2. Run PostgreSQL Integration Tests

Create `backend/.env.test.postgres` first:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
cp .env.test.postgres.example .env.test.postgres
```

Then update `DATABASE_URL` and `POSTGRES_DSN` in that file to your PostgreSQL test database.

Manual example:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
export DATABASE_URL="postgresql+psycopg://lsos:lsos@localhost:5432/lsos_test"
export POSTGRES_DSN="$DATABASE_URL"
. .venv/bin/activate
pytest -m "integration or postgres_required"
```

Make target:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
make test-integration-postgres
```

If you only want integration tests that are not load benchmarks:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
export DATABASE_URL="postgresql+psycopg://lsos:lsos@localhost:5432/lsos_test"
export POSTGRES_DSN="$DATABASE_URL"
. .venv/bin/activate
pytest -m integration
```

## 3. Run Load Benchmarks

Load tests require PostgreSQL explicitly.

Use the same `backend/.env.test.postgres` file.

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
export DATABASE_URL="postgresql+psycopg://lsos:lsos@localhost:5432/lsos_test"
export POSTGRES_DSN="$DATABASE_URL"
. .venv/bin/activate
pytest -m load
```

Make target:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
make test-load-postgres
```

Run the capacity benchmark only:

```bash
cd "/home/verixlabs/SEO Accelerator Tool/backend"
export DATABASE_URL="postgresql+psycopg://lsos:lsos@localhost:5432/lsos_test"
export POSTGRES_DSN="$DATABASE_URL"
. .venv/bin/activate
pytest tests/load/test_platform_capacity_benchmark.py
```

## 4. Why Load Tests Skip On SQLite

The load benchmarks exercise concurrency and capacity behavior that SQLite file-backed temp databases do not represent well. The default SQLite path remains correct for most functional coverage, but capacity benchmarks should run against a client/server database.

## 5. Environment Notes

- The test harness auto-creates isolated SQLite temp files when no PostgreSQL DSN is set.
- The PostgreSQL path is opt-in.
- `tests/load/` is intentionally gated so normal local test runs do not accidentally make misleading capacity claims from SQLite.
- The Make targets `test-integration-postgres` and `test-load-postgres` expect `backend/.env.test.postgres` to exist.
