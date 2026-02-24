from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models.strategy_execution_key import StrategyExecutionKey

VALID_EXECUTION_STATES = {"pending", "running", "completed", "failed"}
_RETRY_BACKOFF_SECONDS = (0.05, 0.1, 0.25)


class ExecutionConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def get_or_create_execution(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    operation_type: str,
    idempotency_key: str,
    input_hash: str,
    version_fingerprint: str,
) -> tuple[StrategyExecutionKey, bool]:
    now = datetime.now(UTC)

    def _op() -> tuple[StrategyExecutionKey, bool]:
        inserted_id = _insert_on_conflict_do_nothing(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            version_fingerprint=version_fingerprint,
            now=now,
        )
        if inserted_id:
            created = db.get(StrategyExecutionKey, inserted_id)
            if created is None:
                raise RuntimeError(f"Execution key inserted but not found: {inserted_id}")
            return created, True

        existing = _select_execution_by_key(
            db,
            tenant_id=tenant_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            raise RuntimeError("Execution key not found after conflict insert")
        _assert_execution_identity(existing, input_hash=input_hash, version_fingerprint=version_fingerprint)
        return existing, False

    return _run_db_retry_loop(db, _op)


def claim_pending_execution(db: Session, *, execution_id: str) -> StrategyExecutionKey | None:
    """Transition pending->running atomically with SKIP LOCKED semantics on PostgreSQL."""

    def _op() -> StrategyExecutionKey | None:
        dialect = db.bind.dialect.name.lower() if db.bind is not None else ""
        now = datetime.now(UTC)

        if dialect == "postgresql":
            row = db.execute(
                text(
                    """
                    WITH claimed AS (
                        SELECT id
                        FROM strategy_execution_keys
                        WHERE id = :execution_id
                          AND status = 'pending'
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE strategy_execution_keys sek
                    SET status = 'running',
                        updated_at = :now
                    FROM claimed
                    WHERE sek.id = claimed.id
                    RETURNING sek.id
                    """
                ),
                {"execution_id": execution_id, "now": now},
            ).scalar_one_or_none()
            if row is None:
                db.rollback()
                return None
            db.commit()
            return db.get(StrategyExecutionKey, row)

        row = (
            db.query(StrategyExecutionKey)
            .filter(StrategyExecutionKey.id == execution_id, StrategyExecutionKey.status == "pending")
            .with_for_update()
            .first()
        )
        if row is None:
            db.rollback()
            return None
        row.status = "running"
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return row

    return _run_db_retry_loop(db, _op)


def mark_execution_failed(db: Session, *, execution_id: str, error_message: str) -> StrategyExecutionKey:
    def _op() -> StrategyExecutionKey:
        row = acquire_execution_lock(db, execution_id=execution_id)
        row.status = "failed"
        row.output_payload_json = _serialize_json({"error": error_message})
        row.completed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row

    return _run_db_retry_loop(db, _op)


def recover_stale_running_executions(
    db: Session,
    *,
    timeout_seconds: int,
    batch_size: int = 100,
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)

    def _op() -> dict[str, Any]:
        query = (
            db.query(StrategyExecutionKey)
            .filter(StrategyExecutionKey.status == "running", StrategyExecutionKey.updated_at < cutoff)
            .order_by(StrategyExecutionKey.updated_at.asc())
            .limit(batch_size)
        )
        dialect = db.bind.dialect.name.lower() if db.bind is not None else ""
        if dialect == "postgresql":
            query = query.with_for_update(skip_locked=True)
        else:
            query = query.with_for_update()

        rows = query.all()
        recovered_ids: list[str] = []
        now = datetime.now(UTC)
        for row in rows:
            row.status = "failed"
            row.output_payload_json = _serialize_json({"error": "stale_running_timeout"})
            row.completed_at = now
            row.updated_at = now
            recovered_ids.append(row.id)
        db.commit()
        return {
            "recovered_count": len(recovered_ids),
            "recovered_execution_ids": recovered_ids,
            "timeout_seconds": timeout_seconds,
        }

    return _run_db_retry_loop(db, _op)


def acquire_execution_lock(db: Session, *, execution_id: str) -> StrategyExecutionKey:
    row = (
        db.query(StrategyExecutionKey)
        .filter(StrategyExecutionKey.id == execution_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise ValueError(f"Execution key not found: {execution_id}")
    return row


def persist_execution_result(
    db: Session,
    *,
    execution_id: str,
    output_hash: str,
    output_payload: dict[str, Any],
) -> StrategyExecutionKey:
    def _op() -> StrategyExecutionKey:
        row = acquire_execution_lock(db, execution_id=execution_id)
        if row.status not in {"running", "completed"}:
            raise RuntimeError(f"Execution state does not allow completion: {row.status}")
        row.output_hash = output_hash
        row.output_payload_json = _serialize_json(output_payload)
        row.status = "completed"
        row.completed_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
        return row

    return _run_db_retry_loop(db, _op)


def _insert_on_conflict_do_nothing(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    operation_type: str,
    idempotency_key: str,
    input_hash: str,
    version_fingerprint: str,
    now: datetime,
) -> str | None:
    execution_id = _new_execution_id()
    params = {
        "id": execution_id,
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
        "operation_type": operation_type,
        "idempotency_key": idempotency_key,
        "input_hash": input_hash,
        "version_fingerprint": version_fingerprint,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    dialect = db.bind.dialect.name.lower() if db.bind is not None else ""

    try:
        if dialect in {"postgresql", "sqlite"}:
            inserted = db.execute(
                text(
                    """
                    INSERT INTO strategy_execution_keys (
                        id,
                        tenant_id,
                        campaign_id,
                        operation_type,
                        idempotency_key,
                        input_hash,
                        version_fingerprint,
                        status,
                        created_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :tenant_id,
                        :campaign_id,
                        :operation_type,
                        :idempotency_key,
                        :input_hash,
                        :version_fingerprint,
                        :status,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT (tenant_id, operation_type, idempotency_key) DO NOTHING
                    RETURNING id
                    """
                ),
                params,
            ).scalar_one_or_none()
            db.commit()
            return str(inserted) if inserted else None

        row = StrategyExecutionKey(**params)
        db.add(row)
        db.commit()
        return row.id
    except IntegrityError:
        db.rollback()
        existing = _select_execution_by_key(
            db,
            tenant_id=tenant_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            return None
        _assert_execution_identity(existing, input_hash=input_hash, version_fingerprint=version_fingerprint)
        return None


def _select_execution_by_key(
    db: Session,
    *,
    tenant_id: str,
    operation_type: str,
    idempotency_key: str,
) -> StrategyExecutionKey | None:
    return (
        db.query(StrategyExecutionKey)
        .filter(
            StrategyExecutionKey.tenant_id == tenant_id,
            StrategyExecutionKey.operation_type == operation_type,
            StrategyExecutionKey.idempotency_key == idempotency_key,
        )
        .first()
    )


def _assert_execution_identity(existing: StrategyExecutionKey, *, input_hash: str, version_fingerprint: str) -> None:
    if existing.input_hash != input_hash or existing.version_fingerprint != version_fingerprint:
        raise ExecutionConflictError(
            "Idempotency conflict: identical idempotency_key was reused with different input_hash/version_fingerprint"
        )


def _run_db_retry_loop(db: Session, operation):
    last_exc: Exception | None = None
    for idx, delay in enumerate((0.0, *_RETRY_BACKOFF_SECONDS), start=1):
        if delay > 0:
            time.sleep(delay)
        try:
            return operation()
        except (OperationalError, DBAPIError) as exc:
            db.rollback()
            if not _is_retryable_db_exception(exc) or idx > len(_RETRY_BACKOFF_SECONDS):
                raise
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Retry loop exhausted without operation result")


def _is_retryable_db_exception(exc: Exception) -> bool:
    message = str(exc).lower()
    if "deadlock" in message or "serialization" in message or "database is locked" in message:
        return True
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode in {"40P01", "40001"}:
        return True
    return False


def _new_execution_id() -> str:
    import uuid

    return str(uuid.uuid4())


def _serialize_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
