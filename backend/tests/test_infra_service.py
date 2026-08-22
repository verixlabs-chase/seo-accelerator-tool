from types import SimpleNamespace

from app.services import infra_service
from app.services.rate_limit_store import RateLimitDecision


class _FakeRedis:
    def __init__(self, *, exists_value: int = 1, ttl_value: int = 60, ping_value: bool = True, raises: bool = False):
        self._exists_value = exists_value
        self._ttl_value = ttl_value
        self._ping_value = ping_value
        self._raises = raises

    def ping(self) -> bool:
        if self._raises:
            raise RuntimeError("redis down")
        return self._ping_value

    def exists(self, _key: str) -> int:
        if self._raises:
            raise RuntimeError("redis down")
        return self._exists_value

    def ttl(self, _key: str) -> int:
        if self._raises:
            raise RuntimeError("redis down")
        return self._ttl_value


def test_worker_active_true_when_heartbeat_exists_and_ttl_positive(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=1, ttl_value=60),
    )
    assert infra_service.worker_active() is True


def test_worker_active_false_when_heartbeat_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=0, ttl_value=60),
    )
    assert infra_service.worker_active() is False


def test_worker_active_false_when_ttl_non_positive(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=1, ttl_value=0),
    )
    assert infra_service.worker_active() is False


def test_redis_connected_false_on_redis_exception(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(raises=True),
    )
    assert infra_service.redis_connected() is False


class _FakePostgresRateLimitStore:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.calls: list[dict[str, object]] = []

    def consume(self, *, scope_hash: str, policy_key: str, limit: int):
        self.calls.append(
            {"scope_hash": scope_hash, "policy_key": policy_key, "limit": limit}
        )
        if self.raises:
            raise RuntimeError("database probe failed")
        return RateLimitDecision(
            allowed=True,
            limit=limit,
            count=1,
            remaining=limit - 1,
            reset_at_epoch=2_000_000_000,
            retry_after_seconds=60,
        )


def test_postgres_rate_limit_probe_consumes_reserved_database_scope(monkeypatch):
    store = _FakePostgresRateLimitStore()
    monkeypatch.setattr(
        infra_service,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_backend="postgres",
            rate_limit_requests_per_minute=73,
        ),
    )
    monkeypatch.setattr(
        infra_service,
        "PostgresFixedWindowRateLimitStore",
        lambda: store,
    )

    assert infra_service.rate_limit_store_connected() is True
    assert store.calls == [
        {
            "scope_hash": "0" * 64,
            "policy_key": "readiness_probe_v1",
            "limit": 73,
        }
    ]


def test_postgres_rate_limit_probe_returns_false_on_store_failure(monkeypatch):
    store = _FakePostgresRateLimitStore(raises=True)
    monkeypatch.setattr(
        infra_service,
        "get_settings",
        lambda: SimpleNamespace(
            rate_limit_backend="postgres",
            rate_limit_requests_per_minute=60,
        ),
    )
    monkeypatch.setattr(
        infra_service,
        "PostgresFixedWindowRateLimitStore",
        lambda: store,
    )

    assert infra_service.rate_limit_store_connected() is False
    assert len(store.calls) == 1


def test_redis_rate_limit_probe_delegates_without_opening_postgres_store(monkeypatch):
    monkeypatch.setattr(
        infra_service,
        "get_settings",
        lambda: SimpleNamespace(rate_limit_backend="redis"),
    )
    monkeypatch.setattr(infra_service, "redis_connected", lambda: True)
    monkeypatch.setattr(
        infra_service,
        "PostgresFixedWindowRateLimitStore",
        lambda: (_ for _ in ()).throw(
            AssertionError("Redis limiter probe must not open the PostgreSQL store")
        ),
    )

    assert infra_service.rate_limit_store_connected() is True
