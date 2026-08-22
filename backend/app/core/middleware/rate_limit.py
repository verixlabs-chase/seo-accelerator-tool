from __future__ import annotations

import asyncio
from functools import partial
import hashlib
import hmac
import ipaddress
import logging
import math
from typing import Protocol

from anyio import to_thread
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.rate_limit_store import (
    PostgresFixedWindowRateLimitStore,
    RateLimitDecision,
    RateLimitStoreUnavailable,
    RedisFixedWindowRateLimitStore,
)


_POLICY_KEY = "coarse_network_ip_v1"
_LIVENESS_PATH = "/api/v1/health"
_CRON_DRAIN_PATH = "/api/v1/internal/jobs/drain"
_DEFAULT_ADMISSION_TIMEOUT_SECONDS = 5.0
logger = logging.getLogger("lsos.api.rate_limit")


class _RateLimitStore(Protocol):
    def consume(
        self,
        *,
        scope_hash: str,
        policy_key: str,
        limit: int,
    ) -> RateLimitDecision: ...


class _IdentityUnavailable(ValueError):
    pass


def _canonical_ip(raw_value: str) -> str:
    value = raw_value.strip()
    if not value or "," in value:
        raise _IdentityUnavailable("request identity is missing or ambiguous")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise _IdentityUnavailable("request identity is not a valid IP address") from exc

    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return address.ipv4_mapped.compressed
        network = ipaddress.ip_network(f"{address.compressed}/64", strict=False)
        return f"{network.network_address.compressed}/64"
    return address.compressed


def _request_identity(request: Request, *, identity_source: str) -> str:
    if identity_source == "vercel":
        forwarded_values = request.headers.getlist("x-vercel-forwarded-for")
        if len(forwarded_values) != 1:
            raise _IdentityUnavailable(
                "request identity is missing or has duplicate forwarding fields"
            )
        return _canonical_ip(forwarded_values[0])
    peer = request.client.host if request.client is not None else ""
    return _canonical_ip(peer or "")


def _scope_hash(*, secret: str, canonical_identity: str) -> str:
    payload = f"insightos|api-rate-limit|v1|{_POLICY_KEY}|ip|{canonical_identity}"
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _quota_headers(decision: RateLimitDecision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(max(0, decision.remaining)),
        "X-RateLimit-Reset": str(max(0, int(decision.reset_at_epoch))),
    }


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        enabled: bool,
        requests_per_minute: int,
        backend: str,
        identity_source: str,
        hmac_secret: str,
        redis_url: str,
        cron_secret: str = "",
        admission_timeout_seconds: float = _DEFAULT_ADMISSION_TIMEOUT_SECONDS,
        store: _RateLimitStore | None = None,
    ) -> None:
        super().__init__(app)
        self._enabled = bool(enabled)
        self._requests_per_minute = max(1, int(requests_per_minute))
        self._identity_source = identity_source.strip().lower()
        self._hmac_secret = hmac_secret
        self._cron_secret = cron_secret.strip()
        normalized_admission_timeout = float(admission_timeout_seconds)
        if (
            not math.isfinite(normalized_admission_timeout)
            or not 0.05 <= normalized_admission_timeout <= 30.0
        ):
            raise ValueError(
                "admission_timeout_seconds must be between 0.05 and 30 seconds"
            )
        self._admission_timeout_seconds = normalized_admission_timeout
        self._store: _RateLimitStore | None = store
        if self._enabled and self._store is None:
            normalized_backend = backend.strip().lower()
            if normalized_backend == "postgres":
                self._store = PostgresFixedWindowRateLimitStore()
            elif normalized_backend == "redis":
                self._store = RedisFixedWindowRateLimitStore(redis_url=redis_url)
            else:
                raise ValueError("Unsupported rate-limit backend")

    def _is_exempt(self, request: Request) -> bool:
        if request.method.upper() == "OPTIONS":
            return True
        method = request.method.upper()
        if method in {"GET", "HEAD"} and request.url.path == _LIVENESS_PATH:
            return True
        if (
            method == "GET"
            and request.url.path == _CRON_DRAIN_PATH
            and self._cron_secret
        ):
            supplied = request.headers.get("Authorization", "").encode("utf-8")
            expected = f"Bearer {self._cron_secret}".encode("utf-8")
            return hmac.compare_digest(supplied, expected)
        return False

    async def dispatch(self, request: Request, call_next):
        if not self._enabled or self._is_exempt(request):
            return await call_next(request)

        try:
            canonical_identity = _request_identity(
                request,
                identity_source=self._identity_source,
            )
            hashed_identity = _scope_hash(
                secret=self._hmac_secret,
                canonical_identity=canonical_identity,
            )
        except _IdentityUnavailable as exc:
            logger.warning(
                "rate_limit_identity_unavailable",
                extra={
                    "event": "rate_limit_identity_unavailable",
                    "identity_source": self._identity_source,
                    "exception_type": exc.__class__.__name__,
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
            )
            return self._unavailable_response()

        try:
            if self._store is None:
                raise RateLimitStoreUnavailable("rate-limit store is not configured")
            consume = partial(
                self._store.consume,
                scope_hash=hashed_identity,
                policy_key=_POLICY_KEY,
                limit=self._requests_per_minute,
            )
            decision = await asyncio.wait_for(
                to_thread.run_sync(consume, abandon_on_cancel=True),
                timeout=self._admission_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "rate_limit_store_timeout",
                extra={
                    "event": "rate_limit_store_timeout",
                    "identity_source": self._identity_source,
                    "timeout_seconds": self._admission_timeout_seconds,
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
            )
            return self._unavailable_response()
        except Exception as exc:
            logger.warning(
                "rate_limit_store_unavailable",
                extra={
                    "event": "rate_limit_store_unavailable",
                    "backend_error_type": exc.__class__.__name__,
                    "identity_source": self._identity_source,
                    "correlation_id": getattr(request.state, "correlation_id", None),
                },
            )
            return self._unavailable_response()

        if not decision.allowed:
            headers = {
                **_quota_headers(decision),
                "Retry-After": str(max(1, int(decision.retry_after_seconds))),
                "Cache-Control": "private, no-store",
            }
            return JSONResponse(
                status_code=429,
                content={
                    "message": "Rate limit exceeded",
                    "reason_code": "rate_limit_exceeded",
                },
                headers=headers,
            )

        response = await call_next(request)
        for header, value in _quota_headers(decision).items():
            response.headers[header] = value
        return response

    @staticmethod
    def _unavailable_response() -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "message": "Request protection is temporarily unavailable",
                "reason_code": "rate_limit_unavailable",
            },
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )
