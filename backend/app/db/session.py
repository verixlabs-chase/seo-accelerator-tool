from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine():
    settings = get_settings()
    connect_args = {'check_same_thread': False} if settings.postgres_dsn.startswith('sqlite') else {}
    return create_engine(settings.postgres_dsn, pool_pre_ping=True, connect_args=connect_args)


@lru_cache
def _sessionmaker_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, class_=Session)


def SessionLocal() -> Session:
    return _sessionmaker_factory()()


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
