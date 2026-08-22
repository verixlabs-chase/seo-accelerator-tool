from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.middleware.rate_limit import RateLimitMiddleware
from app.services import rate_limit_store
from app.services.rate_limit_store import PostgresFixedWindowRateLimitStore


pytestmark = pytest.mark.postgres_required
TABLE = "request_rate_limit_counters"
CONSUME_SIGNATURE = "public.consume_request_rate_limit(text,text,integer)"
PRUNE_SIGNATURE = "public.prune_request_rate_limit_counters(integer,integer)"
HMAC_SECRET = "postgres-middleware-composition-secret-at-least-32-characters"


def _session_factory(apply_migrations) -> tuple[object, Callable[[], Session]]:
    engine = create_engine(str(apply_migrations["database_url"]), pool_pre_ping=True)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _avoid_calendar_window_boundary(engine) -> None:  # noqa: ANN001
    with engine.connect() as connection:
        second = float(
            connection.execute(
                text("SELECT EXTRACT(SECOND FROM clock_timestamp())")
            ).scalar_one()
        )
    if second >= 57.0:
        time.sleep((60.0 - second) + 0.5)


@pytest.mark.parametrize(
    ("identity_source", "request_identities", "raw_identity"),
    [
        pytest.param(
            "peer",
            [
                ("203.0.113.140", {"X-Forwarded-For": "198.51.100.1"}),
                ("203.0.113.140", {"X-Forwarded-For": "198.51.100.2"}),
                ("203.0.113.140", {"X-Forwarded-For": "198.51.100.3"}),
            ],
            "203.0.113.140",
            id="peer",
        ),
        pytest.param(
            "vercel",
            [
                ("192.0.2.140", {"X-Vercel-Forwarded-For": "203.0.113.141"}),
                ("192.0.2.141", {"X-Vercel-Forwarded-For": "203.0.113.141"}),
                ("192.0.2.140", {"X-Vercel-Forwarded-For": "203.0.113.141"}),
            ],
            "203.0.113.141",
            id="vercel-across-proxy-peers",
        ),
    ],
)
def test_postgres_middleware_composes_identity_with_one_atomic_saturated_bucket(
    apply_migrations,
    db_session,
    identity_source: str,
    request_identities: list[tuple[str, dict[str, str]]],
    raw_identity: str,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    _avoid_calendar_window_boundary(engine)
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        requests_per_minute=2,
        backend="postgres",
        identity_source=identity_source,
        hmac_secret=HMAC_SECRET,
        redis_url="redis://unused.invalid:6379/0",
        store=store,
    )

    @app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    async def exercise() -> list:
        responses = []
        for peer, headers in request_identities:
            transport = ASGITransport(app=app, client=(peer, 12345))
            async with AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                responses.append(await client.get("/probe", headers=headers))
        return responses

    try:
        responses = asyncio.run(exercise())
        observed_resets = {
            response.headers.get("X-RateLimit-Reset") for response in responses
        }
        if len(observed_resets) > 1:
            # A calendar-minute rollover between sequential requests is not a
            # limiter failure. Clear that partial proof and retry immediately
            # inside the fresh minute rather than relying on wall-clock luck.
            with engine.begin() as connection:
                connection.execute(text(f"DELETE FROM public.{TABLE}"))
            responses = asyncio.run(exercise())

        assert [response.status_code for response in responses] == [200, 200, 429]
        assert [response.headers["X-RateLimit-Limit"] for response in responses] == [
            "2",
            "2",
            "2",
        ]
        assert [
            response.headers["X-RateLimit-Remaining"] for response in responses
        ] == ["1", "0", "0"]
        reset_headers = [
            response.headers["X-RateLimit-Reset"] for response in responses
        ]
        assert len(set(reset_headers)) == 1
        assert int(reset_headers[0]) > int(time.time())
        assert "Retry-After" not in responses[0].headers
        assert "Retry-After" not in responses[1].headers
        assert 1 <= int(responses[2].headers["Retry-After"]) <= 60
        assert responses[2].headers["Cache-Control"] == "private, no-store"
        assert responses[2].json() == {
            "message": "Rate limit exceeded",
            "reason_code": "rate_limit_exceeded",
        }
        denied_output = f"{responses[2].text} {dict(responses[2].headers)!r}"
        assert raw_identity not in denied_output

        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    f"SELECT scope_hash, policy_key, request_count "
                    f"FROM public.{TABLE}"
                )
            ).mappings().all()
        assert len(persisted) == 1
        assert persisted[0]["policy_key"] == "coarse_network_ip_v1"
        assert int(persisted[0]["request_count"]) == 3
        assert len(str(persisted[0]["scope_hash"])) == 64
        assert raw_identity not in str(persisted[0]["scope_hash"])
    finally:
        engine.dispose()


def test_postgres_consume_function_has_exact_winners_under_concurrency(
    apply_migrations,
    db_session,
) -> None:
    del db_session  # starts this test from the fixture's freshly truncated database
    engine, session_factory = _session_factory(apply_migrations)
    _avoid_calendar_window_boundary(engine)
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    attempt_count = 24
    request_limit = 7
    barrier = threading.Barrier(attempt_count)
    decisions = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def consume() -> None:
        try:
            barrier.wait(timeout=5)
            decision = store.consume(
                scope_hash="a" * 64,
                policy_key="global-per-minute",
                limit=request_limit,
            )
            with result_lock:
                decisions.append(decision)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            with result_lock:
                errors.append(exc)

    threads = [threading.Thread(target=consume, daemon=True) for _ in range(attempt_count)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert len(decisions) == attempt_count
        assert sum(decision.allowed for decision in decisions) == request_limit
        expected_counts = list(range(1, request_limit + 1)) + [
            request_limit + 1
        ] * (attempt_count - request_limit)
        assert sorted(decision.count for decision in decisions) == expected_counts
        assert {decision.limit for decision in decisions} == {request_limit}
        assert len({decision.reset_at_epoch for decision in decisions}) == 1

        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    f"SELECT request_count FROM public.{TABLE} "
                    "WHERE scope_hash=:scope_hash AND policy_key=:policy_key"
                ),
                {
                    "scope_hash": "a" * 64,
                    "policy_key": "global-per-minute",
                },
            ).scalar_one()
        assert int(persisted) == request_limit + 1
    finally:
        engine.dispose()


def test_postgres_distinct_subjects_have_independent_allowances(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    _avoid_calendar_window_boundary(engine)
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    barrier = threading.Barrier(12)
    results: dict[str, list[bool]] = {"a": [], "b": []}
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def consume(subject: str) -> None:
        try:
            barrier.wait(timeout=5)
            decision = store.consume(
                scope_hash=subject * 64,
                policy_key="global-per-minute",
                limit=3,
            )
            with result_lock:
                results[subject].append(decision.allowed)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            with result_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=consume, args=(subject,), daemon=True)
        for subject in ("a", "b")
        for _ in range(6)
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert sum(results["a"]) == 3
        assert sum(results["b"]) == 3
    finally:
        engine.dispose()


def test_default_hosted_postgres_store_uses_normalized_dedicated_factory(
    apply_migrations,
    db_session,
    monkeypatch,
) -> None:
    del db_session
    fixture_url = str(apply_migrations["database_url"])
    plain_url = fixture_url.replace("postgresql+psycopg://", "postgresql://", 1)
    monkeypatch.setattr(
        rate_limit_store,
        "get_settings",
        lambda: SimpleNamespace(
            postgres_dsn=plain_url,
            hosted_serverless=True,
            db_pool_timeout_seconds=2,
        ),
    )
    rate_limit_store._cached_rate_limit_session_factory.cache_clear()
    limiter_engine = None
    try:
        store = PostgresFixedWindowRateLimitStore()
        limiter_engine = store._session_factory.kw["bind"]
        assert limiter_engine.url.drivername == "postgresql+psycopg"
        assert isinstance(limiter_engine.pool, NullPool)

        decision = store.consume(
            scope_hash="3" * 64,
            policy_key="default-hosted-factory",
            limit=2,
        )

        assert decision.allowed is True
        assert decision.count == 1
        assert decision.remaining == 1
    finally:
        if limiter_engine is not None:
            limiter_engine.dispose()
        rate_limit_store._cached_rate_limit_session_factory.cache_clear()


def test_postgres_expired_prior_bucket_resets_to_one_without_sleep(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO public.{TABLE} "
                "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
                "VALUES (:scope_hash, :policy_key, :window_started_at, 99, :last_seen_at)"
            ),
            {
                "scope_hash": "b" * 64,
                "policy_key": "expired-window",
                "window_started_at": now - timedelta(minutes=5),
                "last_seen_at": now,
            },
        )
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    try:
        decision = store.consume(
            scope_hash="b" * 64,
            policy_key="expired-window",
            limit=3,
        )

        assert decision.allowed is True
        assert decision.count == 1
        assert decision.remaining == 2
        assert decision.reset_at_epoch > int(now.timestamp())
        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    f"SELECT request_count, window_started_at FROM public.{TABLE} "
                    "WHERE scope_hash=:scope_hash AND policy_key=:policy_key"
                ),
                {"scope_hash": "b" * 64, "policy_key": "expired-window"},
            ).mappings().one()
        assert int(persisted["request_count"]) == 1
        assert persisted["window_started_at"] > now - timedelta(minutes=1)
    finally:
        engine.dispose()


def test_postgres_future_window_is_preserved_without_granting_fresh_allowance(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    now = datetime.now(UTC).replace(microsecond=0)
    future_window = now + timedelta(minutes=5)
    original_last_seen = now - timedelta(seconds=30)
    scope_hash = "9" * 64
    policy_key = "future-window"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO public.{TABLE} "
                "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
                "VALUES (:scope_hash, :policy_key, :window_started_at, 3, :last_seen_at)"
            ),
            {
                "scope_hash": scope_hash,
                "policy_key": policy_key,
                "window_started_at": future_window,
                "last_seen_at": original_last_seen,
            },
        )

    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    try:
        decision = store.consume(
            scope_hash=scope_hash,
            policy_key=policy_key,
            limit=3,
        )

        assert decision.allowed is False
        assert decision.count == 4
        assert decision.remaining == 0
        assert decision.reset_at_epoch == int((future_window + timedelta(minutes=1)).timestamp())
        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    f"SELECT request_count, window_started_at, last_seen_at FROM public.{TABLE} "
                    "WHERE scope_hash=:scope_hash AND policy_key=:policy_key"
                ),
                {"scope_hash": scope_hash, "policy_key": policy_key},
            ).mappings().one()
        assert int(persisted["request_count"]) == 4
        assert persisted["window_started_at"] == future_window
        assert persisted["last_seen_at"] == original_last_seen
    finally:
        engine.dispose()


def test_postgres_repeated_saturated_denials_do_not_refresh_last_seen_at(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    _avoid_calendar_window_boundary(engine)
    now = datetime.now(UTC).replace(microsecond=0)
    window_started_at = now.replace(second=0)
    original_last_seen = now - timedelta(seconds=30)
    scope_hash = "8" * 64
    policy_key = "saturated-window"
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO public.{TABLE} "
                "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
                "VALUES (:scope_hash, :policy_key, :window_started_at, 4, :last_seen_at)"
            ),
            {
                "scope_hash": scope_hash,
                "policy_key": policy_key,
                "window_started_at": window_started_at,
                "last_seen_at": original_last_seen,
            },
        )

    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    try:
        decisions = [
            store.consume(scope_hash=scope_hash, policy_key=policy_key, limit=3)
            for _ in range(2)
        ]

        assert all(decision.allowed is False for decision in decisions)
        assert [decision.count for decision in decisions] == [4, 4]
        with engine.connect() as connection:
            persisted = connection.execute(
                text(
                    f"SELECT request_count, last_seen_at FROM public.{TABLE} "
                    "WHERE scope_hash=:scope_hash AND policy_key=:policy_key"
                ),
                {"scope_hash": scope_hash, "policy_key": policy_key},
            ).mappings().one()
        assert int(persisted["request_count"]) == 4
        assert persisted["last_seen_at"] == original_last_seen
    finally:
        engine.dispose()


def test_postgres_net_new_identity_evicts_exactly_one_two_day_stale_row(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    now = datetime.now(UTC).replace(microsecond=0)
    insert_sql = text(
        f"INSERT INTO public.{TABLE} "
        "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
        "VALUES (:scope_hash, :policy_key, :window_started_at, 1, :last_seen_at)"
    )
    oldest_scope = "5" * 64
    newer_stale_scope = "6" * 64
    live_scope = "7" * 64
    with engine.begin() as connection:
        connection.execute(
            insert_sql,
            [
                {
                    "scope_hash": oldest_scope,
                    "policy_key": "stale-identity",
                    "window_started_at": now - timedelta(days=4),
                    "last_seen_at": now - timedelta(days=4),
                },
                {
                    "scope_hash": newer_stale_scope,
                    "policy_key": "stale-identity",
                    "window_started_at": now - timedelta(days=3),
                    "last_seen_at": now - timedelta(days=3),
                },
                {
                    "scope_hash": live_scope,
                    "policy_key": "live-identity",
                    "window_started_at": now,
                    "last_seen_at": now,
                },
            ],
        )

    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    new_scope = "4" * 64
    try:
        decision = store.consume(
            scope_hash=new_scope,
            policy_key="net-new-identity",
            limit=10,
        )

        assert decision.allowed is True
        assert decision.count == 1
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"SELECT scope_hash, policy_key FROM public.{TABLE} "
                    "ORDER BY scope_hash"
                )
            ).mappings().all()
        assert rows == [
            {"scope_hash": new_scope, "policy_key": "net-new-identity"},
            {"scope_hash": newer_stale_scope, "policy_key": "stale-identity"},
            {"scope_hash": live_scope, "policy_key": "live-identity"},
        ]
        assert all(row["scope_hash"] != oldest_scope for row in rows)
    finally:
        engine.dispose()


def test_postgres_bounded_cleanup_preserves_live_buckets(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    now = datetime.now(UTC)
    expired = [
        {
            "scope_hash": f"{index:064x}",
            "policy_key": "cleanup-expired",
            "window_started_at": now - timedelta(minutes=5),
            "last_seen_at": now - timedelta(minutes=5),
        }
        for index in range(1, 6)
    ]
    live = {
        "scope_hash": "f" * 64,
        "policy_key": "cleanup-live",
        "window_started_at": now,
        "last_seen_at": now,
    }
    insert_sql = text(
        f"INSERT INTO public.{TABLE} "
        "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
        "VALUES (:scope_hash, :policy_key, :window_started_at, 1, :last_seen_at)"
    )
    with engine.begin() as connection:
        connection.execute(insert_sql, [*expired, live])

    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    try:
        assert store.prune_expired(retention_seconds=60, batch_size=2) == 2
        assert store.prune_expired(retention_seconds=60, batch_size=2) == 2
        assert store.prune_expired(retention_seconds=60, batch_size=2) == 1
        assert store.prune_expired(retention_seconds=60, batch_size=2) == 0

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"SELECT scope_hash, policy_key, request_count FROM public.{TABLE}"
                )
            ).mappings().all()
        assert rows == [
            {
                "scope_hash": "f" * 64,
                "policy_key": "cleanup-live",
                "request_count": 1,
            }
        ]
    finally:
        engine.dispose()


def test_postgres_cleanup_and_consume_are_race_safe(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, session_factory = _session_factory(apply_migrations)
    _avoid_calendar_window_boundary(engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO public.{TABLE} "
                "(scope_hash, policy_key, window_started_at, request_count, last_seen_at) "
                "VALUES (:scope_hash, :policy_key, :window_started_at, 1, :last_seen_at)"
            ),
            [
                {
                    "scope_hash": f"{index:064x}",
                    "policy_key": "race-expired",
                    "window_started_at": now - timedelta(minutes=5),
                    "last_seen_at": now - timedelta(minutes=5),
                }
                for index in range(1, 21)
            ],
        )
    store = PostgresFixedWindowRateLimitStore(session_factory=session_factory)
    barrier = threading.Barrier(14)
    decisions = []
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def consume() -> None:
        try:
            barrier.wait(timeout=5)
            decision = store.consume(
                scope_hash="e" * 64,
                policy_key="race-live",
                limit=50,
            )
            with result_lock:
                decisions.append(decision)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            with result_lock:
                errors.append(exc)

    def cleanup() -> None:
        try:
            barrier.wait(timeout=5)
            store.prune_expired(retention_seconds=60, batch_size=10)
        except BaseException as exc:  # pragma: no cover - asserted by parent thread
            with result_lock:
                errors.append(exc)

    threads = [threading.Thread(target=consume, daemon=True) for _ in range(12)]
    threads.extend(threading.Thread(target=cleanup, daemon=True) for _ in range(2))
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=8)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert len(decisions) == 12
        while store.prune_expired(retention_seconds=60, batch_size=10):
            pass

        with engine.connect() as connection:
            live_count = connection.execute(
                text(
                    f"SELECT request_count FROM public.{TABLE} "
                    "WHERE scope_hash=:scope_hash AND policy_key=:policy_key"
                ),
                {"scope_hash": "e" * 64, "policy_key": "race-live"},
            ).scalar_one()
            expired_count = connection.execute(
                text(
                    f"SELECT count(*) FROM public.{TABLE} "
                    "WHERE policy_key='race-expired'"
                )
            ).scalar_one()
        assert int(live_count) == 12
        assert int(expired_count) == 0
    finally:
        engine.dispose()


def test_postgres_limiter_acl_is_function_only(
    apply_migrations,
    db_session,
) -> None:
    del db_session
    engine, _session_factory_unused = _session_factory(apply_migrations)
    try:
        with engine.connect() as connection:
            table_privileges = {
                privilege: bool(
                    connection.execute(
                        text(
                            "SELECT has_table_privilege("
                            "'lsos_app', 'public.request_rate_limit_counters', :privilege)"
                        ),
                        {"privilege": privilege},
                    ).scalar_one()
                )
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
            }
            function_privileges = {
                signature: bool(
                    connection.execute(
                        text(
                            "SELECT has_function_privilege("
                            "'lsos_app', :signature, 'EXECUTE')"
                        ),
                        {"signature": signature},
                    ).scalar_one()
                )
                for signature in (CONSUME_SIGNATURE, PRUNE_SIGNATURE)
            }
            function_security = connection.execute(
                text(
                    "SELECT p.oid::regprocedure::text AS signature, p.prosecdef, p.proconfig, "
                    "EXISTS ("
                    "  SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) acl "
                    "  WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'"
                    ") AS public_execute "
                    "FROM pg_proc p "
                    "WHERE p.oid IN (to_regprocedure(:consume), to_regprocedure(:prune))"
                ),
                {
                    "consume": CONSUME_SIGNATURE,
                    "prune": PRUNE_SIGNATURE,
                },
            ).mappings().all()

        assert table_privileges == {
            "SELECT": False,
            "INSERT": False,
            "UPDATE": False,
            "DELETE": False,
            "TRUNCATE": False,
        }
        assert function_privileges == {
            CONSUME_SIGNATURE: True,
            PRUNE_SIGNATURE: True,
        }
        assert len(function_security) == 2
        assert all(row["prosecdef"] is True for row in function_security)
        assert all(row["public_execute"] is False for row in function_security)
        assert all(
            any(str(item).lower().startswith("search_path=") for item in (row["proconfig"] or []))
            for row in function_security
        )

        with engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE lsos_app"))
            consumed = connection.execute(
                text(
                    "SELECT * FROM public.consume_request_rate_limit("
                    ":scope_hash, :policy_key, :request_limit)"
                ),
                {
                    "scope_hash": "d" * 64,
                    "policy_key": "acl-function",
                    "request_limit": 1,
                },
            ).mappings().one()
        assert consumed["allowed"] is True

        connection = engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL ROLE lsos_app"))
            with pytest.raises(DBAPIError):
                connection.execute(text(f"SELECT * FROM public.{TABLE}"))
        finally:
            transaction.rollback()
            connection.close()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        (
            "SELECT * FROM public.consume_request_rate_limit(:scope, :policy, :limit)",
            {"scope": "c" * 64, "policy": "invalid-limit", "limit": 0},
        ),
        (
            "SELECT public.prune_request_rate_limit_counters(:retention, :batch)",
            {"retention": 59, "batch": 100},
        ),
        (
            "SELECT public.prune_request_rate_limit_counters(:retention, :batch)",
            {"retention": 60, "batch": 10001},
        ),
    ],
)
def test_postgres_functions_reject_unbounded_or_invalid_inputs(
    apply_migrations,
    db_session,
    sql: str,
    params: dict[str, object],
) -> None:
    del db_session
    engine, _session_factory_unused = _session_factory(apply_migrations)
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(text("SET LOCAL ROLE lsos_app"))
        with pytest.raises(DBAPIError):
            connection.execute(text(sql), params)
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
