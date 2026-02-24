from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_platform_owner
from app.api.response import envelope
from app.db.session import get_db
from app.services.audit_service import write_audit_log
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    upsert_organization_provider_credentials,
    upsert_platform_provider_credentials,
    upsert_provider_policy,
)


class ProviderCredentialUpsertIn(BaseModel):
    auth_mode: str = Field(...)
    credentials: dict = Field(default_factory=dict)


class ProviderPolicyUpsertIn(BaseModel):
    credential_mode: str = Field(...)


tenant_router = APIRouter(tags=["provider-credentials"])
control_plane_router = APIRouter(tags=["provider-credentials"])


@control_plane_router.put("/platform/provider-credentials/{provider_name}")
def upsert_platform_credentials(
    request: Request,
    provider_name: str,
    body: ProviderCredentialUpsertIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    row = upsert_platform_provider_credentials(
        db,
        provider_name=provider_name,
        auth_mode=body.auth_mode,
        credentials=body.credentials,
    )
    write_audit_log(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        event_type="platform.provider.credentials.upserted",
        payload={"provider_name": provider_name, "auth_mode": body.auth_mode},
    )
    db.commit()
    return envelope(
        request,
        {
            "provider_name": row.provider_name,
            "auth_mode": row.auth_mode,
            "updated_at": row.updated_at.isoformat() if row.updated_at else datetime.now(UTC).isoformat(),
        },
    )


@tenant_router.put("/organizations/{organization_id}/provider-credentials/{provider_name}")
def upsert_organization_credentials(
    request: Request,
    organization_id: str,
    provider_name: str,
    body: ProviderCredentialUpsertIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    if user.get("organization_id") != organization_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
    try:
        row = upsert_organization_provider_credentials(
            db,
            organization_id=organization_id,
            provider_name=provider_name,
            auth_mode=body.auth_mode,
            credentials=body.credentials,
        )
    except ProviderCredentialConfigurationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "organization_id": row.organization_id,
            "provider_name": row.provider_name,
            "auth_mode": row.auth_mode,
            "updated_at": row.updated_at.isoformat() if row.updated_at else datetime.now(UTC).isoformat(),
        },
    )


@control_plane_router.put("/platform/organizations/{organization_id}/provider-policies/{provider_name}")
def upsert_policy(
    request: Request,
    organization_id: str,
    provider_name: str,
    body: ProviderPolicyUpsertIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = upsert_provider_policy(
            db,
            organization_id=organization_id,
            provider_name=provider_name,
            credential_mode=body.credential_mode,
        )
    except ProviderCredentialConfigurationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=user["id"],
        event_type="platform.provider.policy.upserted",
        payload={"organization_id": organization_id, "provider_name": provider_name, "credential_mode": body.credential_mode},
    )
    db.commit()
    return envelope(
        request,
        {
            "organization_id": row.organization_id,
            "provider_name": row.provider_name,
            "credential_mode": row.credential_mode,
            "updated_at": row.updated_at.isoformat() if row.updated_at else datetime.now(UTC).isoformat(),
        },
    )
