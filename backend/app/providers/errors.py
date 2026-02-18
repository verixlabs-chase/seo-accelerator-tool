from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ErrorClassification:
    error_code: str
    reason_code: str
    retryable: bool
    severity: str


class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        reason_code: str,
        retryable: bool,
        severity: str,
        upstream_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.reason_code = reason_code
        self.retryable = retryable
        self.severity = severity
        self.upstream_payload = upstream_payload


class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str = "Provider request timed out.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_timeout",
            reason_code="timeout",
            retryable=True,
            severity="error",
            upstream_payload=upstream_payload,
        )


class ProviderConnectionError(ProviderError):
    def __init__(self, message: str = "Provider connection failed.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_connection",
            reason_code="connection_error",
            retryable=True,
            severity="error",
            upstream_payload=upstream_payload,
        )


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str = "Provider rate-limited request.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_rate_limited",
            reason_code="rate_limited",
            retryable=True,
            severity="warning",
            upstream_payload=upstream_payload,
        )


class ProviderAuthError(ProviderError):
    def __init__(self, message: str = "Provider authentication failed.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_auth",
            reason_code="auth_failed",
            retryable=False,
            severity="critical",
            upstream_payload=upstream_payload,
        )


class ProviderQuotaExceededError(ProviderError):
    def __init__(self, message: str = "Provider quota exhausted.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_quota_exhausted",
            reason_code="quota_exhausted",
            retryable=False,
            severity="warning",
            upstream_payload=upstream_payload,
        )


class ProviderBadRequestError(ProviderError):
    def __init__(self, message: str = "Provider rejected request payload.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_bad_request",
            reason_code="bad_request",
            retryable=False,
            severity="error",
            upstream_payload=upstream_payload,
        )


class ProviderResponseFormatError(ProviderError):
    def __init__(self, message: str = "Provider response format is invalid.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_response_invalid",
            reason_code="response_invalid",
            retryable=False,
            severity="error",
            upstream_payload=upstream_payload,
        )


class ProviderDependencyError(ProviderError):
    def __init__(self, message: str = "Provider dependency unavailable.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_dependency_unavailable",
            reason_code="dependency_unavailable",
            retryable=True,
            severity="error",
            upstream_payload=upstream_payload,
        )


class ProviderInternalError(ProviderError):
    def __init__(self, message: str = "Provider internal error.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_internal_error",
            reason_code="internal_error",
            retryable=False,
            severity="critical",
            upstream_payload=upstream_payload,
        )


class ProviderCircuitOpenError(ProviderError):
    def __init__(self, message: str = "Provider circuit breaker is open.", *, upstream_payload: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            error_code="provider_circuit_open",
            reason_code="circuit_open",
            retryable=False,
            severity="warning",
            upstream_payload=upstream_payload,
        )


def classification_from_exception(exc: Exception) -> ErrorClassification:
    if isinstance(exc, ProviderError):
        return ErrorClassification(
            error_code=exc.error_code,
            reason_code=exc.reason_code,
            retryable=exc.retryable,
            severity=exc.severity,
        )
    if isinstance(exc, TimeoutError | httpx.TimeoutException):
        return ErrorClassification("provider_timeout", "timeout", True, "error")
    if isinstance(exc, ConnectionError | httpx.ConnectError):
        return ErrorClassification("provider_connection", "connection_error", True, "error")
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code if exc.response is not None else 0
        if status_code == 401 or status_code == 403:
            return ErrorClassification("provider_auth", "auth_failed", False, "critical")
        if status_code == 429:
            return ErrorClassification("provider_rate_limited", "rate_limited", True, "warning")
        if 400 <= status_code < 500:
            return ErrorClassification("provider_bad_request", "bad_request", False, "error")
        if status_code >= 500:
            return ErrorClassification("provider_dependency_unavailable", "dependency_unavailable", True, "error")
    if isinstance(exc, httpx.HTTPError):
        return ErrorClassification("provider_dependency_unavailable", "dependency_unavailable", True, "error")
    return ErrorClassification("provider_internal_error", "internal_error", False, "critical")


def classify_provider_error(exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    classification = classification_from_exception(exc)
    return ProviderError(
        str(exc) or classification.reason_code,
        error_code=classification.error_code,
        reason_code=classification.reason_code,
        retryable=classification.retryable,
        severity=classification.severity,
    )
