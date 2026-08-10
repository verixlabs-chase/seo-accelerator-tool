from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner, require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.reference_library import (
    AIDecisionContextIn,
    CoreWebVitalsEvaluateIn,
    CruxStandardsCheckIn,
    LexiconReplayIn,
    MetricContractCandidateCreateIn,
    MetricContractReplayIn,
    PerformanceDriftCheckIn,
    PerformanceDriftReviewIn,
    ReferenceLibraryActivateIn,
    ReferenceLibraryActivationOut,
    ReferenceLibraryActiveOut,
    ReferenceLibraryValidateIn,
    ReferenceLibraryValidationOut,
    ReferenceLibraryVersionOut,
    StandardsChangeReviewIn,
    StandardsDecisionIn,
    StandardsRollbackIn,
    StandardsRolloutCreateIn,
    StandardsSourceCheckIn,
)
from app.intelligence.lexicon.ai_context import build_ai_decision_context
from app.intelligence.lexicon.evaluator import evaluate_core_web_vitals
from app.intelligence.lexicon.loader import get_active_lexicon
from app.intelligence.lexicon.standards import (
    latest_crux_standards_check,
    run_and_record_crux_standards_check,
)
from app.services import (
    metric_contract_service,
    performance_drift_service,
    reference_library_service,
    standards_replay_service,
    standards_rollout_service,
    standards_source_service,
)

router = APIRouter(prefix="/reference-library", tags=["reference-library"])


def _ensure_loader_enabled() -> None:
    if not get_settings().reference_library_loader_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reference library loader is disabled"
        )


@router.post("/validate")
def validate_reference_library(
    request: Request,
    body: ReferenceLibraryValidateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.validate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        artifacts=body.artifacts,
        strict_mode=body.strict_mode,
    )
    return envelope(
        request, ReferenceLibraryValidationOut.model_validate(result).model_dump(mode="json")
    )


@router.post("/activate")
def activate_reference_library(
    request: Request,
    body: ReferenceLibraryActivateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.activate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        reason=body.reason,
    )
    return envelope(
        request, ReferenceLibraryActivationOut.model_validate(result).model_dump(mode="json")
    )


@router.get("/versions")
def list_reference_library_versions(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    rows = reference_library_service.list_versions(db, tenant_id=user["tenant_id"])
    return envelope(
        request,
        {
            "items": [
                ReferenceLibraryVersionOut.model_validate(row).model_dump(mode="json")
                for row in rows
            ]
        },
    )


@router.get("/active")
def get_active_reference_library(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.get_active(db, tenant_id=user["tenant_id"])
    return envelope(
        request, ReferenceLibraryActiveOut.model_validate(result).model_dump(mode="json")
    )


@router.get("/lexicon")
def get_intelligence_lexicon(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    return envelope(request, lexicon.model_dump(mode="json"))


@router.post("/core-web-vitals/evaluate")
def evaluate_current_core_web_vitals(
    request: Request,
    body: CoreWebVitalsEvaluateIn,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    result = evaluate_core_web_vitals(
        lexicon,
        body.measurements,
        form_factor=body.form_factor,
        collection_period_days=body.collection_period_days,
        measured_at=body.measured_at,
        source=body.source,
    )
    return envelope(request, result)


@router.post("/core-web-vitals/standards/check")
def check_current_core_web_vitals_standard(
    request: Request,
    body: CruxStandardsCheckIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    settings = get_settings()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    try:
        result = run_and_record_crux_standards_check(
            db,
            lexicon=lexicon,
            api_key=settings.crux_api_key,
            origin=body.origin or settings.cwv_standards_probe_origin,
            timeout_seconds=settings.google_oauth_http_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to verify Core Web Vitals standards with the official CrUX API.",
        ) from exc
    return envelope(request, result)


@router.get("/core-web-vitals/standards/status")
def get_current_core_web_vitals_standard_status(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    latest = latest_crux_standards_check(db)
    return envelope(
        request,
        {
            "lexicon_version": lexicon.meta.version,
            "standards_reviewed_at": lexicon.meta.standards_reviewed_at,
            "latest_check": latest,
            "automatic_activation_allowed": False,
        },
    )


@router.get("/standards/sources/status")
def get_standards_sources_status(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    standards_source_service.ensure_default_sources(db)
    return envelope(request, standards_source_service.list_source_status(db))


@router.post("/standards/sources/check")
def check_standards_source(
    request: Request,
    body: StandardsSourceCheckIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    settings = get_settings()
    standards_source_service.ensure_default_sources(db)
    try:
        result = standards_source_service.check_source(
            db,
            source_id=body.source_id,
            timeout_seconds=settings.standards_source_http_timeout_seconds,
            max_content_bytes=settings.standards_source_max_content_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return envelope(request, result)


@router.get("/standards/changes")
def list_standards_change_candidates(
    request: Request,
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(
        request,
        standards_source_service.list_change_candidates(
            db,
            status_filter=status_filter,
            limit=limit,
        ),
    )


@router.get("/standards/contracts")
def list_objective_metric_contracts(
    request: Request,
    provider_name: str | None = None,
    metric_family: str | None = None,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(
        request,
        metric_contract_service.list_active_contracts(
            db,
            provider_name=provider_name,
            metric_family=metric_family,
        ),
    )


@router.post("/standards/contracts/candidates")
def create_objective_metric_contract_candidate(
    request: Request,
    body: MetricContractCandidateCreateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_replay_service.create_metric_contract_candidate(
            db,
            standards_change_candidate_id=body.standards_change_candidate_id,
            contract_id=body.contract_id,
            candidate_version=body.candidate_version,
            changes=body.changes,
            actor_user_id=user["id"],
            effective_at=body.effective_at,
        )
    except standards_replay_service.StandardsReplayError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.get("/standards/contracts/versions")
def list_objective_metric_contract_versions(
    request: Request,
    contract_id: str | None = None,
    lifecycle_status: str | None = None,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    try:
        result = metric_contract_service.list_contract_versions(
            db,
            contract_id=contract_id,
            lifecycle_status=lifecycle_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/contracts/candidates/{contract_version_id}/replay")
def replay_objective_metric_contract_candidate(
    request: Request,
    contract_version_id: str,
    body: MetricContractReplayIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_replay_service.replay_metric_contract_candidate(
            db,
            candidate_contract_version_id=contract_version_id,
            actor_user_id=user["id"],
            sample_type=body.sample_type,
            evidence_samples=[item.model_dump() for item in body.evidence_samples],
            approval_reference=body.approval_reference,
        )
    except standards_replay_service.StandardsReplayError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/lexicon/candidates/{candidate_version}/replay")
def replay_intelligence_lexicon_candidate(
    request: Request,
    candidate_version: str,
    body: LexiconReplayIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_replay_service.replay_lexicon_candidate(
            db,
            tenant_id=user["tenant_id"],
            candidate_version=candidate_version,
            actor_user_id=user["id"],
            base_version=body.base_version,
            standards_change_candidate_id=body.standards_change_candidate_id,
            sample_type=body.sample_type,
            evidence_samples=[item.model_dump() for item in body.evidence_samples],
            approval_reference=body.approval_reference,
        )
    except standards_replay_service.StandardsReplayError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.get("/standards/replays")
def list_standards_replay_reports(
    request: Request,
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(request, standards_replay_service.list_replay_reports(db, limit=limit))


@router.get("/standards/replays/{report_id}")
def get_standards_replay_report(
    request: Request,
    report_id: str,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    result = standards_replay_service.get_replay_report(db, report_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Replay report was not found.")
    return envelope(request, result)


@router.get("/standards/status")
def get_standards_workspace_status(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    return envelope(
        request,
        standards_rollout_service.standards_status(db, tenant_id=user.get("tenant_id")),
    )


@router.get("/standards/drift/events")
def list_performance_drift_events(
    request: Request,
    status_filter: str | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(
        request,
        performance_drift_service.list_drift_events(
            db, status_filter=status_filter, limit=limit
        ),
    )


@router.post("/standards/drift/check")
def check_performance_drift(
    request: Request,
    body: PerformanceDriftCheckIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = performance_drift_service.run_search_console_drift_check(
            db,
            metrics=body.metrics,
            period_days=body.period_days,
            as_of=body.as_of,
            minimum_organizations=body.minimum_organizations,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/drift/events/{event_id}/review")
def review_performance_drift_event(
    request: Request,
    event_id: str,
    body: PerformanceDriftReviewIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = performance_drift_service.review_drift_event(
            db,
            event_id=event_id,
            status=body.status,
            note=body.note,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return envelope(request, result)


@router.get("/standards/approvals")
def list_standards_approvals(
    request: Request,
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(request, standards_rollout_service.list_approvals(db, limit=limit))


@router.get("/standards/rollouts")
def list_standards_rollouts(
    request: Request,
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    return envelope(request, standards_rollout_service.list_rollouts(db, limit=limit))


@router.post("/standards/replays/{report_id}/decision")
def decide_standards_replay(
    request: Request,
    report_id: str,
    body: StandardsDecisionIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_rollout_service.decide_replay_report(
            db,
            replay_report_id=report_id,
            decision=body.decision,
            rationale=body.rationale,
            rollout_plan=body.rollout_plan.model_dump() if body.rollout_plan else None,
            rollback_plan=body.rollback_plan.model_dump() if body.rollback_plan else None,
            acknowledges_new_baseline=body.acknowledges_new_baseline,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
    except standards_rollout_service.StandardsRolloutError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/approvals/{approval_id}/rollouts")
def create_standards_rollout(
    request: Request,
    approval_id: str,
    body: StandardsRolloutCreateIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_rollout_service.create_rollout(
            db,
            approval_id=approval_id,
            rollout_mode=body.rollout_mode,
            scheduled_for=body.scheduled_for,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
        if body.rollout_mode == "immediate":
            result = standards_rollout_service.execute_rollout(
                db,
                rollout_id=result["id"],
                actor_user_id=user["id"],
                audit_tenant_id=user.get("tenant_id") or user["id"],
            )
    except standards_rollout_service.StandardsRolloutError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/rollouts/{rollout_id}/execute")
def execute_standards_rollout(
    request: Request,
    rollout_id: str,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_rollout_service.execute_rollout(
            db,
            rollout_id=rollout_id,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
    except standards_rollout_service.StandardsRolloutError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/standards/rollouts/{rollout_id}/rollback")
def rollback_standards_rollout(
    request: Request,
    rollout_id: str,
    body: StandardsRollbackIn,
    user: dict = Depends(require_platform_owner()),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_rollout_service.rollback_rollout(
            db,
            rollout_id=rollout_id,
            reason=body.reason,
            actor_user_id=user["id"],
            audit_tenant_id=user.get("tenant_id") or user["id"],
        )
    except standards_rollout_service.StandardsRolloutError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return envelope(request, result)


@router.get("/standards/changes/{candidate_id}")
def get_standards_change_candidate(
    request: Request,
    candidate_id: str,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    del user
    _ensure_loader_enabled()
    result = standards_source_service.get_change_candidate(db, candidate_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Standards change candidate was not found.",
        )
    return envelope(request, result)


@router.post("/standards/changes/{candidate_id}/review")
def review_standards_change_candidate(
    request: Request,
    candidate_id: str,
    body: StandardsChangeReviewIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    try:
        result = standards_source_service.review_change_candidate(
            db,
            candidate_id=candidate_id,
            disposition=body.disposition,
            actor_user_id=user["id"],
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return envelope(request, result)


@router.post("/ai-decision-context")
def create_ai_decision_context(
    request: Request,
    body: AIDecisionContextIn,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    result = build_ai_decision_context(
        lexicon,
        facts=body.facts,
        deterministic_assessments=body.deterministic_assessments,
        diagnostic_ids=body.diagnostic_ids,
        action_ids=body.action_ids,
    )
    return envelope(request, result)
