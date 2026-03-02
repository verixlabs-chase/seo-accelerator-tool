from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.hierarchy_observability_service import get_location_linkage_stats


router = APIRouter(tags=["hierarchy-observability"])


@router.get("/organizations/{org_id}/hierarchy/health")
def get_hierarchy_health(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    payload = get_location_linkage_stats(db, org_id)
    return envelope(request, {"hierarchy_health": payload})


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Organization context does not match request scope.",
                "reason_code": "organization_scope_mismatch",
            },
        )
