# Deployment Runbook

## Purpose

Deploy or update the platform safely using the current repository layout and runtime assumptions.

## Primary artifacts

- compose definition: `docker-compose.yml`
- image build: `backend/Dockerfile`
- migrations: `backend/alembic`
- settings model: `backend/app/core/settings.py`

## Preconditions

- PostgreSQL reachable and writable
- Redis reachable
- required env vars present, especially `POSTGRES_DSN`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `JWT_SECRET`, `PLATFORM_MASTER_KEY`, `PUBLIC_BASE_URL`
- for production-like environments, object storage, SMTP, and OTEL variables set as required by `Settings.validate_production_guardrails`

## Deployment steps

1. Build the backend image from `backend/Dockerfile`.
2. Run database migrations: `alembic upgrade head`.
3. Start API nodes.
4. Verify `/api/v1/health/readiness`.
5. Start Celery workers.
6. Verify Redis worker heartbeat key `infra:worker:heartbeat`.
7. Start Celery Beat.
8. Verify scheduler heartbeat key `infra:scheduler:heartbeat`.
9. Check `/api/v1/system/operational-health`.

## Post-deploy checks

- `GET /api/v1/health/readiness`
- `GET /api/v1/health/liveness`
- `GET /api/v1/system/operational-health`
- `GET /internal/metrics`
- `GET /metrics` if enabled

## Rollback guidance

- If the release is app-only and migrations are backward compatible, redeploy the previous API/worker image.
- If migrations are not backward compatible, stop and evaluate before rollback.
- If Redis-backed workers are unhealthy but API is healthy, stop new queue-producing traffic if possible and recover workers before rolling back API.

## Failure points to watch

- Redis unavailable: API and worker startup should fail fast.
- heartbeat missing: worker or beat is not actually healthy.
- migrations stalled: API may boot against an incompatible schema.
- production guardrails rejecting env vars: startup will fail in `Settings.validate_production_guardrails`.
