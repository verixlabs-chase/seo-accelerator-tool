from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.migration_import import (
    MigrationUploadChunk,
    MigrationUploadSession,
)
from app.services.migration_import_service import (
    MigrationImportError,
    apply_migration_csv,
    dry_run_migration_csv,
)


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_CHUNKS = 100
MAX_CHUNK_BYTES = 600 * 1024
MAX_UPLOAD_ROWS = 25_000
UPLOAD_TTL = timedelta(days=7)
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 250


def create_upload_session(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    actor_user_id: str,
    source_system: str,
    source_filename: str | None,
    total_chunks: int,
    expected_sha256: str | None,
    client_request_id: str,
) -> dict[str, Any]:
    if total_chunks < 1 or total_chunks > MAX_UPLOAD_CHUNKS:
        raise MigrationImportError(
            f"Split the file into between 1 and {MAX_UPLOAD_CHUNKS} parts.",
            reason_code="migration_upload_chunk_count_invalid",
        )
    existing = (
        db.query(MigrationUploadSession)
        .filter(
            MigrationUploadSession.organization_id == organization_id,
            MigrationUploadSession.tenant_id == tenant_id,
            MigrationUploadSession.client_request_id == client_request_id,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.source_system != source_system
            or existing.total_chunks != total_chunks
            or existing.expected_sha256 != expected_sha256
        ):
            raise MigrationImportError(
                "This upload request was already used for a different file.",
                reason_code="migration_upload_idempotency_conflict",
            )
        return serialize_upload_session(db, existing)

    now = datetime.now(UTC)
    session = MigrationUploadSession(
        tenant_id=tenant_id,
        organization_id=organization_id,
        client_request_id=client_request_id,
        source_system=source_system,
        source_filename=_safe_filename(source_filename),
        total_chunks=total_chunks,
        expected_sha256=expected_sha256,
        status="uploading",
        total_bytes=0,
        received_chunks=0,
        created_by=actor_user_id,
        created_at=now,
        updated_at=now,
        expires_at=now + UPLOAD_TTL,
    )
    db.add(session)
    db.flush()
    return serialize_upload_session(db, session)


def get_upload_session(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    upload_id: str,
) -> dict[str, Any]:
    return serialize_upload_session(
        db,
        _session(db, organization_id=organization_id, tenant_id=tenant_id, upload_id=upload_id),
    )


def save_upload_chunk(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    upload_id: str,
    chunk_index: int,
    content: str,
    chunk_sha256: str,
) -> dict[str, Any]:
    upload = _session(
        db,
        organization_id=organization_id,
        tenant_id=tenant_id,
        upload_id=upload_id,
        for_update=True,
    )
    _assert_active(upload)
    if upload.status != "uploading":
        raise MigrationImportError(
            "This reviewed upload is locked. Start a new upload to change the file.",
            reason_code="migration_upload_locked",
        )
    if chunk_index < 0 or chunk_index >= upload.total_chunks:
        raise MigrationImportError(
            "This file part is outside the expected upload range.",
            reason_code="migration_upload_chunk_index_invalid",
        )
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_CHUNK_BYTES:
        raise MigrationImportError(
            "This file part is too large. Use smaller upload parts.",
            reason_code="migration_upload_chunk_too_large",
        )
    actual_hash = hashlib.sha256(encoded).hexdigest()
    if actual_hash != chunk_sha256:
        raise MigrationImportError(
            "This file part changed while uploading. Try that part again.",
            reason_code="migration_upload_chunk_hash_mismatch",
        )
    existing = (
        db.query(MigrationUploadChunk)
        .filter(
            MigrationUploadChunk.session_id == upload.id,
            MigrationUploadChunk.chunk_index == chunk_index,
        )
        .first()
    )
    if existing is not None:
        if existing.chunk_sha256 != chunk_sha256 or existing.content != content:
            raise MigrationImportError(
                "This file part was already uploaded with different contents.",
                reason_code="migration_upload_chunk_conflict",
            )
        return {
            "chunk_index": chunk_index,
            "already_received": True,
            "upload": serialize_upload_session(db, upload),
        }
    if upload.total_bytes + len(encoded) > MAX_UPLOAD_BYTES:
        raise MigrationImportError(
            "Choose a CSV file smaller than 20 MB.",
            reason_code="migration_upload_too_large",
        )
    db.add(
        MigrationUploadChunk(
            session_id=upload.id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            chunk_index=chunk_index,
            chunk_sha256=chunk_sha256,
            byte_size=len(encoded),
            content=content,
            created_at=datetime.now(UTC),
        )
    )
    upload.total_bytes += len(encoded)
    upload.received_chunks += 1
    upload.updated_at = datetime.now(UTC)
    db.flush()
    return {
        "chunk_index": chunk_index,
        "already_received": False,
        "upload": serialize_upload_session(db, upload),
    }


def review_upload(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    upload_id: str,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    upload = _session(
        db,
        organization_id=organization_id,
        tenant_id=tenant_id,
        upload_id=upload_id,
        for_update=True,
    )
    _assert_active(upload)
    if upload.review_payload is None:
        csv_text = _assemble(db, upload)
        source_sha256 = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        if upload.expected_sha256 and source_sha256 != upload.expected_sha256:
            raise MigrationImportError(
                "The completed upload does not match the file you selected. Start the upload again.",
                reason_code="migration_upload_file_hash_mismatch",
            )
        review = dry_run_migration_csv(
            db,
            organization_id=organization_id,
            tenant_id=tenant_id,
            source_system=upload.source_system,
            csv_text=csv_text,
            max_rows=MAX_UPLOAD_ROWS,
        )
        upload.review_payload = review
        upload.review_hash = review["review_hash"]
        upload.source_sha256 = source_sha256
        upload.status = "reviewed"
        upload.updated_at = datetime.now(UTC)
        db.flush()
    return _paged_review(upload.review_payload, page=page, page_size=page_size)


def get_upload_review_page(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    upload_id: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    upload = _session(db, organization_id=organization_id, tenant_id=tenant_id, upload_id=upload_id)
    _assert_active(upload)
    if upload.review_payload is None:
        raise MigrationImportError(
            "Review the completed upload before opening its rows.",
            reason_code="migration_upload_not_reviewed",
        )
    return _paged_review(upload.review_payload, page=page, page_size=page_size)


def apply_upload(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    actor_user_id: str,
    upload_id: str,
    review_hash: str,
    client_request_id: str,
    confirmed: bool,
) -> dict[str, Any]:
    upload = _session(
        db,
        organization_id=organization_id,
        tenant_id=tenant_id,
        upload_id=upload_id,
        for_update=True,
    )
    _assert_active(upload, allow_applied=True)
    if upload.review_payload is None or not upload.review_hash:
        raise MigrationImportError(
            "Review the completed upload before importing it.",
            reason_code="migration_upload_not_reviewed",
        )
    if upload.review_hash != review_hash:
        raise MigrationImportError(
            "The reviewed upload changed. Review it again before importing.",
            reason_code="migration_review_changed",
        )
    csv_text = _assemble(db, upload)
    batch = apply_migration_csv(
        db,
        organization_id=organization_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        source_system=upload.source_system,
        source_filename=upload.source_filename,
        csv_text=csv_text,
        review_hash=review_hash,
        client_request_id=client_request_id,
        confirmed=confirmed,
        max_rows=MAX_UPLOAD_ROWS,
    )
    upload.applied_batch_id = str(batch["id"])
    upload.status = "applied"
    upload.updated_at = datetime.now(UTC)
    db.flush()
    return {"batch": batch, "upload": serialize_upload_session(db, upload)}


def purge_expired_upload_sessions(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff = now or datetime.now(UTC)
    session_ids = [
        str(row[0])
        for row in (
            db.query(MigrationUploadSession.id)
            .filter(MigrationUploadSession.expires_at <= cutoff)
            .all()
        )
    ]
    if not session_ids:
        return {"sessions_deleted": 0, "chunks_deleted": 0}
    chunks_deleted = (
        db.query(MigrationUploadChunk)
        .filter(MigrationUploadChunk.session_id.in_(session_ids))
        .delete(synchronize_session=False)
    )
    sessions_deleted = (
        db.query(MigrationUploadSession)
        .filter(MigrationUploadSession.id.in_(session_ids))
        .delete(synchronize_session=False)
    )
    db.flush()
    return {
        "sessions_deleted": int(sessions_deleted or 0),
        "chunks_deleted": int(chunks_deleted or 0),
    }


def serialize_upload_session(db: Session, upload: MigrationUploadSession) -> dict[str, Any]:
    indexes = [
        int(row[0])
        for row in (
            db.query(MigrationUploadChunk.chunk_index)
            .filter(MigrationUploadChunk.session_id == upload.id)
            .order_by(MigrationUploadChunk.chunk_index.asc())
            .all()
        )
    ]
    return {
        "id": upload.id,
        "source_system": upload.source_system,
        "source_filename": upload.source_filename,
        "status": upload.status,
        "total_chunks": upload.total_chunks,
        "received_chunks": upload.received_chunks,
        "received_chunk_indexes": indexes,
        "total_bytes": upload.total_bytes,
        "expected_sha256": upload.expected_sha256,
        "source_sha256": upload.source_sha256,
        "review_hash": upload.review_hash,
        "applied_batch_id": upload.applied_batch_id,
        "created_at": upload.created_at.isoformat(),
        "updated_at": upload.updated_at.isoformat(),
        "expires_at": upload.expires_at.isoformat(),
    }


def _session(
    db: Session,
    *,
    organization_id: str,
    tenant_id: str,
    upload_id: str,
    for_update: bool = False,
) -> MigrationUploadSession:
    query = db.query(MigrationUploadSession).filter(
        MigrationUploadSession.id == upload_id,
        MigrationUploadSession.organization_id == organization_id,
        MigrationUploadSession.tenant_id == tenant_id,
    )
    if for_update:
        query = query.with_for_update()
    upload = query.first()
    if upload is None:
        raise MigrationImportError(
            "This migration upload could not be found.",
            reason_code="migration_upload_not_found",
        )
    return upload


def _assert_active(upload: MigrationUploadSession, *, allow_applied: bool = False) -> None:
    expires_at = upload.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if datetime.now(UTC) >= expires_at and not (allow_applied and upload.status == "applied"):
        raise MigrationImportError(
            "This saved upload expired after seven days. Start a new upload.",
            reason_code="migration_upload_expired",
        )


def _assemble(db: Session, upload: MigrationUploadSession) -> str:
    chunks = (
        db.query(MigrationUploadChunk)
        .filter(MigrationUploadChunk.session_id == upload.id)
        .order_by(MigrationUploadChunk.chunk_index.asc())
        .all()
    )
    indexes = [chunk.chunk_index for chunk in chunks]
    expected = list(range(upload.total_chunks))
    if indexes != expected:
        missing = [str(index + 1) for index in expected if index not in set(indexes)]
        raise MigrationImportError(
            f"Upload the remaining file parts first: {', '.join(missing[:10])}.",
            reason_code="migration_upload_incomplete",
        )
    return "".join(chunk.content for chunk in chunks)


def _paged_review(review: dict[str, Any], *, page: int, page_size: int) -> dict[str, Any]:
    safe_page = max(1, page)
    safe_page_size = min(max(1, page_size), MAX_PAGE_SIZE)
    rows = list(review.get("rows") or [])
    start = (safe_page - 1) * safe_page_size
    result = {key: value for key, value in review.items() if key != "rows"}
    result["rows"] = rows[start : start + safe_page_size]
    result["pagination"] = {
        "page": safe_page,
        "page_size": safe_page_size,
        "total_rows": len(rows),
        "total_pages": max(1, (len(rows) + safe_page_size - 1) // safe_page_size),
        "has_more": start + safe_page_size < len(rows),
    }
    return result


def _safe_filename(value: str | None) -> str | None:
    if not value:
        return None
    return Path(value.replace("\\", "/")).name[:255] or None
