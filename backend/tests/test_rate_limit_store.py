from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from app.services import rate_limit_store
from app.services.rate_limit_store import (
    PostgresFixedWindowRateLimitStore,
    RateLimitStoreUnavailable,
    RedisFixedWindowRateLimitStore,
)


class _RegisteredScript:
    def __init__(self, result: object = None, *, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    def __call__(self, *, keys: list[str], args: list[int]) -> object:
        self.calls.append({"keys": keys, "args": args})
        if self.error is not None:
            raise self.error
        return self.result


class _RedisClient:
    def __init__(self, registered_script: _RegisteredScript) -> None:
        self.registered_script = registered_script
        self.script_source = ""

    def register_script(self, source: str) -> _RegisteredScript:
        self.script_source = source
        return self.registered_script


def _store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: object = None,
    error: BaseException | None = None,
) -> tuple[RedisFixedWindowRateLimitStore, _RedisClient, _RegisteredScript]:
    script = _RegisteredScript(result, error=error)
    client = _RedisClient(script)
    from_url_calls: list[tuple[str, dict[str, Any]]] = []

    def _from_url(url: str, **kwargs: Any) -> _RedisClient:
        from_url_calls.append((url, kwargs))
        return client

    monkeypatch.setattr(rate_limit_store.redis.Redis, "from_url", _from_url)
    store = RedisFixedWindowRateLimitStore("redis://redis.example/0")
    assert from_url_calls == [
        (
            "redis://redis.example/0",
            {
                "socket_connect_timeout": 0.5,
                "socket_timeout": 0.5,
                "retry_on_timeout": False,
            },
        )
    ]
    return store, client, script


def test_redis_decision_preserves_store_returned_future_window(monkeypatch) -> None:
    now_epoch = 1_999_999_980
    future_window = now_epoch + 120
    store, client, script = _store(
        monkeypatch,
        result=[4, future_window, now_epoch],
    )

    decision = store.consume(
        scope_hash="a" * 64,
        policy_key="global-per-minute",
        limit=3,
    )

    assert decision.allowed is False
    assert decision.limit == 3
    assert decision.count == 4
    assert decision.remaining == 0
    assert decision.reset_at_epoch == future_window + 60
    assert decision.retry_after_seconds == 180
    assert script.calls == [
        {
            "keys": [f"request_rate_limit:v1:global-per-minute:{'a' * 64}"],
            "args": [3],
        }
    ]
    assert client.script_source == rate_limit_store._REDIS_FIXED_WINDOW_SCRIPT


def test_redis_lua_contract_does_not_roll_back_or_rewrite_saturated_bucket(
    monkeypatch,
) -> None:
    _store(monkeypatch, result=[4, 2_000_000_000, 2_000_000_001])
    script = " ".join(rate_limit_store._REDIS_FIXED_WINDOW_SCRIPT.split())

    # Only an older stored window is reset; an equal or future window stays intact.
    assert "stored_window < window_started_at" in script
    assert "or stored_window > window_started_at" not in script
    # Equality with limit + 1 enters neither branch, leaving should_write false.
    assert "if request_count < capped_count then" in script
    assert "elseif request_count > capped_count then" in script
    assert "if should_write then redis.call( 'HSET'" in script
    # A future bucket refreshes only its TTL when needed; it never rewrites the
    # saturated counter or expires before the preserved reset boundary.
    assert "elseif stored_window > window_started_at then" in script
    assert "if current_ttl < expiry_seconds then" in script


def test_redis_script_outage_is_reported_as_typed_store_unavailability(monkeypatch) -> None:
    store, _client, script = _store(
        monkeypatch,
        error=RedisError("redis unavailable"),
    )

    with pytest.raises(RateLimitStoreUnavailable, match="Redis rate-limit store is unavailable"):
        store.consume(
            scope_hash="b" * 64,
            policy_key="global-per-minute",
            limit=60,
        )

    assert len(script.calls) == 1


def _capture_postgres_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hosted_serverless: bool,
) -> tuple[object, object, dict[str, object]]:
    engine_marker = object()
    session_factory_marker = object()
    engine_calls: list[tuple[object, dict[str, object]]] = []
    sessionmaker_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        rate_limit_store,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_dsn="postgresql://user:pass@host:5432/app",
            hosted_serverless=hosted_serverless,
            db_pool_timeout_seconds=99,
        ),
    )

    def _create_engine(database_url: object, **kwargs: object) -> object:
        engine_calls.append((database_url, kwargs))
        return engine_marker

    def _sessionmaker(**kwargs: object) -> object:
        sessionmaker_calls.append(kwargs)
        return session_factory_marker

    monkeypatch.setattr(rate_limit_store, "create_engine", _create_engine)
    monkeypatch.setattr(rate_limit_store, "sessionmaker", _sessionmaker)
    rate_limit_store._cached_rate_limit_session_factory.cache_clear()
    try:
        factory = rate_limit_store._rate_limit_session_factory(1_750, 400)
    finally:
        rate_limit_store._cached_rate_limit_session_factory.cache_clear()

    assert factory is session_factory_marker
    assert len(engine_calls) == 1
    assert sessionmaker_calls == [
        {"bind": engine_marker, "autocommit": False, "autoflush": False}
    ]
    database_url, engine_kwargs = engine_calls[0]
    return factory, database_url, engine_kwargs


def test_persistent_postgres_factory_normalizes_plain_dsn_and_uses_bounded_queue_pool(
    monkeypatch,
) -> None:
    factory, database_url, engine_kwargs = (
        _capture_postgres_session_factory(
            monkeypatch,
            hosted_serverless=False,
        )
    )

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.render_as_string(hide_password=False) == (
        "postgresql+psycopg://user:pass@host:5432/app"
    )
    assert engine_kwargs == {
        "pool_pre_ping": False,
        "pool_size": 2,
        "max_overflow": 3,
        "pool_timeout": 1.75,
        "pool_recycle": 60,
        "pool_use_lifo": True,
        "connect_args": {
            "connect_timeout": 2,
            "tcp_user_timeout": 2_000,
            "prepare_threshold": None,
        },
    }
    assert "options" not in engine_kwargs["connect_args"]
    assert factory is not None


def test_hosted_postgres_factory_uses_null_pool_without_startup_options(
    monkeypatch,
) -> None:
    _factory, database_url, engine_kwargs = (
        _capture_postgres_session_factory(
            monkeypatch,
            hosted_serverless=True,
        )
    )

    assert database_url.drivername == "postgresql+psycopg"
    assert database_url.render_as_string(hide_password=False) == (
        "postgresql+psycopg://user:pass@host:5432/app"
    )
    assert engine_kwargs == {
        "pool_pre_ping": False,
        "poolclass": rate_limit_store.NullPool,
        "connect_args": {
            "connect_timeout": 2,
            "tcp_user_timeout": 2_000,
            "prepare_threshold": None,
        },
    }
    assert "options" not in engine_kwargs["connect_args"]


class _TransactionContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> bool:
        return False


class _PostgresResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self._row = row

    def mappings(self) -> _PostgresResult:
        return self

    def one(self) -> dict[str, object]:
        assert self._row is not None
        return self._row


class _PostgresSession:
    def __init__(
        self,
        *,
        consume_error: BaseException | None = None,
        row: dict[str, object] | None = None,
    ) -> None:
        self.consume_error = consume_error
        self.row = row
        self.closed = False
        self.executed: list[object] = []

    def begin(self) -> _TransactionContext:
        return _TransactionContext()

    def execute(self, statement: object, _params: object = None) -> _PostgresResult:
        self.executed.append(statement)
        if statement is rate_limit_store._CONSUME_SQL:
            if self.consume_error is not None:
                raise self.consume_error
            return _PostgresResult(self.row)
        return _PostgresResult()

    def close(self) -> None:
        self.closed = True


class _PostgresDriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _operational_error(sqlstate: str) -> OperationalError:
    return OperationalError(
        "SELECT public.consume_request_rate_limit(...) ",
        {},
        _PostgresDriverError(sqlstate),
    )


@pytest.mark.parametrize("sqlstate", ["40001", "40P01", "55P03"])
def test_postgres_store_retries_only_rolled_back_transaction_contention(
    monkeypatch: pytest.MonkeyPatch,
    sqlstate: str,
) -> None:
    reset_at = datetime.now(UTC) + timedelta(seconds=30)
    first = _PostgresSession(consume_error=_operational_error(sqlstate))
    second = _PostgresSession(
        row={
            "allowed": True,
            "request_count": 1,
            "remaining": 2,
            "window_started_at": reset_at - timedelta(minutes=1),
            "reset_at": reset_at,
            "retry_after_seconds": 30,
        }
    )
    sessions = iter([first, second])
    sleeps: list[float] = []
    monkeypatch.setattr(rate_limit_store.time, "sleep", sleeps.append)
    store = PostgresFixedWindowRateLimitStore(session_factory=lambda: next(sessions))

    decision = store.consume(
        scope_hash="a" * 64,
        policy_key="global-per-minute",
        limit=3,
    )

    assert decision.allowed is True
    assert decision.count == 1
    assert decision.remaining == 2
    assert first.closed is True
    assert second.closed is True
    assert sleeps == [0.025]


def test_postgres_store_does_not_retry_ambiguous_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _PostgresSession(consume_error=_operational_error("08006"))
    factory_calls = 0

    def session_factory() -> _PostgresSession:
        nonlocal factory_calls
        factory_calls += 1
        return session

    sleeps: list[float] = []
    monkeypatch.setattr(rate_limit_store.time, "sleep", sleeps.append)
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)

    with pytest.raises(
        RateLimitStoreUnavailable,
        match="PostgreSQL rate-limit store is unavailable",
    ):
        store.consume(
            scope_hash="b" * 64,
            policy_key="global-per-minute",
            limit=3,
        )

    assert factory_calls == 1
    assert session.closed is True
    assert sleeps == []
