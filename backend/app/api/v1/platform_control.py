from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.provider_health import ProviderHealthState
from app.models.provider_policy import ProviderPolicy
from app.models.provider_quota import ProviderQuotaState
from app.services.audit_service import write_audit_log

ALLOWED_PLAN_TYPES = {"internal_anchor", "standard", "enterprise"}
ALLOWED_BILLING_MODES = {"platform_sponsored", "subscription", "custom_contract"}
ALLOWED_ORG_STATUSES = {"active", "suspended", "archived"}

router = APIRouter(tags=["platform-control"])


class PlanPatchIn(BaseModel):
    plan_type: str = Field(...)


class BillingPatchIn(BaseModel):
    billing_mode: str = Field(...)


class StatusPatchIn(BaseModel):
    status: str = Field(...)


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
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    org = _org_or_404(db, organization_id)
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
            "provider_policies": [
                {"provider_name": row.provider_name, "credential_mode": row.credential_mode, "updated_at": row.updated_at.isoformat()}
                for row in policies
            ],
        },
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
    org = _org_or_404(db, organization_id)
    previous = org.plan_type
    org.plan_type = body.plan_type
    org.updated_at = datetime.now(UTC)
    write_audit_log(
        db,
        tenant_id=org.id,
        actor_user_id=user["id"],
        event_type="platform.org.plan.updated",
        payload={"organization_id": org.id, "before": previous, "after": org.plan_type},
    )
    db.commit()
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
