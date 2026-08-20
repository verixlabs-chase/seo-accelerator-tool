from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.core.config import get_settings
from app.core.security import set_auth_cookies
from app.db.session import get_db, set_session_security_context
from app.schemas.enterprise_client_invitation import (
    EnterpriseClientInvitationAcceptIn,
    EnterpriseClientInvitationCreateIn,
    EnterpriseClientInvitationRevokeIn,
)
from app.services import auth_service, enterprise_client_invitation_service
from app.services.cost_economics_service import CostEconomicsError


router = APIRouter(prefix="/enterprise/client-invitations", tags=["enterprise-client-invitations"])
public_router = APIRouter(prefix="/client-invitations", tags=["enterprise-client-invitations"])
owner = require_org_role({"org_owner"})


@router.get("")
def get_client_invitations(
    request: Request,
    user: dict = Depends(owner),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = enterprise_client_invitation_service.list_client_invitations(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
        )
    except (enterprise_client_invitation_service.EnterpriseClientInvitationError, CostEconomicsError) as exc:
        _raise_invitation_error(exc)
    return envelope(request, payload)


@router.post("")
def post_client_invitation(
    request: Request,
    body: EnterpriseClientInvitationCreateIn,
    user: dict = Depends(owner),
    db: Session = Depends(get_db),
) -> dict:
    try:
        item, token, created = enterprise_client_invitation_service.create_client_invitation(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            actor_user_id=str(user["id"]),
            email=body.email,
            location_group_id=body.location_group_id,
            expires_in_days=body.expires_in_days,
        )
        db.commit()
    except (enterprise_client_invitation_service.EnterpriseClientInvitationError, CostEconomicsError) as exc:
        db.rollback()
        _raise_invitation_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "That invitation changed at the same time. Refresh and try again.",
                "reason_code": "client_invitation_conflict",
            },
        ) from exc
    base_url = (get_settings().customer_app_base_url or get_settings().public_base_url).strip().rstrip("/")
    return envelope(
        request,
        {
            "item": item,
            "created": created,
            "setup_url": f"{base_url}/client-invite/{token}",
            "truth": {
                "setup_url_shown_once": True,
                "password_shared_with_owner": False,
            },
        },
    )


@router.post("/{invitation_id}/revoke")
def post_client_invitation_revoke(
    invitation_id: str,
    request: Request,
    body: EnterpriseClientInvitationRevokeIn,
    user: dict = Depends(owner),
    db: Session = Depends(get_db),
) -> dict:
    try:
        item = enterprise_client_invitation_service.revoke_client_invitation(
            db,
            tenant_id=str(user["tenant_id"]),
            organization_id=str(user["organization_id"]),
            actor_user_id=str(user["id"]),
            invitation_id=invitation_id,
            expected_version=body.expected_version,
        )
        db.commit()
    except (enterprise_client_invitation_service.EnterpriseClientInvitationError, CostEconomicsError) as exc:
        db.rollback()
        _raise_invitation_error(exc)
    return envelope(request, {"item": item})


@public_router.get("/{token}")
def get_client_invitation_preview(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    _public_security_context(db)
    try:
        payload = enterprise_client_invitation_service.preview_client_invitation(db, token=token)
    except (enterprise_client_invitation_service.EnterpriseClientInvitationError, CostEconomicsError) as exc:
        _raise_invitation_error(exc)
    return envelope(request, payload)


@public_router.post("/{token}/accept")
def post_client_invitation_accept(
    token: str,
    body: EnterpriseClientInvitationAcceptIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    _public_security_context(db)
    try:
        accepted = enterprise_client_invitation_service.accept_client_invitation(
            db,
            token=token,
            password=body.password,
        )
        db.commit()
        payload = auth_service.login(
            db,
            accepted["email"],
            body.password,
            accepted["organization_id"],
        )
    except (enterprise_client_invitation_service.EnterpriseClientInvitationError, CostEconomicsError) as exc:
        db.rollback()
        _raise_invitation_error(exc)
    request.state.tenant_id = payload["user"]["organization_id"]
    set_auth_cookies(
        response,
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
    )
    return envelope(
        request,
        {
            "expires_in": payload["expires_in"],
            "user": payload["user"],
        },
    )


def _public_security_context(db: Session) -> None:
    set_session_security_context(
        db,
        tenant_id=None,
        organization_id=None,
        user_id="public-client-invitation",
        platform_access=True,
    )


def _raise_invitation_error(exc: Exception) -> None:
    raise HTTPException(
        status_code=int(getattr(exc, "status_code", 400)),
        detail={
            "message": str(exc),
            "reason_code": str(getattr(exc, "reason_code", "client_invitation_failed")),
        },
    ) from exc
