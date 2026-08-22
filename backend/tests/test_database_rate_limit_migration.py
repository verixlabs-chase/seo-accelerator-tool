from __future__ import annotations

from pathlib import Path


MIGRATION_NAME = "20260821_0208_postgres_rate_limit.py"
TABLE_NAME = "request_rate_limit_counters"


def _migration_source() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "alembic" / "versions" / MIGRATION_NAME).read_text(
        encoding="utf-8"
    )


def test_database_rate_limit_migration_is_the_next_linear_revision() -> None:
    migration = _migration_source()

    assert 'revision = "20260821_0208"' in migration
    assert 'down_revision = "20260820_0207"' in migration
    assert f'TABLE = "{TABLE_NAME}"' in migration or f'"{TABLE_NAME}"' in migration


def test_database_rate_limit_migration_defines_atomic_bucket_and_cleanup_contract() -> None:
    migration = _migration_source()

    for column_name in (
        "scope_hash",
        "policy_key",
        "window_started_at",
        "request_count",
        "last_seen_at",
    ):
        assert f'"{column_name}"' in migration
    assert "ix_request_rate_limit_counters_last_seen_at" in migration
    assert "consume_request_rate_limit" in migration
    assert "prune_request_rate_limit_counters" in migration
    assert "p_scope_hash" in migration
    assert "p_policy_key" in migration
    assert "p_request_limit" in migration
    assert "p_retention_seconds" in migration
    assert "p_batch_size" in migration


def test_database_rate_limit_functions_are_security_definer_and_function_only() -> None:
    migration = _migration_source()
    normalized = " ".join(migration.upper().split())

    assert normalized.count("SECURITY DEFINER") >= 2
    assert "SET SEARCH_PATH" in normalized
    assert "PG_CATALOG" in normalized
    assert "REVOKE" in normalized
    assert "ON TABLE PUBLIC.{TABLE}" in normalized
    assert "PUBLIC, LSOS_APP" in normalized
    assert normalized.count("FROM PUBLIC") >= 2
    assert normalized.count("GRANT EXECUTE") >= 2
    assert normalized.count("TO LSOS_APP") >= 2
    assert "SET STATEMENT_TIMEOUT = '750MS'" in normalized
    assert "SET LOCK_TIMEOUT = '250MS'" in normalized
    assert "SET STATEMENT_TIMEOUT = '2S'" in normalized
    assert "SET LOCK_TIMEOUT = '500MS'" in normalized


def test_database_rate_limit_resamples_time_after_insert_conflict_waits() -> None:
    migration = _migration_source()

    insert_result = migration.index("IF FOUND THEN")
    cleanup = migration.index("WITH stale AS", insert_result)
    post_insert_branch = migration[insert_result:cleanup]
    assert "clock_timestamp()" in post_insert_branch
    assert "date_trunc('minute', v_now)" in post_insert_branch
    assert "SET window_started_at = v_stored_window" in post_insert_branch


def test_database_rate_limit_cleanup_inputs_are_bounded_in_the_database() -> None:
    migration = _migration_source()

    assert "2592000" in migration
    assert "10000" in migration
    assert "86400" in migration
    assert "1000" in migration
