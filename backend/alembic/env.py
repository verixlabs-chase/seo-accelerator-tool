import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app import models  # noqa: F401

config = context.config


def _resolve_sqlalchemy_url() -> tuple[str, str]:
    explicit_url = config.attributes.get("connection_url")
    if explicit_url:
        return str(explicit_url), "config.attributes.connection_url"

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url, "env.DATABASE_URL"

    postgres_dsn = os.getenv("POSTGRES_DSN", "").strip()
    if postgres_dsn:
        return postgres_dsn, "env.POSTGRES_DSN"

    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured, "alembic.ini sqlalchemy.url"

    settings = get_settings()
    return settings.postgres_dsn, "settings.postgres_dsn"


resolved_url, url_source = _resolve_sqlalchemy_url()
config.set_main_option("sqlalchemy.url", resolved_url)
print(f"[alembic] sqlalchemy.url source={url_source} value={resolved_url}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
