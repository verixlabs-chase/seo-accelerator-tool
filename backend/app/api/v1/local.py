from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.services import local_service
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import local_collect_profile_snapshot, local_compute_health_score, reviews_compute_velocity, reviews_ingest

local_router = APIRouter(prefix="/local", tags=["local"])
reviews_router = APIRouter(prefix="/reviews", tags=["reviews"])


def _local_provider_truth(*, has_data: bool, job_queued: bool, captured_at: str | None = None) -> dict:
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
        snapshot_task = local_collect_profile_snapshot.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
        score_task = local_compute_health_score.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        snapshot_task = None
        score_task = None
    try:
        latest_health = local_service.get_latest_health(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
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
        profile = local_service.collect_profile_snapshot(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
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
        reviews = local_service.get_reviews(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
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


@reviews_router.get("/velocity")
def get_review_velocity(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ingest_task = reviews_ingest.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
        velocity_task = reviews_compute_velocity.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        ingest_task = None
        velocity_task = None
    try:
        velocity = local_service.get_velocity(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
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
