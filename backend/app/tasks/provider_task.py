from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
import hashlib
from typing import Callable

from celery import Task
from sqlalchemy.orm import Session

import app.db.session as db_session_module
from app.providers.base import ProviderBase
from app.providers.errors import ProviderTimeoutError, classify_provider_error
from app.providers.execution_types import ProviderExecutionRequest, ProviderExecutionResult
from app.providers.retry import RetryExhaustedError, RetryPolicy
from app.services.provider_telemetry_service import ProviderTelemetryService


logger = logging.getLogger("lsos.provider.task")


class CeleryProviderTask(Task):
    abstract = True

    provider_name = "unknown"
    capability = "unknown"
    timeout_budget_seconds = 30.0
    retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=2.0, jitter_ratio=0.0)

    def __init__(self) -> None:
        super().__init__()
        self._idempotent_results: dict[str, ProviderExecutionResult] = {}

    def build_idempotency_key(self, request: ProviderExecutionRequest) -> str:
        public_payload = self._normalize_public_fields_only(request.payload)
        normalized = json.dumps(
            {
                "provider_name": self.provider_name,
                "operation": request.operation,
                "public_payload": public_payload,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"{self.provider_name}:{request.operation}:{digest}"

    def run_provider_call(
        self,
        *,
        provider: ProviderBase,
        request: ProviderExecutionRequest,
        dead_letter_hook: Callable[[dict], None] | None = None,
    ) -> ProviderExecutionResult:
        idempotency_key = self.build_idempotency_key(request)
        if idempotency_key in self._idempotent_results:
            result = self._idempotent_results[idempotency_key]
            self._log_event("provider.idempotent_hit", request=request, idempotency_key=idempotency_key, result=result)
            return result

        started_at = time.perf_counter()
        attempt_number = 0
        tenant_id = self._extract_tenant_id(request)
        sub_account_id = self._extract_sub_account_id(request)
        campaign_id = self._extract_campaign_id(request)
        capability = self._resolve_capability(provider=provider, request=request)
        provider_version = self._resolve_provider_version(provider)

        def _operation() -> ProviderExecutionResult:
            nonlocal attempt_number
            attempt_number += 1
            attempt_started_at = time.perf_counter()
            try:
                result = self._invoke_with_timeout(provider=provider, request=request, started_at=started_at)
                self._record_execution_metric(
                    tenant_id=tenant_id,
                    sub_account_id=sub_account_id,
                    campaign_id=campaign_id,
                    request=request,
                    idempotency_key=idempotency_key,
                    capability=capability,
                    provider_version=provider_version,
                    attempt_number=attempt_number,
                    duration_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                    outcome="success",
                    retryable=False,
                    reason_code=None,
                    error_severity=None,
                )
                return result
            except Exception as exc:
                provider_error = classify_provider_error(exc)
                self._record_execution_metric(
                    tenant_id=tenant_id,
                    sub_account_id=sub_account_id,
                    campaign_id=campaign_id,
                    request=request,
                    idempotency_key=idempotency_key,
                    capability=capability,
                    provider_version=provider_version,
                    attempt_number=attempt_number,
                    duration_ms=int((time.perf_counter() - attempt_started_at) * 1000),
                    outcome="retry" if provider_error.retryable and attempt_number < self.retry_policy.max_attempts else "failed",
                    retryable=provider_error.retryable,
                    reason_code=provider_error.reason_code,
                    error_severity=provider_error.severity,
                )
                self._upsert_health_failure(
                    tenant_id=tenant_id,
                    provider=provider,
                    capability=capability,
                    provider_version=provider_version,
                    error_code=provider_error.error_code,
                )
                raise

        try:
            result = self.retry_policy.execute(
                _operation,
                classify_error=classify_provider_error,
            )
            self._idempotent_results[idempotency_key] = result
            self._upsert_health_success(
                tenant_id=tenant_id,
                provider=provider,
                capability=capability,
                provider_version=provider_version,
            )
            self._upsert_quota(
                tenant_id=tenant_id,
                provider=provider,
                capability=capability,
                result=result,
            )
            self._log_event("provider.execution_finished", request=request, idempotency_key=idempotency_key, result=result)
            return result
        except RetryExhaustedError as exhausted:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            failed_result = ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=exhausted.last_error,
            )
            self._idempotent_results[idempotency_key] = failed_result
            self._upsert_health_failure(
                tenant_id=tenant_id,
                provider=provider,
                capability=capability,
                provider_version=provider_version,
                error_code=exhausted.last_error.error_code,
            )
            self._log_event("provider.execution_failed", request=request, idempotency_key=idempotency_key, result=failed_result)
            if dead_letter_hook is not None:
                dead_letter_hook(self._dead_letter_payload(request=request, idempotency_key=idempotency_key, result=failed_result))
                self._record_execution_metric(
                    tenant_id=tenant_id,
                    sub_account_id=sub_account_id,
                    campaign_id=campaign_id,
                    request=request,
                    idempotency_key=idempotency_key,
                    capability=capability,
                    provider_version=provider_version,
                    attempt_number=attempt_number,
                    duration_ms=latency_ms,
                    outcome="dead_letter",
                    retryable=exhausted.last_error.retryable,
                    reason_code=exhausted.last_error.reason_code,
                    error_severity=exhausted.last_error.severity,
                )
            return failed_result
        except Exception as exc:  # noqa: BLE001
            provider_error = classify_provider_error(exc)
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            failed_result = ProviderExecutionResult(
                success=False,
                latency_ms=latency_ms,
                error=provider_error,
            )
            self._idempotent_results[idempotency_key] = failed_result
            self._upsert_health_failure(
                tenant_id=tenant_id,
                provider=provider,
                capability=capability,
                provider_version=provider_version,
                error_code=provider_error.error_code,
            )
            self._log_event("provider.execution_failed", request=request, idempotency_key=idempotency_key, result=failed_result)
            if dead_letter_hook is not None and provider_error.retryable:
                dead_letter_hook(self._dead_letter_payload(request=request, idempotency_key=idempotency_key, result=failed_result))
                self._record_execution_metric(
                    tenant_id=tenant_id,
                    sub_account_id=sub_account_id,
                    campaign_id=campaign_id,
                    request=request,
                    idempotency_key=idempotency_key,
                    capability=capability,
                    provider_version=provider_version,
                    attempt_number=attempt_number,
                    duration_ms=latency_ms,
                    outcome="dead_letter",
                    retryable=provider_error.retryable,
                    reason_code=provider_error.reason_code,
                    error_severity=provider_error.severity,
                )
            return failed_result

    def _invoke_with_timeout(self, *, provider: ProviderBase, request: ProviderExecutionRequest, started_at: float) -> ProviderExecutionResult:
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds > self.timeout_budget_seconds:
            raise ProviderTimeoutError("Task timeout budget exceeded before provider call.")
        result = provider.execute(request)
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds > self.timeout_budget_seconds:
            raise ProviderTimeoutError("Task timeout budget exceeded after provider call.")
        if not result.success and result.error is not None:
            raise result.error
        return result

    def _dead_letter_payload(
        self,
        *,
        request: ProviderExecutionRequest,
        idempotency_key: str,
        result: ProviderExecutionResult,
    ) -> dict:
        error = result.error
        return {
            "task_name": self.name,
            "provider_name": self.provider_name,
            "operation": request.operation,
            "idempotency_key": idempotency_key,
            "correlation_id": request.correlation_id,
            "reason_code": error.reason_code if error is not None else "unknown",
            "error_code": error.error_code if error is not None else "unknown",
            "error_message": str(error) if error is not None else "unknown",
            "retryable": error.retryable if error is not None else False,
            "latency_ms": result.latency_ms,
        }

    def _log_event(
        self,
        event: str,
        *,
        request: ProviderExecutionRequest,
        idempotency_key: str,
        result: ProviderExecutionResult,
    ) -> None:
        logger.info(
            json.dumps(
                {
                    "event": event,
                    "task_name": self.name,
                    "provider_name": self.provider_name,
                    "operation": request.operation,
                    "correlation_id": request.correlation_id,
                    "idempotency_key": idempotency_key,
                    "success": result.success,
                    "latency_ms": result.latency_ms,
                    "reason_code": result.error.reason_code if result.error is not None else None,
                }
            )
        )

    def _resolve_provider_version(self, provider: ProviderBase) -> str | None:
        version = getattr(provider, "provider_version", None)
        if isinstance(version, str):
            return version
        return None

    def _resolve_capability(self, *, provider: ProviderBase, request: ProviderExecutionRequest) -> str:
        provider_capability = getattr(provider, "capability", None)
        if isinstance(provider_capability, str) and provider_capability:
            return provider_capability
        if isinstance(self.capability, str) and self.capability and self.capability != "unknown":
            return self.capability
        return request.operation

    def _extract_tenant_id(self, request: ProviderExecutionRequest) -> str:
        tenant_id = request.payload.get("tenant_id")
        if isinstance(tenant_id, str) and tenant_id:
            return tenant_id
        return "system"

    def _extract_sub_account_id(self, request: ProviderExecutionRequest) -> str | None:
        sub_account_id = request.payload.get("sub_account_id")
        if isinstance(sub_account_id, str) and sub_account_id:
            return sub_account_id
        return None

    def _extract_campaign_id(self, request: ProviderExecutionRequest) -> str | None:
        campaign_id = request.payload.get("campaign_id")
        if isinstance(campaign_id, str) and campaign_id:
            return campaign_id
        return None

    def _record_execution_metric(
        self,
        *,
        tenant_id: str,
        sub_account_id: str | None,
        campaign_id: str | None,
        request: ProviderExecutionRequest,
        idempotency_key: str,
        capability: str,
        provider_version: str | None,
        attempt_number: int,
        duration_ms: int,
        outcome: str,
        retryable: bool,
        reason_code: str | None,
        error_severity: str | None,
    ) -> None:
        self._with_telemetry_service(
            lambda telemetry: telemetry.record_execution_metric(
                tenant_id=tenant_id,
                sub_account_id=sub_account_id,
                campaign_id=campaign_id,
                provider_name=self.provider_name,
                provider_version=provider_version,
                capability=capability,
                operation=request.operation,
                idempotency_key=idempotency_key,
                correlation_id=request.correlation_id,
                attempt_number=attempt_number,
                max_attempts=self.retry_policy.max_attempts,
                duration_ms=duration_ms,
                timeout_budget_ms=int(self.timeout_budget_seconds * 1000),
                outcome=outcome,
                reason_code=reason_code,
                error_severity=error_severity,
                retryable=retryable,
            )
        )

    def _upsert_health_failure(
        self,
        *,
        tenant_id: str,
        provider: ProviderBase,
        capability: str,
        provider_version: str | None,
        error_code: str | None,
    ) -> None:
        breaker_state = "open"
        consecutive_failures = 1
        health_snapshot = getattr(provider, "health", None)
        if callable(health_snapshot):
            try:
                snapshot = health_snapshot()
                breaker_state = snapshot.state
                consecutive_failures = snapshot.consecutive_failures
            except Exception:  # noqa: BLE001
                pass
        self._with_telemetry_service(
            lambda telemetry: telemetry.upsert_health_state(
                tenant_id=tenant_id,
                provider_name=self.provider_name,
                provider_version=provider_version,
                capability=capability,
                breaker_state=breaker_state,
                consecutive_failures=consecutive_failures,
                last_error_code=error_code,
                last_error_at=time_to_utc_datetime(time.time()),
                last_success_at=None,
            )
        )

    def _upsert_health_success(
        self,
        *,
        tenant_id: str,
        provider: ProviderBase,
        capability: str,
        provider_version: str | None,
    ) -> None:
        breaker_state = "closed"
        health_snapshot = getattr(provider, "health", None)
        if callable(health_snapshot):
            try:
                snapshot = health_snapshot()
                breaker_state = snapshot.state
            except Exception:  # noqa: BLE001
                pass
        self._with_telemetry_service(
            lambda telemetry: telemetry.upsert_health_state(
                tenant_id=tenant_id,
                provider_name=self.provider_name,
                provider_version=provider_version,
                capability=capability,
                breaker_state=breaker_state,
                consecutive_failures=0,
                last_error_code=None,
                last_error_at=None,
                last_success_at=time_to_utc_datetime(time.time()),
            )
        )

    def _upsert_quota(
        self,
        *,
        tenant_id: str,
        provider: ProviderBase,
        capability: str,
        result: ProviderExecutionResult,
    ) -> None:
        quota_snapshot = result.quota_state
        if quota_snapshot is None:
            quota_fn = getattr(provider, "quota", None)
            if callable(quota_fn):
                try:
                    quota_snapshot = quota_fn()
                except Exception:  # noqa: BLE001
                    quota_snapshot = None
        if quota_snapshot is None:
            return
        now = time_to_utc_datetime(time.time())
        reset_at = now
        if quota_snapshot.reset_epoch_seconds is not None:
            reset_at = time_to_utc_datetime(quota_snapshot.reset_epoch_seconds)
        limit_count = max(0, int(quota_snapshot.limit))
        remaining_count = max(0, int(quota_snapshot.remaining))
        used_count = max(0, limit_count - remaining_count)
        last_exhausted_at = now if remaining_count == 0 else None
        self._with_telemetry_service(
            lambda telemetry: telemetry.upsert_quota_state(
                tenant_id=tenant_id,
                provider_name=self.provider_name,
                capability=capability,
                window_start=now,
                window_end=reset_at,
                limit_count=limit_count,
                used_count=used_count,
                remaining_count=remaining_count,
                last_exhausted_at=last_exhausted_at,
            )
        )

    def _with_telemetry_service(self, callback: Callable[[ProviderTelemetryService], None]) -> None:
        db: Session | None = None
        try:
            db = db_session_module.SessionLocal()
            telemetry = ProviderTelemetryService(db)
            callback(telemetry)
        except Exception:  # noqa: BLE001
            logger.warning("provider telemetry callback failed", exc_info=True)
        finally:
            if db is not None:
                db.close()

    def _normalize_public_fields_only(self, payload: dict) -> dict:
        normalized: dict = {}
        for key, value in payload.items():
            if self._is_sensitive_key(str(key)):
                continue
            normalized[str(key)] = self._sanitize_value(value)
        return normalized

    def _sanitize_value(self, value):
        if isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in sorted(value.items()) if not self._is_sensitive_key(str(k))}
        if isinstance(value, list):
            return [self._sanitize_value(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self._sanitize_value(v) for v in value)
        return value

    def _is_sensitive_key(self, key: str) -> bool:
        lower = key.lower()
        sensitive_markers = (
            "credential",
            "secret",
            "token",
            "authorization",
            "auth_header",
            "auth_token",
            "password",
            "api_key",
            "private_key",
        )
        return any(marker in lower for marker in sensitive_markers)


def time_to_utc_datetime(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)
