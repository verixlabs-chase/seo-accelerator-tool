from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.models.authority import Citation
from app.schemas.authority import BacklinkOut, CitationSubmissionIn, OutreachCampaignIn, OutreachContactIn
from app.services import authority_service
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import (
    authority_sync_backlinks,
    citation_refresh_status,
    citation_submit_batch,
    outreach_enrich_contacts,
    outreach_execute_sequence_step,
)

authority_router = APIRouter(prefix="/authority", tags=["authority"])
citations_router = APIRouter(prefix="/citations", tags=["citations"])


def _citation_truth(*, citation_count: int, live_count: int, job_queued: bool, captured_at: str | None = None) -> dict:
    settings = get_settings()
    backend = getattr(settings, "authority_provider_backend", "synthetic").strip().lower()
    environment = getattr(settings, "app_env", "").strip().lower()

    states: list[str] = []
    reasons: list[str] = []
    provider_state = backend or "unknown"
    setup_state = "configured"
    operator_state = "self_serve"

    if backend == "synthetic":
        if environment == "test":
            states.append("synthetic")
            reasons.append("citation_runtime_uses_test_fixture_provider")
            summary = "Citation refresh is using a synthetic fixture provider in test mode."
        else:
            states.extend(["unavailable", "operator_assisted"])
            provider_state = "synthetic_disabled_outside_test"
            setup_state = "provider_unavailable"
            operator_state = "operator_assisted"
            reasons.extend(
                [
                    "citation_refresh_provider_not_available_in_this_runtime",
                    "citation_status_can_reflect_workflow_rows_without_live_directory_confirmation",
                ]
            )
            summary = "Citation statuses are workflow records in this runtime. Live directory refresh is not provider-backed here."
    else:
        states.append("provider_backed")
        summary = f"Citation refresh is using the configured {backend} provider."

    freshness_state = freshness_state_from_timestamp(captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("citation_status_is_stale")
    if job_queued:
        states.append("in_progress")
        reasons.append("citation_refresh_queued")
    if citation_count > 0 and live_count == 0:
        states.append("operator_assisted")
        reasons.append("citation_status_requires_manual_directory_confirmation")

    return build_truth(
        states=states,
        summary=summary,
        provider_state=provider_state,
        setup_state=setup_state,
        operator_state=operator_state,
        freshness_state=freshness_state,
        reasons=reasons,
    )


@authority_router.post("/outreach-campaigns")
def create_outreach_campaign(
    request: Request,
    body: OutreachCampaignIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    item = authority_service.create_outreach_campaign(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        name=body.name,
    )
    try:
        outreach_execute_sequence_step.delay(tenant_id=user["tenant_id"], outreach_campaign_id=item.id)
    except KombuError:
        pass
    return envelope(request, {"id": item.id, "campaign_id": item.campaign_id, "name": item.name, "status": item.status})


@authority_router.post("/contacts")
def create_outreach_contact(
    request: Request,
    body: OutreachContactIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    contact = authority_service.create_outreach_contact(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        outreach_campaign_id=body.outreach_campaign_id,
        full_name=body.full_name,
        email=body.email,
    )
    try:
        outreach_enrich_contacts.delay(tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
    except KombuError:
        pass
    return envelope(
        request,
        {
            "id": contact.id,
            "campaign_id": contact.campaign_id,
            "outreach_campaign_id": contact.outreach_campaign_id,
            "full_name": contact.full_name,
            "email": contact.email,
            "status": contact.status,
        },
    )


@authority_router.get("/backlinks")
def get_backlinks(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = authority_sync_backlinks.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        task = None
    rows = authority_service.list_backlinks(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "items": [BacklinkOut.model_validate(row).model_dump(mode="json") for row in rows],
        },
    )


@citations_router.post("/submissions")
def submit_citation(
    request: Request,
    body: CitationSubmissionIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    citation = authority_service.submit_citation(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=body.campaign_id,
        directory_name=body.directory_name,
    )
    try:
        citation_submit_batch.delay(tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
    except KombuError:
        pass
    return envelope(
        request,
        {
            "id": citation.id,
            "campaign_id": citation.campaign_id,
            "directory_name": citation.directory_name,
            "submission_status": citation.submission_status,
        },
    )


@citations_router.get("/status")
def get_citation_status(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        task = citation_refresh_status.delay(tenant_id=user["tenant_id"], campaign_id=campaign_id)
    except KombuError:
        task = None
    rows = (
        db.query(Citation)
        .filter(Citation.tenant_id == user["tenant_id"], Citation.campaign_id == campaign_id)
        .order_by(Citation.updated_at.desc())
        .all()
    )
    live_count = sum(1 for row in rows if row.submission_status in {"live", "verified"} or row.listing_url)
    truth = _citation_truth(
        citation_count=len(rows),
        live_count=live_count,
        job_queued=task is not None,
        captured_at=rows[0].updated_at.isoformat() if rows and rows[0].updated_at else None,
    )
    return envelope(
        request,
        {
            "job_id": task.id if task is not None else None,
            "items": [
                {
                    "id": row.id,
                    "directory_name": row.directory_name,
                    "submission_status": row.submission_status,
                    "listing_url": row.listing_url,
                }
                for row in rows
            ],
            "truth": truth,
        },
    )
