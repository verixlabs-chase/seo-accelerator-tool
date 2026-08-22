from collections.abc import Generator
from time import monotonic

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.operational_telemetry_service import record_query_duration

_engine: Engine | None = None
_session_local: sessionmaker | None = None
_RLS_CONTEXT_KEY = "lsos_database_security_context"
_RLS_APP_ROLE = "lsos_app"


def _normalize_postgres_dsn(dsn: str) -> str:
    """Use the installed psycopg v3 driver for common hosted Postgres URLs."""
    if dsn.startswith("postgres://"):
        return f"postgresql+psycopg://{dsn.removeprefix('postgres://')}"
    if dsn.startswith("postgresql://"):
        return f"postgresql+psycopg://{dsn.removeprefix('postgresql://')}"
    return dsn


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = _normalize_postgres_dsn(settings.postgres_dsn)
        is_sqlite = database_url.startswith('sqlite')
        connect_args = {'check_same_thread': False} if is_sqlite else {}
        if settings.hosted_serverless and not is_sqlite:
            # Supabase transaction mode does not support prepared statements.
            connect_args['prepare_threshold'] = None
            # Serverless request protection and readiness probes must fail
            # within the invocation budget when the pooler cannot be reached.
            connect_args['connect_timeout'] = max(
                1,
                min(10, int(settings.db_pool_timeout_seconds)),
            )
        engine_kwargs: dict = {'pool_pre_ping': True, 'connect_args': connect_args}
        if settings.hosted_serverless and not is_sqlite:
            # Supabase's transaction pooler owns connection pooling. Keeping a
            # process-local pool in an ephemeral function wastes connections.
            engine_kwargs['poolclass'] = NullPool
        elif not is_sqlite:
            engine_kwargs['pool_size'] = settings.db_pool_size
            engine_kwargs['max_overflow'] = settings.db_max_overflow
            engine_kwargs['pool_timeout'] = settings.db_pool_timeout_seconds
        if is_sqlite and settings.app_env.lower() == 'test':
            engine_kwargs['poolclass'] = NullPool
        _engine = create_engine(database_url, **engine_kwargs)
        _attach_query_instrumentation(_engine)
    return _engine


def get_session_local() -> sessionmaker:
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, class_=Session)
    return _session_local


class _SessionLocalProxy:
    def __call__(self, *args, **kwargs) -> Session:
        return get_session_local()(*args, **kwargs)


SessionLocal = _SessionLocalProxy()


def reset_engine_state() -> None:
    """Dispose and clear global engine/session state (used by tests)."""
    global _engine, _session_local
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_local = None


def bind_session_factory_for_tests(factory: sessionmaker) -> None:
    """Bind an explicit session factory for test isolation."""
    global _engine, _session_local
    reset_engine_state()
    _session_local = factory
    _engine = factory.kw.get('bind')
    if _engine is not None:
        _attach_query_instrumentation(_engine)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_session_security_context(
    db: Session,
    *,
    tenant_id: str | None,
    organization_id: str | None,
    user_id: str,
    platform_access: bool,
) -> None:
    """Apply transaction-local database identity for PostgreSQL RLS policies."""
    context = {
        "tenant_id": str(tenant_id or ""),
        "organization_id": str(organization_id or ""),
        "user_id": str(user_id),
        "platform_access": bool(platform_access),
    }
    db.info[_RLS_CONTEXT_KEY] = context
    if db.in_transaction():
        _apply_session_security_context(db.connection(), context)


def clear_session_security_context(db: Session) -> None:
    db.info.pop(_RLS_CONTEXT_KEY, None)


def _apply_session_security_context(connection, context: dict[str, object]) -> None:  # noqa: ANN001
    settings = get_settings()
    if not settings.database_rls_enabled or connection.dialect.name != "postgresql":
        return

    connection.exec_driver_sql(f"SET LOCAL ROLE {_RLS_APP_ROLE}")
    connection.execute(
        text(
            """
            SELECT
                set_config('app.current_tenant_id', :tenant_id, true),
                set_config('app.current_organization_id', :organization_id, true),
                set_config('app.current_user_id', :user_id, true),
                set_config('app.platform_access', :platform_access, true)
            """
        ),
        {
            "tenant_id": str(context.get("tenant_id") or ""),
            "organization_id": str(context.get("organization_id") or ""),
            "user_id": str(context.get("user_id") or ""),
            "platform_access": "on" if bool(context.get("platform_access")) else "off",
        },
    )


@event.listens_for(Session, "after_begin")
def _restore_session_security_context(session, transaction, connection) -> None:  # noqa: ANN001
    del transaction
    context = session.info.get(_RLS_CONTEXT_KEY)
    if isinstance(context, dict):
        _apply_session_security_context(connection, context)


def _attach_query_instrumentation(engine: Engine) -> None:
    if getattr(engine, '_lsos_query_instrumented', False):
        return

    @event.listens_for(engine, 'before_cursor_execute')
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        del cursor, parameters, context, executemany
        conn.info['_lsos_query_started_at'] = monotonic()
        conn.info['_lsos_query_statement'] = statement

    @event.listens_for(engine, 'after_cursor_execute')
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        del cursor, statement, parameters, context, executemany
        started_at = conn.info.pop('_lsos_query_started_at', None)
        raw_statement = conn.info.pop('_lsos_query_statement', '')
        if started_at is None:
            return
        duration_ms = (monotonic() - started_at) * 1000.0
        record_query_duration(statement=str(raw_statement), duration_ms=duration_ms)

    engine._lsos_query_instrumented = True
