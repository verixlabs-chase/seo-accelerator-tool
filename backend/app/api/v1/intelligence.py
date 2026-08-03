from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.schemas.intelligence import (
    ActionPlanStepUpdateIn,
    AdvanceMonthIn,
    GenerateIntelligenceBriefIn,
    IntelligenceScoreOut,
    RecommendationOut,
    RecommendationTransitionIn,
)
from app.services import durable_job_service, governed_ai_service, intelligence_service
from app.services.intelligence_runtime_service import build_intelligence_engine_state
from app.services.recommendation_outcome_service import (
    get_campaign_outcome_history,
    measure_recommendation_outcome,
)
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
    engine: dict | None = None,
) -> dict:
    engine = engine or {}
    orchestrator_count = int(engine.get("orchestrator_recommendation_count", 0) or 0)
    heuristic_count = int(engine.get("heuristic_recommendation_count", 0) or 0)
    states = ["generated"] if orchestrator_count and not heuristic_count else ["heuristic"]
    reasons = (
        ["stored_data_orchestrator_generated_guidance"]
        if orchestrator_count
        else ["intelligence_surfaces_are_threshold_and_rule_driven"]
    )
    if orchestrator_count and heuristic_count:
        reasons.append("guidance_contains_orchestrator_and_threshold_recommendations")
    if engine.get("activation_mode") == "recommendation_only":
        reasons.append("recommendation_only_mode_blocks_mutation_scheduling_and_execution")
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
        provider_state=(
            "stored_data_orchestrator"
            if orchestrator_count
            else "heuristic_model"
        ),
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
    engine = build_intelligence_engine_state([], fallback_source="heuristic_score_v1")
    truth = _intelligence_truth(
        job_queued=task is not None,
        has_items=score is not None,
        captured_at=score_payload.get("captured_at"),
        summary="Opportunity score is heuristic. It summarizes stored crawl, ranking, content, and local signals, not live provider-backed execution readiness.",
        engine=engine,
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "score_value": score_payload["score_value"],
            "latest_score": score_payload,
            "engine": engine,
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
    action_plans = intelligence_service.build_recommendation_action_plans(
        db,
        tenant_id=user["tenant_id"],
        recommendations=recs,
    )
    work_items = intelligence_service.ensure_action_plan_occurrences(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        recommendations=recs,
        action_plans=action_plans,
    )
    for item in items:
        item["action_plan"] = action_plans.get(item["id"])
        if item["action_plan"] is not None:
            item["action_plan"]["work_item"] = work_items.get(item["id"])
    engine = build_intelligence_engine_state(recs)
    has_orchestrator_guidance = engine["orchestrator_recommendation_count"] > 0
    truth = _intelligence_truth(
        job_queued=task is not None,
        has_items=len(items) > 0,
        captured_at=items[0]["created_at"] if items else None,
        summary=(
            "Recommendations include stored-data orchestrator guidance. Production remains recommendation-only: operator review is required and no business changes are scheduled or executed automatically."
            if has_orchestrator_guidance
            else "Recommendations are heuristic guidance. They require operator review and do not schedule or execute business changes automatically."
        ),
        engine=engine,
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "items": items,
            "engine": engine,
            "truth": truth,
        },
    )


@intelligence_router.patch(
    "/action-plans/{occurrence_id}/steps/{step_id}"
)
def update_action_plan_checklist_step(
    request: Request,
    occurrence_id: str,
    step_id: str,
    body: ActionPlanStepUpdateIn,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    work_item = intelligence_service.update_action_plan_step(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        occurrence_id=occurrence_id,
        step_id=step_id,
        step_status=body.status,
        blocker_reason=body.blocker_reason,
        evidence=body.evidence,
        actor_user_id=user["user_id"],
    )
    return envelope(request, {"work_item": work_item})


@intelligence_router.get("/brief")
def get_intelligence_brief(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = governed_ai_service.latest_governed_brief(
        db,
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@intelligence_router.post("/brief")
def generate_intelligence_brief(
    request: Request,
    body: GenerateIntelligenceBriefIn,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = governed_ai_service.generate_governed_brief(
        db,
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        requested_by_user_id=user["user_id"],
        retry_failed=body.retry_failed,
    )
    return envelope(request, payload)


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


@intelligence_router.get("/outcomes")
def get_intelligence_outcomes(
    request: Request,
    campaign_id: str = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = get_campaign_outcome_history(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        limit=limit,
    )
    truth = build_truth(
        states=["heuristic"] + (["unavailable"] if payload["count"] == 0 else []),
        summary=(
            "Outcome history compares saved opportunity-score checkpoints. It can show change over time, but it does not prove that a recommendation caused the change."
        ),
        provider_state="stored_data_model",
        setup_state="configured",
        operator_state="operator_review_required",
        freshness_state=(
            freshness_state_from_timestamp(
                payload["summary"]["latest_measured_at"],
                stale_after=timedelta(days=30),
            )
            if payload["count"]
            else "unknown"
        ),
        reasons=[
            "outcomes_compare_heuristic_score_checkpoints",
            "observation_only_learning_does_not_update_policies",
            "causal_claims_are_disabled",
        ],
    )
    return envelope(request, {**payload, "truth": truth})


@intelligence_router.post("/cycles/run")
def run_intelligence_cycle(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.setup_state.lower() != "active":
        raise HTTPException(status_code=400, detail="Campaign must be active")

    job = durable_job_service.run_intelligence_campaign_job_now(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    activation = (
        result.get("activation")
        if isinstance(result.get("activation"), dict)
        else {}
    )
    safety = {
        "provider_checks_allowed": False,
        "activation_mode": activation.get("mode", "recommendation_only"),
        "mutation_scheduling_enabled": bool(
            activation.get("mutation_scheduling_enabled", False)
        ),
        "mutation_execution_enabled": bool(
            activation.get("mutation_execution_enabled", False)
        ),
        "executions_scheduled": int(result.get("executions_scheduled", 0) or 0),
        "executions_completed": int(result.get("executions_completed", 0) or 0),
    }
    if (
        safety["mutation_scheduling_enabled"]
        or safety["mutation_execution_enabled"]
        or safety["executions_scheduled"] > 0
        or safety["executions_completed"] > 0
    ):
        raise HTTPException(
            status_code=500,
            detail="Intelligence cycle violated recommendation-only safety constraints",
        )
    return envelope(request, {**job, "safety": safety})


@intelligence_router.post("/recommendations/{recommendation_id}/measure-outcome")
def measure_intelligence_outcome(
    request: Request,
    recommendation_id: str,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    outcome, created = measure_recommendation_outcome(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        recommendation_id=recommendation_id,
    )
    history = get_campaign_outcome_history(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        limit=50,
    )
    item = next(
        (item for item in history["items"] if item["id"] == outcome.id),
        None,
    )
    return envelope(
        request,
        {
            "created": created,
            "outcome": item,
            "summary": history["summary"],
            "learning": history["learning"],
        },
    )


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
