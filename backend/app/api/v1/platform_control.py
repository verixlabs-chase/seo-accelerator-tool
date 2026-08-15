from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_platform_role
from app.api.response import envelope, public_data_source_label
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.provider_health import ProviderHealthState
from app.models.provider_policy import ProviderPolicy
from app.models.provider_quota import ProviderQuotaState
from app.models.tenant import Tenant
from app.services.audit_service import write_audit_log
from app.services.cost_economics_service import CostEconomicsError, resolve_plan_economics
from app.services.commercial_plan_service import apply_commercial_plan
from app.services import reputation_response_execution_service

ALLOWED_PLAN_TYPES = {
    "internal_anchor",
    "standard",
    "pro",
    "solo",
    "multi_location",
    "enterprise",
}
ALLOWED_BILLING_MODES = {"platform_sponsored", "subscription", "custom_contract"}
ALLOWED_ORG_STATUSES = {"active", "suspended", "archived"}
INTERNAL_ACCEPTANCE_ORG_NAME = "internal_anchor_enterprise_seed"

router = APIRouter(tags=["platform-control"])


class PlanPatchIn(BaseModel):
    plan_type: str = Field(...)


class BillingPatchIn(BaseModel):
    billing_mode: str = Field(...)


class StatusPatchIn(BaseModel):
    status: str = Field(...)


class ReviewReplyCapabilityIn(BaseModel):
    connection_id: str = Field(..., min_length=1, max_length=36)
    proof_reference: str = Field(..., min_length=8, max_length=2000)


class ReviewReplyCapabilityRevokeIn(BaseModel):
    connection_id: str = Field(..., min_length=1, max_length=36)
    reason: str = Field(default="manually_revoked", min_length=1, max_length=120)


def _org_or_404(db: Session, organization_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


def _serialize_org(org: Organization) -> dict:
    return {
        "id": org.id,
        "name": org.name,
        "plan_type": org.plan_type,
        "billing_mode": org.billing_mode,
        "status": org.status,
        "created_at": org.created_at.isoformat() if org.created_at else None,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
    }


@router.get("/platform/orgs")
def list_platform_orgs(
    request: Request,
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(Organization).order_by(Organization.created_at.desc()).all()
    return envelope(request, {"items": [_serialize_org(row) for row in rows]})


@router.get("/platform/orgs/{organization_id}")
def get_platform_org(
    request: Request,
    organization_id: str,
    user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    org = _org_or_404(db, organization_id)
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user["user_id"],
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == "active",
        )
        .first()
    )
    policies = (
        db.query(ProviderPolicy)
        .filter(ProviderPolicy.organization_id == organization_id)
        .order_by(ProviderPolicy.provider_name.asc())
        .all()
    )
    return envelope(
        request,
        {
            "organization": _serialize_org(org),
            "current_user_membership": (
                {
                    "organization_id": membership.organization_id,
                    "role": membership.role,
                    "status": membership.status,
                }
                if membership is not None
                else None
            ),
            "can_grant_internal_access": (
                user.get("platform_role") == "platform_owner"
                and org.name == INTERNAL_ACCEPTANCE_ORG_NAME
                and org.billing_mode == "platform_sponsored"
                and org.plan_type in {"enterprise", "internal_anchor"}
                and org.status == "active"
            ),
            "provider_policies": [
                {
                    "provider_name": row.provider_name,
                    "data_source_name": public_data_source_label(row.provider_name),
                    "credential_mode": row.credential_mode,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in policies
            ],
        },
    )


@router.post("/platform/orgs/{organization_id}/internal-access")
def grant_internal_workspace_access(
    request: Request,
    organization_id: str,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    """Grant the platform owner access to the seeded, sponsored acceptance workspace."""
    org = _org_or_404(db, organization_id)
    if not (
        org.name == INTERNAL_ACCEPTANCE_ORG_NAME
        and org.billing_mode == "platform_sponsored"
        and org.plan_type in {"enterprise", "internal_anchor"}
        and org.status == "active"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Internal access is only available for the active sponsored acceptance workspace.",
        )

    tenant = db.get(Tenant, org.id)
    if tenant is None:
        tenant = Tenant(
            id=org.id,
            name=f"{INTERNAL_ACCEPTANCE_ORG_NAME}-{org.id[:8]}",
            status="Active",
        )
        db.add(tenant)
        db.flush()

    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user["user_id"],
            OrganizationMembership.organization_id == org.id,
        )
        .first()
    )
    if membership is None:
        membership = OrganizationMembership(
            user_id=user["user_id"],
            organization_id=org.id,
            role="org_owner",
            status="active",
        )
        db.add(membership)
    else:
        membership.role = "org_owner"
        membership.status = "active"

    write_audit_log(
        db,
        tenant_id=org.id,
        actor_user_id=user["user_id"],
        event_type="platform.org.internal_access.granted",
        payload={"organization_id": org.id, "role": membership.role},
    )
    db.commit()
    db.refresh(membership)
    return envelope(
        request,
        {
            "organization": _serialize_org(org),
            "membership": {
                "organization_id": membership.organization_id,
                "role": membership.role,
                "status": membership.status,
            },
        },
    )


@router.post("/platform/orgs/{organization_id}/review-reply-capability")
def authorize_review_reply_capability(
    request: Request,
    organization_id: str,
    body: ReviewReplyCapabilityIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _org_or_404(db, organization_id)
    row = reputation_response_execution_service.authorize_validation(
        db,
        organization_id=organization_id,
        connection_id=body.connection_id,
        authorized_by_user_id=user["id"],
        proof_reference=body.proof_reference,
    )
    write_audit_log(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=user["id"],
        event_type="platform.review_reply_capability.validation_authorized",
        payload={
            "organization_id": organization_id,
            "connection_id": body.connection_id,
            "capability": row.capability,
            "status": row.status,
        },
    )
    db.commit()
    return envelope(
        request,
        {"capability": reputation_response_execution_service.serialize_capability(row)},
    )


@router.delete("/platform/orgs/{organization_id}/review-reply-capability")
def revoke_review_reply_capability(
    request: Request,
    organization_id: str,
    body: ReviewReplyCapabilityRevokeIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _org_or_404(db, organization_id)
    row = reputation_response_execution_service.revoke_capability(
        db,
        organization_id=organization_id,
        connection_id=body.connection_id,
        revoked_by_user_id=user["id"],
        reason=body.reason,
    )
    write_audit_log(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=user["id"],
        event_type="platform.review_reply_capability.revoked",
        payload={
            "organization_id": organization_id,
            "connection_id": body.connection_id,
            "capability": row.capability,
            "reason": body.reason,
        },
    )
    db.commit()
    return envelope(
        request,
        {"capability": reputation_response_execution_service.serialize_capability(row)},
    )
@router.patch("/platform/orgs/{organization_id}/plan")
def patch_org_plan(
    request: Request,
    organization_id: str,
    body: PlanPatchIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    if body.plan_type not in ALLOWED_PLAN_TYPES:
        raise HTTPException(status_code=400, detail="Invalid plan_type")
    try:
        resolve_plan_economics(body.plan_type)
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    try:
        org, materialization = apply_commercial_plan(
            db,
            organization_id=organization_id,
            plan_code=body.plan_type,
        )
        write_audit_log(
            db,
            tenant_id=org.id,
            actor_user_id=user["id"],
            event_type="platform.org.plan.updated",
            payload={
                "organization_id": org.id,
                "before": materialization["previous_plan_code"],
                "after": org.plan_type,
                "tier_version": materialization["tier_version"],
            },
        )
        db.commit()
    except CostEconomicsError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    db.refresh(org)
    return envelope(request, {"organization": _serialize_org(org)})


@router.patch("/platform/orgs/{organization_id}/billing")
def patch_org_billing(
    request: Request,
    organization_id: str,
    body: BillingPatchIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    if body.billing_mode not in ALLOWED_BILLING_MODES:
        raise HTTPException(status_code=400, detail="Invalid billing_mode")
    org = _org_or_404(db, organization_id)
    previous = org.billing_mode
    org.billing_mode = body.billing_mode
    org.updated_at = datetime.now(UTC)
    write_audit_log(
        db,
        tenant_id=org.id,
        actor_user_id=user["id"],
        event_type="platform.org.billing.updated",
        payload={"organization_id": org.id, "before": previous, "after": org.billing_mode},
    )
    db.commit()
    db.refresh(org)
    return envelope(request, {"organization": _serialize_org(org)})


@router.patch("/platform/orgs/{organization_id}/status")
def patch_org_status(
    request: Request,
    organization_id: str,
    body: StatusPatchIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    if body.status not in ALLOWED_ORG_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    org = _org_or_404(db, organization_id)
    previous = org.status
    org.status = body.status
    org.updated_at = datetime.now(UTC)
    write_audit_log(
        db,
        tenant_id=org.id,
        actor_user_id=user["id"],
        event_type="platform.org.status.updated",
        payload={"organization_id": org.id, "before": previous, "after": org.status},
    )
    db.commit()
    db.refresh(org)
    return envelope(request, {"organization": _serialize_org(org)})


@router.get("/platform/provider-health/summary")
def platform_provider_health_summary(
    request: Request,
    environment: str = Query(default="production"),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    health_rows = db.query(ProviderHealthState).filter(ProviderHealthState.environment == environment).all()
    quotas = db.query(ProviderQuotaState).filter(ProviderQuotaState.environment == environment).all()
    orgs = {row.id: row for row in db.query(Organization).all()}

    latest_quota_by_key: dict[tuple[str, str, str], ProviderQuotaState] = {}
    now = datetime.now(UTC)
    for quota in quotas:
        if quota.window_end.replace(tzinfo=UTC) < now if quota.window_end.tzinfo is None else quota.window_end.astimezone(UTC) < now:
            continue
        key = (quota.tenant_id, quota.provider_name, quota.capability)
        existing: ProviderQuotaState | None = latest_quota_by_key.get(key)
        if existing is None or quota.window_end > existing.window_end:
            latest_quota_by_key[key] = quota

    items: list[dict] = []
    for row in health_rows:
        quota_row = latest_quota_by_key.get((row.tenant_id, row.provider_name, row.capability))
        org = orgs.get(row.tenant_id)
        items.append(
            {
                "organization_id": row.tenant_id,
                "organization_name": org.name if org else None,
                "provider_name": row.provider_name,
                "data_source_name": public_data_source_label(row.provider_name),
                "capability": row.capability,
                "breaker_state": row.breaker_state,
                "consecutive_failures": row.consecutive_failures,
                "success_rate_1h": row.success_rate_1h,
                "p95_latency_ms_1h": row.p95_latency_ms_1h,
                "last_error_code": row.last_error_code,
                "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
                "remaining_quota": quota_row.remaining_count if quota_row else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
    return envelope(request, {"environment": environment, "generated_at": datetime.now(UTC).isoformat(), "items": items})


@router.get("/platform/audit")
def list_platform_audit(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    items: list[dict] = []
    for row in rows:
        payload: dict = {}
        try:
            parsed = json.loads(row.payload_json)
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001
            payload = {}
        items.append(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "actor_user_id": row.actor_user_id,
                "event_type": row.event_type,
                "payload": payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return envelope(request, {"items": items})
