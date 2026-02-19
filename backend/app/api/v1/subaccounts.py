from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.models.sub_account import SubAccount
from app.schemas.sub_account import SubAccountCreateIn, SubAccountOut, SubAccountPatchIn


ALLOWED_SUBACCOUNT_STATUS = {"active", "suspended", "archived"}

router = APIRouter(tags=["subaccounts"])


@router.post("/organizations/{org_id}/subaccounts")
def create_subaccount(
    request: Request,
    org_id: str,
    body: SubAccountCreateIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    now = datetime.now(UTC)
    row = SubAccount(
        organization_id=org_id,
        name=body.name.strip(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "SubAccount name already exists for this organization.", "reason_code": "subaccount_name_conflict"},
        ) from exc
    db.refresh(row)
    return envelope(request, {"subaccount": SubAccountOut.model_validate(row).model_dump(mode="json")})


@router.get("/organizations/{org_id}/subaccounts")
def list_subaccounts(
    request: Request,
    org_id: str,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _assert_org_scope(user, org_id)
    rows = db.query(SubAccount).filter(SubAccount.organization_id == org_id).order_by(SubAccount.created_at.desc()).all()
    return envelope(request, {"items": [SubAccountOut.model_validate(row).model_dump(mode="json") for row in rows]})


@router.patch("/subaccounts/{id}")
def patch_subaccount(
    request: Request,
    id: str,
    body: SubAccountPatchIn,
    user: dict = Depends(require_org_role({"org_owner", "org_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    org_id = user.get("organization_id")
    row = (
        db.query(SubAccount)
        .filter(
            SubAccount.id == id,
            SubAccount.organization_id == org_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SubAccount not found")

    if body.name is not None:
        row.name = body.name.strip()
    if body.status is not None:
        next_status = body.status.strip().lower()
        if next_status not in ALLOWED_SUBACCOUNT_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid subaccount status")
        row.status = next_status
    row.updated_at = datetime.now(UTC)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "SubAccount name already exists for this organization.", "reason_code": "subaccount_name_conflict"},
        ) from exc
    db.refresh(row)
    return envelope(request, {"subaccount": SubAccountOut.model_validate(row).model_dump(mode="json")})


def _assert_org_scope(user: dict, org_id: str) -> None:
    if user.get("organization_id") != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "Organization context does not match request scope.", "reason_code": "organization_scope_mismatch"},
        )
