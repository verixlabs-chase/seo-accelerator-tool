from fastapi import APIRouter, Depends, Query, Request
from kombu.exceptions import KombuError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.schemas.entity import EntityAnalyzeIn, EntityReportOut
from app.services import entity_service
from app.tasks.tasks import entity_analyze_campaign

router = APIRouter(prefix="/entity", tags=["entity"])


@router.post("/analyze")
def analyze_entities(
    request: Request,
    body: EntityAnalyzeIn,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        entity_analyze_campaign.delay(tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
        return envelope(request, {"campaign_id": body.campaign_id, "status": "queued"})
    except KombuError:
        payload = entity_service.run_entity_analysis(db, tenant_id=user["tenant_id"], campaign_id=body.campaign_id)
        return envelope(request, EntityReportOut.model_validate(payload).model_dump(mode="json"))


@router.get("/report")
def get_entity_report(
    request: Request,
    campaign_id: str = Query(...),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    payload = entity_service.get_latest_entity_report(db, tenant_id=user["tenant_id"], campaign_id=campaign_id)
    return envelope(request, EntityReportOut.model_validate(payload).model_dump(mode="json"))
