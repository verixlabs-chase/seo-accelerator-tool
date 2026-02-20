from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.events import emit_event
from app.models.campaign import Campaign
from app.models.sub_account import SubAccount
from app.models.tenant import Tenant
from app.schemas.campaigns import CampaignCreateRequest, CampaignOut, CampaignSetupTransitionRequest
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
