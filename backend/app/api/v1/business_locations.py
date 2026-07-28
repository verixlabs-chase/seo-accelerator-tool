from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.business_location import BusinessLocation
from app.schemas.business_location import (
    BusinessLocationCreateIn,
    BusinessLocationOut,
    BusinessLocationPatchIn,
)
from app.services.business_location_service import (
    BusinessLocationConflictError,
    BusinessLocationInvariantError,
    create_business_location_with_portfolio,
    update_business_location,
)


router = APIRouter(tags=["business-locations"])


@router.post("/organizations/{org_id}/business-locations")
def create_business_location(
    request: Request,
    org_id: str,
    body: BusinessLocationCreateIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    try:
        payload = create_business_location_with_portfolio(
            db,
            organization_id=org_id,
            name=body.name,
            domain=body.domain,
            primary_city=body.primary_city,
            sub_account_id=body.sub_account_id,
        )
        db.commit()
    except BusinessLocationConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "BusinessLocation could not be created.",
                "reason_code": str(exc),
            },
        ) from exc
    except BusinessLocationInvariantError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "BusinessLocation creation violated organization invariants.",
                "reason_code": str(exc),
            },
        ) from exc

    return envelope(request, {"business_location": BusinessLocationOut.model_validate(payload).model_dump(mode="json")})


@router.get("/organizations/{org_id}/business-locations")
def list_business_locations(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    rows = (
        db.query(BusinessLocation)
        .filter(BusinessLocation.organization_id == org_id)
        .order_by(BusinessLocation.created_at.asc(), BusinessLocation.id.asc())
        .all()
    )
    return envelope(
        request,
        {
            "items": [
                BusinessLocationOut.model_validate(row).model_dump(mode="json")
                for row in rows
            ]
        },
    )


@router.get("/organizations/{org_id}/business-locations/{business_location_id}")
def get_business_location(
    request: Request,
    org_id: str,
    business_location_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    row = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == business_location_id,
            BusinessLocation.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business location not found")
    return envelope(
        request,
        {"business_location": BusinessLocationOut.model_validate(row).model_dump(mode="json")},
    )


@router.patch("/organizations/{org_id}/business-locations/{business_location_id}")
def patch_business_location(
    request: Request,
    org_id: str,
    business_location_id: str,
    body: BusinessLocationPatchIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    changes = {
        field: getattr(body, field)
        for field in body.model_fields_set
    }
    try:
        row = update_business_location(
            db,
            organization_id=org_id,
            business_location_id=business_location_id,
            changes=changes,
        )
        db.commit()
        db.refresh(row)
    except BusinessLocationInvariantError as exc:
        db.rollback()
        reason = str(exc)
        response_status = (
            status.HTTP_404_NOT_FOUND
            if reason in {"business_location_not_found", "subaccount_not_found"}
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=response_status,
            detail={"message": "Business location could not be updated.", "reason_code": reason},
        ) from exc
    return envelope(
        request,
        {"business_location": BusinessLocationOut.model_validate(row).model_dump(mode="json")},
    )


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
