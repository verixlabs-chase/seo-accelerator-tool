from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.data_governance import DataExportCreateIn, ProviderDisconnectCreateIn
from app.services.data_governance_service import (
    DataGovernanceError,
    create_data_export,
    download_data_export,
    list_data_exports,
)
from app.services.provider_disconnect_service import (
    ProviderDisconnectError,
    disconnect_google_provider,
    list_provider_disconnects,
    preview_google_disconnect,
)


router = APIRouter(tags=["data-governance"])


@router.post("/organizations/{org_id}/data-governance/exports")
def request_data_export(
    request: Request,
    org_id: str,
    body: DataExportCreateIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        result = create_data_export(
            db,
            tenant_id=str(user.get("tenant_id") or ""),
            organization_id=org_id,
            actor_user_id=str(user["id"]),
            client_request_id=str(body.client_request_id),
        )
        db.commit()
    except DataGovernanceError as exc:
        db.rollback()
        raise _governance_http_error(exc) from exc
    return envelope(request, {"export": result})


@router.get("/organizations/{org_id}/data-governance/exports")
def data_export_history(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    items = list_data_exports(
        db,
        tenant_id=str(user.get("tenant_id") or ""),
        organization_id=org_id,
    )
    return envelope(request, {"items": items})


@router.get("/organizations/{org_id}/data-governance/exports/{export_id}/download")
def download_account_export(
    org_id: str,
    export_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> Response:
    _assert_org_scope(user, org_id)
    try:
        content, filename = download_data_export(
            db,
            tenant_id=str(user.get("tenant_id") or ""),
            organization_id=org_id,
            actor_user_id=str(user["id"]),
            export_id=export_id,
        )
        db.commit()
    except DataGovernanceError as exc:
        db.rollback()
        raise _governance_http_error(exc) from exc
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/organizations/{org_id}/data-governance/provider-disconnects/google/preview")
def google_disconnect_preview(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    preview = preview_google_disconnect(
        db,
        tenant_id=str(user.get("tenant_id") or ""),
        organization_id=org_id,
    )
    return envelope(request, {"preview": preview})


@router.get("/organizations/{org_id}/data-governance/provider-disconnects")
def provider_disconnect_history(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    items = list_provider_disconnects(
        db,
        tenant_id=str(user.get("tenant_id") or ""),
        organization_id=org_id,
    )
    return envelope(request, {"items": items})


@router.post("/organizations/{org_id}/data-governance/provider-disconnects")
def disconnect_provider(
    request: Request,
    org_id: str,
    body: ProviderDisconnectCreateIn,
    user: dict = Depends(require_org_role({"org_owner"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        if body.provider_name != "google":
            raise ProviderDisconnectError(
                "This provider cannot be disconnected here.",
                reason_code="provider_disconnect_not_supported",
                status_code=400,
            )
        result = disconnect_google_provider(
            db,
            tenant_id=str(user.get("tenant_id") or ""),
            organization_id=org_id,
            actor_user_id=str(user["id"]),
            client_request_id=str(body.client_request_id),
            confirmation=body.confirmation,
        )
        db.commit()
    except ProviderDisconnectError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(request, {"disconnect": result})


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )


def _governance_http_error(exc: DataGovernanceError) -> HTTPException:
    if exc.reason_code == "data_export_not_found":
        response_status = status.HTTP_404_NOT_FOUND
    elif exc.reason_code == "data_export_expired":
        response_status = status.HTTP_410_GONE
    else:
        response_status = status.HTTP_409_CONFLICT
    return HTTPException(
        status_code=response_status,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )
