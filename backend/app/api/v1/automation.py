from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.strategy_automation_event import StrategyAutomationEvent

router = APIRouter(prefix='/automation', tags=['automation'])


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Campaign not found')
    return campaign


def _event_rows(db: Session, campaign_id: str) -> list[StrategyAutomationEvent]:
    return (
        db.query(StrategyAutomationEvent)
        .filter(StrategyAutomationEvent.campaign_id == campaign_id)
        .order_by(StrategyAutomationEvent.evaluation_date.asc(), StrategyAutomationEvent.id.asc())
        .all()
    )


def _serialize_event(row: StrategyAutomationEvent) -> dict:
    return {
        'evaluation_date': row.evaluation_date.isoformat(),
        'prior_phase': row.prior_phase,
        'new_phase': row.new_phase,
        'triggered_rules': json.loads(row.triggered_rules or '[]'),
        'decision_hash': row.decision_hash,
        'momentum_snapshot': json.loads(row.momentum_snapshot or '{}'),
        'action_snapshot': json.loads(row.action_summary or '{}'),
    }


@router.get('/campaign/{campaign_id}/timeline')
def get_automation_timeline(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    _campaign_or_404(db, str(user['tenant_id']), campaign_id)
    items = [_serialize_event(row) for row in _event_rows(db, campaign_id)]
    return envelope(request, {'items': items})


@router.get('/campaign/{campaign_id}/export')
def export_automation_events(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    _campaign_or_404(db, str(user['tenant_id']), campaign_id)
    events = [_serialize_event(row) for row in _event_rows(db, campaign_id)]
    payload = {
        'campaign_id': campaign_id,
        'export_generated_at': datetime.now(UTC).replace(microsecond=0).isoformat(),
        'events': events,
    }
    return envelope(request, payload)
