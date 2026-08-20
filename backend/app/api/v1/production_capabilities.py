from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.production_capability_service import (
    ProductionCapabilityError,
    build_production_capability_matrix,
    create_production_capability_proof,
    serialize_production_capability_proof,
)


router = APIRouter(prefix="/system/production-capabilities", tags=["production-capabilities"])


class ProductionCapabilityProofIn(BaseModel):
    capability_code: str = Field(min_length=3, max_length=64)
    result: Literal["proven", "limited", "unavailable"]
    summary: str = Field(min_length=20, max_length=300)
    customer_limitation: str | None = Field(default=None, max_length=300)
    evidence_reference: str = Field(min_length=8, max_length=160)
    observed_at: datetime
    expires_at: datetime


@router.get("")
def get_production_capability_matrix(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, build_production_capability_matrix(db))


@router.post("/proofs")
def record_production_capability_proof(
    request: Request,
    body: ProductionCapabilityProofIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_platform_owner()),
) -> dict:
    try:
        proof, created = create_production_capability_proof(
            db,
            capability_code=body.capability_code,
            result=body.result,
            summary=body.summary,
            customer_limitation=body.customer_limitation,
            evidence_reference=body.evidence_reference,
            observed_at=body.observed_at,
            expires_at=body.expires_at,
            recorded_by_user_id=user["id"],
        )
        db.commit()
        db.refresh(proof)
        matrix = build_production_capability_matrix(db)
    except ProductionCapabilityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "created": created,
            "proof": serialize_production_capability_proof(
                proof,
                now=datetime.fromisoformat(matrix["evaluated_at"]),
            ),
            "matrix": matrix,
        },
    )
