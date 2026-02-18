from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.tenant import TenantCreateRequest, TenantOut, TenantStatusTransitionRequest
from app.services import lifecycle_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("")
def create_tenant(
    request: Request,
    body: TenantCreateRequest,
    _user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = lifecycle_service.create_tenant(db, name=body.name)
    return envelope(request, TenantOut.model_validate(row).model_dump(mode="json"))


@router.get("")
def list_tenants(
    request: Request,
    _user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = lifecycle_service.list_tenants(db)
    return envelope(request, {"items": [TenantOut.model_validate(row).model_dump(mode="json") for row in rows]})


@router.patch("/{tenant_id}/status")
def transition_tenant_status(
    request: Request,
    tenant_id: str,
    body: TenantStatusTransitionRequest,
    _user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = lifecycle_service.transition_tenant_status(db, tenant_id=tenant_id, target_status=body.target_status)
    return envelope(request, TenantOut.model_validate(row).model_dump(mode="json"))
