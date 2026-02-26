from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_engine: Engine | None = None
_session_local: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.postgres_dsn.startswith('sqlite')
        connect_args = {'check_same_thread': False} if is_sqlite else {}
        engine_kwargs: dict = {'pool_pre_ping': True, 'connect_args': connect_args}
        if is_sqlite and settings.app_env.lower() == 'test':
            # SQLite test DBs are short-lived and should avoid pooled handles.
            engine_kwargs['poolclass'] = NullPool
        _engine = create_engine(settings.postgres_dsn, **engine_kwargs)
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


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
