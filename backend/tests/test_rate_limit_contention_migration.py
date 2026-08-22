from __future__ import annotations

from pathlib import Path


MIGRATION_NAME = "20260822_0209_rate_limit_contention.py"


def _migration_source() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "alembic" / "versions" / MIGRATION_NAME).read_text(
        encoding="utf-8"
    )


def test_rate_limit_contention_migration_is_linear_and_bounded() -> None:
    migration = " ".join(_migration_source().lower().split())

    assert 'revision = "20260822_0209"' in migration
    assert 'down_revision = "20260821_0208"' in migration
    assert "alter function" in migration
    assert "consume_request_rate_limit(text, text, integer)" in migration
    assert "set statement_timeout = '2s'" in migration
    assert "set lock_timeout = '750ms'" in migration


def test_rate_limit_contention_migration_restores_prior_timeouts_on_downgrade() -> None:
    migration = " ".join(_migration_source().lower().split())

    assert "set statement_timeout = '750ms'" in migration
    assert "set lock_timeout = '250ms'" in migration
