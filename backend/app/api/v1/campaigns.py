from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.schemas.campaigns import CampaignCreateRequest, CampaignOut

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("")
def create_campaign(
    request: Request,
    body: CampaignCreateRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = Campaign(tenant_id=user["tenant_id"], name=body.name, domain=body.domain)
    db.add(campaign)
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
