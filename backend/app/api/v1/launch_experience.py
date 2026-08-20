from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_platform_role
from app.api.response import envelope
from app.db.session import get_db
from app.services.launch_experience_service import (
    LaunchExperienceError,
    build_launch_experience_readiness,
    create_launch_experience_review,
    serialize_launch_experience_review,
)


router = APIRouter(prefix="/system/launch-experience", tags=["launch-experience"])


class LaunchExperienceReviewIn(BaseModel):
    review_kind: Literal["route_audit", "moderated_session"]
    subject_code: str = Field(min_length=3, max_length=64)
    viewport: Literal["desktop", "mobile", "not_applicable"]
    result: Literal["passed", "failed"]
    session_reference: str | None = Field(default=None, max_length=40)
    summary: str = Field(min_length=20, max_length=400)
    issue_count: int = Field(ge=0, le=999)
    blocking_issue_count: int = Field(ge=0, le=999)
    evidence_reference: str = Field(min_length=8, max_length=160)
    observed_at: datetime
    expires_at: datetime


@router.get("")
def get_launch_experience_readiness(
    request: Request,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_platform_role({"platform_owner", "platform_admin"})),
) -> dict:
    return envelope(request, build_launch_experience_readiness(db))


@router.post("/reviews")
def record_launch_experience_review(
    request: Request,
    body: LaunchExperienceReviewIn,
    db: Session = Depends(get_db),
    user: dict = Depends(require_platform_owner()),
) -> dict:
    try:
        review, created = create_launch_experience_review(
            db,
            review_kind=body.review_kind,
            subject_code=body.subject_code,
            viewport=body.viewport,
            result=body.result,
            session_reference=body.session_reference,
            summary=body.summary,
            issue_count=body.issue_count,
            blocking_issue_count=body.blocking_issue_count,
            evidence_reference=body.evidence_reference,
            observed_at=body.observed_at,
            expires_at=body.expires_at,
            recorded_by_user_id=user["id"],
        )
        db.commit()
        db.refresh(review)
        readiness = build_launch_experience_readiness(db)
    except LaunchExperienceError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": str(exc), "reason_code": exc.reason_code},
        ) from exc
    return envelope(
        request,
        {
            "created": created,
            "review": serialize_launch_experience_review(
                review, now=datetime.fromisoformat(readiness["evaluated_at"])
            ),
            "readiness": readiness,
        },
    )
