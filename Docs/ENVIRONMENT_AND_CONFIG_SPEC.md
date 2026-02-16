# ENVIRONMENT_AND_CONFIG_SPEC.md

## 1) Scope

Defines configuration governance for local, staging, and production LSOS environments.

## 2) Environment Tiers

- `local`: developer productivity, reduced scale, mock integrations allowed.
- `staging`: production-like validation, full integrations where possible.
- `production`: hardened security, autoscaling, managed services.

## 3) Configuration Principles

- 12-factor configuration via environment variables.
- No secrets in source control.
- Strong defaults for local only; explicit values required for staging/prod.
- Versioned config schema for services and workers.

## 4) Required Environment Variables

Core:
- `APP_ENV`
- `APP_NAME`
- `API_BASE_URL`
- `JWT_PRIVATE_KEY`
- `JWT_PUBLIC_KEY`
- `JWT_ACCESS_TTL_SECONDS`
- `JWT_REFRESH_TTL_SECONDS`

Database/Redis:
- `POSTGRES_DSN`
- `POSTGRES_POOL_SIZE`
- `READ_REPLICA_DSN`
- `REDIS_URL`

Celery:
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CELERY_DEFAULT_QUEUE`
- `CELERY_PREFETCH_MULTIPLIER`

Storage/Reports:
- `OBJECT_STORAGE_ENDPOINT`
- `OBJECT_STORAGE_BUCKET`
- `OBJECT_STORAGE_ACCESS_KEY`
- `OBJECT_STORAGE_SECRET_KEY`
- `REPORT_TEMPLATE_VERSION_DEFAULT`

Email:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`

Proxy:
- `PROXY_PROVIDER_CONFIG_JSON`
- `PROXY_MAX_CONCURRENCY`

Observability:
- `LOG_LEVEL`
- `METRICS_ENABLED`
- `OTEL_EXPORTER_ENDPOINT`

## 5) Feature Flag Governance

- Flags managed centrally with environment-specific defaults.
- Flag keys follow `module.feature_name` format.
- Every flag requires:
  - owner
  - rollout plan
  - removal date

## 6) Secrets Management

- Secrets loaded from secure store, not `.env` in production.
- Rotate high-sensitivity secrets every 90 days or after incidents.
- Access to secrets manager restricted by least privilege.

## 7) Config Validation

- Startup validation rejects missing required variables.
- Type-safe parsing with explicit error messages.
- Environment-specific guardrails:
  - production disallows debug mode and weak key sizes.

## 8) Deployment Config Policy

- Immutable image with runtime env injection.
- Separate config maps for API, scheduler, and worker pools.
- No direct manual edits in running cluster; changes via IaC and deployment pipeline.

## 9) Audit and Change Tracking

- Config changes logged with actor, timestamp, and diff summary.
- Critical config changes require approval workflow.

This document is the governing environment and configuration policy for LSOS.
