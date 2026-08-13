from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_WORDPRESS_EXECUTION,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.wordpress_automation_policy_service import (
    SUPPORTED_WORDPRESS_AUTOMATION_ACTIONS,
    WordPressAutomationPolicyError,
    get_wordpress_automation_policy,
    save_wordpress_automation_policy,
    serialize_wordpress_automation_policy,
)


router = APIRouter(prefix="/wordpress-automation", tags=["wordpress-automation"])


class BlackoutWindowIn(BaseModel):
    start: datetime
    end: datetime
    label: str = Field(default="Scheduled pause", min_length=1, max_length=120)


class WordPressAutomationPolicyIn(BaseModel):
    automation_enabled: bool = False
    emergency_stop: bool = False
    allowed_action_types: list[
        Literal[
            "create_content_brief",
            "fix_missing_title",
            "improve_internal_links",
            "publish_schema_markup",
        ]
    ] = Field(default_factory=list, max_length=4)
    allowed_url_prefixes: list[str] = Field(default_factory=list, max_length=50)
    schedule_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    schedule_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6], max_length=7)
    window_start_local: str = Field(default="00:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    window_end_local: str = Field(default="23:59", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    blackout_windows: list[BlackoutWindowIn] = Field(default_factory=list, max_length=24)
    monthly_action_limit: int = Field(default=0, ge=0, le=500)
    risk_tier_ceiling: int = Field(default=1, ge=1, le=3)
    requires_manual_approval: bool = True


def _campaign_or_404(
    db: Session,
    *,
    campaign_id: str,
    tenant_id: str,
    organization_id: str | None,
) -> Campaign:
    query = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.tenant_id == tenant_id,
    )
    if organization_id:
        query = query.filter(Campaign.organization_id == organization_id)
    campaign = query.first()
    if campaign is None or not campaign.organization_id:
        raise HTTPException(status_code=404, detail="Business not found")
    return campaign


def _require_feature(db: Session, *, organization_id: str) -> None:
    try:
        require_commercial_feature(
            db,
            organization_id=organization_id,
            feature_code=FEATURE_WORDPRESS_EXECUTION,
        )
    except CostEconomicsError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc


@router.get("/policy")
def get_policy(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(
        db,
        campaign_id=campaign_id,
        tenant_id=user["tenant_id"],
        organization_id=user.get("organization_id"),
    )
    _require_feature(db, organization_id=campaign.organization_id)
    policy = get_wordpress_automation_policy(db, campaign_id=campaign.id)
    return envelope(
        request,
        {
            "policy": serialize_wordpress_automation_policy(
                policy,
                campaign_id=campaign.id,
            ),
            "supported_action_types": sorted(SUPPORTED_WORDPRESS_AUTOMATION_ACTIONS),
            "message": (
                "Managed website updates are on."
                if policy is not None and policy.automation_enabled and not policy.emergency_stop
                else "Managed website updates are off. Manual review and rollback remain available."
            ),
        },
    )


@router.put("/policy")
def update_policy(
    request: Request,
    body: WordPressAutomationPolicyIn,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = _campaign_or_404(
        db,
        campaign_id=campaign_id,
        tenant_id=user["tenant_id"],
        organization_id=user.get("organization_id"),
    )
    _require_feature(db, organization_id=campaign.organization_id)
    actor = str(user.get("user_id") or user.get("id") or "tenant_admin")
    try:
        policy = save_wordpress_automation_policy(
            db,
            tenant_id=campaign.tenant_id,
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            actor_user_id=actor,
            values=body.model_dump(mode="json"),
        )
    except WordPressAutomationPolicyError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    write_audit_log(
        db,
        tenant_id=campaign.tenant_id,
        actor_user_id=actor,
        event_type="wordpress.automation_policy.updated",
        payload={
            "campaign_id": campaign.id,
            "organization_id": campaign.organization_id,
            "policy_id": policy.id,
            "policy_version": policy.version,
            "automation_enabled": policy.automation_enabled,
            "emergency_stop": policy.emergency_stop,
            "allowed_action_types": list(policy.allowed_action_types or []),
            "monthly_action_limit": policy.monthly_action_limit,
            "risk_tier_ceiling": policy.risk_tier_ceiling,
            "requires_manual_approval": policy.requires_manual_approval,
        },
    )
    db.commit()
    db.refresh(policy)
    return envelope(
        request,
        {
            "policy": serialize_wordpress_automation_policy(
                policy,
                campaign_id=campaign.id,
            ),
            "supported_action_types": sorted(SUPPORTED_WORDPRESS_AUTOMATION_ACTIONS),
            "message": (
                "Managed website updates are on within the saved limits."
                if policy.automation_enabled and not policy.emergency_stop
                else "Managed website updates are off. No automatic website changes will run."
            ),
        },
    )
