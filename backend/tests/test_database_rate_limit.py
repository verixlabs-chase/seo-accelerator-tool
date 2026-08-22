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


class _StatefulFakeStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._counts: dict[tuple[str, str], int] = {}

    def consume(self, *, scope_hash: str, policy_key: str, limit: int) -> RateLimitDecision:
        self.calls.append(
            {
                "scope_hash": scope_hash,
                "policy_key": policy_key,
                "limit": limit,
            }
        )
        bucket = (scope_hash, policy_key)
        count = min(self._counts.get(bucket, 0) + 1, limit + 1)
        self._counts[bucket] = count
        return _decision(
            allowed=count <= limit,
            limit=limit,
            count=count,
            remaining=max(0, limit - count),
            reset_at_epoch=2_000_000_000,
            retry_after_seconds=19,
        )


def _app(
    store: _FakeStore | _StatefulFakeStore,
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
    headers: dict[str, str] | list[tuple[str, str]] | None = None,
    raise_app_exceptions: bool = True,
):
    transport = ASGITransport(
        app=app,
        client=(peer, 12345),
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers)


def _assert_quota_headers(
    response,
    *,
    limit: int,
    remaining: int,
    reset_at_epoch: int,
) -> None:
    assert response.headers["X-RateLimit-Limit"] == str(limit)
    assert response.headers["X-RateLimit-Remaining"] == str(remaining)
    assert response.headers["X-RateLimit-Reset"] == str(reset_at_epoch)


def _assert_no_quota_headers(response) -> None:
    assert "X-RateLimit-Limit" not in response.headers
    assert "X-RateLimit-Remaining" not in response.headers
    assert "X-RateLimit-Reset" not in response.headers


def _assert_unavailable_response(response) -> None:
    assert response.status_code == 503
    assert response.json() == {
        "message": "Request protection is temporarily unavailable",
        "reason_code": "rate_limit_unavailable",
    }
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "private, no-store"
    _assert_no_quota_headers(response)


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
    _assert_quota_headers(
        allowed,
        limit=1,
        remaining=0,
        reset_at_epoch=2_000_000_000,
    )
    assert denied.status_code == 429
    assert denied.json() == {
        "message": "Rate limit exceeded",
        "reason_code": "rate_limit_exceeded",
    }
    assert denied.headers["Retry-After"] == "17"
    assert denied.headers["Cache-Control"] == "private, no-store"
    _assert_quota_headers(
        denied,
        limit=1,
        remaining=0,
        reset_at_epoch=123,
    )
    serialized = f"{store.calls!r} {denied.text}"
    assert "203.0.113.10" not in serialized
    assert "198.51.100.99" not in serialized
    assert len(str(store.calls[0]["scope_hash"])) == 64
    assert store.calls[0]["scope_hash"] == store.calls[1]["scope_hash"]
    assert store.calls[0]["policy_key"] == store.calls[1]["policy_key"]
    denied_output = f"{denied.text} {dict(denied.headers)!r}"
    assert str(store.calls[1]["scope_hash"]) not in denied_output


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("identity_source", "peer", "headers", "raw_identity"),
    [
        ("peer", "203.0.113.44", {"Authorization": "Bearer must-not-leak"}, "203.0.113.44"),
        (
            "vercel",
            "192.0.2.10",
            {
                "Authorization": "Bearer must-not-leak",
                "X-Vercel-Forwarded-For": "198.51.100.44",
            },
            "198.51.100.44",
        ),
    ],
)
async def test_store_outage_fails_closed_as_503_without_quota_or_identity_leak(
    caplog: pytest.LogCaptureFixture,
    identity_source: str,
    peer: str,
    headers: dict[str, str],
    raw_identity: str,
) -> None:
    store = _FakeStore(error=RateLimitStoreUnavailable("database unavailable"))

    response = await _request(
        _app(store, identity_source=identity_source),
        "/probe",
        peer=peer,
        headers=headers,
    )

    _assert_unavailable_response(response)
    assert len(store.calls) == 1
    captured = f"{response.text} {dict(response.headers)!r} {caplog.text}"
    assert raw_identity not in captured
    assert "must-not-leak" not in captured
    assert str(store.calls[0]["scope_hash"]) not in captured


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
    health_head = await _request(app, "/api/v1/health", method="HEAD")
    health_trailing_slash = await _request(app, "/api/v1/health/")
    readiness = await _request(app, "/api/v1/health/readiness")
    options = await _request(app, "/probe", method="OPTIONS")
    near_match = await _request(app, "/api/v1/health/readiness-extra")
    unknown = await _request(app, "/not-a-real-route")

    assert health.status_code == 200
    assert health_head.status_code == 405
    assert health_trailing_slash.status_code == 429
    assert readiness.status_code == 429
    assert options.status_code == 204
    assert near_match.status_code == 429
    assert unknown.status_code == 429
    _assert_no_quota_headers(health)
    _assert_no_quota_headers(health_head)
    _assert_no_quota_headers(options)
    assert len(store.calls) == 4


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
async def test_peer_identity_cannot_reset_its_bucket_with_forwarding_headers() -> None:
    store = _StatefulFakeStore()
    app = _app(store, identity_source="peer")

    allowed = await _request(
        app,
        "/probe",
        peer="203.0.113.90",
        headers={
            "X-Forwarded-For": "198.51.100.10",
            "X-Real-IP": "198.51.100.11",
            "CF-Connecting-IP": "198.51.100.12",
        },
    )
    denied = await _request(
        app,
        "/probe",
        peer="203.0.113.90",
        headers={
            "X-Forwarded-For": "192.0.2.10",
            "X-Real-IP": "192.0.2.11",
            "CF-Connecting-IP": "192.0.2.12",
        },
    )

    assert allowed.status_code == 200
    assert denied.status_code == 429
    _assert_quota_headers(
        allowed,
        limit=1,
        remaining=0,
        reset_at_epoch=2_000_000_000,
    )
    _assert_quota_headers(
        denied,
        limit=1,
        remaining=0,
        reset_at_epoch=2_000_000_000,
    )
    assert store.calls[0]["scope_hash"] == store.calls[1]["scope_hash"]


@pytest.mark.anyio
async def test_vercel_identity_shares_a_bucket_across_proxy_peers_and_isolates_clients() -> None:
    store = _StatefulFakeStore()
    app = _app(store, identity_source="vercel")

    first = await _request(
        app,
        "/probe",
        peer="192.0.2.20",
        headers={"X-Vercel-Forwarded-For": "203.0.113.91"},
    )
    same_client_new_proxy = await _request(
        app,
        "/probe",
        peer="192.0.2.21",
        headers={"X-Vercel-Forwarded-For": "203.0.113.91"},
    )
    different_client_same_proxy = await _request(
        app,
        "/probe",
        peer="192.0.2.21",
        headers={"X-Vercel-Forwarded-For": "203.0.113.92"},
    )

    assert first.status_code == 200
    assert same_client_new_proxy.status_code == 429
    assert different_client_same_proxy.status_code == 200
    assert same_client_new_proxy.headers["Retry-After"] == "19"
    assert same_client_new_proxy.headers["Cache-Control"] == "private, no-store"
    _assert_quota_headers(
        same_client_new_proxy,
        limit=1,
        remaining=0,
        reset_at_epoch=2_000_000_000,
    )
    assert store.calls[0]["scope_hash"] == store.calls[1]["scope_hash"]
    assert store.calls[0]["scope_hash"] != store.calls[2]["scope_hash"]
    denied_output = (
        f"{same_client_new_proxy.text} "
        f"{dict(same_client_new_proxy.headers)!r}"
    )
    for sensitive_value in (
        "203.0.113.91",
        "192.0.2.21",
        str(store.calls[1]["scope_hash"]),
    ):
        assert sensitive_value not in denied_output


@pytest.mark.anyio
async def test_vercel_identity_requires_one_valid_exact_forwarded_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
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
        _assert_unavailable_response(response)
    unavailable_output = " ".join(
        [
            *(f"{response.text} {dict(response.headers)!r}" for response in (missing, comma_list, malformed)),
            caplog.text,
        ]
    )
    assert "203.0.113.80, 198.51.100.1" not in unavailable_output
    assert "not-an-ip" not in unavailable_output
    assert len(store.calls) == calls_after_valid


@pytest.mark.anyio
async def test_duplicate_vercel_forwarded_for_headers_fail_closed_without_store_call() -> None:
    store = _FakeStore([_decision()])
    app = _app(store, identity_source="vercel")

    response = await _request(
        app,
        "/probe",
        headers=[
            ("X-Vercel-Forwarded-For", "203.0.113.93"),
            ("X-Vercel-Forwarded-For", "198.51.100.93"),
        ],
    )

    _assert_unavailable_response(response)
    assert store.calls == []


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
