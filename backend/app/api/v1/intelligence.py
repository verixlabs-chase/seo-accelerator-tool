from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.intelligence import AdvanceMonthIn, IntelligenceScoreOut, RecommendationOut
from app.services import intelligence_service
from app.tasks.tasks import (
    campaigns_evaluate_monthly_rules,
    campaigns_schedule_monthly_actions,
    intelligence_compute_score,
    intelligence_detect_anomalies,
)

intelligence_router = APIRouter(prefix="/intelligence", tags=["intelligence"])
campaign_intelligence_router = APIRouter(tags=["campaigns"])


@intelligence_router.get("/score")
def get_intelligence_score(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    score = intelligence_service.compute_score(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        intelligence_compute_score.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        pass
    return envelope(request, IntelligenceScoreOut.model_validate(score).model_dump(mode="json"))


@intelligence_router.get("/recommendations")
def get_intelligence_recommendations(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    intelligence_service.detect_anomalies(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    recs = intelligence_service.get_recommendations(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        intelligence_detect_anomalies.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        pass
    return envelope(request, {"items": [RecommendationOut.model_validate(r).model_dump(mode="json") for r in recs]})


@campaign_intelligence_router.post("/campaigns/{campaign_id}/advance-month")
def advance_campaign_month(
    request: Request,
    campaign_id: str,
    body: AdvanceMonthIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    result = intelligence_service.advance_month(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        override=body.override,
    )
    try:
        campaigns_evaluate_monthly_rules.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id, month_number=result["advanced_to_month"])
        campaigns_schedule_monthly_actions.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id, month_number=result["advanced_to_month"])
    except KombuError:
        pass
    return envelope(request, result)

