# Database Maintenance

## Scope

This runbook covers schema migrations, slow-query investigation, and routine health checks for PostgreSQL.

## Key paths

- migration config: `backend/alembic.ini`, `backend/alembic/env.py`
- migration versions: `backend/alembic/versions`
- engine/session setup: `backend/app/db/session.py`

## Routine tasks

### Apply migrations

Run `alembic upgrade head` before bringing new API and worker code fully online.

### Watch slow queries

The app records queries slower than 200 ms through `record_query_duration` and increments `slow_queries_total`.

### Verify core tables

Focus on write-heavy tables during incidents or maintenance:

- `event_outbox`
- knowledge graph tables
- recommendation execution/outcome tables
- learning metric/report tables

## Maintenance checks

1. Confirm DB connectivity with a simple `SELECT 1`.
2. Check migration head matches code.
3. Check slow-query logs and rates.
4. Check table growth for outbox and graph-related tables.
5. Confirm application write latency is normal after maintenance.

## Cautions

- Do not run destructive cleanup on outbox or graph tables without confirming downstream replay requirements.
- Because the platform uses DB-backed intelligence artifacts, partial restores can create inconsistent learning state even when core tenant data looks healthy.
