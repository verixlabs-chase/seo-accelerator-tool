from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
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
    profile = local_service.collect_profile_snapshot(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    payload = local_service.compute_health_score(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        local_collect_profile_snapshot.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
        local_compute_health_score.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        pass
    return envelope(
        request,
        {
            **payload,
            "map_pack_position": profile.map_pack_position,
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
    ingest_summary = local_service.ingest_reviews(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        reviews_ingest.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        pass
    reviews = local_service.get_reviews(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, {"summary": ingest_summary, "items": reviews})


@reviews_router.get("/velocity")
def get_review_velocity(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    local_service.ingest_reviews(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    velocity = local_service.compute_review_velocity(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    try:
        reviews_compute_velocity.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        pass
    return envelope(request, velocity)

