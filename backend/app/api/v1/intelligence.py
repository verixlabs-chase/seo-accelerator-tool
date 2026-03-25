from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.intelligence import AdvanceMonthIn, IntelligenceScoreOut, RecommendationOut, RecommendationTransitionIn
from app.services import intelligence_service
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import (
    campaigns_evaluate_monthly_rules,
    campaigns_schedule_monthly_actions,
    intelligence_compute_score,
    intelligence_detect_anomalies,
)

intelligence_router = APIRouter(prefix="/intelligence", tags=["intelligence"])
campaign_intelligence_router = APIRouter(tags=["campaigns"])


def _intelligence_truth(
    *,
    job_queued: bool,
    has_items: bool,
    captured_at: str | None = None,
    summary: str,
) -> dict:
    states = ["heuristic"]
    reasons = ["intelligence_surfaces_are_threshold_and_rule_driven"]
    if not has_items:
        states.append("in_progress" if job_queued else "unavailable")
    if job_queued:
        states.append("in_progress")
        reasons.append("intelligence_refresh_queued")
    freshness_state = freshness_state_from_timestamp(captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("intelligence_snapshot_is_stale")
    return build_truth(
        states=states,
        summary=summary,
        provider_state="heuristic_model",
        setup_state="configured",
        operator_state="operator_review_required",
        freshness_state=freshness_state,
        reasons=reasons,
    )


@intelligence_router.get("/score")
def get_intelligence_score(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = intelligence_compute_score.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        task = None
    score = intelligence_service.get_latest_score(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    score_payload = IntelligenceScoreOut.model_validate(score).model_dump(mode="json")
    truth = _intelligence_truth(
        job_queued=task is not None,
        has_items=score is not None,
        captured_at=score_payload.get("captured_at"),
        summary="Opportunity score is heuristic. It summarizes stored crawl, ranking, content, and local signals, not live provider-backed execution readiness.",
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "score_value": score_payload["score_value"],
            "latest_score": score_payload,
            "truth": truth,
        },
    )


@intelligence_router.get("/recommendations")
def get_intelligence_recommendations(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = intelligence_detect_anomalies.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        task = None
    recs = intelligence_service.get_recommendations(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    items = [RecommendationOut.model_validate(r).model_dump(mode="json") for r in recs]
    truth = _intelligence_truth(
        job_queued=task is not None,
        has_items=len(items) > 0,
        captured_at=items[0]["created_at"] if items else None,
        summary="Recommendations are heuristic guidance. They still require operator review and, where relevant, provider-ready execution before they should be treated as complete.",
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "items": items,
            "truth": truth,
        },
    )


@intelligence_router.post("/recommendations/{recommendation_id}/transition")
def transition_recommendation(
    request: Request,
    recommendation_id: str,
    body: RecommendationTransitionIn,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = intelligence_service.transition_recommendation_state(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        recommendation_id=recommendation_id,
        target_state=body.target_state,
    )
    return envelope(request, RecommendationOut.model_validate(row).model_dump(mode="json"))


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
