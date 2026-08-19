from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
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
from app.services.automation_command_service import (
    COMMAND_SCHEMA_VERSION,
    AutomationCommandError,
    authenticate_service_account,
    create_service_account,
    execute_automation_command,
    get_command_receipt_for_account,
    list_command_receipts,
    list_service_accounts,
    n8n_report_ready_starter_workflow,
    n8n_recommendation_ready_starter_workflow,
    n8n_saved_report_schedule_starter_workflow,
    read_command_report_artifact,
    revoke_service_account,
    rotate_service_account_token,
)
from app.services.cost_economics_service import CostEconomicsError

router = APIRouter(prefix='/automation', tags=['automation'])

_CONFORMANCE_PROVIDERS = frozenset({"zapier", "make", "pipedream", "n8n"})
_BEARER_PATTERN = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


class AutomationConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(min_length=2, max_length=20)
    destination_url: str = Field(min_length=10, max_length=2_000)
    event_types: list[str] = Field(min_length=1, max_length=6)


class AutomationServiceAccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    location_id: str = Field(min_length=36, max_length=36)
    expires_in_days: int = Field(default=30, ge=1, le=90)
    allowed_commands: list[
        Literal["report.retrieve", "report.generate_saved", "recommendation.retrieve", "recommendation.request_review", "connection.refresh_saved", "listing.check_public", "content.create_working_draft", "content.request_draft_review"]
    ] | None = Field(default=None, min_length=1, max_length=8)


class AutomationServiceAccountRotateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_commands: list[
        Literal["report.retrieve", "report.generate_saved", "recommendation.retrieve", "recommendation.request_review", "connection.refresh_saved", "listing.check_public", "content.create_working_draft", "content.request_draft_review"]
    ] | None = Field(default=None, min_length=1, max_length=8)


class AutomationReportTargetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str | None = Field(default=None, min_length=36, max_length=36)
    campaign_id: str | None = Field(default=None, min_length=36, max_length=36)
    recommendation_id: str | None = Field(default=None, min_length=36, max_length=36)
    connection_id: str | None = Field(default=None, min_length=36, max_length=36)
    brief_id: str | None = Field(default=None, min_length=36, max_length=36)
    draft_id: str | None = Field(default=None, min_length=36, max_length=36)


class AutomationCommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=COMMAND_SCHEMA_VERSION, min_length=1, max_length=80)
    command_type: Literal[
        "report.retrieve", "report.generate_saved", "recommendation.retrieve",
        "recommendation.request_review",
        "connection.refresh_saved",
        "listing.check_public",
        "content.create_working_draft",
        "content.request_draft_review",
    ]
    organization_id: str = Field(min_length=36, max_length=36)
    location_id: str = Field(min_length=36, max_length=36)
    correlation_id: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    idempotency_key: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    reason: str = Field(min_length=3, max_length=500)
    target: AutomationReportTargetIn

    @model_validator(mode="after")
    def validate_target(self) -> "AutomationCommandIn":
        if self.command_type == "report.retrieve":
            valid = (
                self.target.report_id is not None
                and self.target.campaign_id is None
                and self.target.recommendation_id is None
                and self.target.connection_id is None
                and self.target.brief_id is None
                and self.target.draft_id is None
            )
        elif self.command_type in {"report.generate_saved", "listing.check_public"}:
            valid = (
                self.target.campaign_id is not None
                and self.target.report_id is None
                and self.target.recommendation_id is None
                and self.target.connection_id is None
                and self.target.brief_id is None
                and self.target.draft_id is None
            )
        elif self.command_type == "content.create_working_draft":
            valid = (
                self.target.campaign_id is not None
                and self.target.brief_id is not None
                and self.target.report_id is None
                and self.target.recommendation_id is None
                and self.target.connection_id is None
                and self.target.draft_id is None
            )
        elif self.command_type == "content.request_draft_review":
            valid = (
                self.target.campaign_id is not None
                and self.target.draft_id is not None
                and self.target.report_id is None
                and self.target.recommendation_id is None
                and self.target.connection_id is None
                and self.target.brief_id is None
            )
        elif self.command_type == "connection.refresh_saved":
            valid = (
                self.target.connection_id is not None
                and self.target.report_id is None
                and self.target.campaign_id is None
                and self.target.recommendation_id is None
                and self.target.brief_id is None
                and self.target.draft_id is None
            )
        else:
            valid = (
                self.target.recommendation_id is not None
                and self.target.report_id is None
                and self.target.campaign_id is None
                and self.target.connection_id is None
                and self.target.brief_id is None
                and self.target.draft_id is None
            )
        if not valid:
            raise ValueError("Choose the exact target required by this workflow action.")
        return self


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


@router.get('/service-accounts')
def get_automation_service_accounts(
    request: Request,
    user: dict = Depends(require_org_role({'org_user'})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        list_service_accounts(db, organization_id=str(user['organization_id'])),
    )


@router.post('/service-accounts', status_code=status.HTTP_201_CREATED)
def post_automation_service_account(
    request: Request,
    body: AutomationServiceAccountIn,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = create_service_account(
            db,
            organization_id=str(user['organization_id']),
            actor_user_id=str(user['id']),
            name=body.name,
            business_location_id=body.location_id,
            expires_in_days=body.expires_in_days,
            allowed_commands=body.allowed_commands,
        )
    except (AutomationCommandError, CostEconomicsError) as exc:
        raise _automation_command_http_error(exc) from exc
    return envelope(request, data)


@router.post('/service-accounts/{service_account_id}/rotate')
def rotate_automation_service_account(
    request: Request,
    service_account_id: str,
    body: AutomationServiceAccountRotateIn | None = None,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = rotate_service_account_token(
            db,
            organization_id=str(user['organization_id']),
            service_account_id=service_account_id,
            actor_user_id=str(user['id']),
            allowed_commands=body.allowed_commands if body is not None else None,
        )
    except (AutomationCommandError, CostEconomicsError) as exc:
        raise _automation_command_http_error(exc) from exc
    return envelope(request, data)


@router.delete('/service-accounts/{service_account_id}')
def delete_automation_service_account(
    request: Request,
    service_account_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> dict:
    try:
        data = revoke_service_account(
            db,
            organization_id=str(user['organization_id']),
            service_account_id=service_account_id,
            actor_user_id=str(user['id']),
        )
    except AutomationCommandError as exc:
        raise _automation_command_http_error(exc) from exc
    return envelope(request, data)


@router.get('/command-history')
def get_automation_command_history(
    request: Request,
    user: dict = Depends(require_org_role({'org_user'})),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(
        request,
        list_command_receipts(db, organization_id=str(user['organization_id'])),
    )


@router.get('/starter-workflows/n8n/report-ready')
def download_n8n_report_ready_starter_workflow(
    service_account_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> Response:
    try:
        workflow = n8n_report_ready_starter_workflow(
            db,
            organization_id=str(user['organization_id']),
            service_account_id=service_account_id,
        )
    except (AutomationCommandError, CostEconomicsError) as exc:
        raise _automation_command_http_error(exc) from exc
    return Response(
        content=json.dumps(workflow, indent=2, ensure_ascii=True) + "\n",
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="insightos-n8n-report-ready.json"'
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get('/starter-workflows/n8n/saved-report-schedule')
def download_n8n_saved_report_schedule_starter_workflow(
    service_account_id: str,
    campaign_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> Response:
    try:
        workflow = n8n_saved_report_schedule_starter_workflow(
            db,
            organization_id=str(user['organization_id']),
            service_account_id=service_account_id,
            campaign_id=campaign_id,
        )
    except (AutomationCommandError, CostEconomicsError) as exc:
        raise _automation_command_http_error(exc) from exc
    return Response(
        content=json.dumps(workflow, indent=2, ensure_ascii=True) + "\n",
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="insightos-n8n-monthly-private-report.json"'
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get('/starter-workflows/n8n/recommendation-ready')
def download_n8n_recommendation_ready_starter_workflow(
    service_account_id: str,
    user: dict = Depends(require_org_role({'org_owner'})),
    db: Session = Depends(get_db),
) -> Response:
    try:
        workflow = n8n_recommendation_ready_starter_workflow(
            db,
            organization_id=str(user['organization_id']),
            service_account_id=service_account_id,
        )
    except (AutomationCommandError, CostEconomicsError) as exc:
        raise _automation_command_http_error(exc) from exc
    return Response(
        content=json.dumps(workflow, indent=2, ensure_ascii=True) + "\n",
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="insightos-n8n-recommendation-ready.json"'
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post('/commands')
def post_automation_command(
    request: Request,
    body: AutomationCommandIn,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        account = authenticate_service_account(
            db,
            bearer_token=_bearer_token(authorization),
        )
        data = execute_automation_command(
            db,
            account=account,
            request_payload=body.model_dump(mode="json", exclude_none=True),
        )
    except AutomationCommandError as exc:
        raise _automation_command_http_error(exc) from exc
    return envelope(request, data)


@router.get('/commands/{receipt_id}')
def get_automation_command(
    request: Request,
    receipt_id: str,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        account = authenticate_service_account(
            db,
            bearer_token=_bearer_token(authorization),
        )
        data = get_command_receipt_for_account(
            db,
            account=account,
            receipt_id=receipt_id,
        )
    except AutomationCommandError as exc:
        raise _automation_command_http_error(exc) from exc
    return envelope(request, data)


@router.get('/commands/{receipt_id}/artifacts/{artifact_id}')
def download_automation_command_artifact(
    receipt_id: str,
    artifact_id: str,
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> Response:
    try:
        account = authenticate_service_account(
            db,
            bearer_token=_bearer_token(authorization),
        )
        artifact, content = read_command_report_artifact(
            db,
            account=account,
            receipt_id=receipt_id,
            artifact_id=artifact_id,
        )
    except AutomationCommandError as exc:
        raise _automation_command_http_error(exc) from exc
    extension = "pdf" if artifact.artifact_type == "pdf" else "html"
    return Response(
        content=content,
        media_type=artifact.content_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="insightos-report.{extension}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


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


def _bearer_token(authorization: str) -> str:
    match = _BEARER_PATTERN.fullmatch(authorization.strip())
    if match is None:
        raise AutomationCommandError(
            "The workflow command key is missing or invalid.",
            reason_code="automation_service_account_token_invalid",
            status_code=401,
        )
    return match.group(1).strip()


def _automation_command_http_error(
    exc: AutomationCommandError | CostEconomicsError,
) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"message": str(exc), "reason_code": exc.reason_code},
    )
