from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.authority import Citation
from app.schemas.authority import BacklinkOut, CitationSubmissionIn, OutreachCampaignIn, OutreachContactIn
from app.services import authority_service
from app.tasks.tasks import (
    authority_sync_backlinks,
    citation_refresh_status,
    citation_submit_batch,
    outreach_enrich_contacts,
    outreach_execute_sequence_step,
)

authority_router = APIRouter(prefix="/authority", tags=["authority"])
citations_router = APIRouter(prefix="/citations", tags=["citations"])


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
        .order_by(Citation.created_at.desc())
        .all()
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
            ]
        },
    )
