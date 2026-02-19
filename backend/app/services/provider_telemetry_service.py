from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.provider_health import ProviderHealthState
from app.models.provider_metric import ProviderExecutionMetric
from app.models.provider_quota import ProviderQuotaState


logger = logging.getLogger("lsos.provider.telemetry")

VALID_PROVIDER_OPERATIONS = {
    "snapshot",
    "rank_snapshot",
    "crawl_fetch",
    "health_check",
    "sync",
    "enrich",
    "validate",
    "dispatch",
    "unknown",
}


class ProviderTelemetryService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def record_execution_metric(
        self,
        *,
        tenant_id: str,
        provider_name: str,
        capability: str,
        operation: str,
        idempotency_key: str,
        attempt_number: int,
        max_attempts: int,
        duration_ms: int,
        timeout_budget_ms: int,
        outcome: str,
        retryable: bool,
        environment: str = "production",
        task_execution_id: str | None = None,
        provider_version: str | None = None,
        correlation_id: str | None = None,
        reason_code: str | None = None,
        error_severity: str | None = None,
        http_status: int | None = None,
    ) -> None:
        normalized_operation = self._normalize_operation(operation)
        try:
            metric = ProviderExecutionMetric(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                environment=environment,
                task_execution_id=task_execution_id,
                provider_name=provider_name,
                provider_version=provider_version,
                capability=capability,
                operation=normalized_operation,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                duration_ms=duration_ms,
                timeout_budget_ms=timeout_budget_ms,
                outcome=outcome,
                reason_code=reason_code,
                error_severity=error_severity,
                retryable=retryable,
                http_status=http_status,
                created_at=datetime.now(UTC),
            )
            self._db.add(metric)
            self._db.commit()
        except Exception:  # noqa: BLE001
            self._db.rollback()
            logger.warning("provider telemetry metric persistence failed", exc_info=True)

    def upsert_health_state(
        self,
        *,
        tenant_id: str,
        provider_name: str,
        capability: str,
        breaker_state: str,
        consecutive_failures: int,
        environment: str = "production",
        provider_version: str | None = None,
        success_rate_1h: float | None = None,
        p95_latency_ms_1h: int | None = None,
        last_error_code: str | None = None,
        last_error_at: datetime | None = None,
        last_success_at: datetime | None = None,
    ) -> None:
        try:
            row = (
                self._db.query(ProviderHealthState)
                .filter(
                    ProviderHealthState.tenant_id == tenant_id,
                    ProviderHealthState.environment == environment,
                    ProviderHealthState.provider_name == provider_name,
                    ProviderHealthState.capability == capability,
                )
                .first()
            )
            if row is None:
                row = ProviderHealthState(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    environment=environment,
                    provider_name=provider_name,
                    provider_version=provider_version,
                    capability=capability,
                    breaker_state=breaker_state,
                    consecutive_failures=consecutive_failures,
                    success_rate_1h=success_rate_1h,
                    p95_latency_ms_1h=p95_latency_ms_1h,
                    last_error_code=last_error_code,
                    last_error_at=last_error_at,
                    last_success_at=last_success_at,
                    updated_at=datetime.now(UTC),
                )
                self._db.add(row)
            else:
                row.provider_version = provider_version
                row.breaker_state = breaker_state
                row.consecutive_failures = consecutive_failures
                row.success_rate_1h = success_rate_1h
                row.p95_latency_ms_1h = p95_latency_ms_1h
                row.last_error_code = last_error_code
                row.last_error_at = last_error_at
                row.last_success_at = last_success_at
                row.updated_at = datetime.now(UTC)
            self._db.commit()
        except Exception:  # noqa: BLE001
            self._db.rollback()
            logger.warning("provider health state persistence failed", exc_info=True)

    def upsert_quota_state(
        self,
        *,
        tenant_id: str,
        provider_name: str,
        capability: str,
        window_start: datetime,
        window_end: datetime,
        limit_count: int,
        used_count: int,
        remaining_count: int,
        environment: str = "production",
        last_exhausted_at: datetime | None = None,
    ) -> None:
        try:
            row = (
                self._db.query(ProviderQuotaState)
                .filter(
                    ProviderQuotaState.tenant_id == tenant_id,
                    ProviderQuotaState.environment == environment,
                    ProviderQuotaState.provider_name == provider_name,
                    ProviderQuotaState.capability == capability,
                    ProviderQuotaState.window_start == window_start,
                )
                .first()
            )
            if row is None:
                row = ProviderQuotaState(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    environment=environment,
                    provider_name=provider_name,
                    capability=capability,
                    window_start=window_start,
                    window_end=window_end,
                    limit_count=limit_count,
                    used_count=used_count,
                    remaining_count=remaining_count,
                    last_exhausted_at=last_exhausted_at,
                    updated_at=datetime.now(UTC),
                )
                self._db.add(row)
            else:
                row.window_end = window_end
                row.limit_count = limit_count
                row.used_count = used_count
                row.remaining_count = remaining_count
                row.last_exhausted_at = last_exhausted_at
                row.updated_at = datetime.now(UTC)
            self._db.commit()
        except Exception:  # noqa: BLE001
            self._db.rollback()
            logger.warning("provider quota state persistence failed", exc_info=True)

    def summary(self, *, tenant_id: str, environment: str = "production") -> list[dict]:
        health_rows = (
            self._db.query(ProviderHealthState)
            .filter(ProviderHealthState.tenant_id == tenant_id, ProviderHealthState.environment == environment)
            .all()
        )
        quotas = (
            self._db.query(ProviderQuotaState)
            .filter(ProviderQuotaState.tenant_id == tenant_id, ProviderQuotaState.environment == environment)
            .all()
        )
        quota_by_key: dict[tuple[str, str], ProviderQuotaState] = {}
        now = datetime.now(UTC)
        for quota in quotas:
            if self._as_utc(quota.window_end) < now:
                continue
            key = (quota.provider_name, quota.capability)
            existing = quota_by_key.get(key)
            if existing is None or quota.window_end > existing.window_end:
                quota_by_key[key] = quota

        items: list[dict] = []
        for health_row in health_rows:
            quota_row = quota_by_key.get((health_row.provider_name, health_row.capability))
            items.append(
                {
                    "provider_name": health_row.provider_name,
                    "capability": health_row.capability,
                    "breaker_state": health_row.breaker_state,
                    "consecutive_failures": health_row.consecutive_failures,
                    "success_rate_1h": health_row.success_rate_1h,
                    "p95_latency_ms_1h": health_row.p95_latency_ms_1h,
                    "last_error_code": health_row.last_error_code,
                    "last_error_at": health_row.last_error_at.isoformat() if health_row.last_error_at else None,
                    "remaining_quota": quota_row.remaining_count if quota_row is not None else None,
                }
            )
        return items

    def _normalize_operation(self, operation: str) -> str:
        if operation in VALID_PROVIDER_OPERATIONS:
            return operation
        logger.warning("provider operation outside controlled vocabulary: %s", operation)
        return "unknown"

    def _as_utc(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
