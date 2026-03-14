from collections.abc import Generator
from time import monotonic

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.services.operational_telemetry_service import record_query_duration

_engine: Engine | None = None
_session_local: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.postgres_dsn.startswith('sqlite')
        connect_args = {'check_same_thread': False} if is_sqlite else {}
        engine_kwargs: dict = {'pool_pre_ping': True, 'connect_args': connect_args}
        if not is_sqlite:
            engine_kwargs['pool_size'] = settings.db_pool_size
            engine_kwargs['max_overflow'] = settings.db_max_overflow
            engine_kwargs['pool_timeout'] = settings.db_pool_timeout_seconds
        if is_sqlite and settings.app_env.lower() == 'test':
            engine_kwargs['poolclass'] = NullPool
        _engine = create_engine(settings.postgres_dsn, **engine_kwargs)
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
