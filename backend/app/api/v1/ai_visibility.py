from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.ai_visibility import (
    AIVisibilityCollectionPreviewOut,
    AIVisibilityEngineListOut,
    AIVisibilityQuestionSetEnvelopeOut,
    AIVisibilitySummaryOut,
)
from app.services import ai_visibility_service


router = APIRouter(prefix="/ai-search", tags=["ai-search"])


@router.get("/engines")
def list_engines(
    request: Request,
    _user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = ai_visibility_service.list_public_engines(db)
    data = AIVisibilityEngineListOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


@router.post("/checks/preview")
def preview_collection(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = ai_visibility_service.preview_collection(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
    )
    data = AIVisibilityCollectionPreviewOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


@router.post("/question-sets")
def create_question_set(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = ai_visibility_service.create_question_set(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
        actor_user_id=str(user["user_id"]),
    )
    data = AIVisibilityQuestionSetEnvelopeOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


@router.get("/question-sets/current")
def get_current_question_set(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = ai_visibility_service.get_current_question_set(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
    )
    data = AIVisibilityQuestionSetEnvelopeOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)


@router.get("/summary")
def get_summary(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_org_role({"org_user"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = ai_visibility_service.get_summary(
        db,
        tenant_id=str(user["tenant_id"]),
        organization_id=str(user["organization_id"]),
        campaign_id=campaign_id,
    )
    data = AIVisibilitySummaryOut.model_validate(payload).model_dump(mode="json")
    return envelope(request, data)
