from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.local import ReviewVelocitySnapshot
from app.services import local_service
from app.tasks.tasks import local_collect_profile_snapshot, local_compute_health_score, reviews_compute_velocity, reviews_ingest

local_router = APIRouter(prefix="/local", tags=["local"])
reviews_router = APIRouter(prefix="/reviews", tags=["reviews"])


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
    return envelope(
        request,
        {
            "campaign_id": campaign_id,
            "job_id": score_task.id if score_task is not None else None,
            "snapshot_job_id": snapshot_task.id if snapshot_task is not None else None,
        },
    )


@local_router.get("/map-pack")
def get_map_pack(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    profile = local_service.collect_profile_snapshot(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(
        request,
        {
            "campaign_id": campaign_id,
            "provider": profile.provider,
            "map_pack_position": profile.map_pack_position,
            "profile_name": profile.profile_name,
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
    reviews = local_service.get_reviews(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(
        request,
        {
            "campaign_id": campaign_id,
            "job_id": task.id if task is not None else None,
            "items": reviews,
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
    velocity_snapshot = (
        db.query(ReviewVelocitySnapshot)
        .filter(
            ReviewVelocitySnapshot.tenant_id == user["tenant_id"],
            ReviewVelocitySnapshot.campaign_id == campaign_id,
        )
        .order_by(ReviewVelocitySnapshot.captured_at.desc())
        .first()
    )
    return envelope(
        request,
        {
            "campaign_id": campaign_id,
            "velocity": (
                {
                    "profile_id": velocity_snapshot.profile_id,
                    "reviews_last_30d": velocity_snapshot.reviews_last_30d,
                    "avg_rating_last_30d": velocity_snapshot.avg_rating_last_30d,
                    "captured_at": velocity_snapshot.captured_at.isoformat(),
                }
                if velocity_snapshot is not None
                else None
            ),
            "job_id": velocity_task.id if velocity_task is not None else None,
            "ingest_job_id": ingest_task.id if ingest_task is not None else None,
        },
    )
