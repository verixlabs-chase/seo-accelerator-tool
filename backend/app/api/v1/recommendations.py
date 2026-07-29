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
    engine = payload["engine"]
    has_orchestrator_guidance = engine["orchestrator_recommendation_count"] > 0
    truth = build_truth(
        states=(
            ["generated"]
            if has_orchestrator_guidance and engine["heuristic_recommendation_count"] == 0
            else ["heuristic"]
        )
        + (["unavailable"] if payload["total_count"] == 0 else []),
        summary=(
            "Recommendation counts include stored-data orchestrator guidance. They require operator review and do not prove execution or provider-backed completion."
            if has_orchestrator_guidance
            else "Recommendation counts summarize heuristic strategy recommendations. They do not prove execution or provider-backed completion."
        ),
        provider_state=(
            "stored_data_orchestrator"
            if has_orchestrator_guidance
            else "heuristic_model"
        ),
        setup_state="configured",
        operator_state="operator_review_required",
        freshness_state="current",
        reasons=[
            (
                "recommendation_summary_includes_stored_data_orchestrator_guidance"
                if has_orchestrator_guidance
                else "recommendation_summary_rolls_up_heuristic_states"
            ),
            "recommendation_only_mode_blocks_automatic_mutations"
            if engine["activation_mode"] == "recommendation_only"
            else "autonomous_test_mode_enabled",
        ],
    )
    return envelope(request, {**payload, "truth": truth})
