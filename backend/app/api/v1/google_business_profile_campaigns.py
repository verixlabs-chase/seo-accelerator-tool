from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.google_business_profile_campaign import GoogleBusinessProfileCampaign
from app.models.portfolio_targeting import PortfolioTargetSnapshot
from app.schemas.google_business_profile_campaign import (
    ProfileCampaignCreateIn,
    ProfileCampaignDecisionIn,
)
from app.services.google_business_profile_campaign_service import (
    ProfileCampaignError,
    approve_profile_campaign_hold,
    create_profile_campaign,
    get_profile_campaign,
    list_profile_campaigns,
    run_profile_campaign_preflight,
    serialize_profile_campaign,
)
from app.services.portfolio_access_service import (
    PortfolioAccessError,
    accessible_location_group_ids,
    require_location_group_access,
)


router = APIRouter(tags=["google-business-profile-campaigns"])
portfolio_member = require_org_role({"org_user"})


@router.get("/organizations/{organization_id}/profile-campaigns")
def get_profile_campaigns(
    request: Request,
    organization_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    group_ids = accessible_location_group_ids(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        required_access_role="viewer",
    )
    return envelope(
        request,
        {
            "items": list_profile_campaigns(
                db,
                organization_id=organization_id,
                limit=limit,
                location_group_ids=group_ids,
            ),
            "provider_changes_enabled": False,
        },
    )


@router.post(
    "/organizations/{organization_id}/profile-campaigns",
    status_code=status.HTTP_201_CREATED,
)
def post_profile_campaign(
    request: Request,
    organization_id: str,
    body: ProfileCampaignCreateIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_snapshot_access(
            db,
            user=user,
            organization_id=organization_id,
            target_snapshot_id=body.target_snapshot_id,
            required_access_role="operator",
        )
        row, created = create_profile_campaign(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            target_snapshot_id=body.target_snapshot_id,
            request_key=body.request_key,
            name=body.name,
            action_type=body.action_type,
            payload_template=body.payload_template,
            scheduled_for=body.scheduled_for,
        )
        db.commit()
        db.refresh(row)
    except ProfileCampaignError as exc:
        db.rollback()
        _raise_campaign_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "That profile-campaign request was already used for different work.",
                "reason_code": "profile_campaign_request_key_conflict",
            },
        ) from exc
    response = envelope(
        request,
        {
            "profile_campaign": serialize_profile_campaign(db, row),
            "created": created,
        },
    )
    if not created:
        response["meta"]["idempotent_replay"] = True
    return response


@router.get("/organizations/{organization_id}/profile-campaigns/{profile_campaign_id}")
def get_profile_campaign_detail(
    request: Request,
    organization_id: str,
    profile_campaign_id: str,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_campaign_access(
            db,
            user=user,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
            required_access_role="viewer",
        )
        row = get_profile_campaign(
            db,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
        )
    except ProfileCampaignError as exc:
        _raise_campaign_error(exc)
    except PortfolioAccessError as exc:
        _raise_access_error(exc)
    return envelope(request, {"profile_campaign": serialize_profile_campaign(db, row)})


@router.post(
    "/organizations/{organization_id}/profile-campaigns/{profile_campaign_id}/preflight"
)
def post_profile_campaign_preflight(
    request: Request,
    organization_id: str,
    profile_campaign_id: str,
    body: ProfileCampaignDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_campaign_access(
            db,
            user=user,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
            required_access_role="operator",
        )
        row = run_profile_campaign_preflight(
            db,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
        db.commit()
        db.refresh(row)
    except ProfileCampaignError as exc:
        db.rollback()
        _raise_campaign_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"profile_campaign": serialize_profile_campaign(db, row)})


@router.post(
    "/organizations/{organization_id}/profile-campaigns/{profile_campaign_id}/approve"
)
def post_profile_campaign_approval(
    request: Request,
    organization_id: str,
    profile_campaign_id: str,
    body: ProfileCampaignDecisionIn,
    user: dict = Depends(portfolio_member),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        _require_campaign_access(
            db,
            user=user,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
            required_access_role="approver",
        )
        row = approve_profile_campaign_hold(
            db,
            organization_id=organization_id,
            profile_campaign_id=profile_campaign_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
        )
        db.commit()
        db.refresh(row)
    except ProfileCampaignError as exc:
        db.rollback()
        _raise_campaign_error(exc)
    except PortfolioAccessError as exc:
        db.rollback()
        _raise_access_error(exc)
    return envelope(request, {"profile_campaign": serialize_profile_campaign(db, row)})


def _enforce_scope(user: dict, organization_id: str) -> None:
    enforce_organization_scope(user=user, organization_id=organization_id, allow_platform=False)


def _require_snapshot_access(
    db: Session,
    *,
    user: dict,
    organization_id: str,
    target_snapshot_id: str,
    required_access_role: str,
) -> None:
    snapshot = (
        db.query(PortfolioTargetSnapshot)
        .filter(
            PortfolioTargetSnapshot.organization_id == organization_id,
            PortfolioTargetSnapshot.id == target_snapshot_id,
        )
        .first()
    )
    if snapshot is None:
        return
    require_location_group_access(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        location_group_id=snapshot.location_group_id,
        required_access_role=required_access_role,
    )


def _require_campaign_access(
    db: Session,
    *,
    user: dict,
    organization_id: str,
    profile_campaign_id: str,
    required_access_role: str,
) -> None:
    row = (
        db.query(PortfolioTargetSnapshot.location_group_id)
        .join(
            GoogleBusinessProfileCampaign,
            GoogleBusinessProfileCampaign.target_snapshot_id == PortfolioTargetSnapshot.id,
        )
        .filter(
            GoogleBusinessProfileCampaign.organization_id == organization_id,
            GoogleBusinessProfileCampaign.id == profile_campaign_id,
            PortfolioTargetSnapshot.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        return
    require_location_group_access(
        db,
        organization_id=organization_id,
        user_id=user["id"],
        org_role=str(user.get("org_role") or ""),
        location_group_id=row[0],
        required_access_role=required_access_role,
    )


def _raise_campaign_error(exc: ProfileCampaignError) -> None:
    messages = {
        "organization_not_found": "The business account was not found.",
        "target_snapshot_not_found": "The saved location list was not found.",
        "profile_campaign_not_found": "That profile campaign was not found.",
        "profile_campaign_upgrade_required": "Profile campaigns are available on Growth and Enterprise plans.",
        "profile_campaign_target_action_mismatch": "Create a new location preview for this type of profile work.",
        "profile_campaign_request_key_conflict": "That request key already belongs to different profile work.",
        "profile_campaign_version_conflict": "This profile campaign changed. Refresh before trying again.",
        "profile_campaign_preflight_locked": "Approved profile campaigns cannot be changed. Create a new draft instead.",
        "profile_campaign_target_changed": "The approved location list changed. Create a new preview.",
        "profile_campaign_not_ready_for_approval": "Run the checks and resolve at least one location before approval.",
        "profile_campaign_approval_snapshot_changed": "The preview changed. Run the checks again before approval.",
        "profile_campaign_unknown_placeholder": "The draft uses a location detail that InsightOS does not support.",
        "profile_campaign_schedule_must_be_future": "Choose a future date and time.",
        "profile_campaign_asset_rights_required": "Confirm that this business can use the photo.",
        "profile_campaign_secure_asset_required": "Use a secure https address for the photo.",
        "profile_campaign_asset_checksum_invalid": "The photo checksum is not valid.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "This profile campaign could not be saved."),
            "reason_code": exc.reason_code,
        },
    )


def _raise_access_error(exc: PortfolioAccessError) -> None:
    messages = {
        "portfolio_access_group_required": "Choose one of your assigned location groups.",
        "portfolio_access_denied": "You are not assigned to this location group.",
        "portfolio_access_operator_required": "Operator access is required for this location group.",
        "portfolio_access_approval_required": "Approver access is required for this profile campaign.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "This location-group action is not allowed."),
            "reason_code": exc.reason_code,
        },
    )
