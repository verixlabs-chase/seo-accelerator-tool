from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.services import intelligence_service
from app.services.runtime_truth_service import build_truth

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/summary")
def get_recommendation_summary(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = intelligence_service.get_recommendation_summary(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    truth = build_truth(
        states=["heuristic"] + (["unavailable"] if payload["total_count"] == 0 else []),
        summary="Recommendation counts summarize heuristic strategy recommendations. They do not prove execution or provider-backed completion.",
        provider_state="heuristic_model",
        setup_state="configured",
        operator_state="operator_review_required",
        freshness_state="current",
        reasons=["recommendation_summary_rolls_up_heuristic_states"],
    )
    return envelope(request, {**payload, "truth": truth})
