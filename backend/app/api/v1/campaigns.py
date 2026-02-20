from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.events import emit_event
from app.models.campaign import Campaign
from app.models.sub_account import SubAccount
from app.models.tenant import Tenant
from app.schemas.campaign_dashboard import CampaignDashboardOut
from app.schemas.campaigns import CampaignCreateRequest, CampaignOut, CampaignSetupTransitionRequest
from app.services.campaign_dashboard_service import build_campaign_dashboard
from app.services import lifecycle_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("")
def create_campaign(
    request: Request,
    body: CampaignCreateRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    tenant = db.get(Tenant, user["tenant_id"])
    if tenant is None or tenant.status != "Active":
        return envelope(
            request,
            None,
            {
                "code": "tenant_inactive",
                "message": "Tenant must be Active to create campaigns.",
                "details": {},
            },
        )
    sub_account_id = body.sub_account_id
    if sub_account_id is not None:
        sub_account = (
            db.query(SubAccount)
            .filter(
                SubAccount.id == sub_account_id,
                SubAccount.organization_id == user["organization_id"],
            )
            .first()
        )
        if sub_account is None:
            return envelope(
                request,
                None,
                {
                    "code": "subaccount_not_found",
                    "message": "SubAccount not found in organization scope.",
                    "details": {"sub_account_id": sub_account_id},
                },
            )
        if sub_account.status != "active":
            return envelope(
                request,
                None,
                {
                    "code": "subaccount_inactive",
                    "message": "SubAccount must be active to attach new campaigns.",
                    "details": {"sub_account_id": sub_account_id, "status": sub_account.status},
                },
            )

    campaign = Campaign(
        tenant_id=user["tenant_id"],
        sub_account_id=sub_account_id,
        name=body.name,
        domain=body.domain,
    )
    db.add(campaign)
    db.flush()
    emit_event(
        db,
        tenant_id=user["tenant_id"],
        event_type="campaign.created",
        payload={"campaign_id": campaign.id, "setup_state": campaign.setup_state, "sub_account_id": campaign.sub_account_id},
    )
    db.commit()
    db.refresh(campaign)
    return envelope(request, CampaignOut.model_validate(campaign).model_dump(mode="json"))


@router.get("")
def list_campaigns(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == user["tenant_id"])
        .order_by(Campaign.created_at.desc())
        .all()
    )
    data = [CampaignOut.model_validate(c).model_dump(mode="json") for c in campaigns]
    return envelope(request, {"items": data})


@router.patch("/{campaign_id}/setup-state")
def transition_campaign_setup_state(
    request: Request,
    campaign_id: str,
    body: CampaignSetupTransitionRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = lifecycle_service.transition_campaign_setup_state(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        target_state=body.target_state,
    )
    return envelope(request, CampaignOut.model_validate(row).model_dump(mode="json"))


@router.get("/{id}/dashboard")
def get_campaign_dashboard(
    request: Request,
    id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    normalized_date_to = _as_utc(date_to) or datetime.now(UTC)
    normalized_date_from = _as_utc(date_from) or (normalized_date_to - timedelta(days=30))
    if normalized_date_from > normalized_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )

    payload = build_campaign_dashboard(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=id,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
    )
    return envelope(request, CampaignDashboardOut.model_validate(payload).model_dump(mode="json"))


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
