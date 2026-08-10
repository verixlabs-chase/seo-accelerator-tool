from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.models.data_connection import DataConnection
from app.schemas.local_rank_grid import LocalRankGridCreateRequest, LocalRankGridRequest
from app.schemas.reputation import (
    ReputationResponseDraftCreate,
    ReputationResponseDraftDecision,
    ReputationResponseExecutionControl,
    ReputationResponsePublishRequest,
    ReputationReviewOut,
)
from app.services import (
    data_connections_service,
    durable_job_service,
    local_rank_grid_service,
    local_service,
    reputation_inventory_service,
    reputation_response_execution_service,
    reputation_response_service,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.location_normalization_service import (
    LocationContextError,
    get_campaign_location_context,
    normalize_campaign_location,
)
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import (
    local_collect_profile_snapshot,
    local_compute_health_score,
    reviews_compute_velocity,
    reviews_ingest,
)

local_router = APIRouter(prefix="/local", tags=["local"])
reviews_router = APIRouter(prefix="/reviews", tags=["reviews"])


@local_router.get("/location-context")
def get_location_context(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = get_campaign_location_context(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=campaign_id,
        )
    except LocationContextError as exc:
        _raise_location_context_error(exc)
    return envelope(request, payload)


@local_router.post("/location-context/resolve")
def resolve_location_context(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = normalize_campaign_location(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=campaign_id,
        )
        db.commit()
    except LocationContextError as exc:
        db.rollback()
        _raise_location_context_error(exc)
    return envelope(request, payload)


def _raise_location_context_error(exc: LocationContextError) -> None:
    reason = str(exc)
    response_status = (
        status.HTTP_404_NOT_FOUND
        if reason in {"campaign_not_found", "business_location_not_found"}
        else status.HTTP_409_CONFLICT
    )
    raise HTTPException(
        status_code=response_status,
        detail={
            "message": "Location context is not available for this campaign.",
            "reason_code": reason,
        },
    ) from exc


def _raise_rank_grid_error(exc: Exception) -> None:
    response_status = int(getattr(exc, "status_code", status.HTTP_409_CONFLICT))
    raise HTTPException(
        status_code=response_status,
        detail={
            "message": str(exc),
            "reason_code": str(getattr(exc, "reason_code", "area_search_unavailable")),
        },
    ) from exc


@local_router.post("/rank-grid/preview")
def preview_local_rank_grid(
    request: Request,
    body: LocalRankGridRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = local_rank_grid_service.preview_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            campaign_id=body.campaign_id,
            keyword_ids=body.keyword_ids,
            grid_size=body.grid_size,
            radius_miles=body.radius_miles,
        )
    except (local_rank_grid_service.LocalRankGridError, CostEconomicsError) as exc:
        _raise_rank_grid_error(exc)
    return envelope(request, payload)


@local_router.post("/rank-grid/runs", status_code=status.HTTP_202_ACCEPTED)
def create_local_rank_grid_run(
    request: Request,
    body: LocalRankGridCreateRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run, created = local_rank_grid_service.create_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            created_by_user_id=user["id"],
            campaign_id=body.campaign_id,
            keyword_ids=body.keyword_ids,
            grid_size=body.grid_size,
            radius_miles=body.radius_miles,
            idempotency_key=body.idempotency_key,
        )
        durable_job_service.run_local_rank_grid_dispatch_now(
            db,
            tenant_id=user["tenant_id"],
            run_id=run.id,
        )
        run = local_rank_grid_service.get_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            run_id=run.id,
        )
    except (local_rank_grid_service.LocalRankGridError, CostEconomicsError) as exc:
        db.rollback()
        _raise_rank_grid_error(exc)
    return envelope(
        request,
        {
            "created": created,
            "run": local_rank_grid_service.serialize_run(db, run),
        },
    )


@local_router.get("/rank-grid/runs")
def list_local_rank_grid_runs(
    request: Request,
    campaign_id: str = Query(...),
    limit: int = Query(default=12, ge=1, le=50),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = local_rank_grid_service.list_runs(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        limit=limit,
    )
    return envelope(
        request,
        {
            "items": [local_rank_grid_service.serialize_run(db, row) for row in rows],
            "count": len(rows),
        },
    )


@local_router.get("/rank-grid/runs/{run_id}")
def get_local_rank_grid_run(
    request: Request,
    run_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run = local_rank_grid_service.get_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            run_id=run_id,
        )
    except local_rank_grid_service.LocalRankGridError as exc:
        _raise_rank_grid_error(exc)
    return envelope(request, local_rank_grid_service.serialize_run(db, run))


@local_router.post("/rank-grid/runs/{run_id}/refresh")
def refresh_local_rank_grid_run(
    request: Request,
    run_id: str,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run = local_rank_grid_service.refresh_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            run_id=run_id,
        )
    except local_rank_grid_service.LocalRankGridError as exc:
        _raise_rank_grid_error(exc)
    return envelope(request, local_rank_grid_service.serialize_run(db, run))


def _local_provider_truth(
    *, has_data: bool, job_queued: bool, captured_at: str | None = None
) -> dict:
    settings = get_settings()
    backend = getattr(settings, "local_provider_backend", "synthetic").strip().lower()
    environment = getattr(settings, "app_env", "").strip().lower()

    states: list[str] = []
    reasons: list[str] = []
    provider_state = backend or "unknown"
    setup_state = "configured"
    operator_state = "self_serve"

    if backend == "synthetic":
        if environment == "test":
            states.append("synthetic")
            reasons.append("local_runtime_uses_test_fixture_provider")
            summary = "Local visibility is coming from a synthetic fixture provider in test mode."
        else:
            states.append("unavailable")
            provider_state = "synthetic_disabled_outside_test"
            setup_state = "provider_unavailable"
            operator_state = "operator_assisted"
            reasons.append("local_provider_not_available_in_this_runtime")
            summary = "Local visibility is not provider-backed in this runtime. The configured synthetic provider is disabled outside test mode."
    else:
        states.append("provider_backed")
        summary = f"Local visibility is using the configured {backend} provider."

    freshness_state = freshness_state_from_timestamp(captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("local_data_is_stale")
    if job_queued:
        states.append("in_progress")
        reasons.append("local_refresh_queued")
    if has_data and "provider_backed" not in states and "synthetic" not in states:
        states.append("operator_assisted")
        reasons.append("local_surface_depends_on_stored_rows_or_manual_follow_up")

    return build_truth(
        states=states,
        summary=summary,
        provider_state=provider_state,
        setup_state=setup_state,
        operator_state=operator_state,
        freshness_state=freshness_state,
        reasons=reasons,
    )


@local_router.get("/health")
def get_local_health(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        snapshot_task = local_collect_profile_snapshot.delay(
            tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
        score_task = local_compute_health_score.delay(
            tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
    except KombuError:
        snapshot_task = None
        score_task = None
    try:
        latest_health = local_service.get_latest_health(
            db, tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
    except ValueError:
        latest_health = {"campaign_id": campaign_id, "health_score": None, "captured_at": None}
    truth = _local_provider_truth(
        has_data=latest_health.get("health_score") is not None,
        job_queued=score_task is not None or snapshot_task is not None,
        captured_at=latest_health.get("captured_at"),
    )
    return envelope(
        request,
        {
            **latest_health,
            "job_id": score_task.id if score_task is not None else None,
            "snapshot_job_id": snapshot_task.id if snapshot_task is not None else None,
            "truth": truth,
        },
    )


@local_router.get("/map-pack")
def get_map_pack(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        profile = local_service.collect_profile_snapshot(
            db, tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
        payload = {
            "campaign_id": campaign_id,
            "provider": profile.provider,
            "map_pack_position": profile.map_pack_position,
            "profile_name": profile.profile_name,
            "captured_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }
    except ValueError:
        payload = {
            "campaign_id": campaign_id,
            "provider": None,
            "map_pack_position": None,
            "profile_name": None,
            "captured_at": None,
        }
    truth = _local_provider_truth(
        has_data=payload.get("map_pack_position") is not None,
        job_queued=False,
        captured_at=payload.get("captured_at"),
    )
    return envelope(
        request,
        {
            **payload,
            "truth": truth,
        },
    )


@reviews_router.get("")
def get_reviews(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = reviews_ingest.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        task = None
    try:
        reviews = local_service.get_reviews(
            db, tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
    except ValueError:
        reviews = []
    truth = _local_provider_truth(
        has_data=len(reviews) > 0,
        job_queued=task is not None,
        captured_at=reviews[0]["reviewed_at"] if reviews else None,
    )
    return envelope(
        request,
        {
            "campaign_id": campaign_id,
            "job_id": task.id if task is not None else None,
            "items": reviews,
            "truth": truth,
        },
    )


@reviews_router.get("/inventory")
def get_review_inventory(
    request: Request,
    campaign_id: str = Query(...),
    source_type: str | None = Query(default=None),
    response_status: str | None = Query(default=None),
    rating_lte: float | None = Query(default=None, ge=1, le=5),
    limit: int = Query(default=100, ge=1, le=250),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = reputation_inventory_service.list_reviews(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        source_type=source_type,
        response_status=response_status,
        rating_lte=rating_lte,
        limit=limit,
    )
    posting = reputation_response_execution_service.posting_status(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(
        request,
        {
            "items": [
                ReputationReviewOut.model_validate(row).model_dump(mode="json") for row in rows
            ],
            "summary": reputation_inventory_service.inventory_summary(rows),
            "truth": {
                "classification": "provider_backed" if rows else "not_collected",
                "summary": (
                    "These reviews were saved from an authorized owned business profile."
                    if rows
                    else "No owned-profile review inventory has been collected for this location yet."
                ),
                "source_coverage": "owned_profiles",
                "direct_reply_available": posting["available"],
                "direct_reply_reason": posting["reason"],
                "ai_reply_available": True,
                "ai_reply_reason": "AI can prepare a draft when the review passes the safety check.",
            },
        },
    )


@reviews_router.get("/response-policy")
def get_review_response_policy(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = reputation_response_service.policy_status(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        requested_by_user_id=user["id"],
    )
    return envelope(request, payload)


@reviews_router.get("/posting-status")
def get_review_posting_status(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        reputation_response_execution_service.posting_status(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            campaign_id=campaign_id,
        ),
    )


@reviews_router.get("/executions")
def get_review_response_executions(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        {
            "items": reputation_response_execution_service.list_executions(
                db,
                tenant_id=user["tenant_id"],
                organization_id=user["organization_id"],
                campaign_id=campaign_id,
            )
        },
    )


@reviews_router.post("/drafts/{draft_id}/publish")
def publish_review_response_draft(
    draft_id: str,
    payload: ReputationResponsePublishRequest,
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reputation_response_execution_service.queue_execution(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        draft_id=draft_id,
        requested_by_user_id=user["id"],
        confirmation_version=payload.confirmation_version,
        confirm_publish_to_google=payload.confirm_publish_to_google,
    )
    return envelope(request, reputation_response_execution_service.serialize_execution(row))


@reviews_router.patch("/executions/{execution_id}")
def control_review_response_execution(
    execution_id: str,
    payload: ReputationResponseExecutionControl,
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reputation_response_execution_service.control_execution(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        execution_id=execution_id,
        action=payload.action,
    )
    return envelope(request, reputation_response_execution_service.serialize_execution(row))


@reviews_router.get("/drafts")
def get_review_response_drafts(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        {
            "items": reputation_response_service.list_response_drafts(
                db,
                tenant_id=user["tenant_id"],
                organization_id=user["organization_id"],
                campaign_id=campaign_id,
            )
        },
    )


@reviews_router.post("/{review_id}/drafts")
def create_review_response_draft(
    review_id: str,
    payload: ReputationResponseDraftCreate,
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reputation_response_service.generate_response_draft(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        review_id=review_id,
        requested_by_user_id=user["id"],
        refresh=payload.refresh,
    )
    return envelope(request, row)


@reviews_router.patch("/drafts/{draft_id}")
def decide_review_response_draft(
    draft_id: str,
    payload: ReputationResponseDraftDecision,
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = reputation_response_service.review_response_draft(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        draft_id=draft_id,
        user_id=user["id"],
        decision=payload.decision,
        approved_text=payload.approved_text,
    )
    return envelope(request, row)


@reviews_router.post("/sync")
def sync_review_inventory(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.tenant_id == user["tenant_id"],
            DataConnection.organization_id == user["organization_id"],
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == reputation_inventory_service.OWNED_PROFILE_PROVIDER,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Connect this location to its Google business listing before reviews can update.",
                "reason_code": "owned_profile_connection_required",
            },
        )
    try:
        job = durable_job_service.run_owned_review_sync_now(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            connection_id=connection.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "reason_code": "review_update_unavailable",
            },
        ) from exc

    rows = reputation_inventory_service.list_reviews(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
        source_type="owned_profile",
        limit=250,
    )
    job_status = str(job.get("status") or "queued")
    if job_status == "completed":
        message = f"Review check finished. {len(rows)} reviews are saved for this location."
    elif job_status == "running":
        message = "Review check is still running. Saved reviews remain available below."
    else:
        message = (
            "Reviews could not be updated yet. Check the business listing connection and try again."
        )
    return envelope(
        request,
        {
            "job": {
                "id": job.get("job_id"),
                "status": job_status,
                "message": message,
            },
            "items": [
                ReputationReviewOut.model_validate(row).model_dump(mode="json") for row in rows
            ],
            "summary": reputation_inventory_service.inventory_summary(rows),
            "reply_tools_available": True,
        },
    )


@reviews_router.get("/velocity")
def get_review_velocity(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ingest_task = reviews_ingest.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
        velocity_task = reviews_compute_velocity.delay(
            tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
    except KombuError:
        ingest_task = None
        velocity_task = None
    try:
        velocity = local_service.get_velocity(
            db, tenant_id=user["tenant_id"], campaign_id=campaign_id
        )
    except ValueError:
        velocity = {
            "campaign_id": campaign_id,
            "profile_id": None,
            "reviews_last_30d": 0,
            "avg_rating_last_30d": 0.0,
            "captured_at": None,
        }
    truth = _local_provider_truth(
        has_data=bool(velocity.get("profile_id")) or bool(velocity.get("reviews_last_30d")),
        job_queued=velocity_task is not None or ingest_task is not None,
        captured_at=velocity.get("captured_at"),
    )
    return envelope(
        request,
        {
            **velocity,
            "job_id": velocity_task.id if velocity_task is not None else None,
            "ingest_job_id": ingest_task.id if ingest_task is not None else None,
            "truth": truth,
        },
    )
