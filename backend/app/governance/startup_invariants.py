from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from sqlalchemy import inspect, text

from app.db.session import get_engine

logger = logging.getLogger("lsos.invariants")


@dataclass
class InvariantError(RuntimeError):
    code: str
    context: dict[str, object]

    def __str__(self) -> str:
        return json.dumps({"event": "invariant_error", "code": self.code, "context": self.context}, sort_keys=True)


def run_startup_invariants(*, runtime: str) -> None:
    if os.getenv("APP_ENV", "").strip().lower() == "test":
        return

    engine = get_engine()
    inspector = inspect(engine)

    expected_schema = os.getenv("EXPECTED_SCHEMA_HEAD", "20260224_0028")
    code_fingerprint = os.getenv("CODE_VERSION_FINGERPRINT", "dev")

    _assert_schema_version(engine, expected_schema=expected_schema, runtime=runtime)
    _assert_registry_checksum(engine, runtime=runtime)
    _assert_active_threshold_bundle(engine, runtime=runtime)
    _assert_required_not_null_constraints(inspector, runtime=runtime)
    _assert_cluster_version_fingerprint(engine, runtime=runtime, expected_schema=expected_schema, code_fingerprint=code_fingerprint)


def _raise(code: str, context: dict[str, object]) -> None:
    logger.error(json.dumps({"event": "invariant_error", "code": code, "context": context}, sort_keys=True))
    raise InvariantError(code=code, context=context)


def _assert_schema_version(engine, *, expected_schema: str, runtime: str) -> None:
    with engine.begin() as conn:
        if not inspect(engine).has_table("alembic_version"):
            _raise("schema_version_table_missing", {"runtime": runtime})
        current = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    if current != expected_schema:
        _raise(
            "schema_version_mismatch",
            {"runtime": runtime, "expected_schema": expected_schema, "actual_schema": current},
        )


def _assert_registry_checksum(engine, *, runtime: str) -> None:
    with engine.begin() as conn:
        if not inspect(engine).has_table("threshold_bundles"):
            _raise("threshold_bundles_table_missing", {"runtime": runtime})
        checksum = conn.execute(
            text(
                """
                SELECT checksum
                FROM threshold_bundles
                WHERE status = 'active'
                ORDER BY CASE WHEN activated_at IS NULL THEN 1 ELSE 0 END, activated_at DESC, created_at DESC
                LIMIT 1
                """
            )
        ).scalar_one_or_none()
    if not isinstance(checksum, str) or not checksum.strip():
        _raise("active_threshold_checksum_missing", {"runtime": runtime})


def _assert_active_threshold_bundle(engine, *, runtime: str) -> None:
    with engine.begin() as conn:
        active_count = conn.execute(
            text("SELECT count(*) FROM threshold_bundles WHERE status = 'active' AND is_valid = true")
        ).scalar_one()
    if int(active_count) != 1:
        _raise("active_threshold_bundle_count_invalid", {"runtime": runtime, "active_count": int(active_count)})


def _assert_required_not_null_constraints(inspector, *, runtime: str) -> None:
    required_not_null: dict[str, set[str]] = {
        "strategy_execution_keys": {
            "tenant_id",
            "campaign_id",
            "operation_type",
            "idempotency_key",
            "input_hash",
            "version_fingerprint",
            "status",
        },
        "threshold_bundles": {"version", "status", "checksum", "is_valid"},
        "runtime_version_locks": {"expected_schema_revision", "expected_code_fingerprint", "active"},
    }

    for table_name, required_columns in required_not_null.items():
        if not inspector.has_table(table_name):
            _raise("required_table_missing", {"runtime": runtime, "table_name": table_name})
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        missing_columns = required_columns - set(columns.keys())
        if missing_columns:
            _raise(
                "required_columns_missing",
                {"runtime": runtime, "table_name": table_name, "missing_columns": sorted(missing_columns)},
            )
        nullable_columns = [name for name in required_columns if columns[name].get("nullable", True)]
        if nullable_columns:
            _raise(
                "required_not_null_violation",
                {"runtime": runtime, "table_name": table_name, "nullable_columns": sorted(nullable_columns)},
            )


def _assert_cluster_version_fingerprint(
    engine,
    *,
    runtime: str,
    expected_schema: str,
    code_fingerprint: str,
) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT expected_schema_revision, expected_code_fingerprint
                FROM runtime_version_locks
                WHERE active = true
                LIMIT 1
                """
            )
        ).mappings().first()
    if row is None:
        _raise("runtime_version_lock_missing", {"runtime": runtime})

    if row["expected_schema_revision"] != expected_schema:
        _raise(
            "runtime_schema_fingerprint_mismatch",
            {
                "runtime": runtime,
                "expected_schema": expected_schema,
                "cluster_schema": row["expected_schema_revision"],
            },
        )
    if row["expected_code_fingerprint"] != code_fingerprint:
        _raise(
            "runtime_code_fingerprint_mismatch",
            {
                "runtime": runtime,
                "expected_code_fingerprint": code_fingerprint,
                "cluster_code_fingerprint": row["expected_code_fingerprint"],
            },
        )
