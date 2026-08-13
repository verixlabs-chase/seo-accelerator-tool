from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.migration_import import (
    MigrationApplyIn,
    MigrationDryRunIn,
    MigrationRollbackIn,
)
from app.services.migration_import_service import (
    MigrationImportError,
    apply_migration_csv,
    dry_run_migration_csv,
    list_migration_batches,
    rollback_migration_batch,
)


router = APIRouter(tags=["migration-imports"])


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
    if exc.reason_code == "migration_batch_not_found":
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
