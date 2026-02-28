from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.business_location import BusinessLocationCreateIn, BusinessLocationOut
from app.services.business_location_service import (
    BusinessLocationConflictError,
    BusinessLocationInvariantError,
    create_business_location_with_portfolio,
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


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
