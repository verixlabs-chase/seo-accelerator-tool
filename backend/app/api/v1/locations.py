from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
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
    sub_account = _resolve_active_subaccount(db, org_id)

    try:
        payload = _write_service.create_location(
            db,
            organization_id=org_id,
            sub_account_id=sub_account.id,
            location_code=_build_location_code(),
            name=body.name,
            country_code="US",
            business_location_id=body.business_location_id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise

    return envelope(request, {"location": LocationOut.model_validate(payload).model_dump(mode="json")})


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


def _resolve_active_subaccount(db: Session, org_id: str) -> SubAccount:
    sub_account = (
        db.query(SubAccount)
        .filter(
            SubAccount.organization_id == org_id,
            SubAccount.status == "active",
        )
        .order_by(SubAccount.created_at.asc())
        .first()
    )
    if sub_account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "At least one active SubAccount is required before creating a Location.",
                "reason_code": "subaccount_required_for_location_create",
            },
        )
    return sub_account


def _build_location_code() -> str:
    return f"loc-{uuid.uuid4().hex[:12]}"
