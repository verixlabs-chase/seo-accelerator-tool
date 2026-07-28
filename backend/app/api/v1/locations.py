from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.location import Location
from app.models.portfolio import Portfolio
from app.models.sub_account import SubAccount
from app.schemas.location import LocationCreateIn, LocationOut, LocationUpdateRequest
from app.services.location_service import LocationWriteService


router = APIRouter(tags=["locations"])
_write_service = LocationWriteService()


@router.post("/organizations/{org_id}/locations")
def create_location(
    request: Request,
    org_id: str,
    body: LocationCreateIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    business_location = _resolve_business_location(
        db,
        org_id=org_id,
        business_location_id=body.business_location_id,
    )
    inherited_subaccount_id = business_location.sub_account_id if business_location else None
    if (
        body.sub_account_id is not None
        and inherited_subaccount_id is not None
        and body.sub_account_id != inherited_subaccount_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Execution location and business location must use the same subaccount.",
                "reason_code": "business_location_subaccount_mismatch",
            },
        )
    sub_account = _resolve_active_subaccount(
        db,
        org_id,
        sub_account_id=body.sub_account_id or inherited_subaccount_id,
    )
    portfolio = _resolve_business_location_portfolio(
        db,
        org_id=org_id,
        business_location_id=body.business_location_id,
    )
    campaign = _resolve_campaign(
        db,
        org_id=org_id,
        campaign_id=body.campaign_id,
        sub_account_id=sub_account.id,
        business_location_id=body.business_location_id,
    )

    try:
        payload = _write_service.create_location(
            db,
            organization_id=org_id,
            sub_account_id=sub_account.id,
            portfolio_id=portfolio.id if portfolio else None,
            campaign_id=campaign.id if campaign else None,
            location_code=_build_location_code(),
            name=body.name,
            country_code=body.country_code,
            region=body.region,
            city=body.city,
            lat=body.lat,
            lng=body.lng,
            business_location_id=body.business_location_id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise

    return envelope(request, {"location": LocationOut.model_validate(payload).model_dump(mode="json")})


@router.get("/organizations/{org_id}/locations")
def list_locations(
    request: Request,
    org_id: str,
    sub_account_id: str | None = Query(default=None),
    business_location_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    query = db.query(Location).filter(Location.organization_id == org_id)
    if sub_account_id is not None:
        query = query.filter(Location.sub_account_id == sub_account_id)
    if business_location_id is not None:
        query = query.filter(Location.business_location_id == business_location_id)
    if status_filter is not None:
        query = query.filter(Location.status == status_filter)
    rows = query.order_by(Location.created_at.asc(), Location.id.asc()).all()
    return envelope(
        request,
        {"items": [LocationOut.model_validate(row).model_dump(mode="json") for row in rows]},
    )


@router.patch("/organizations/{org_id}/locations/{location_id}")
def patch_location(
    request: Request,
    org_id: str,
    location_id: str,
    body: LocationUpdateRequest,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    current = db.execute(
        sa.text(
            '''
            SELECT id, organization_id
            FROM locations
            WHERE id = :location_id
            '''
        ),
        {"location_id": location_id},
    ).mappings().first()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Location not found.", "reason_code": "location_not_found"},
        )
    if current["organization_id"] != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Location is outside organization scope.",
                "reason_code": "location_scope_mismatch",
            },
        )

    update_data: dict[str, object] = {
        "location_id": location_id,
        "organization_id": org_id,
    }
    if body.name is not None:
        update_data["name"] = body.name
    if "business_location_id" in body.model_fields_set:
        update_data["business_location_id"] = body.business_location_id
        if body.business_location_id is None:
            update_data["portfolio_id"] = None
        else:
            business_location = _resolve_business_location(
                db,
                org_id=org_id,
                business_location_id=body.business_location_id,
            )
            if business_location is not None and business_location.sub_account_id is not None:
                update_data["sub_account_id"] = business_location.sub_account_id
            portfolio = _resolve_business_location_portfolio(
                db,
                org_id=org_id,
                business_location_id=body.business_location_id,
            )
            update_data["portfolio_id"] = portfolio.id if portfolio else None

    try:
        payload = _write_service.update_location(db, **update_data)
        db.commit()
    except HTTPException:
        db.rollback()
        raise

    return envelope(request, {"location": LocationOut.model_validate(payload).model_dump(mode="json")})


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )


def _resolve_active_subaccount(
    db: Session,
    org_id: str,
    *,
    sub_account_id: str | None,
) -> SubAccount:
    query = db.query(SubAccount).filter(
        SubAccount.organization_id == org_id,
        SubAccount.status == "active",
    )
    if sub_account_id is not None:
        query = query.filter(SubAccount.id == sub_account_id)
    else:
        query = query.order_by(SubAccount.created_at.asc())
    sub_account = query.first()
    if sub_account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "At least one active SubAccount is required before creating a Location.",
                "reason_code": "subaccount_required_for_location_create",
            },
        )
    return sub_account


def _resolve_business_location(
    db: Session,
    *,
    org_id: str,
    business_location_id: str | None,
) -> BusinessLocation | None:
    if business_location_id is None:
        return None
    row = db.query(BusinessLocation).filter(BusinessLocation.id == business_location_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Business location not found.", "reason_code": "business_location_not_found"},
        )
    if row.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Business location is outside organization scope.",
                "reason_code": "business_location_org_mismatch",
            },
        )
    return row


def _resolve_business_location_portfolio(
    db: Session,
    *,
    org_id: str,
    business_location_id: str | None,
) -> Portfolio | None:
    if business_location_id is None:
        return None
    return (
        db.query(Portfolio)
        .filter(
            Portfolio.organization_id == org_id,
            Portfolio.business_location_id == business_location_id,
        )
        .first()
    )


def _resolve_campaign(
    db: Session,
    *,
    org_id: str,
    campaign_id: str | None,
    sub_account_id: str,
    business_location_id: str | None,
) -> Campaign | None:
    if campaign_id is None:
        return None
    row = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Campaign not found.", "reason_code": "campaign_not_found"},
        )
    if row.sub_account_id not in {None, sub_account_id}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Campaign and execution location must use the same subaccount.",
                "reason_code": "campaign_subaccount_mismatch",
            },
        )
    if row.business_location_id not in {None, business_location_id}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Campaign and execution location must use the same business location.",
                "reason_code": "campaign_business_location_mismatch",
            },
        )
    return row


def _build_location_code() -> str:
    return f"loc-{uuid.uuid4().hex[:12]}"
