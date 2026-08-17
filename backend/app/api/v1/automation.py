from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_org_role, require_roles
from app.api.response import envelope
from app.automation import automation_provider_conformance_kit
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.strategy_automation_event import StrategyAutomationEvent
from app.services.automation_webhook_service import (
    AutomationWebhookError,
    create_connection,
    disconnect_connection,
    list_connections,
    list_deliveries,
    retry_delivery,
    recover_dead_letter_delivery,
    pause_connection,
    resume_connection,
    rotate_signing_secret,
    send_test_delivery,
)

router = APIRouter(prefix='/automation', tags=['automation'])

_CONFORMANCE_PROVIDERS = frozenset({"zapier", "make", "pipedream", "n8n"})


class AutomationConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(min_length=2, max_length=20)
    destination_url: str = Field(min_length=10, max_length=2_000)
    event_types: list[str] = Field(min_length=1, max_length=6)


def _campaign_or_404(db: Session, tenant_id: str, organization_id: str | None, campaign_id: str) -> Campaign:
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Campaign not found')
    if organization_id is not None and campaign.organization_id != organization_id:
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
    _campaign_or_404(db, str(user['tenant_id']), user.get('organization_id'), campaign_id)
    items = [_serialize_event(row) for row in _event_rows(db, campaign_id)]
    return envelope(request, {'items': items})


@router.get('/campaign/{campaign_id}/export')
def export_automation_events(
    request: Request,
    campaign_id: str,
    user: dict = Depends(require_roles({'tenant_admin'})),
    db: Session = Depends(get_db),
) -> dict:
    _campaign_or_404(db, str(user['tenant_id']), user.get('organization_id'), campaign_id)
    events = [_serialize_event(row) for row in _event_rows(db, campaign_id)]
    payload = {
        'campaign_id': campaign_id,
        'export_generated_at': datetime.now(UTC).replace(microsecond=0).isoformat(),
        'events': events,
    }
    return envelope(request, payload)


@router.get('/connections')
def get_automation_connections(
    request: Request,
    user: dict = Depends(require_org_role({'org_user'})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        list_connections(db, organization_id=str(user['organization_id'])),
    )


@router.get('/conformance/{provider}')
def get_automation_provider_conformance(
    request: Request,
    provider: str,
    user: dict = Depends(require_org_role({'org_user'})),
) -> dict:
    del user
    try:
        data = automation_provider_conformance_kit(
            provider=provider,
            supported_provider_codes=_CONFORMANCE_PROVIDERS,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "This automation provider is not supported.",
                "reason_code": "automation_provider_not_supported",
            },
        ) from exc
    return envelope(request, data)


@router.post('/connections', status_code=status.HTTP_201_CREATED)
def create_automation_connection(
    request: Request,
    body: AutomationConnectionIn,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_connection(
            db,
            organization_id=str(user['organization_id']),
            actor_user_id=str(user['id']),
            name=body.name,
            provider=body.provider,
            destination_url=body.destination_url,
            event_types=body.event_types,
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.post('/connections/{connection_id}/test')
def test_automation_connection(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = send_test_delivery(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.post('/connections/{connection_id}/rotate-secret')
def rotate_automation_connection_secret(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = rotate_signing_secret(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.post('/connections/{connection_id}/pause')
def pause_automation_connection(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = pause_connection(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.post('/connections/{connection_id}/resume')
def resume_automation_connection(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = resume_connection(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.delete('/connections/{connection_id}')
def delete_automation_connection(
    request: Request,
    connection_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = disconnect_connection(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.get('/deliveries')
def get_automation_deliveries(
    request: Request,
    connection_id: str | None = None,
    user: dict = Depends(require_org_role({'org_user'})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        list_deliveries(
            db,
            organization_id=str(user['organization_id']),
            connection_id=connection_id,
        ),
    )


@router.post('/deliveries/{delivery_id}/retry')
def retry_automation_delivery(
    request: Request,
    delivery_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = retry_delivery(
            db,
            organization_id=str(user['organization_id']),
            delivery_id=delivery_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


@router.post('/deliveries/{delivery_id}/recover')
def recover_automation_delivery(
    request: Request,
    delivery_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = recover_dead_letter_delivery(
            db,
            organization_id=str(user['organization_id']),
            delivery_id=delivery_id,
            actor_user_id=str(user['id']),
        )
    except AutomationWebhookError as exc:
        raise _webhook_http_error(exc) from exc
    return envelope(request, data)


def _webhook_http_error(exc: AutomationWebhookError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )
