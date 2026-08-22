from __future__ import annotations

from threading import Event
import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middleware.rate_limit import RateLimitMiddleware
from app.services.rate_limit_store import RateLimitDecision


HMAC_SECRET = "test-rate-limit-hmac-secret-with-at-least-32-characters"


class _BlockingStore:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.finished = Event()

    def consume(
        self,
        *,
        scope_hash: str,
        policy_key: str,
        limit: int,
    ) -> RateLimitDecision:
        self.started.set()
        self.release.wait(timeout=1)
        self.finished.set()
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            count=1,
            remaining=max(0, limit - 1),
            reset_at_epoch=2_000_000_000,
            retry_after_seconds=1,
        )


def _app(store: _BlockingStore, *, timeout_seconds: float) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        requests_per_minute=10,
        backend="postgres",
        identity_source="peer",
        hmac_secret=HMAC_SECRET,
        redis_url="redis://unused.invalid:6379/0",
        admission_timeout_seconds=timeout_seconds,
        store=store,
    )

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.mark.anyio
async def test_slow_store_fails_closed_before_the_request_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log_events: list[tuple[str, dict[str, object]]] = []

    def _capture_warning(message: str, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        log_events.append((message, dict(kwargs.get("extra", {}))))

    monkeypatch.setattr(
        "app.core.middleware.rate_limit.logger.warning",
        _capture_warning,
    )
    store = _BlockingStore()
    transport = ASGITransport(app=_app(store, timeout_seconds=0.05))
    started_at = time.monotonic()

    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/probe")
    finally:
        store.release.set()

    elapsed = time.monotonic() - started_at
    assert store.started.is_set()
    assert store.finished.wait(timeout=1)
    assert elapsed < 0.5
    assert response.status_code == 503
    assert response.json() == {
        "message": "Request protection is temporarily unavailable",
        "reason_code": "rate_limit_unavailable",
    }
    assert response.headers["Retry-After"] == "5"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert log_events == [
        (
            "rate_limit_store_timeout",
            {
                "event": "rate_limit_store_timeout",
                "identity_source": "peer",
                "timeout_seconds": 0.05,
                "correlation_id": None,
            },
        )
    ]
    assert "127.0.0.1" not in f"{log_events!r} {response.text}"


@pytest.mark.parametrize(
    "timeout_seconds",
    [0, 0.049, 30.001, float("inf"), float("nan")],
)
@pytest.mark.anyio
async def test_invalid_admission_timeout_is_rejected(
    timeout_seconds: float,
) -> None:
    store = _BlockingStore()
    transport = ASGITransport(app=_app(store, timeout_seconds=timeout_seconds))

    with pytest.raises(
        ValueError,
        match="admission_timeout_seconds must be between 0.05 and 30 seconds",
    ):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.get("/probe")
