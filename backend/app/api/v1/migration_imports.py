from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.migration_import import (
    MigrationApplyIn,
    MigrationDryRunIn,
    MigrationRollbackIn,
    MigrationUploadApplyIn,
    MigrationUploadChunkIn,
    MigrationUploadCreateIn,
)
from app.services.migration_import_service import (
    MigrationImportError,
    apply_migration_csv,
    dry_run_migration_csv,
    list_migration_batches,
    rollback_migration_batch,
)
from app.services.migration_upload_service import (
    apply_upload,
    create_upload_session,
    get_upload_review_page,
    get_upload_session,
    review_upload,
    save_upload_chunk,
)


router = APIRouter(tags=["migration-imports"])


@router.post("/organizations/{org_id}/migration-imports/uploads")
def start_migration_upload(
    request: Request,
    org_id: str,
    body: MigrationUploadCreateIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        upload = create_upload_session(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            actor_user_id=str(user["id"]),
            source_system=body.source_system,
            source_filename=body.source_filename,
            total_chunks=body.total_chunks,
            expected_sha256=body.expected_sha256,
            client_request_id=str(body.client_request_id),
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, {"upload": upload})


@router.get("/organizations/{org_id}/migration-imports/uploads/{upload_id}")
def migration_upload_status(
    request: Request,
    org_id: str,
    upload_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        upload = get_upload_session(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            upload_id=upload_id,
        )
    except MigrationImportError as exc:
        raise _migration_http_error(exc) from exc
    return envelope(request, {"upload": upload})


@router.put("/organizations/{org_id}/migration-imports/uploads/{upload_id}/chunks/{chunk_index}")
def upload_migration_chunk(
    request: Request,
    org_id: str,
    upload_id: str,
    chunk_index: int,
    body: MigrationUploadChunkIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = save_upload_chunk(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            upload_id=upload_id,
            chunk_index=chunk_index,
            content=body.content,
            chunk_sha256=body.chunk_sha256,
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, result)


@router.post("/organizations/{org_id}/migration-imports/uploads/{upload_id}/review")
def review_migration_upload(
    request: Request,
    org_id: str,
    upload_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = review_upload(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            upload_id=upload_id,
            page=page,
            page_size=page_size,
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, result)


@router.get("/organizations/{org_id}/migration-imports/uploads/{upload_id}/review/rows")
def migration_upload_review_rows(
    request: Request,
    org_id: str,
    upload_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = get_upload_review_page(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            upload_id=upload_id,
            page=page,
            page_size=page_size,
        )
    except MigrationImportError as exc:
        raise _migration_http_error(exc) from exc
    return envelope(request, result)


@router.post("/organizations/{org_id}/migration-imports/uploads/{upload_id}/apply")
def apply_migration_upload(
    request: Request,
    org_id: str,
    upload_id: str,
    body: MigrationUploadApplyIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = apply_upload(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            actor_user_id=str(user["id"]),
            upload_id=upload_id,
            review_hash=body.review_hash,
            client_request_id=str(body.client_request_id),
            confirmed=body.confirmed,
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, result)


@router.post("/organizations/{org_id}/migration-imports/dry-run")
def review_migration_import(
    request: Request,
    org_id: str,
    body: MigrationDryRunIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
    try:
        result = dry_run_migration_csv(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            source_system=body.source_system,
            csv_text=body.csv_text,
        )
    except MigrationImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(request, result)


@router.post("/organizations/{org_id}/migration-imports/apply")
def apply_migration_import(
    request: Request,
    org_id: str,
    body: MigrationApplyIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = apply_migration_csv(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            actor_user_id=str(user["id"]),
            source_system=body.source_system,
            source_filename=body.source_filename,
            csv_text=body.csv_text,
            review_hash=body.review_hash,
            client_request_id=str(body.client_request_id),
            confirmed=body.confirmed,
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, {"batch": result})


@router.get("/organizations/{org_id}/migration-imports")
def migration_import_history(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    items = list_migration_batches(
        db,
        organization_id=org_id,
        tenant_id=str(user.get("tenant_id") or ""),
    )
    return envelope(request, {"items": items})


@router.post("/organizations/{org_id}/migration-imports/{batch_id}/rollback")
def rollback_migration_import(
    request: Request,
    org_id: str,
    batch_id: str,
    body: MigrationRollbackIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = rollback_migration_batch(
            db,
            organization_id=org_id,
            tenant_id=str(user.get("tenant_id") or ""),
            actor_user_id=str(user["id"]),
            batch_id=batch_id,
            confirmed=body.confirmed,
        )
        db.commit()
    except MigrationImportError as exc:
        db.rollback()
        raise _migration_http_error(exc) from exc
    return envelope(request, {"batch": result})


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )


def _migration_http_error(exc: MigrationImportError) -> HTTPException:
    if exc.reason_code in {"migration_batch_not_found", "migration_upload_not_found"}:
        response_status = status.HTTP_404_NOT_FOUND
    elif exc.reason_code in {
        "migration_confirmation_required",
        "migration_rollback_confirmation_required",
    }:
        response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        response_status = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=response_status,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )
