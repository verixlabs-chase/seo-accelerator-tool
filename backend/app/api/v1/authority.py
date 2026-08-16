from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.authority import Citation
from app.schemas.authority import (
    AuthorityActionIn,
    AuthorityGapRefreshIn,
    AuthorityInventoryRefreshIn,
    AuthorityLinkChangeRefreshIn,
    AuthorityOutreachDraftIn,
    AuthorityOutreachDraftUpdateIn,
    BacklinkOut,
    CitationSubmissionIn,
    DirectoryListingDiscoveryPreviewIn,
    DirectoryListingDiscoveryRunIn,
    DirectoryListingOut,
    OutreachCampaignIn,
    OutreachContactIn,
)
from app.services import (
    authority_service,
    durable_job_service,
    listing_discovery_service,
    listing_inventory_service,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp
from app.tasks.tasks import (
    authority_sync_backlinks,
)

authority_router = APIRouter(prefix="/authority", tags=["authority"])
citations_router = APIRouter(prefix="/citations", tags=["citations"])


def _raise_listing_discovery_error(exc: Exception) -> None:
    raise HTTPException(
        status_code=int(getattr(exc, "status_code", status.HTTP_409_CONFLICT)),
        detail={
            "message": str(exc),
            "reason_code": str(getattr(exc, "reason_code", "public_listing_check_unavailable")),
        },
    ) from exc


def _raise_listing_correction_error(exc: CostEconomicsError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "message": str(exc),
            "reason_code": exc.reason_code,
        },
    ) from exc


def _citation_truth(
    *, citation_count: int, live_count: int, captured_at: str | None = None
) -> dict:
    states: list[str] = ["unavailable", "operator_assisted"]
    reasons: list[str] = [
        "listing_correction_provider_not_approved",
        "saved_request_history_is_not_live_directory_confirmation",
    ]
    provider_state = "correction_provider_not_approved"
    setup_state = "provider_unavailable"
    operator_state = "operator_assisted"
    summary = (
        "Saved listing request history is shown here. Live directory submission and status "
        "synchronization are not available yet."
    )

    freshness_state = freshness_state_from_timestamp(captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("citation_status_is_stale")
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
    return envelope(
        request,
        {
            "id": item.id,
            "campaign_id": item.campaign_id,
            "name": item.name,
            "status": item.status,
            "manual_send_only": True,
            "message": "Saved as a draft. No outreach was scheduled or sent.",
        },
    )


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
    return envelope(
        request,
        {
            "id": contact.id,
            "campaign_id": contact.campaign_id,
            "outreach_campaign_id": contact.outreach_campaign_id,
            "full_name": contact.full_name,
            "email": contact.email,
            "status": contact.status,
            "manual_send_only": True,
            "message": "Saved for owner review. The address was not enriched or contacted.",
        },
    )


@authority_router.post("/link-gaps/refresh")
def refresh_authority_link_gaps(
    request: Request,
    body: AuthorityGapRefreshIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.refresh_authority_link_gaps(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        idempotency_key=body.idempotency_key,
    )
    return envelope(request, payload)


@authority_router.get("/link-gaps")
def get_authority_link_gaps(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.latest_authority_link_gaps(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@authority_router.post("/link-changes/refresh")
def refresh_authority_link_changes(
    request: Request,
    body: AuthorityLinkChangeRefreshIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.refresh_authority_link_changes(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        idempotency_key=body.idempotency_key,
    )
    return envelope(request, payload)


@authority_router.get("/link-changes")
def get_authority_link_changes(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.latest_authority_link_changes(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@authority_router.post("/inventory/refresh")
def refresh_authority_inventory(
    request: Request,
    body: AuthorityInventoryRefreshIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.refresh_authority_inventory(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        business_name=body.business_name,
        idempotency_key=body.idempotency_key,
    )
    return envelope(request, payload)


@authority_router.get("/inventory")
def get_authority_inventory(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.latest_authority_inventory(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@authority_router.post("/actions")
def create_authority_action(
    request: Request,
    body: AuthorityActionIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.create_authority_action(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        source_type=body.source_type,
        source_id=body.source_id,
        owner_confirmed_relevant=body.owner_confirmed_relevant,
    )
    return envelope(request, payload)


@authority_router.post("/outreach-drafts")
def create_authority_outreach_draft(
    request: Request,
    body: AuthorityOutreachDraftIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.create_authority_outreach_draft(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        source_type=body.source_type,
        source_id=body.source_id,
        owner_confirmed_relevant=body.owner_confirmed_relevant,
        actor_user_id=user["user_id"],
    )
    return envelope(request, payload)


@authority_router.get("/outreach-drafts")
def list_authority_outreach_drafts(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.list_authority_outreach_drafts(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=campaign_id,
    )
    return envelope(request, payload)


@authority_router.patch("/outreach-drafts/{draft_id}")
def update_authority_outreach_draft(
    draft_id: str,
    request: Request,
    body: AuthorityOutreachDraftUpdateIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = authority_service.update_authority_outreach_draft(
        db,
        tenant_id=user["tenant_id"],
        organization_id=user["organization_id"],
        campaign_id=body.campaign_id,
        draft_id=draft_id,
        updates=body.model_dump(exclude={"campaign_id"}, exclude_unset=True),
    )
    return envelope(request, payload)


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
    rows = authority_service.list_backlinks(
        db, tenant_id=user["tenant_id"], campaign_id=campaign_id
    )
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
    try:
        citation = authority_service.submit_citation(
            db,
            tenant_id=user["tenant_id"],
            campaign_id=body.campaign_id,
            directory_name=body.directory_name,
        )
    except CostEconomicsError as exc:
        db.rollback()
        _raise_listing_correction_error(exc)
    return envelope(
        request,
        {
            "id": citation.id,
            "campaign_id": citation.campaign_id,
            "directory_name": citation.directory_name,
            "submission_status": citation.submission_status,
        },
    )


@citations_router.get("/inventory")
def get_listing_inventory(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    rows = listing_inventory_service.list_inventory(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    summary = listing_inventory_service.inventory_summary(rows)
    correction_access = authority_service.listing_correction_access(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    return envelope(
        request,
        {
            "items": [
                DirectoryListingOut.model_validate(row).model_dump(mode="json") for row in rows
            ],
            "summary": summary,
            "truth": {
                "classification": (
                    "provider_backed"
                    if summary["freshly_checked"]
                    else "imported_history"
                    if summary["imported_history"]
                    else "not_collected"
                ),
                "summary": (
                    "These are saved public listing observations for this business location. Imported history is labeled and does not count as a fresh check."
                    if summary["freshly_checked"]
                    else "Imported listing history is available, but a fresh public listing check has not been completed yet."
                    if summary["imported_history"]
                    else "No public listing inventory has been collected for this business location yet."
                ),
                "correction_available": False,
                "correction_reason": "A directory correction provider has not been approved.",
                "correction_access": correction_access,
            },
        },
    )


@citations_router.post("/discovery/preview")
def preview_listing_discovery(
    request: Request,
    body: DirectoryListingDiscoveryPreviewIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        payload = listing_discovery_service.preview_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            campaign_id=body.campaign_id,
        )
    except (listing_discovery_service.ListingDiscoveryError, CostEconomicsError) as exc:
        _raise_listing_discovery_error(exc)
    return envelope(request, payload)


@citations_router.post(
    "/discovery/runs",
    status_code=status.HTTP_202_ACCEPTED,
)
def create_listing_discovery_run(
    request: Request,
    body: DirectoryListingDiscoveryRunIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run, created = listing_discovery_service.create_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            campaign_id=body.campaign_id,
            requested_by_user_id=user["id"],
            idempotency_key=body.idempotency_key,
        )
        durable_job_service.run_directory_listing_discovery_now(
            db,
            tenant_id=user["tenant_id"],
            run_id=run.id,
        )
        run = listing_discovery_service.get_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            run_id=run.id,
        )
    except (listing_discovery_service.ListingDiscoveryError, CostEconomicsError) as exc:
        db.rollback()
        _raise_listing_discovery_error(exc)
    return envelope(
        request,
        {
            "created": created,
            "run": listing_discovery_service.serialize_run(run),
        },
    )


@citations_router.get("/discovery/latest")
def get_latest_listing_discovery_run(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        run = listing_discovery_service.latest_run(
            db,
            tenant_id=user["tenant_id"],
            organization_id=user["organization_id"],
            campaign_id=campaign_id,
        )
    except listing_discovery_service.ListingDiscoveryError as exc:
        _raise_listing_discovery_error(exc)
    return envelope(
        request,
        {"run": listing_discovery_service.serialize_run(run) if run is not None else None},
    )


@citations_router.get("/status")
def get_citation_status(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    correction_access = authority_service.listing_correction_access(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
    )
    rows = (
        db.query(Citation)
        .filter(Citation.tenant_id == user["tenant_id"], Citation.campaign_id == campaign_id)
        .order_by(Citation.updated_at.desc())
        .all()
    )
    live_count = sum(
        1 for row in rows if row.submission_status in {"live", "verified"} or row.listing_url
    )
    truth = _citation_truth(
        citation_count=len(rows),
        live_count=live_count,
        captured_at=rows[0].updated_at.isoformat() if rows and rows[0].updated_at else None,
    )
    return envelope(
        request,
        {
            "job_id": None,
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
            "correction_access": correction_access,
        },
    )
