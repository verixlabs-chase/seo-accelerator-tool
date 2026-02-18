from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.reference_library import (
    ReferenceLibraryActivateIn,
    ReferenceLibraryActivationOut,
    ReferenceLibraryActiveOut,
    ReferenceLibraryValidateIn,
    ReferenceLibraryValidationOut,
    ReferenceLibraryVersionOut,
)
from app.services import reference_library_service

router = APIRouter(prefix="/reference-library", tags=["reference-library"])


def _ensure_loader_enabled() -> None:
    if not get_settings().reference_library_loader_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference library loader is disabled")


@router.post("/validate")
def validate_reference_library(
    request: Request,
    body: ReferenceLibraryValidateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.validate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        artifacts=body.artifacts,
        strict_mode=body.strict_mode,
    )
    return envelope(request, ReferenceLibraryValidationOut.model_validate(result).model_dump(mode="json"))


@router.post("/activate")
def activate_reference_library(
    request: Request,
    body: ReferenceLibraryActivateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.activate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        reason=body.reason,
    )
    return envelope(request, ReferenceLibraryActivationOut.model_validate(result).model_dump(mode="json"))


@router.get("/versions")
def list_reference_library_versions(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    rows = reference_library_service.list_versions(db, tenant_id=user["tenant_id"])
    return envelope(request, {"items": [ReferenceLibraryVersionOut.model_validate(row).model_dump(mode="json") for row in rows]})


@router.get("/active")
def get_active_reference_library(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.get_active(db, tenant_id=user["tenant_id"])
    return envelope(request, ReferenceLibraryActiveOut.model_validate(result).model_dump(mode="json"))
