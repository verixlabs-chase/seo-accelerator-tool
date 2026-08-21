from __future__ import annotations

from collections.abc import Iterable

import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient

from app.core.middleware.rate_limit import RateLimitMiddleware
from app.services.rate_limit_store import RateLimitDecision, RateLimitStoreUnavailable


HMAC_SECRET = "test-rate-limit-hmac-secret-with-at-least-32-characters"


def _decision(
    *,
    allowed: bool = True,
    limit: int = 1,
    count: int = 1,
    remaining: int = 0,
    reset_at_epoch: int = 2_000_000_000,
    retry_after_seconds: int = 0,
) -> RateLimitDecision:
    return RateLimitDecision(
        allowed=allowed,
        limit=limit,
        count=count,
        remaining=remaining,
        reset_at_epoch=reset_at_epoch,
        retry_after_seconds=retry_after_seconds,
    )


class _FakeStore:
    def __init__(
        self,
        decisions: Iterable[RateLimitDecision] | None = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self._decisions = list(decisions or [_decision()])
        self._error = error
        self.calls: list[dict[str, object]] = []

    def consume(self, *, scope_hash: str, policy_key: str, limit: int) -> RateLimitDecision:
        self.calls.append(
            {
                "scope_hash": scope_hash,
                "policy_key": policy_key,
                "limit": limit,
            }
        )
        if self._error is not None:
            raise self._error
        index = min(len(self.calls) - 1, len(self._decisions) - 1)
        return self._decisions[index]


def _app(
    store: _FakeStore,
    *,
    enabled: bool = True,
    backend: str = "postgres",
    identity_source: str = "peer",
    cron_secret: str = "",
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=enabled,
        requests_per_minute=1,
        backend=backend,
        identity_source=identity_source,
        hmac_secret=HMAC_SECRET,
        redis_url="redis://unused.invalid:6379/0",
        cron_secret=cron_secret,
        store=store,
    )

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("downstream failure")

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/readiness")
    async def readiness() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/v1/health/readiness-extra")
    async def readiness_extra() -> dict[str, str]:
        return {"status": "not-exempt"}

    @app.options("/probe")
    async def probe_options() -> Response:
        return Response(status_code=204)

    @app.get("/api/v1/internal/jobs/drain")
    async def cron_drain() -> dict[str, str]:
        return {"status": "drained"}

    return app


async def _request(
    app: FastAPI,
    path: str,
    *,
    method: str = "GET",
    peer: str = "203.0.113.10",
    headers: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
):
    transport = ASGITransport(
        app=app,
        client=(peer, 12345),
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers)


@pytest.mark.anyio
async def test_disabled_middleware_never_calls_the_store() -> None:
    store = _FakeStore(error=AssertionError("disabled limiter called its store"))

    response = await _request(_app(store, enabled=False), "/probe")

    assert response.status_code == 200
    assert store.calls == []


@pytest.mark.anyio
async def test_limit_exceeded_uses_database_retry_metadata_and_never_exposes_identity() -> None:
    store = _FakeStore(
        [
            _decision(),
            _decision(
                allowed=False,
                count=2,
                remaining=0,
                reset_at_epoch=123,
                retry_after_seconds=17,
            ),
        ]
    )
    app = _app(store)

    allowed = await _request(app, "/probe")
    denied = await _request(
        app,
        "/probe?attempt=2",
        headers={"X-Forwarded-For": "198.51.100.99"},
    )

    assert allowed.status_code == 200
    assert denied.status_code == 429
    assert denied.json() == {
        "message": "Rate limit exceeded",
        "reason_code": "rate_limit_exceeded",
    }
    assert denied.headers["Retry-After"] == "17"
    assert "no-store" in denied.headers["Cache-Control"]
    assert denied.headers.get("X-RateLimit-Reset") in {None, "123"}
    serialized = f"{store.calls!r} {denied.text}"
    assert "203.0.113.10" not in serialized
    assert "198.51.100.99" not in serialized
    assert len(str(store.calls[0]["scope_hash"])) == 64
    assert store.calls[0]["scope_hash"] == store.calls[1]["scope_hash"]
    assert store.calls[0]["policy_key"] == store.calls[1]["policy_key"]


@pytest.mark.anyio
async def test_store_outage_fails_closed_as_503_without_quota_or_identity_leak(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = _FakeStore(error=RateLimitStoreUnavailable("database unavailable"))

    response = await _request(
        _app(store),
        "/probe",
        peer="203.0.113.44",
        headers={"Authorization": "Bearer must-not-leak"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "message": "Request protection is temporarily unavailable",
        "reason_code": "rate_limit_unavailable",
    }
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers
    captured = f"{response.text} {caplog.text}"
    assert "203.0.113.44" not in captured
    assert "must-not-leak" not in captured


@pytest.mark.anyio
async def test_liveness_and_options_exemptions_are_exact_and_readiness_is_limited() -> None:
    denied = _decision(
        allowed=False,
        count=2,
        retry_after_seconds=30,
    )
    store = _FakeStore([denied])
    app = _app(store)

    health = await _request(app, "/api/v1/health")
    readiness = await _request(app, "/api/v1/health/readiness")
    options = await _request(app, "/probe", method="OPTIONS")
    near_match = await _request(app, "/api/v1/health/readiness-extra")
    unknown = await _request(app, "/not-a-real-route")

    assert health.status_code == 200
    assert readiness.status_code == 429
    assert options.status_code == 204
    assert near_match.status_code == 429
    assert unknown.status_code == 429
    assert len(store.calls) == 3


@pytest.mark.anyio
async def test_only_exact_get_with_valid_cron_secret_bypasses_rate_limit() -> None:
    denied = _decision(
        allowed=False,
        count=2,
        retry_after_seconds=30,
    )
    store = _FakeStore([denied])
    app = _app(store, cron_secret="test-cron-secret")

    valid = await _request(
        app,
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert valid.status_code == 200
    assert store.calls == []

    invalid = await _request(
        app,
        "/api/v1/internal/jobs/drain",
        headers={"Authorization": "Bearer wrong"},
    )
    wrong_method = await _request(
        app,
        "/api/v1/internal/jobs/drain",
        method="POST",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    near_match = await _request(
        app,
        "/api/v1/internal/jobs/drain-extra",
        headers={"Authorization": "Bearer test-cron-secret"},
    )

    assert invalid.status_code == 429
    assert wrong_method.status_code == 429
    assert near_match.status_code == 429
    assert len(store.calls) == 3


@pytest.mark.anyio
async def test_peer_identity_ignores_forwarded_headers_and_canonicalizes_ip_addresses() -> None:
    store = _FakeStore([_decision()])
    app = _app(store, identity_source="peer")

    await _request(
        app,
        "/probe",
        peer="203.0.113.9",
        headers={"X-Forwarded-For": "198.51.100.1, 198.51.100.2"},
    )
    ipv4_hash = store.calls[-1]["scope_hash"]
    await _request(app, "/probe", peer="::ffff:203.0.113.9")
    mapped_hash = store.calls[-1]["scope_hash"]
    await _request(app, "/probe", peer="2001:db8:1234:5678::1")
    ipv6_a_hash = store.calls[-1]["scope_hash"]
    await _request(app, "/probe", peer="2001:db8:1234:5678:ffff::2")
    ipv6_b_hash = store.calls[-1]["scope_hash"]
    await _request(app, "/probe", peer="2001:db8:1234:5679::1")
    ipv6_other_network_hash = store.calls[-1]["scope_hash"]

    assert ipv4_hash == mapped_hash
    assert ipv6_a_hash == ipv6_b_hash
    assert ipv6_a_hash != ipv6_other_network_hash


@pytest.mark.anyio
async def test_vercel_identity_requires_one_valid_exact_forwarded_address() -> None:
    store = _FakeStore([_decision()])
    app = _app(store, identity_source="vercel")

    valid = await _request(
        app,
        "/probe",
        headers={"X-Vercel-Forwarded-For": "203.0.113.80"},
    )
    valid_hash = store.calls[-1]["scope_hash"]
    mapped = await _request(
        app,
        "/probe",
        headers={"X-Vercel-Forwarded-For": "::ffff:203.0.113.80"},
    )
    mapped_hash = store.calls[-1]["scope_hash"]
    calls_after_valid = len(store.calls)

    missing = await _request(app, "/probe")
    comma_list = await _request(
        app,
        "/probe",
        headers={"X-Vercel-Forwarded-For": "203.0.113.80, 198.51.100.1"},
    )
    malformed = await _request(
        app,
        "/probe",
        headers={"X-Vercel-Forwarded-For": "not-an-ip"},
    )

    assert valid.status_code == 200
    assert mapped.status_code == 200
    assert valid_hash == mapped_hash
    for response in (missing, comma_list, malformed):
        assert response.status_code == 503
        assert response.json() == {
            "message": "Request protection is temporarily unavailable",
            "reason_code": "rate_limit_unavailable",
        }
        assert response.headers["Retry-After"] == "5"
        assert response.headers["Cache-Control"] == "private, no-store"
    assert len(store.calls) == calls_after_valid


@pytest.mark.anyio
async def test_downstream_failure_still_consumes_the_request() -> None:
    store = _FakeStore([_decision()])

    response = await _request(
        _app(store),
        "/boom",
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    assert len(store.calls) == 1
