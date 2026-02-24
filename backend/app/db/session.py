from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_local: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if settings.postgres_dsn.startswith("sqlite") else {}
        _engine = create_engine(settings.postgres_dsn, pool_pre_ping=True, connect_args=connect_args)
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


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
