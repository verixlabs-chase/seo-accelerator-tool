from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import enforce_organization_scope, require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.portfolio_targeting import (
    LocationGroupCreateIn,
    LocationGroupUpdateIn,
    TargetSnapshotCreateIn,
)
from app.services.portfolio_targeting_service import (
    PortfolioTargetingError,
    create_location_group,
    create_target_snapshot,
    list_location_groups,
    list_target_snapshots,
    serialize_location_group,
    serialize_target_snapshot,
    update_location_group,
)


router = APIRouter(tags=["portfolio-targeting"])
owner_or_admin = require_org_role({"org_owner", "org_admin"})


@router.get("/organizations/{organization_id}/location-groups")
def get_location_groups(
    request: Request,
    organization_id: str,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    return envelope(
        request,
        {"items": list_location_groups(db, organization_id=organization_id)},
    )


@router.post(
    "/organizations/{organization_id}/location-groups",
    status_code=status.HTTP_201_CREATED,
)
def post_location_group(
    request: Request,
    organization_id: str,
    body: LocationGroupCreateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        group = create_location_group(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            name=body.name,
            description=body.description,
            location_ids=body.location_ids,
        )
        db.commit()
        db.refresh(group)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "That saved group conflicts with an existing group.",
                "reason_code": "location_group_conflict",
            },
        ) from exc
    return envelope(request, {"location_group": serialize_location_group(db, group)})


@router.patch("/organizations/{organization_id}/location-groups/{location_group_id}")
def patch_location_group(
    request: Request,
    organization_id: str,
    location_group_id: str,
    body: LocationGroupUpdateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        group = update_location_group(
            db,
            organization_id=organization_id,
            location_group_id=location_group_id,
            actor_user_id=user["id"],
            expected_version=body.expected_version,
            name=body.name,
            description=body.description,
            status=body.status,
            location_ids=body.location_ids,
        )
        db.commit()
        db.refresh(group)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "That saved group conflicts with an existing group.",
                "reason_code": "location_group_conflict",
            },
        ) from exc
    return envelope(request, {"location_group": serialize_location_group(db, group)})


@router.get("/organizations/{organization_id}/target-snapshots")
def get_target_snapshots(
    request: Request,
    organization_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    return envelope(
        request,
        {
            "items": list_target_snapshots(
                db,
                organization_id=organization_id,
                limit=limit,
            )
        },
    )


@router.post(
    "/organizations/{organization_id}/target-snapshots",
    status_code=status.HTTP_201_CREATED,
)
def post_target_snapshot(
    request: Request,
    organization_id: str,
    body: TargetSnapshotCreateIn,
    user: dict = Depends(owner_or_admin),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_scope(user, organization_id)
    try:
        snapshot, created = create_target_snapshot(
            db,
            organization_id=organization_id,
            actor_user_id=user["id"],
            action_key=body.action_key,
            request_key=body.request_key,
            location_group_id=body.location_group_id,
            select_all_active=body.select_all_active,
            regions=body.regions,
            included_location_ids=body.included_location_ids,
            excluded_location_ids=body.excluded_location_ids,
        )
        db.commit()
        db.refresh(snapshot)
    except PortfolioTargetingError as exc:
        db.rollback()
        _raise_targeting_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This target request was already used for a different list.",
                "reason_code": "target_request_key_conflict",
            },
        ) from exc
    response = envelope(
        request,
        {
            "target_snapshot": serialize_target_snapshot(snapshot),
            "created": created,
        },
    )
    if not created:
        response["meta"]["idempotent_replay"] = True
    return response


def _enforce_scope(user: dict, organization_id: str) -> None:
    enforce_organization_scope(
        user=user,
        organization_id=organization_id,
        allow_platform=False,
    )


def _raise_targeting_error(exc: PortfolioTargetingError) -> None:
    messages = {
        "location_group_not_found": "Saved location group not found.",
        "location_group_version_conflict": "This group changed after you opened it. Refresh before saving again.",
        "location_group_name_conflict": "A group with this name already exists.",
        "location_group_not_active": "This saved group is archived.",
        "one_or_more_locations_unavailable": "One or more locations are not available in this account.",
        "explicit_target_selection_required": "Choose a saved group or select locations before continuing.",
        "ambiguous_target_selection": "Choose either a saved group or every active location, not both.",
        "region_filter_requires_base_selection": "Choose a saved group or every active location before filtering by area.",
        "location_cannot_be_included_and_excluded": "A location cannot be both included and excluded.",
        "target_request_key_conflict": "This target request was already used for a different list.",
    }
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": messages.get(exc.reason_code, "The target list could not be saved."),
            "reason_code": exc.reason_code,
        },
    ) from exc
