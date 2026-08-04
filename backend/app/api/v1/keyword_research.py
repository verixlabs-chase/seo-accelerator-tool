from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.keyword_research import (
    KeywordRelevanceFeedbackIn,
    KeywordResearchAIReviewIn,
    KeywordResearchDiscoverIn,
    KeywordResearchTrackIn,
)
from app.services import keyword_relevance_ai_service, keyword_research_service


router = APIRouter(prefix="/keyword-research", tags=["keyword-research"])


@router.get("")
def get_keyword_research(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = keyword_research_service.get_latest(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@router.post("/discover")
def discover_keywords(
    request: Request,
    body: KeywordResearchDiscoverIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = keyword_research_service.discover(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        max_suggestions=body.max_suggestions,
    )
    return envelope(request, payload)


@router.post("/track")
def track_keyword_suggestions(
    request: Request,
    body: KeywordResearchTrackIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = keyword_research_service.track_suggestions(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        suggestion_ids=body.suggestion_ids,
    )
    return envelope(request, payload)


@router.post("/feedback")
def save_keyword_relevance_feedback(
    request: Request,
    body: KeywordRelevanceFeedbackIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = keyword_research_service.save_relevance_feedback(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        suggestion_id=body.suggestion_id,
        decision=body.decision,
        service_id=body.service_id,
        created_by_user_id=user["user_id"],
    )
    return envelope(request, payload)


@router.post("/review-uncertain")
def review_uncertain_keyword_suggestions(
    request: Request,
    body: KeywordResearchAIReviewIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = keyword_relevance_ai_service.review_uncertain(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        requested_by_user_id=user["user_id"],
        max_items=body.max_items,
        retry_failed=body.retry_failed,
    )
    return envelope(request, payload)
