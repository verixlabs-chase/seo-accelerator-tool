from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.intelligence.intelligence_metrics_aggregator import (
    compute_campaign_metrics,
    compute_campaign_trends,
    compute_system_metrics,
    compute_system_trends,
)
from app.models.campaign import Campaign
from app.schemas.intelligence_metrics import (
    CampaignIntelligenceMetricsOut,
    IntelligenceMetricsSnapshotOut,
    IntelligenceTrendsOut,
    SystemIntelligenceMetricsOut,
)

router = APIRouter(prefix='/intelligence/metrics', tags=['intelligence'])


@router.get('/campaign/{campaign_id}')
def get_campaign_metrics(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != user['tenant_id']:
        raise HTTPException(status_code=404, detail='Campaign not found')

    snapshot = compute_campaign_metrics(campaign_id, db=db)
    trends = compute_campaign_trends(campaign_id, db=db)

    outcomes = snapshot.positive_outcomes + snapshot.negative_outcomes
    payload = {
        'snapshot': IntelligenceMetricsSnapshotOut.model_validate(snapshot).model_dump(mode='json'),
        'recommendation_success_rate': round(snapshot.positive_outcomes / max(outcomes, 1), 6),
        'execution_success_rate': round(snapshot.positive_outcomes / max(snapshot.executions_run, 1), 6),
        'pattern_discovery_rate': round(snapshot.patterns_detected / max(snapshot.features_computed, 1), 6),
        'learning_velocity': round(float(trends['learning_velocity']), 6),
        'campaign_improvement_trend': round(float(trends['campaign_improvement_trend']), 6),
    }
    return envelope(request, CampaignIntelligenceMetricsOut.model_validate(payload).model_dump(mode='json'))


@router.get('/system')
def get_system_metrics(
    request: Request,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    _ = user
    metrics = compute_system_metrics(db=db)
    return envelope(request, SystemIntelligenceMetricsOut.model_validate(metrics).model_dump(mode='json'))


@router.get('/trends')
def get_intelligence_trends(
    request: Request,
    campaign_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=2, le=120),
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    if campaign_id:
        campaign = db.get(Campaign, campaign_id)
        if campaign is None or campaign.tenant_id != user['tenant_id']:
            raise HTTPException(status_code=404, detail='Campaign not found')
        trends = compute_campaign_trends(campaign_id, db=db, days=days)
    else:
        trends = compute_system_trends(db=db, days=days)
    return envelope(request, IntelligenceTrendsOut.model_validate(trends).model_dump(mode='json'))
