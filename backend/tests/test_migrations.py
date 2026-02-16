import os
import shutil
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_upgrade_and_downgrade():
    tmp_root = Path(".tmp_test_migrations")
    tmp_root.mkdir(exist_ok=True)
    tmp = tmp_root / str(uuid.uuid4())
    tmp.mkdir(exist_ok=True)
    try:
        db_path = os.path.join(str(tmp.resolve()), "mig.db")
        dsn = f"sqlite:///{db_path}"
        os.environ["POSTGRES_DSN"] = dsn

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", dsn)

        command.upgrade(cfg, "head")
        engine = create_engine(dsn)
        inspector = inspect(engine)
        assert "campaigns" in inspector.get_table_names()
        assert "task_executions" in inspector.get_table_names()
        assert "crawl_runs" in inspector.get_table_names()
        assert "technical_issues" in inspector.get_table_names()

        command.downgrade(cfg, "base")
        inspector2 = inspect(engine)
        assert "campaigns" not in inspector2.get_table_names()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
