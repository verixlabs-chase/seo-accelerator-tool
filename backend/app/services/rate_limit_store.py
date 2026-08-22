from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Protocol

import redis
from redis.exceptions import RedisError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import _normalize_postgres_dsn


_MAX_REQUEST_LIMIT = 1_000_000
_DEFAULT_STATEMENT_TIMEOUT_MS = 750
_DEFAULT_LOCK_TIMEOUT_MS = 250
_SCOPE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_POLICY_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,63}$")

_SET_ROLE_SQL = text("SET LOCAL ROLE lsos_app")
_SET_TIMEOUTS_SQL = text(
    """
    SELECT
        set_config('statement_timeout', :statement_timeout, true),
        set_config('lock_timeout', :lock_timeout, true)
    """
)
_CONSUME_SQL = text(
    """
    SELECT
        allowed,
        request_count,
        remaining,
        window_started_at,
        reset_at,
        retry_after_seconds
    FROM public.consume_request_rate_limit(
        :scope_hash,
        :policy_key,
        :request_limit
    )
    """
)
_PRUNE_SQL = text(
    """
    SELECT public.prune_request_rate_limit_counters(
        :retention_seconds,
        :batch_size
    )
    """
)

_REDIS_FIXED_WINDOW_SCRIPT = """
local current_time = redis.call('TIME')
local now_epoch = tonumber(current_time[1])
local window_started_at = now_epoch - (now_epoch % 60)
local stored = redis.call('HMGET', KEYS[1], 'window_started_at', 'request_count')
local stored_window = tonumber(stored[1])
local request_count = tonumber(stored[2])
local request_limit = tonumber(ARGV[1])
local should_write = false
local expiry_seconds = 120

if stored_window == nil or request_count == nil or stored_window < window_started_at then
    request_count = 1
    stored_window = window_started_at
    should_write = true
else
    local capped_count = request_limit + 1
    expiry_seconds = math.max(120, (stored_window + 60) - now_epoch)
    if request_count < capped_count then
        request_count = request_count + 1
        should_write = true
    elseif request_count > capped_count then
        request_count = capped_count
        should_write = true
    end
end

if should_write then
    redis.call(
        'HSET',
        KEYS[1],
        'window_started_at',
        stored_window,
        'request_count',
        request_count
    )
    redis.call('EXPIRE', KEYS[1], expiry_seconds)
elseif stored_window > window_started_at then
    -- A backward clock jump must not let a future saturated bucket expire and
    -- hand out a second allowance. Refresh only when the anomalous TTL is short.
    local current_ttl = redis.call('TTL', KEYS[1])
    if current_ttl < expiry_seconds then
        redis.call('EXPIRE', KEYS[1], expiry_seconds)
    end
end

return {request_count, stored_window, now_epoch}
"""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    count: int
    remaining: int
    reset_at_epoch: int
    retry_after_seconds: int


class RateLimitStoreUnavailable(RuntimeError):
    """Raised when a configured distributed rate-limit store cannot decide."""


class RateLimitStore(Protocol):
    def consume(
        self,
        scope_hash: str,
        policy_key: str,
        limit: int,
    ) -> RateLimitDecision: ...


class PostgresFixedWindowRateLimitStore:
    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        *,
        statement_timeout_ms: int = _DEFAULT_STATEMENT_TIMEOUT_MS,
        lock_timeout_ms: int = _DEFAULT_LOCK_TIMEOUT_MS,
    ) -> None:
        if not 1 <= int(statement_timeout_ms) <= 60_000:
            raise ValueError("statement_timeout_ms must be between 1 and 60000")
        if not 1 <= int(lock_timeout_ms) <= int(statement_timeout_ms):
            raise ValueError(
                "lock_timeout_ms must be positive and no greater than statement_timeout_ms"
            )
        self._statement_timeout_ms = int(statement_timeout_ms)
        self._lock_timeout_ms = int(lock_timeout_ms)
        self._session_factory = session_factory or _rate_limit_session_factory(
            self._statement_timeout_ms,
            self._lock_timeout_ms,
        )

    def consume(
        self,
        scope_hash: str,
        policy_key: str,
        limit: int,
    ) -> RateLimitDecision:
        _validate_consume_input(
            scope_hash=scope_hash,
            policy_key=policy_key,
            limit=limit,
        )
        session: Session | None = None
        try:
            session = self._session_factory()
            with session.begin():
                self._restrict_transaction(session)
                row = (
                    session.execute(
                        _CONSUME_SQL,
                        {
                            "scope_hash": scope_hash,
                            "policy_key": policy_key,
                            "request_limit": limit,
                        },
                    )
                    .mappings()
                    .one()
                )
            count = int(row["request_count"])
            remaining = int(row["remaining"])
            reset_at = row["reset_at"]
            if reset_at is None or not hasattr(reset_at, "timestamp"):
                raise RateLimitStoreUnavailable(
                    "PostgreSQL rate-limit store returned an invalid reset time"
                )
            allowed = row["allowed"]
            retry_after_seconds = int(row["retry_after_seconds"])
            if (
                not isinstance(allowed, bool)
                or not 1 <= count <= int(limit) + 1
                or remaining != max(0, int(limit) - count)
                or allowed != (count <= int(limit))
                or retry_after_seconds < 1
            ):
                raise RateLimitStoreUnavailable(
                    "PostgreSQL rate-limit store returned an invalid decision"
                )
            return RateLimitDecision(
                allowed=allowed,
                limit=int(limit),
                count=count,
                remaining=remaining,
                reset_at_epoch=int(reset_at.timestamp()),
                retry_after_seconds=retry_after_seconds,
            )
        except RateLimitStoreUnavailable:
            raise
        except Exception as exc:
            raise RateLimitStoreUnavailable(
                "PostgreSQL rate-limit store is unavailable"
            ) from exc
        finally:
            if session is not None:
                session.close()

    def prune_expired(
        self,
        *,
        retention_seconds: int = 86_400,
        batch_size: int = 1_000,
    ) -> int:
        if not 60 <= int(retention_seconds) <= 2_592_000:
            raise ValueError("retention_seconds must be between 60 and 2592000")
        if not 1 <= int(batch_size) <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        session: Session | None = None
        try:
            session = self._session_factory()
            with session.begin():
                self._restrict_transaction(session)
                deleted = session.execute(
                    _PRUNE_SQL,
                    {
                        "retention_seconds": int(retention_seconds),
                        "batch_size": int(batch_size),
                    },
                ).scalar_one()
            return int(deleted)
        except Exception as exc:
            raise RateLimitStoreUnavailable(
                "PostgreSQL rate-limit cleanup is unavailable"
            ) from exc
        finally:
            if session is not None:
                session.close()

    def _restrict_transaction(self, session: Session) -> None:
        # The runtime DSN owns the schema so migrations can run, but normal
        # request work must cross the narrow SECURITY DEFINER boundary as the
        # unprivileged application role.
        session.execute(
            _SET_TIMEOUTS_SQL,
            {
                "statement_timeout": f"{self._statement_timeout_ms}ms",
                "lock_timeout": f"{self._lock_timeout_ms}ms",
            },
        )
        session.execute(_SET_ROLE_SQL)


class RedisFixedWindowRateLimitStore:
    def __init__(self, redis_url: str) -> None:
        if not redis_url.strip():
            raise ValueError("redis_url is required")
        self._redis = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            retry_on_timeout=False,
        )
        self._consume_script = self._redis.register_script(
            _REDIS_FIXED_WINDOW_SCRIPT
        )

    def consume(
        self,
        scope_hash: str,
        policy_key: str,
        limit: int,
    ) -> RateLimitDecision:
        _validate_consume_input(
            scope_hash=scope_hash,
            policy_key=policy_key,
            limit=limit,
        )
        redis_key = f"request_rate_limit:v1:{policy_key}:{scope_hash}"
        try:
            result = self._consume_script(
                keys=[redis_key],
                args=[int(limit)],
            )
            if not isinstance(result, (list, tuple)) or len(result) != 3:
                raise RateLimitStoreUnavailable(
                    "Redis rate-limit store returned an invalid decision"
                )
            count = int(result[0])
            window_started_at = int(result[1])
            now_epoch = int(result[2])
        except RateLimitStoreUnavailable:
            raise
        except (RedisError, TypeError, ValueError) as exc:
            raise RateLimitStoreUnavailable(
                "Redis rate-limit store is unavailable"
            ) from exc

        reset_at_epoch = window_started_at + 60
        if (
            not 1 <= count <= int(limit) + 1
            or window_started_at < 0
            or window_started_at % 60 != 0
            or now_epoch < 0
            or reset_at_epoch <= now_epoch
        ):
            raise RateLimitStoreUnavailable(
                "Redis rate-limit store returned an invalid decision"
            )
        return RateLimitDecision(
            allowed=count <= int(limit),
            limit=int(limit),
            count=count,
            remaining=max(0, int(limit) - count),
            reset_at_epoch=reset_at_epoch,
            retry_after_seconds=max(1, reset_at_epoch - now_epoch),
        )


def _rate_limit_session_factory(
    statement_timeout_ms: int,
    lock_timeout_ms: int,
) -> Callable[[], Session]:
    """Build a dedicated, bounded PostgreSQL session factory.

    Hosted transaction-pooler connections use ``NullPool`` plus bounded connect
    and TCP settings. SQL timeouts are transaction-local and function-local so
    they remain compatible with Supavisor transaction mode.
    """

    settings = get_settings()
    return _cached_rate_limit_session_factory(
        _normalize_postgres_dsn(settings.postgres_dsn),
        bool(settings.hosted_serverless),
        int(getattr(settings, "db_pool_timeout_seconds", 30)),
        statement_timeout_ms,
        lock_timeout_ms,
    )


@lru_cache(maxsize=16)
def _cached_rate_limit_session_factory(
    normalized_database_url: str,
    hosted_serverless: bool,
    configured_pool_timeout_seconds: int,
    statement_timeout_ms: int,
    lock_timeout_ms: int,
) -> Callable[[], Session]:
    database_url = make_url(normalized_database_url)
    if database_url.get_backend_name() != "postgresql":
        raise RateLimitStoreUnavailable(
            "PostgreSQL rate limiting requires a PostgreSQL database URL"
        )
    connect_timeout_seconds = max(
        1,
        min(
            3,
            configured_pool_timeout_seconds,
            (statement_timeout_ms + 999) // 1_000,
        ),
    )
    connect_args: dict[str, object] = {
        "connect_timeout": connect_timeout_seconds,
        "tcp_user_timeout": 2_000,
        "prepare_threshold": None,
    }
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": False,
        "connect_args": connect_args,
    }
    if hosted_serverless:
        # Supavisor already provides transaction pooling. Never retain a second
        # process-local pool in an autoscaled serverless function.
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs.update(
            {
                "pool_size": 2,
                "max_overflow": 3,
                "pool_timeout": max(0.1, statement_timeout_ms / 1000),
                "pool_recycle": 60,
                "pool_use_lifo": True,
            }
        )
    engine = create_engine(database_url, **engine_kwargs)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _validate_consume_input(
    *,
    scope_hash: str,
    policy_key: str,
    limit: int,
) -> None:
    if not isinstance(scope_hash, str) or _SCOPE_HASH_PATTERN.fullmatch(scope_hash) is None:
        raise ValueError("scope_hash must be 64 lowercase hexadecimal characters")
    if not isinstance(policy_key, str) or _POLICY_KEY_PATTERN.fullmatch(policy_key) is None:
        raise ValueError("policy_key contains unsupported characters")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_REQUEST_LIMIT:
        raise ValueError("limit must be between 1 and 1000000")


__all__ = [
    "PostgresFixedWindowRateLimitStore",
    "RateLimitDecision",
    "RateLimitStore",
    "RateLimitStoreUnavailable",
    "RedisFixedWindowRateLimitStore",
]
