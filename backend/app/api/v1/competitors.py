from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.competitor import CompetitorCreateIn, CompetitorOut
from app.services import competitor_service
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import competitor_collect_snapshot

router = APIRouter(prefix="/competitors", tags=["competitors"])


def _competitor_truth(*, competitor_count: int, snapshot_count: int, job_queued: bool, captured_at: str | None = None) -> dict:
    settings = get_settings()
    backend = getattr(settings, "competitor_provider_backend", "dataset").strip().lower()
    environment = getattr(settings, "app_env", "").strip().lower()

    states: list[str] = []
    reasons: list[str] = []
    provider_state = backend or "unknown"
    setup_state = "configured"
    operator_state = "self_serve"

    if backend == "dataset":
        provider_state = "dataset_backed"
        states.append("operator_assisted")
        reasons.append("competitor_data_depends_on_preloaded_dataset_rows")
        if competitor_count > 0 and snapshot_count == 0:
            states.append("unavailable")
            setup_state = "dataset_seed_required"
            summary = "Competitor tracking is not provider-backed here. The default dataset mode needs stored competitor rows before gap data becomes real."
        else:
            summary = "Competitor tracking is dataset-backed, not live-provider-backed. Snapshot coverage depends on stored competitor rows."
    elif backend in {"fixture", "synthetic"} and environment == "test":
        states.append("synthetic")
        reasons.append("competitor_runtime_uses_test_fixture_provider")
        summary = "Competitor tracking is using a synthetic fixture provider in test mode."
    else:
        states.append("provider_backed")
        summary = f"Competitor tracking is using the configured {backend} provider."

    freshness_state = freshness_state_from_timestamp(captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("competitor_snapshot_is_stale")
    if job_queued:
        states.append("in_progress")
        reasons.append("competitor_snapshot_refresh_queued")

    return build_truth(
        states=states,
        summary=summary,
        provider_state=provider_state,
        setup_state=setup_state,
        operator_state=operator_state,
        freshness_state=freshness_state,
        reasons=reasons,
    )


@router.post("")
def create_competitor(
    request: Request,
    body: CompetitorCreateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    item = competitor_service.create_competitor(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        domain=body.domain,
        label=body.label,
    )
    return envelope(request, CompetitorOut.model_validate(item).model_dump(mode="json"))


@router.get("")
def get_competitors(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    items = competitor_service.list_competitors(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    truth = _competitor_truth(competitor_count=len(items), snapshot_count=0, job_queued=False)
    return envelope(
        request,
        {
            "items": [CompetitorOut.model_validate(i).model_dump(mode="json") for i in items],
            "truth": truth,
        },
    )


@router.get("/snapshots")
def get_snapshots(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = competitor_collect_snapshot.delay(campaign_id=campaign_id, tenant_id=user["tenant_id"])
    except KombuError:
        task = None
    snapshots = competitor_service.list_snapshots(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    competitors = competitor_service.list_competitors(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    snapshots_collected = len({str(item.get("competitor_id", "")) for item in snapshots if item.get("competitor_id")})
    truth = _competitor_truth(
        competitor_count=len(competitors),
        snapshot_count=snapshots_collected,
        job_queued=task is not None,
        captured_at=snapshots[0]["captured_at"] if snapshots else None,
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "summary": {"snapshots_collected": snapshots_collected},
            "items": snapshots,
            "truth": truth,
        },
    )


@router.get("/gaps")
def get_gaps(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    gaps = competitor_service.compute_gaps(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    competitors = competitor_service.list_competitors(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    truth = _competitor_truth(
        competitor_count=len(competitors),
        snapshot_count=len(gaps),
        job_queued=False,
    )
    return envelope(request, {"items": gaps, "truth": truth})
