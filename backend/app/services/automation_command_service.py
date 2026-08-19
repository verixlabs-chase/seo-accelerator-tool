from __future__ import annotations

import hashlib
import json
import re
import secrets
from time import monotonic, sleep
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.automation.n8n_starter_workflow import (
    build_n8n_content_draft_review_workflow,
    build_n8n_saved_review_routing_workflow,
    build_n8n_review_response_draft_workflow,
    build_n8n_recommendation_ready_workflow,
    build_n8n_report_ready_workflow,
    build_n8n_saved_report_schedule_workflow,
)
from app.core.config import get_settings
from app.db.session import set_session_security_context
from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
    AutomationServiceAccountLocation,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.content import ContentDraft
from app.models.data_connection import DataConnection
from app.models.platform_job import PlatformJob
from app.models.authority import DirectoryListingDiscoveryRun
from app.models.organization import Organization
from app.models.reporting import MonthlyReport, ReportArtifact
from app.models.intelligence import StrategyRecommendation
from app.models.reputation import ReputationReview
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_CAMPAIGN_REPORT,
    FEATURE_EXTERNAL_AUTOMATION,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services import (
    data_connections_service,
    content_service,
    durable_job_service,
    google_business_profile_service,
    intelligence_service,
    listing_discovery_service,
    premium_report_service,
    reporting_service,
    reputation_response_service,
)


COMMAND_SCHEMA_VERSION = "insightos.automation.command.v1"
COMMAND_REPORT_RETRIEVE = "report.retrieve"
COMMAND_REPORT_GENERATE_SAVED = "report.generate_saved"
COMMAND_RECOMMENDATION_RETRIEVE = "recommendation.retrieve"
COMMAND_RECOMMENDATION_REQUEST_REVIEW = "recommendation.request_review"
COMMAND_CONNECTION_REFRESH_SAVED = "connection.refresh_saved"
COMMAND_LISTING_CHECK_PUBLIC = "listing.check_public"
COMMAND_CONTENT_CREATE_WORKING_DRAFT = "content.create_working_draft"
COMMAND_CONTENT_REQUEST_DRAFT_REVIEW = "content.request_draft_review"
COMMAND_REVIEW_RETRIEVE = "review.retrieve"
COMMAND_REVIEW_CREATE_RESPONSE_DRAFT = "review.create_response_draft"
ALLOWED_COMMANDS = (
    COMMAND_REPORT_RETRIEVE,
    COMMAND_REPORT_GENERATE_SAVED,
    COMMAND_RECOMMENDATION_RETRIEVE,
    COMMAND_RECOMMENDATION_REQUEST_REVIEW,
    COMMAND_CONNECTION_REFRESH_SAVED,
    COMMAND_LISTING_CHECK_PUBLIC,
    COMMAND_CONTENT_CREATE_WORKING_DRAFT,
    COMMAND_CONTENT_REQUEST_DRAFT_REVIEW,
    COMMAND_REVIEW_RETRIEVE,
    COMMAND_REVIEW_CREATE_RESPONSE_DRAFT,
)
DEFAULT_COMMANDS = (COMMAND_REPORT_RETRIEVE,)
MAX_SERVICE_ACCOUNT_DAYS = 90
TOKEN_PATTERN = re.compile(
    r"^iosa_([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})_([A-Za-z0-9_-]{32,})$"
)


class AutomationCommandError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def create_service_account(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    name: str,
    business_location_id: str,
    additional_business_location_ids: list[str] | None = None,
    expires_in_days: int,
    allowed_commands: list[str] | None = None,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    organization = _locked_active_organization(db, organization_id)
    location = _active_location(
        db,
        organization_id=organization.id,
        business_location_id=business_location_id,
    )
    requested_location_ids = list(
        dict.fromkeys([location.id, *(additional_business_location_ids or [])])
    )
    if len(requested_location_ids) > 10:
        raise AutomationCommandError(
            "Choose no more than 10 locations for one workflow key.",
            reason_code="automation_location_scope_limit_reached",
            status_code=422,
        )
    locations = [
        _active_location(
            db,
            organization_id=organization.id,
            business_location_id=location_id,
        )
        for location_id in requested_location_ids
    ]
    active_account = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.organization_id == organization.id,
            AutomationServiceAccount.status == "active",
        )
        .one_or_none()
    )
    if active_account is not None:
        raise AutomationCommandError(
            "This workspace already has an active workflow command key. Revoke it before creating another.",
            reason_code="automation_service_account_limit_reached",
            status_code=409,
        )

    now = datetime.now(UTC)
    account_id = str(uuid.uuid4())
    token = _new_token(account_id)
    resolved_commands = _validated_allowed_commands(allowed_commands)
    row = AutomationServiceAccount(
        id=account_id,
        tenant_id=organization.id,
        organization_id=organization.id,
        business_location_id=location.id,
        name=_normalized_name(name),
        status="active",
        token_hash=_hash_text(token),
        token_hint=token[-8:],
        token_version=1,
        allowed_commands_json=_json(resolved_commands),
        expires_at=now + timedelta(days=expires_in_days),
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    for scoped_location in locations:
        db.add(
            AutomationServiceAccountLocation(
                tenant_id=organization.id,
                organization_id=organization.id,
                service_account_id=row.id,
                business_location_id=scoped_location.id,
                created_at=now,
            )
        )
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="automation.service_account.created",
        payload={
            "service_account_id": row.id,
            "business_location_id": row.business_location_id,
            "business_location_ids": requested_location_ids,
            "allowed_commands": resolved_commands,
            "expires_at": row.expires_at.isoformat(),
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AutomationCommandError(
            "This workspace already has an active workflow command key.",
            reason_code="automation_service_account_limit_reached",
            status_code=409,
        ) from exc
    db.refresh(row)
    return {
        "created": True,
        "service_account": _account_contract(db, row),
        "token": token,
        "token_shown_once": True,
        "command_endpoint": "/api/v1/automation/commands",
        "safety": _safety_contract(),
    }


def list_service_accounts(db: Session, *, organization_id: str) -> dict[str, Any]:
    rows = (
        db.query(AutomationServiceAccount)
        .filter(AutomationServiceAccount.organization_id == organization_id)
        .order_by(AutomationServiceAccount.created_at.desc())
        .all()
    )
    return {
        "items": [_account_contract(db, row) for row in rows],
        "command_schema_version": COMMAND_SCHEMA_VERSION,
        "supported_commands": _command_catalog(),
        "max_active_service_accounts": 1,
        "safety": _safety_contract(),
    }


def automation_command_client_kit(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> dict[str, Any]:
    """Return one provider-neutral HTTPS setup contract without credential material."""
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this connection guide.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    endpoint = (
        f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}"
        "/automation/commands"
    )
    allowed = set(_allowed_commands(row))
    commands = [
        item for item in _command_catalog() if str(item["code"]) in allowed
    ]
    return {
        "version": "insightos.automation.command-client-kit.v1",
        "name": row.name,
        "works_with": ["Zapier", "Make", "n8n", "Pipedream", "Any HTTPS client"],
        "scope": {
            "service_account_id": row.id,
            "organization_id": row.organization_id,
            "primary_location_id": row.business_location_id,
            "primary_location_name": location.name,
            "allowed_location_ids": _account_location_ids(db, row.id)
            or [row.business_location_id],
            "expires_at": row.expires_at.isoformat(),
        },
        "request": {
            "method": "POST",
            "url": endpoint,
            "verification_url": endpoint.rsplit("/", 1)[0] + "/command-access",
            "content_type": "application/json",
            "authentication": {
                "type": "Bearer token",
                "header": "Authorization: Bearer YOUR_WORKFLOW_KEY",
                "credential_included": False,
            },
            "schema_version": COMMAND_SCHEMA_VERSION,
            "body_template": {
                "schema_version": COMMAND_SCHEMA_VERSION,
                "command_type": "CHOOSE_ONE_ALLOWED_ACTION",
                "organization_id": row.organization_id,
                "location_id": row.business_location_id,
                "correlation_id": "WORKFLOW-RUN-ID",
                "idempotency_key": "STABLE-KEY-FOR-THIS-INTENDED-ACTION",
                "reason": "Plain-language reason for this workflow request",
                "target": {"required_id": "REPLACE-WITH-SAVED-RECORD-ID"},
            },
        },
        "allowed_actions": commands,
        "setup_steps": [
            "Add an HTTPS request action in your workflow tool.",
            "Test the private Bearer credential with the verification URL before configuring an action.",
            "Choose POST and use the request URL in this file.",
            "Store the one-time workflow key in the tool's private credential store and use Bearer authentication.",
            "Choose only an allowed action and map its required saved-record ID into target.",
            "Use one stable idempotency key for retries of the same intended action.",
            "Test once, confirm the saved result in InsightOS, then turn on the workflow.",
        ],
        "safety": {
            "contains_workflow_key": False,
            "arbitrary_commands_allowed": False,
            "approval_allowed": False,
            "publishing_allowed": False,
            "website_changes_allowed": False,
            "business_profile_changes_allowed": False,
            "human_review_remains_required": True,
        },
    }


def n8n_report_ready_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    api_base_url = f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}"
    return build_n8n_report_ready_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        api_base_url=api_base_url,
    )


def n8n_saved_report_schedule_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    if COMMAND_REPORT_GENERATE_SAVED not in _allowed_commands(row):
        raise AutomationCommandError(
            "Turn on private report creation before downloading this workflow.",
            reason_code="automation_command_not_allowed",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == row.tenant_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id == row.business_location_id,
        )
        .one_or_none()
    )
    if campaign is None:
        raise AutomationCommandError(
            "That location setup was not found for this workflow key.",
            reason_code="automation_campaign_not_found",
            status_code=404,
        )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    api_base_url = f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}"
    return build_n8n_saved_report_schedule_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        campaign_id=campaign.id,
        api_base_url=api_base_url,
    )


def n8n_recommendation_ready_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    if not {
        COMMAND_RECOMMENDATION_RETRIEVE,
        COMMAND_RECOMMENDATION_REQUEST_REVIEW,
    }.issubset(set(_allowed_commands(row))):
        raise AutomationCommandError(
            "Turn on saved recommendation review routing before downloading this workflow.",
            reason_code="automation_command_not_allowed",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    return build_n8n_recommendation_ready_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        api_base_url=f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}",
    )


def n8n_content_draft_review_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    if not {
        COMMAND_CONTENT_CREATE_WORKING_DRAFT,
        COMMAND_CONTENT_REQUEST_DRAFT_REVIEW,
    }.issubset(set(_allowed_commands(row))):
        raise AutomationCommandError(
            "Turn on private draft creation and owner review before downloading this workflow.",
            reason_code="automation_command_not_allowed",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == row.tenant_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id == row.business_location_id,
        )
        .one_or_none()
    )
    if campaign is None:
        raise AutomationCommandError(
            "That location setup was not found for this workflow key.",
            reason_code="automation_campaign_not_found",
            status_code=404,
        )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    return build_n8n_content_draft_review_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        campaign_id=campaign.id,
        api_base_url=f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}",
    )


def n8n_saved_review_routing_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    if COMMAND_REVIEW_RETRIEVE not in _allowed_commands(row):
        raise AutomationCommandError(
            "Turn on saved-review routing before downloading this workflow.",
            reason_code="automation_command_not_allowed",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    return build_n8n_saved_review_routing_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        api_base_url=f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}",
    )


def n8n_review_response_draft_starter_workflow(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "Create or replace the workflow key before downloading this starter workflow.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    if COMMAND_REVIEW_CREATE_RESPONSE_DRAFT not in _allowed_commands(row):
        raise AutomationCommandError(
            "Turn on private reply drafting before downloading this workflow.",
            reason_code="automation_command_not_allowed",
            status_code=409,
        )
    location = _active_location(
        db,
        organization_id=organization_id,
        business_location_id=row.business_location_id,
    )
    settings = get_settings()
    public_app_url = (
        settings.customer_app_base_url or settings.public_base_url
    ).strip().rstrip("/")
    return build_n8n_review_response_draft_workflow(
        service_account_id=row.id,
        organization_id=row.organization_id,
        location_id=row.business_location_id,
        location_name=location.name,
        api_base_url=f"{public_app_url}{settings.api_v1_prefix.rstrip('/')}",
    )


def rotate_service_account_token(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
    actor_user_id: str,
    allowed_commands: list[str] | None = None,
    additional_business_location_ids: list[str] | None = None,
) -> dict[str, Any]:
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    row = _locked_account(
        db,
        organization_id=organization_id,
        service_account_id=service_account_id,
    )
    if row.status != "active" or _is_expired(row.expires_at):
        raise AutomationCommandError(
            "This workflow command key is no longer active.",
            reason_code="automation_service_account_inactive",
            status_code=409,
        )
    now = datetime.now(UTC)
    token = _new_token(row.id)
    row.token_hash = _hash_text(token)
    row.token_hint = token[-8:]
    row.token_version += 1
    if allowed_commands is not None:
        row.allowed_commands_json = _json(
            _validated_allowed_commands(allowed_commands)
        )
    if additional_business_location_ids is not None:
        requested_location_ids = list(
            dict.fromkeys([row.business_location_id, *additional_business_location_ids])
        )
        if len(requested_location_ids) > 10:
            raise AutomationCommandError(
                "Choose no more than 10 locations for one workflow key.",
                reason_code="automation_location_scope_limit_reached",
                status_code=422,
            )
        locations = [
            _active_location(
                db,
                organization_id=row.organization_id,
                business_location_id=location_id,
            )
            for location_id in requested_location_ids
        ]
        (
            db.query(AutomationServiceAccountLocation)
            .filter(AutomationServiceAccountLocation.service_account_id == row.id)
            .delete(synchronize_session=False)
        )
        for location in locations:
            db.add(
                AutomationServiceAccountLocation(
                    tenant_id=row.tenant_id,
                    organization_id=row.organization_id,
                    service_account_id=row.id,
                    business_location_id=location.id,
                    created_at=now,
                )
            )
    row.last_rotated_at = now
    row.updated_at = now
    write_audit_log(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=actor_user_id,
        event_type="automation.service_account.rotated",
        payload={
            "service_account_id": row.id,
            "token_version": row.token_version,
            "allowed_commands": _allowed_commands(row),
            "business_location_ids": (
                requested_location_ids
                if additional_business_location_ids is not None
                else _account_location_ids(db, row.id)
            ),
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "rotated": True,
        "service_account": _account_contract(db, row),
        "token": token,
        "token_shown_once": True,
        "safety": _safety_contract(),
    }


def revoke_service_account(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _locked_account(
        db,
        organization_id=organization_id,
        service_account_id=service_account_id,
    )
    if row.status == "active":
        now = datetime.now(UTC)
        row.status = "revoked"
        row.revoked_at = now
        row.revoked_by_user_id = actor_user_id
        row.updated_at = now
        write_audit_log(
            db,
            tenant_id=row.tenant_id,
            actor_user_id=actor_user_id,
            event_type="automation.service_account.revoked",
            payload={"service_account_id": row.id},
        )
        db.commit()
        db.refresh(row)
    return {
        "revoked": True,
        "service_account": _account_contract(db, row),
        "safety": _safety_contract(),
    }


def list_command_receipts(
    db: Session,
    *,
    organization_id: str,
    limit: int = 25,
) -> dict[str, Any]:
    rows = (
        db.query(AutomationCommandReceipt)
        .filter(AutomationCommandReceipt.organization_id == organization_id)
        .order_by(AutomationCommandReceipt.created_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return {
        "items": [_receipt_contract(db, row, created=False) for row in rows],
        "safety": _safety_contract(),
    }


def authenticate_service_account(
    db: Session,
    *,
    bearer_token: str,
) -> AutomationServiceAccount:
    match = TOKEN_PATTERN.fullmatch(bearer_token.strip())
    if match is None:
        raise _invalid_token()
    account_id = match.group(1).lower()
    supplied_hash = _hash_text(bearer_token.strip())
    row = db.get(AutomationServiceAccount, account_id)
    if (
        row is None
        or not secrets.compare_digest(row.token_hash, supplied_hash)
        or row.status != "active"
        or _is_expired(row.expires_at)
    ):
        raise _invalid_token()
    set_session_security_context(
        db,
        tenant_id=row.tenant_id,
        organization_id=row.organization_id,
        user_id=row.created_by_user_id,
        platform_access=False,
    )
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == account_id,
            AutomationServiceAccount.token_hash == supplied_hash,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if row is None or row.status != "active" or _is_expired(row.expires_at):
        raise _invalid_token()
    organization = db.get(Organization, row.organization_id)
    if organization is None or organization.status != "active":
        raise AutomationCommandError(
            "This workspace is not available for workflow commands.",
            reason_code="automation_workspace_unavailable",
            status_code=403,
        )
    return row


def get_service_account_access_contract(
    db: Session,
    *,
    account: AutomationServiceAccount,
) -> dict[str, Any]:
    """Confirm the bounded credential without running work or writing customer state."""
    require_commercial_feature(
        db,
        organization_id=account.organization_id,
        feature_code=FEATURE_EXTERNAL_AUTOMATION,
    )
    _active_location(
        db,
        organization_id=account.organization_id,
        business_location_id=account.business_location_id,
    )
    allowed = set(_allowed_commands(account))
    return {
        "connected": True,
        "schema_version": COMMAND_SCHEMA_VERSION,
        "service_account_id": account.id,
        "organization_id": account.organization_id,
        "primary_location_id": account.business_location_id,
        "allowed_location_ids": _account_location_ids(db, account.id)
        or [account.business_location_id],
        "allowed_actions": [
            item for item in _command_catalog() if str(item["code"]) in allowed
        ],
        "expires_at": account.expires_at.isoformat(),
        "truth": {
            "credential_valid": True,
            "workspace_available": True,
            "primary_location_available": True,
            "command_executed": False,
            "provider_called": False,
            "credits_used": False,
            "customer_data_changed": False,
        },
        "safety": _safety_contract(),
    }


def execute_report_retrieval(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    request_hash = _hash_payload(request_payload)
    existing = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.idempotency_key
            == str(request_payload["idempotency_key"]),
        )
        .one_or_none()
    )
    if existing is not None:
        if not secrets.compare_digest(existing.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, existing, created=False)

    now = datetime.now(UTC)
    account.last_used_at = now
    account.updated_at = now
    report_id = str(request_payload["target"]["report_id"])
    denial_reason: str | None = None
    campaign: Campaign | None = None
    report: MonthlyReport | None = None
    requested_location_id = str(request_payload["location_id"])

    if request_payload["schema_version"] != COMMAND_SCHEMA_VERSION:
        denial_reason = "automation_command_schema_unsupported"
    elif request_payload["command_type"] not in _allowed_commands(account):
        denial_reason = "automation_command_not_allowed"
    elif request_payload["organization_id"] != account.organization_id:
        denial_reason = "automation_command_scope_mismatch"
    elif not _account_can_read_location(
        db, account=account, business_location_id=requested_location_id
    ):
        denial_reason = "automation_command_scope_mismatch"
    else:
        try:
            require_commercial_feature(
                db,
                organization_id=account.organization_id,
                feature_code=FEATURE_EXTERNAL_AUTOMATION,
            )
        except CostEconomicsError:
            denial_reason = "external_automation_upgrade_required"

    location = db.get(BusinessLocation, requested_location_id)
    if denial_reason is None and (
        location is None
        or location.organization_id != account.organization_id
        or location.status != "active"
    ):
        denial_reason = "automation_command_location_unavailable"

    if denial_reason is None:
        report = (
            db.query(MonthlyReport)
            .join(Campaign, Campaign.id == MonthlyReport.campaign_id)
            .filter(
                MonthlyReport.id == report_id,
                MonthlyReport.tenant_id == account.tenant_id,
                Campaign.tenant_id == account.tenant_id,
                Campaign.organization_id == account.organization_id,
                Campaign.business_location_id == requested_location_id,
            )
            .one_or_none()
        )
        if report is None:
            denial_reason = "automation_report_not_found"
        else:
            campaign = db.get(Campaign, report.campaign_id)

    result = (
        _report_result(db, report=report, campaign=campaign)
        if denial_reason is None and report is not None and campaign is not None
        else {
            "message": _denial_message(denial_reason or "automation_command_denied"),
            "resource": None,
            "artifacts": [],
        }
    )
    status_value = "succeeded" if denial_reason is None else "denied"
    artifact_payload = {
        "schema_version": COMMAND_SCHEMA_VERSION,
        "service_account_id": account.id,
        "request_hash": request_hash,
        "status": status_value,
        "denial_reason_code": denial_reason,
        "result": result,
    }
    receipt = AutomationCommandReceipt(
        tenant_id=account.tenant_id,
        organization_id=account.organization_id,
        service_account_id=account.id,
        business_location_id=requested_location_id,
        campaign_id=campaign.id if campaign is not None else None,
        report_id=report_id,
        schema_version=COMMAND_SCHEMA_VERSION,
        command_type=COMMAND_REPORT_RETRIEVE,
        idempotency_key=str(request_payload["idempotency_key"]),
        correlation_id=str(request_payload["correlation_id"]),
        reason=str(request_payload["reason"]),
        request_hash=request_hash,
        status=status_value,
        denial_reason_code=denial_reason,
        result_json=_json(result),
        artifact_hash=_hash_payload(artifact_payload),
        created_at=now,
        completed_at=now,
    )
    try:
        with db.begin_nested():
            db.add(receipt)
            db.flush()
    except IntegrityError:
        db.expire_all()
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .one()
        )
        if not secrets.compare_digest(existing.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, existing, created=False)

    write_audit_log(
        db,
        tenant_id=account.tenant_id,
        actor_user_id=None,
        event_type="automation.command.decided",
        payload={
            "service_account_id": account.id,
            "command_receipt_id": receipt.id,
            "command_type": receipt.command_type,
            "business_location_id": requested_location_id,
            "status": status_value,
            "denial_reason_code": denial_reason,
        },
    )
    db.commit()
    db.refresh(receipt)
    return _receipt_contract(db, receipt, created=True)


def execute_automation_command(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if request_payload["command_type"] == COMMAND_REPORT_RETRIEVE:
        return execute_report_retrieval(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_REPORT_GENERATE_SAVED:
        return execute_saved_report_generation(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] in {
        COMMAND_RECOMMENDATION_RETRIEVE,
        COMMAND_RECOMMENDATION_REQUEST_REVIEW,
    }:
        return execute_recommendation_retrieval(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_CONNECTION_REFRESH_SAVED:
        return execute_saved_connection_refresh(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_LISTING_CHECK_PUBLIC:
        return execute_public_listing_check(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_CONTENT_CREATE_WORKING_DRAFT:
        return execute_content_working_draft_creation(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_CONTENT_REQUEST_DRAFT_REVIEW:
        return execute_content_draft_review_request(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_REVIEW_RETRIEVE:
        return execute_review_retrieval(
            db, account=account, request_payload=request_payload
        )
    if request_payload["command_type"] == COMMAND_REVIEW_CREATE_RESPONSE_DRAFT:
        return execute_review_response_draft_creation(
            db, account=account, request_payload=request_payload
        )
    raise AutomationCommandError(
        "This workflow command is not supported.",
        reason_code="automation_command_not_allowed",
        status_code=422,
    )


def execute_review_retrieval(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return minimized facts for one saved review without exposing customer text."""
    request_hash = _hash_payload(request_payload)
    existing = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.idempotency_key
            == str(request_payload["idempotency_key"]),
        )
        .one_or_none()
    )
    if existing is not None:
        if not secrets.compare_digest(existing.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, existing, created=False)

    denial_reason = _base_command_denial(db, account, request_payload)
    review_id = str(request_payload["target"]["review_id"])
    review: ReputationReview | None = None
    campaign: Campaign | None = None
    if denial_reason is None:
        review = (
            db.query(ReputationReview)
            .join(Campaign, Campaign.id == ReputationReview.campaign_id)
            .filter(
                ReputationReview.id == review_id,
                ReputationReview.tenant_id == account.tenant_id,
                ReputationReview.organization_id == account.organization_id,
                ReputationReview.business_location_id == account.business_location_id,
                ReputationReview.source_type == "owned_profile",
                Campaign.tenant_id == account.tenant_id,
                Campaign.organization_id == account.organization_id,
                Campaign.business_location_id == account.business_location_id,
            )
            .one_or_none()
        )
        if review is None:
            denial_reason = "automation_review_not_found"
        else:
            campaign = db.get(Campaign, review.campaign_id)

    result = (
        {
            "message": "Saved review returned",
            "review": {
                "id": review.id,
                "campaign_id": review.campaign_id,
                "rating": review.rating,
                "reviewed_at": review.reviewed_at.isoformat(),
                "response_status": review.response_status,
                "comment_present": bool(str(review.body or "").strip()),
            },
            "truth": {
                "read_only": True,
                "reviewer_identity_shared": False,
                "comment_text_shared": False,
                "reply_created": False,
                "reply_posted": False,
                "business_profile_changed": False,
            },
        }
        if denial_reason is None and review is not None
        else {
            "message": _denial_message(denial_reason or "automation_command_denied"),
            "review": None,
        }
    )
    now = datetime.now(UTC)
    account.last_used_at = now
    account.updated_at = now
    status_value = "succeeded" if denial_reason is None else "denied"
    receipt = AutomationCommandReceipt(
        tenant_id=account.tenant_id,
        organization_id=account.organization_id,
        service_account_id=account.id,
        business_location_id=account.business_location_id,
        campaign_id=campaign.id if campaign is not None else None,
        schema_version=COMMAND_SCHEMA_VERSION,
        command_type=COMMAND_REVIEW_RETRIEVE,
        idempotency_key=str(request_payload["idempotency_key"]),
        correlation_id=str(request_payload["correlation_id"]),
        reason=str(request_payload["reason"]),
        request_hash=request_hash,
        status=status_value,
        denial_reason_code=denial_reason,
        result_json=_json(result),
        artifact_hash=_hash_payload(
            {
                "schema_version": COMMAND_SCHEMA_VERSION,
                "service_account_id": account.id,
                "request_hash": request_hash,
                "status": status_value,
                "denial_reason_code": denial_reason,
                "result": result,
            }
        ),
        created_at=now,
        completed_at=now,
    )
    try:
        with db.begin_nested():
            db.add(receipt)
            db.flush()
    except IntegrityError:
        db.expire_all()
        duplicate = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .one()
        )
        if not secrets.compare_digest(duplicate.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, duplicate, created=False)

    write_audit_log(
        db,
        tenant_id=account.tenant_id,
        actor_user_id=None,
        event_type="automation.command.decided",
        payload={
            "service_account_id": account.id,
            "command_receipt_id": receipt.id,
            "command_type": receipt.command_type,
            "business_location_id": account.business_location_id,
            "status": status_value,
            "denial_reason_code": denial_reason,
        },
    )
    db.commit()
    db.refresh(receipt)
    return _receipt_contract(db, receipt, created=True)


def execute_review_response_draft_creation(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Request one private reply draft without approving or posting it."""
    request_hash = _hash_payload(request_payload)
    existing = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.idempotency_key
            == str(request_payload["idempotency_key"]),
        )
        .one_or_none()
    )
    if existing is not None:
        if not secrets.compare_digest(existing.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, existing, created=False)

    denial_reason = _base_command_denial(db, account, request_payload)
    review_id = str(request_payload["target"]["review_id"])
    review: ReputationReview | None = None
    campaign: Campaign | None = None
    draft: dict[str, Any] | None = None
    if denial_reason is None:
        review = (
            db.query(ReputationReview)
            .join(Campaign, Campaign.id == ReputationReview.campaign_id)
            .filter(
                ReputationReview.id == review_id,
                ReputationReview.tenant_id == account.tenant_id,
                ReputationReview.organization_id == account.organization_id,
                ReputationReview.business_location_id == account.business_location_id,
                ReputationReview.source_type == "owned_profile",
                Campaign.tenant_id == account.tenant_id,
                Campaign.organization_id == account.organization_id,
                Campaign.business_location_id == account.business_location_id,
            )
            .one_or_none()
        )
        if review is None:
            denial_reason = "automation_review_not_found"
        elif review.response_status == "responded":
            denial_reason = "automation_review_already_responded"
        else:
            campaign = db.get(Campaign, review.campaign_id)

    if denial_reason is None and review is not None and campaign is not None:
        try:
            draft = reputation_response_service.generate_response_draft(
                db,
                tenant_id=account.tenant_id,
                organization_id=account.organization_id,
                campaign_id=campaign.id,
                review_id=review.id,
                requested_by_user_id=None,
                refresh=False,
            )
        except HTTPException as exc:
            denial_reason = (
                "automation_review_draft_unavailable"
                if exc.status_code >= 500
                else "automation_review_draft_not_allowed"
            )

    result = (
        {
            "message": "Private reply draft requested",
            "draft": {
                "id": str(draft["id"]),
                "review_id": str(draft["review_id"]),
                "status": str(draft["status"]),
                "human_review_required": True,
            },
            "truth": {
                "draft_text_shared": False,
                "approved": False,
                "reply_posted": False,
                "business_profile_changed": False,
            },
        }
        if denial_reason is None and draft is not None
        else {
            "message": _denial_message(denial_reason or "automation_command_denied"),
            "draft": None,
        }
    )
    now = datetime.now(UTC)
    account.last_used_at = now
    account.updated_at = now
    status_value = "succeeded" if denial_reason is None else "denied"
    receipt = AutomationCommandReceipt(
        tenant_id=account.tenant_id,
        organization_id=account.organization_id,
        service_account_id=account.id,
        business_location_id=account.business_location_id,
        campaign_id=campaign.id if campaign is not None else None,
        schema_version=COMMAND_SCHEMA_VERSION,
        command_type=COMMAND_REVIEW_CREATE_RESPONSE_DRAFT,
        idempotency_key=str(request_payload["idempotency_key"]),
        correlation_id=str(request_payload["correlation_id"]),
        reason=str(request_payload["reason"]),
        request_hash=request_hash,
        status=status_value,
        denial_reason_code=denial_reason,
        result_json=_json(result),
        artifact_hash=_hash_payload(
            {
                "schema_version": COMMAND_SCHEMA_VERSION,
                "service_account_id": account.id,
                "request_hash": request_hash,
                "status": status_value,
                "denial_reason_code": denial_reason,
                "result": result,
            }
        ),
        created_at=now,
        completed_at=now,
    )
    try:
        with db.begin_nested():
            db.add(receipt)
            db.flush()
    except IntegrityError:
        db.expire_all()
        duplicate = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .one()
        )
        if not secrets.compare_digest(duplicate.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, duplicate, created=False)

    write_audit_log(
        db,
        tenant_id=account.tenant_id,
        actor_user_id=None,
        event_type="automation.command.decided",
        payload={
            "service_account_id": account.id,
            "command_receipt_id": receipt.id,
            "command_type": receipt.command_type,
            "business_location_id": account.business_location_id,
            "status": status_value,
            "denial_reason_code": denial_reason,
        },
    )
    db.commit()
    db.refresh(receipt)
    return _receipt_contract(db, receipt, created=True)


def execute_recommendation_retrieval(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return one saved recommendation without approving or executing it."""
    request_hash = _hash_payload(request_payload)
    existing = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.idempotency_key
            == str(request_payload["idempotency_key"]),
        )
        .one_or_none()
    )
    if existing is not None:
        if not secrets.compare_digest(existing.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, existing, created=False)

    denial_reason = _base_command_denial(db, account, request_payload)
    recommendation_id = str(request_payload["target"]["recommendation_id"])
    recommendation: StrategyRecommendation | None = None
    campaign: Campaign | None = None
    if denial_reason is None:
        recommendation = (
            db.query(StrategyRecommendation)
            .join(Campaign, Campaign.id == StrategyRecommendation.campaign_id)
            .filter(
                StrategyRecommendation.id == recommendation_id,
                StrategyRecommendation.tenant_id == account.tenant_id,
                Campaign.tenant_id == account.tenant_id,
                Campaign.organization_id == account.organization_id,
                Campaign.business_location_id == account.business_location_id,
            )
            .one_or_none()
        )
        if recommendation is None:
            denial_reason = "automation_recommendation_not_found"
        else:
            campaign = db.get(Campaign, recommendation.campaign_id)

    review_requested = (
        request_payload["command_type"] == COMMAND_RECOMMENDATION_REQUEST_REVIEW
    )
    result = (
        _recommendation_result(
            db, recommendation, review_requested=review_requested
        )
        if denial_reason is None and recommendation is not None
        else {
            "message": _denial_message(denial_reason or "automation_command_denied"),
            "resource": None,
            "artifacts": [],
        }
    )
    now = datetime.now(UTC)
    account.last_used_at = now
    account.updated_at = now
    status_value = "succeeded" if denial_reason is None else "denied"
    artifact_payload = {
        "schema_version": COMMAND_SCHEMA_VERSION,
        "service_account_id": account.id,
        "request_hash": request_hash,
        "status": status_value,
        "denial_reason_code": denial_reason,
        "result": result,
    }
    receipt = AutomationCommandReceipt(
        tenant_id=account.tenant_id,
        organization_id=account.organization_id,
        service_account_id=account.id,
        business_location_id=account.business_location_id,
        campaign_id=campaign.id if campaign is not None else None,
        recommendation_id=recommendation.id if recommendation is not None else None,
        schema_version=COMMAND_SCHEMA_VERSION,
        command_type=str(request_payload["command_type"]),
        idempotency_key=str(request_payload["idempotency_key"]),
        correlation_id=str(request_payload["correlation_id"]),
        reason=str(request_payload["reason"]),
        request_hash=request_hash,
        status=status_value,
        denial_reason_code=denial_reason,
        result_json=_json(result),
        artifact_hash=_hash_payload(artifact_payload),
        created_at=now,
        completed_at=now,
    )
    try:
        with db.begin_nested():
            db.add(receipt)
            db.flush()
    except IntegrityError:
        db.expire_all()
        duplicate = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .one()
        )
        if not secrets.compare_digest(duplicate.request_hash, request_hash):
            raise AutomationCommandError(
                "This idempotency key was already used for a different command.",
                reason_code="automation_command_idempotency_conflict",
                status_code=409,
            )
        return _receipt_contract(db, duplicate, created=False)
    write_audit_log(
        db,
        tenant_id=account.tenant_id,
        actor_user_id=None,
        event_type="automation.command.decided",
        payload={
            "service_account_id": account.id,
            "command_receipt_id": receipt.id,
            "command_type": receipt.command_type,
            "business_location_id": account.business_location_id,
            "status": status_value,
            "denial_reason_code": denial_reason,
        },
    )
    db.commit()
    db.refresh(receipt)
    return _receipt_contract(db, receipt, created=True)


def execute_saved_connection_refresh(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Queue one bounded refresh for an already-connected location data source."""
    request_hash = _hash_payload(request_payload)
    lock_scope = f"automation-command:{account.id}:{request_payload['idempotency_key']}"
    with _serialized_command(lock_scope, db):
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .populate_existing()
            .one_or_none()
        )
        if existing is not None:
            if not secrets.compare_digest(existing.request_hash, request_hash):
                raise AutomationCommandError(
                    "This idempotency key was already used for a different command.",
                    reason_code="automation_command_idempotency_conflict",
                    status_code=409,
                )
            return _receipt_contract(db, existing, created=False)

        denial_reason = _base_command_denial(db, account, request_payload)
        connection_id = str(request_payload["target"]["connection_id"])
        connection: DataConnection | None = None
        job: PlatformJob | None = None
        if denial_reason is None:
            connection = (
                db.query(DataConnection)
                .filter(
                    DataConnection.id == connection_id,
                    DataConnection.tenant_id == account.tenant_id,
                    DataConnection.organization_id == account.organization_id,
                    DataConnection.business_location_id == account.business_location_id,
                    DataConnection.status
                    != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
                )
                .one_or_none()
            )
            if connection is None:
                denial_reason = "automation_connection_not_found"
            elif connection.provider_name == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER:
                job = durable_job_service.create_search_console_sync_job(db, connection=connection)
            elif connection.provider_name == data_connections_service.GOOGLE_ANALYTICS_PROVIDER:
                job = durable_job_service.create_google_analytics_sync_job(db, connection=connection)
            elif connection.provider_name == google_business_profile_service.GOOGLE_BUSINESS_PROFILE_PROVIDER:
                job = durable_job_service.create_business_profile_sync_job(db, connection=connection)
            else:
                denial_reason = "automation_connection_refresh_unsupported"

        result = (
            {
                "message": "InsightOS accepted a refresh of this connected source.",
                "resource": {
                    "type": "data_connection",
                    "id": connection.id,
                    "href": "/settings#connections",
                },
                "job": _safe_job_contract(job),
                "truth": {
                    "accepted": True,
                    "completed": job.status == "completed",
                    "publishing_allowed": False,
                },
                "artifacts": [],
            }
            if denial_reason is None and connection is not None and job is not None
            else {
                "message": _denial_message(denial_reason or "automation_command_denied"),
                "resource": None,
                "job": None,
                "artifacts": [],
            }
        )
        now = datetime.now(UTC)
        account.last_used_at = now
        account.updated_at = now
        status_value = "succeeded" if denial_reason is None else "denied"
        artifact_payload = {
            "schema_version": COMMAND_SCHEMA_VERSION,
            "service_account_id": account.id,
            "request_hash": request_hash,
            "status": status_value,
            "denial_reason_code": denial_reason,
            "result": result,
        }
        receipt = AutomationCommandReceipt(
            tenant_id=account.tenant_id,
            organization_id=account.organization_id,
            service_account_id=account.id,
            business_location_id=account.business_location_id,
            campaign_id=connection.campaign_id if connection is not None else None,
            schema_version=COMMAND_SCHEMA_VERSION,
            command_type=COMMAND_CONNECTION_REFRESH_SAVED,
            idempotency_key=str(request_payload["idempotency_key"]),
            correlation_id=str(request_payload["correlation_id"]),
            reason=str(request_payload["reason"]),
            request_hash=request_hash,
            status=status_value,
            denial_reason_code=denial_reason,
            result_json=_json(result),
            artifact_hash=_hash_payload(artifact_payload),
            created_at=now,
            completed_at=now,
        )
        db.add(receipt)
        write_audit_log(
            db,
            tenant_id=account.tenant_id,
            actor_user_id=None,
            event_type="automation.command.decided",
            payload={
                "service_account_id": account.id,
                "command_receipt_id": receipt.id,
                "command_type": receipt.command_type,
                "business_location_id": account.business_location_id,
                "status": status_value,
                "denial_reason_code": denial_reason,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _receipt_contract(db, receipt, created=True)


def execute_public_listing_check(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Request one native allowance-priced public listing inventory check."""
    request_hash = _hash_payload(request_payload)
    lock_scope = f"automation-command:{account.id}:{request_payload['idempotency_key']}"
    with _serialized_command(lock_scope, db):
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .populate_existing()
            .one_or_none()
        )
        if existing is not None:
            if not secrets.compare_digest(existing.request_hash, request_hash):
                raise AutomationCommandError(
                    "This idempotency key was already used for a different command.",
                    reason_code="automation_command_idempotency_conflict",
                    status_code=409,
                )
            return _receipt_contract(db, existing, created=False)

        denial_reason = _base_command_denial(db, account, request_payload)
        campaign_id = str(request_payload["target"]["campaign_id"])
        campaign: Campaign | None = None
        run: DirectoryListingDiscoveryRun | None = None
        created_run = False
        if denial_reason is None:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == account.tenant_id,
                    Campaign.organization_id == account.organization_id,
                    Campaign.business_location_id == account.business_location_id,
                )
                .one_or_none()
            )
            if campaign is None:
                denial_reason = "automation_campaign_not_found"
        if denial_reason is None and campaign is not None:
            try:
                run, created_run = listing_discovery_service.create_run(
                    db,
                    tenant_id=account.tenant_id,
                    organization_id=account.organization_id,
                    campaign_id=campaign.id,
                    requested_by_user_id=account.created_by_user_id,
                    idempotency_key=(
                        f"automation:{account.id}:{request_payload['idempotency_key']}"
                    ),
                )
            except (listing_discovery_service.ListingDiscoveryError, CostEconomicsError) as exc:
                denial_reason = str(
                    getattr(exc, "reason_code", "public_listing_check_unavailable")
                )

        result = (
            {
                "message": "InsightOS accepted a public listing inventory check.",
                "resource": {
                    "type": "public_listing_check",
                    "id": run.id,
                    "href": "/citations",
                },
                "job": _safe_listing_run_contract(run),
                "truth": {
                    "accepted": True,
                    "completed": run.status == "completed",
                    "uses_allowance": int(run.estimated_credit_units or 0) > 0,
                    "publishing_allowed": False,
                    "corrections_allowed": False,
                },
                "artifacts": [],
            }
            if denial_reason is None and run is not None
            else {
                "message": _denial_message(denial_reason or "automation_command_denied"),
                "resource": None,
                "job": None,
                "artifacts": [],
            }
        )
        now = datetime.now(UTC)
        account.last_used_at = now
        account.updated_at = now
        status_value = "succeeded" if denial_reason is None else "denied"
        artifact_payload = {
            "schema_version": COMMAND_SCHEMA_VERSION,
            "service_account_id": account.id,
            "request_hash": request_hash,
            "status": status_value,
            "denial_reason_code": denial_reason,
            "result": result,
        }
        receipt = AutomationCommandReceipt(
            tenant_id=account.tenant_id,
            organization_id=account.organization_id,
            service_account_id=account.id,
            business_location_id=account.business_location_id,
            campaign_id=campaign.id if campaign is not None else None,
            schema_version=COMMAND_SCHEMA_VERSION,
            command_type=COMMAND_LISTING_CHECK_PUBLIC,
            idempotency_key=str(request_payload["idempotency_key"]),
            correlation_id=str(request_payload["correlation_id"]),
            reason=str(request_payload["reason"]),
            request_hash=request_hash,
            status=status_value,
            denial_reason_code=denial_reason,
            result_json=_json(result),
            artifact_hash=_hash_payload(artifact_payload),
            created_at=now,
            completed_at=now,
        )
        db.add(receipt)
        write_audit_log(
            db,
            tenant_id=account.tenant_id,
            actor_user_id=None,
            event_type="automation.command.decided",
            payload={
                "service_account_id": account.id,
                "command_receipt_id": receipt.id,
                "command_type": receipt.command_type,
                "business_location_id": account.business_location_id,
                "status": status_value,
                "denial_reason_code": denial_reason,
                "created_native_run": created_run,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _receipt_contract(db, receipt, created=True)


def execute_content_working_draft_creation(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Create one empty private draft from an owner-accepted saved brief."""
    request_hash = _hash_payload(request_payload)
    lock_scope = f"automation-command:{account.id}:{request_payload['idempotency_key']}"
    with _serialized_command(lock_scope, db):
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .populate_existing()
            .one_or_none()
        )
        if existing is not None:
            if not secrets.compare_digest(existing.request_hash, request_hash):
                raise AutomationCommandError(
                    "This idempotency key was already used for a different command.",
                    reason_code="automation_command_idempotency_conflict",
                    status_code=409,
                )
            return _receipt_contract(db, existing, created=False)

        denial_reason = _base_command_denial(db, account, request_payload)
        brief_id = str(request_payload["target"]["brief_id"])
        campaign_id = str(request_payload["target"]["campaign_id"])
        campaign: Campaign | None = None
        draft_payload: dict[str, Any] | None = None
        if denial_reason is None:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == account.tenant_id,
                    Campaign.organization_id == account.organization_id,
                    Campaign.business_location_id == account.business_location_id,
                )
                .one_or_none()
            )
            if campaign is None:
                denial_reason = "automation_campaign_not_found"
        if denial_reason is None and campaign is not None:
            try:
                draft_payload = content_service.create_content_draft(
                    db,
                    tenant_id=account.tenant_id,
                    campaign_id=campaign.id,
                    brief_id=brief_id,
                    actor_user_id=account.created_by_user_id,
                )
            except HTTPException as exc:
                denial_reason = _content_draft_denial_reason(exc)

        item = draft_payload.get("item") if draft_payload is not None else None
        result = (
            {
                "message": "InsightOS created a private working draft from the accepted brief.",
                "resource": {
                    "type": "content_working_draft",
                    "id": str(item["id"]),
                    "href": "/content",
                },
                "draft": {
                    "id": str(item["id"]),
                    "brief_id": brief_id,
                    "status": "working",
                    "title": str(item.get("title") or "Working draft"),
                    "revision": int(item.get("revision") or 1),
                },
                "truth": {
                    "created": bool(draft_payload.get("created")),
                    "owner_review_required": True,
                    "approved": False,
                    "scheduled": False,
                    "published": False,
                },
                "artifacts": [],
            }
            if denial_reason is None and isinstance(item, dict) and item.get("id")
            else {
                "message": _denial_message(denial_reason or "automation_command_denied"),
                "resource": None,
                "draft": None,
                "artifacts": [],
            }
        )
        now = datetime.now(UTC)
        account.last_used_at = now
        account.updated_at = now
        status_value = "succeeded" if denial_reason is None else "denied"
        artifact_payload = {
            "schema_version": COMMAND_SCHEMA_VERSION,
            "service_account_id": account.id,
            "request_hash": request_hash,
            "status": status_value,
            "denial_reason_code": denial_reason,
            "result": result,
        }
        receipt = AutomationCommandReceipt(
            tenant_id=account.tenant_id,
            organization_id=account.organization_id,
            service_account_id=account.id,
            business_location_id=account.business_location_id,
            campaign_id=campaign.id if campaign is not None else None,
            schema_version=COMMAND_SCHEMA_VERSION,
            command_type=COMMAND_CONTENT_CREATE_WORKING_DRAFT,
            idempotency_key=str(request_payload["idempotency_key"]),
            correlation_id=str(request_payload["correlation_id"]),
            reason=str(request_payload["reason"]),
            request_hash=request_hash,
            status=status_value,
            denial_reason_code=denial_reason,
            result_json=_json(result),
            artifact_hash=_hash_payload(artifact_payload),
            created_at=now,
            completed_at=now,
        )
        db.add(receipt)
        write_audit_log(
            db,
            tenant_id=account.tenant_id,
            actor_user_id=None,
            event_type="automation.command.decided",
            payload={
                "service_account_id": account.id,
                "command_receipt_id": receipt.id,
                "command_type": receipt.command_type,
                "business_location_id": account.business_location_id,
                "status": status_value,
                "denial_reason_code": denial_reason,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _receipt_contract(db, receipt, created=True)


def _content_draft_denial_reason(exc: HTTPException) -> str:
    if exc.status_code == 404:
        return "automation_content_brief_not_found"
    if exc.status_code == 409:
        return "automation_content_brief_not_accepted"
    return "automation_content_draft_unavailable"


def execute_content_draft_review_request(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Record an immutable owner-review request without changing the draft."""
    request_hash = _hash_payload(request_payload)
    lock_scope = f"automation-command:{account.id}:{request_payload['idempotency_key']}"
    with _serialized_command(lock_scope, db):
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .populate_existing()
            .one_or_none()
        )
        if existing is not None:
            if not secrets.compare_digest(existing.request_hash, request_hash):
                raise AutomationCommandError(
                    "This idempotency key was already used for a different command.",
                    reason_code="automation_command_idempotency_conflict",
                    status_code=409,
                )
            return _receipt_contract(db, existing, created=False)

        denial_reason = _base_command_denial(db, account, request_payload)
        campaign_id = str(request_payload["target"]["campaign_id"])
        draft_id = str(request_payload["target"]["draft_id"])
        campaign = None
        draft = None
        if denial_reason is None:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == account.tenant_id,
                    Campaign.organization_id == account.organization_id,
                    Campaign.business_location_id == account.business_location_id,
                )
                .one_or_none()
            )
            if campaign is None:
                denial_reason = "automation_campaign_not_found"
        if denial_reason is None:
            draft = _scoped_content_draft(
                db,
                account=account,
                campaign_id=campaign_id,
                draft_id=draft_id,
            )
            if draft is None:
                denial_reason = "automation_content_draft_not_found"

        result = (
            {
                "message": "A connected workflow asked the owner to review this private draft.",
                "resource": {"type": "content_working_draft", "id": draft.id, "href": "/content"},
                "draft": {
                    "id": draft.id,
                    "brief_id": draft.content_brief_id,
                    "status": draft.status,
                    "title": draft.title,
                    "revision": int(draft.revision),
                },
                "truth": {
                    "review_requested": True,
                    "approved": False,
                    "scheduled": False,
                    "published": False,
                    "website_changed": False,
                },
                "artifacts": [],
            }
            if denial_reason is None and draft is not None
            else {
                "message": _denial_message(denial_reason or "automation_command_denied"),
                "resource": None,
                "draft": None,
                "artifacts": [],
            }
        )
        now = datetime.now(UTC)
        account.last_used_at = now
        account.updated_at = now
        status_value = "succeeded" if denial_reason is None else "denied"
        receipt = AutomationCommandReceipt(
            tenant_id=account.tenant_id,
            organization_id=account.organization_id,
            service_account_id=account.id,
            business_location_id=account.business_location_id,
            campaign_id=campaign.id if campaign is not None else None,
            schema_version=COMMAND_SCHEMA_VERSION,
            command_type=COMMAND_CONTENT_REQUEST_DRAFT_REVIEW,
            idempotency_key=str(request_payload["idempotency_key"]),
            correlation_id=str(request_payload["correlation_id"]),
            reason=str(request_payload["reason"]),
            request_hash=request_hash,
            status=status_value,
            denial_reason_code=denial_reason,
            result_json=_json(result),
            artifact_hash=_hash_payload({"request_hash": request_hash, "status": status_value, "result": result}),
            created_at=now,
            completed_at=now,
        )
        db.add(receipt)
        write_audit_log(
            db,
            tenant_id=account.tenant_id,
            actor_user_id=None,
            event_type="automation.command.decided",
            payload={
                "service_account_id": account.id,
                "command_receipt_id": receipt.id,
                "command_type": receipt.command_type,
                "business_location_id": account.business_location_id,
                "status": status_value,
                "denial_reason_code": denial_reason,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _receipt_contract(db, receipt, created=True)


def _scoped_content_draft(
    db: Session,
    *,
    account: AutomationServiceAccount,
    campaign_id: str,
    draft_id: str,
) -> ContentDraft | None:
    return (
        db.query(ContentDraft)
        .filter(
            ContentDraft.id == draft_id,
            ContentDraft.tenant_id == account.tenant_id,
            ContentDraft.organization_id == account.organization_id,
            ContentDraft.campaign_id == campaign_id,
            ContentDraft.business_location_id == account.business_location_id,
            ContentDraft.status == "working",
        )
        .one_or_none()
    )


def execute_saved_report_generation(
    db: Session,
    *,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate one private report from existing InsightOS evidence only."""
    request_hash = _hash_payload(request_payload)
    lock_scope = (
        f"automation-command:{account.id}:{request_payload['idempotency_key']}"
    )
    with _serialized_command(lock_scope, db):
        existing = (
            db.query(AutomationCommandReceipt)
            .filter(
                AutomationCommandReceipt.service_account_id == account.id,
                AutomationCommandReceipt.idempotency_key
                == str(request_payload["idempotency_key"]),
            )
            .populate_existing()
            .one_or_none()
        )
        if existing is not None:
            if not secrets.compare_digest(existing.request_hash, request_hash):
                raise AutomationCommandError(
                    "This idempotency key was already used for a different command.",
                    reason_code="automation_command_idempotency_conflict",
                    status_code=409,
                )
            return _receipt_contract(db, existing, created=False)

        denial_reason = _base_command_denial(db, account, request_payload)
        campaign_id = str(request_payload["target"]["campaign_id"])
        campaign: Campaign | None = None
        if denial_reason is None:
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.id == campaign_id,
                    Campaign.tenant_id == account.tenant_id,
                    Campaign.organization_id == account.organization_id,
                    Campaign.business_location_id == account.business_location_id,
                )
                .one_or_none()
            )
            if campaign is None:
                denial_reason = "automation_campaign_not_found"
        if denial_reason is None:
            try:
                require_commercial_feature(
                    db,
                    organization_id=account.organization_id,
                    feature_code=FEATURE_CAMPAIGN_REPORT,
                )
            except CostEconomicsError:
                denial_reason = "campaign_report_upgrade_required"

        report: MonthlyReport | None = None
        if denial_reason is None and campaign is not None:
            snapshot = premium_report_service.build_report_snapshot(
                db,
                tenant_id=account.tenant_id,
                campaign=campaign,
                month_number=campaign.month_number,
            )
            report = reporting_service.create_report_from_snapshot(
                db,
                tenant_id=account.tenant_id,
                campaign_id=campaign.id,
                month_number=campaign.month_number,
                snapshot=snapshot,
            )
            result = _report_result(db, report=report, campaign=campaign)
            result["message"] = (
                "InsightOS created a private report from saved results."
            )
        else:
            result = {
                "message": _denial_message(
                    denial_reason or "automation_command_denied"
                ),
                "resource": None,
                "artifacts": [],
            }

        now = datetime.now(UTC)
        account.last_used_at = now
        account.updated_at = now
        status_value = "succeeded" if denial_reason is None else "denied"
        artifact_payload = {
            "schema_version": COMMAND_SCHEMA_VERSION,
            "service_account_id": account.id,
            "request_hash": request_hash,
            "status": status_value,
            "denial_reason_code": denial_reason,
            "result": result,
        }
        receipt = AutomationCommandReceipt(
            tenant_id=account.tenant_id,
            organization_id=account.organization_id,
            service_account_id=account.id,
            business_location_id=account.business_location_id,
            campaign_id=campaign.id if campaign is not None else None,
            report_id=report.id if report is not None else None,
            schema_version=COMMAND_SCHEMA_VERSION,
            command_type=COMMAND_REPORT_GENERATE_SAVED,
            idempotency_key=str(request_payload["idempotency_key"]),
            correlation_id=str(request_payload["correlation_id"]),
            reason=str(request_payload["reason"]),
            request_hash=request_hash,
            status=status_value,
            denial_reason_code=denial_reason,
            result_json=_json(result),
            artifact_hash=_hash_payload(artifact_payload),
            created_at=now,
            completed_at=now,
        )
        db.add(receipt)
        write_audit_log(
            db,
            tenant_id=account.tenant_id,
            actor_user_id=None,
            event_type="automation.command.decided",
            payload={
                "service_account_id": account.id,
                "command_receipt_id": receipt.id,
                "command_type": receipt.command_type,
                "business_location_id": account.business_location_id,
                "status": status_value,
                "denial_reason_code": denial_reason,
            },
        )
        db.commit()
        db.refresh(receipt)
        return _receipt_contract(db, receipt, created=True)


def get_command_receipt_for_account(
    db: Session,
    *,
    account: AutomationServiceAccount,
    receipt_id: str,
) -> dict[str, Any]:
    row = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.id == receipt_id,
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.organization_id == account.organization_id,
        )
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command result not found.",
            reason_code="automation_command_not_found",
            status_code=404,
        )
    return _receipt_contract(db, row, created=False)


def read_command_report_artifact(
    db: Session,
    *,
    account: AutomationServiceAccount,
    receipt_id: str,
    artifact_id: str,
) -> tuple[ReportArtifact, bytes]:
    receipt = (
        db.query(AutomationCommandReceipt)
        .filter(
            AutomationCommandReceipt.id == receipt_id,
            AutomationCommandReceipt.service_account_id == account.id,
            AutomationCommandReceipt.organization_id == account.organization_id,
            AutomationCommandReceipt.status == "succeeded",
        )
        .one_or_none()
    )
    if receipt is None:
        raise AutomationCommandError(
            "Workflow command result not found.",
            reason_code="automation_command_not_found",
            status_code=404,
        )
    try:
        return reporting_service.read_report_artifact(
            db,
            tenant_id=account.tenant_id,
            report_id=receipt.report_id,
            artifact_id=artifact_id,
            organization_id=account.organization_id,
        )
    except HTTPException as exc:
        raise AutomationCommandError(
            "This report file is not available.",
            reason_code="automation_report_artifact_unavailable",
            status_code=404 if exc.status_code == 404 else 409,
        ) from exc


def _report_result(
    db: Session,
    *,
    report: MonthlyReport,
    campaign: Campaign,
) -> dict[str, Any]:
    artifacts = reporting_service.get_report_artifacts(
        db,
        tenant_id=report.tenant_id,
        report_id=report.id,
        organization_id=campaign.organization_id,
    )
    return {
        "message": "The saved InsightOS report is ready for this workflow.",
        "report": {
            "id": report.id,
            "status": report.report_status,
            "month_number": report.month_number,
            "generated_at": report.generated_at.isoformat(),
        },
        "resource": {
            "type": "report",
            "id": report.id,
            "href": "/reports",
        },
        "artifacts": [
            {
                "id": artifact.id,
                "type": artifact.artifact_type,
                "ready": bool(reporting_service.artifact_contract(artifact)["ready"]),
            }
            for artifact in artifacts
        ],
    }


def _recommendation_result(
    db: Session,
    recommendation: StrategyRecommendation,
    *,
    review_requested: bool = False,
) -> dict[str, Any]:
    plans = intelligence_service.build_recommendation_action_plans(
        db,
        tenant_id=recommendation.tenant_id,
        recommendations=[recommendation],
    )
    plan = plans.get(recommendation.id, {})
    metrics = []
    for metric in plan.get("success_metrics", []):
        if not isinstance(metric, dict):
            continue
        metrics.append(
            {
                key: metric[key]
                for key in ("display_name", "plain_language", "unit")
                if metric.get(key) is not None
            }
        )
    action = {
        "title": str(plan.get("display_name") or "Saved recommendation"),
        "why_it_matters": str(
            plan.get("why_it_matters") or recommendation.rationale
        ),
        "steps": [str(step) for step in plan.get("steps", [])],
        "effort": plan.get("effort"),
        "owner_role": plan.get("owner_role"),
        "success_metrics": metrics,
        "observation_window_days": plan.get("observation_window_days"),
    }
    return {
        "message": (
            "The recommendation is waiting for owner review in InsightOS."
            if review_requested
            else "InsightOS returned a saved recommendation for owner review."
        ),
        "recommendation": {
            "id": recommendation.id,
            "status": recommendation.status.value,
            "created_at": recommendation.created_at.isoformat(),
            "action": action,
        },
        "resource": {
            "type": "recommendation",
            "id": recommendation.id,
            "href": "/opportunities",
        },
        "artifacts": [],
        "truth": {
            "saved_result_only": True,
            "owner_review_required": True,
            "review_requested": review_requested,
            "approved": False,
            "executed": False,
        },
    }


def _account_contract(db: Session, row: AutomationServiceAccount) -> dict[str, Any]:
    location = db.get(BusinessLocation, row.business_location_id)
    command_count = (
        db.query(AutomationCommandReceipt)
        .filter(AutomationCommandReceipt.service_account_id == row.id)
        .count()
    )
    location_ids = _account_location_ids(db, row.id) or [row.business_location_id]
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "location_id": row.business_location_id,
        "location_name": location.name if location is not None else "Saved location",
        "location_ids": location_ids,
        "location_count": len(location_ids),
        "allowed_commands": _allowed_commands(row),
        "token_hint": row.token_hint,
        "token_version": row.token_version,
        "expires_at": row.expires_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "last_rotated_at": row.last_rotated_at.isoformat() if row.last_rotated_at else None,
        "created_at": row.created_at.isoformat(),
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "command_count": command_count,
        "token_revealed": False,
    }


def _account_location_ids(db: Session, service_account_id: str) -> list[str]:
    rows = (
        db.query(AutomationServiceAccountLocation)
        .filter(AutomationServiceAccountLocation.service_account_id == service_account_id)
        .order_by(
            AutomationServiceAccountLocation.created_at,
            AutomationServiceAccountLocation.id,
        )
        .all()
    )
    return [item.business_location_id for item in rows]


def _account_can_read_location(
    db: Session,
    *,
    account: AutomationServiceAccount,
    business_location_id: str,
) -> bool:
    return (
        db.query(AutomationServiceAccountLocation.id)
        .filter(
            AutomationServiceAccountLocation.service_account_id == account.id,
            AutomationServiceAccountLocation.tenant_id == account.tenant_id,
            AutomationServiceAccountLocation.organization_id == account.organization_id,
            AutomationServiceAccountLocation.business_location_id == business_location_id,
        )
        .first()
        is not None
    )


def _receipt_contract(
    db: Session, row: AutomationCommandReceipt, *, created: bool
) -> dict[str, Any]:
    result = json.loads(row.result_json)
    job_value = result.get("job")
    if isinstance(job_value, dict) and job_value.get("id"):
        job = (
            db.query(PlatformJob)
            .filter(
                PlatformJob.id == str(job_value["id"]),
                PlatformJob.tenant_id == row.tenant_id,
                PlatformJob.entity_type == "data_connection",
            )
            .one_or_none()
        )
        if job is not None:
            result["job"] = _safe_job_contract(job)
            if isinstance(result.get("truth"), dict):
                result["truth"]["completed"] = job.status == "completed"
    resource = result.get("resource")
    if isinstance(resource, dict) and resource.get("type") == "public_listing_check":
        run = (
            db.query(DirectoryListingDiscoveryRun)
            .filter(
                DirectoryListingDiscoveryRun.id == str(resource.get("id")),
                DirectoryListingDiscoveryRun.tenant_id == row.tenant_id,
                DirectoryListingDiscoveryRun.organization_id == row.organization_id,
                DirectoryListingDiscoveryRun.business_location_id
                == row.business_location_id,
            )
            .one_or_none()
        )
        if run is not None:
            result["job"] = _safe_listing_run_contract(run)
            if isinstance(result.get("truth"), dict):
                result["truth"]["completed"] = run.status == "completed"
    for artifact in result.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("ready") is True:
            artifact["download_path"] = (
                f"/api/v1/automation/commands/{row.id}/artifacts/{artifact['id']}"
            )
    return {
        "created": created,
        "receipt": {
            "id": row.id,
            "schema_version": row.schema_version,
            "command_type": row.command_type,
            "idempotency_key": row.idempotency_key,
            "correlation_id": row.correlation_id,
            "location_id": row.business_location_id,
            "status": row.status,
            "denial_reason_code": row.denial_reason_code,
            "result": result,
            "artifact_hash": row.artifact_hash,
            "created_at": row.created_at.isoformat(),
            "completed_at": row.completed_at.isoformat(),
        },
        "safety": _safety_contract(),
    }


def _safe_job_contract(job: PlatformJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _safe_listing_run_contract(run: DirectoryListingDiscoveryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "estimated_credits": int(run.estimated_credit_units or 0),
        "result_count": int(run.result_count or 0),
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _locked_active_organization(db: Session, organization_id: str) -> Organization:
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if organization is None or organization.status != "active":
        raise AutomationCommandError(
            "This workspace is not available for workflow commands.",
            reason_code="automation_workspace_unavailable",
            status_code=409,
        )
    return organization


def _active_location(
    db: Session,
    *,
    organization_id: str,
    business_location_id: str,
) -> BusinessLocation:
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == business_location_id,
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.status == "active",
        )
        .one_or_none()
    )
    if location is None:
        raise AutomationCommandError(
            "Choose an active location in this workspace.",
            reason_code="automation_command_location_unavailable",
            status_code=409,
        )
    campaign_exists = (
        db.query(Campaign.id)
        .filter(
            Campaign.tenant_id == organization_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id == location.id,
        )
        .first()
    )
    if campaign_exists is None:
        raise AutomationCommandError(
            "Finish setting up this location before creating a workflow command key.",
            reason_code="automation_command_campaign_required",
            status_code=409,
        )
    return location


def _locked_account(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
) -> AutomationServiceAccount:
    row = (
        db.query(AutomationServiceAccount)
        .filter(
            AutomationServiceAccount.id == service_account_id,
            AutomationServiceAccount.organization_id == organization_id,
        )
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise AutomationCommandError(
            "Workflow command key not found.",
            reason_code="automation_service_account_not_found",
            status_code=404,
        )
    return row


def _allowed_commands(row: AutomationServiceAccount) -> list[str]:
    try:
        value = json.loads(row.allowed_commands_json)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value if str(item) in ALLOWED_COMMANDS]


def _validated_allowed_commands(value: list[str] | None) -> list[str]:
    requested = list(DEFAULT_COMMANDS if value is None else value)
    normalized = list(dict.fromkeys(str(item) for item in requested))
    if COMMAND_REPORT_RETRIEVE not in normalized or any(
        item not in ALLOWED_COMMANDS for item in normalized
    ):
        raise AutomationCommandError(
            "Choose only the available workflow actions. Saved-report access is required.",
            reason_code="automation_service_account_scope_invalid",
            status_code=422,
        )
    return normalized


def _base_command_denial(
    db: Session,
    account: AutomationServiceAccount,
    request_payload: dict[str, Any],
) -> str | None:
    if request_payload["schema_version"] != COMMAND_SCHEMA_VERSION:
        return "automation_command_schema_unsupported"
    if request_payload["command_type"] not in _allowed_commands(account):
        return "automation_command_not_allowed"
    if request_payload["organization_id"] != account.organization_id:
        return "automation_command_scope_mismatch"
    if request_payload["location_id"] != account.business_location_id:
        return "automation_command_scope_mismatch"
    try:
        require_commercial_feature(
            db,
            organization_id=account.organization_id,
            feature_code=FEATURE_EXTERNAL_AUTOMATION,
        )
    except CostEconomicsError:
        return "external_automation_upgrade_required"
    location = db.get(BusinessLocation, account.business_location_id)
    if (
        location is None
        or location.organization_id != account.organization_id
        or location.status != "active"
    ):
        return "automation_command_location_unavailable"
    return None


@contextmanager
def _serialized_command(scope: str, db: Session):
    """Hold a PostgreSQL session fence across report generation's commit."""
    bind = db.get_bind()
    if bind.dialect.name.lower() != "postgresql":
        yield
        return
    engine = bind.engine if hasattr(bind, "engine") else bind
    connection = engine.connect()
    acquired = False
    try:
        deadline = monotonic() + 5.0
        while monotonic() < deadline:
            acquired = bool(
                connection.execute(
                    text(
                        "SELECT pg_try_advisory_lock(hashtextextended(:scope, 0))"
                    ),
                    {"scope": scope},
                ).scalar_one()
            )
            if acquired:
                break
            sleep(0.05)
        if not acquired:
            raise AutomationCommandError(
                "This workflow request is already being handled. Try again shortly.",
                reason_code="automation_command_in_progress",
                status_code=409,
            )
        yield
    finally:
        try:
            if acquired:
                connection.execute(
                    text(
                        "SELECT pg_advisory_unlock(hashtextextended(:scope, 0))"
                    ),
                    {"scope": scope},
                )
        finally:
            connection.close()


def _command_catalog() -> list[dict[str, Any]]:
    return [
        {
            "code": COMMAND_REPORT_RETRIEVE,
            "label": "Retrieve a saved report",
            "summary": "Let a workflow read one existing report for the selected location.",
            "read_only": True,
            "paid_provider_call": False,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_REPORT_GENERATE_SAVED,
            "label": "Create a report from saved results",
            "summary": "Let a workflow create one private report without starting new checks.",
            "read_only": False,
            "paid_provider_call": False,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_RECOMMENDATION_RETRIEVE,
            "label": "Retrieve a saved recommendation",
            "summary": "Let a workflow read one saved recommendation for owner review.",
            "read_only": True,
            "paid_provider_call": False,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_RECOMMENDATION_REQUEST_REVIEW,
            "label": "Ask an owner to review a recommendation",
            "summary": "Place one saved recommendation in the owner review queue without approving it.",
            "read_only": False,
            "paid_provider_call": False,
            "approval_required": True,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_CONNECTION_REFRESH_SAVED,
            "label": "Refresh a connected source",
            "summary": "Let a workflow request one saved-data refresh for the selected location.",
            "read_only": False,
            "paid_provider_call": False,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_LISTING_CHECK_PUBLIC,
            "label": "Check public business listings",
            "summary": "Let a workflow request one priced public listing inventory check for the selected location.",
            "read_only": False,
            "paid_provider_call": True,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_CONTENT_CREATE_WORKING_DRAFT,
            "label": "Start an accepted working draft",
            "summary": "Let a workflow create one private empty draft from an owner-accepted saved brief.",
            "read_only": False,
            "paid_provider_call": False,
            "approval_required": True,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_CONTENT_REQUEST_DRAFT_REVIEW,
            "label": "Ask an owner to review a private draft",
            "summary": "Place one existing working draft in owner review without approving or publishing it.",
            "read_only": False,
            "paid_provider_call": False,
            "approval_required": True,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_REVIEW_RETRIEVE,
            "label": "Retrieve saved review facts",
            "summary": "Let a workflow route one saved rating and reply state without sharing customer text.",
            "read_only": True,
            "paid_provider_call": False,
            "approval_required": False,
            "publishing_allowed": False,
        },
        {
            "code": COMMAND_REVIEW_CREATE_RESPONSE_DRAFT,
            "label": "Prepare a private review reply draft",
            "summary": "Let a workflow request one governed draft while approval and posting stay in InsightOS.",
            "read_only": False,
            "paid_provider_call": True,
            "approval_required": True,
            "publishing_allowed": False,
        },
    ]


def _safety_contract() -> dict[str, Any]:
    return {
        "database_access_allowed": False,
        "arbitrary_commands_allowed": False,
        "arbitrary_prompts_allowed": False,
        "paid_provider_calls_allowed": False,
        "approval_bypass_allowed": False,
        "publishing_allowed": False,
        "wordpress_changes_allowed": False,
        "business_profile_changes_allowed": False,
    }


def _denial_message(reason_code: str) -> str:
    messages = {
        "automation_command_schema_unsupported": "This workflow uses an unsupported command version.",
        "automation_command_not_allowed": "This workflow key cannot request that command.",
        "automation_command_scope_mismatch": "This workflow key is limited to a different workspace or location.",
        "external_automation_upgrade_required": "Workflow commands are not available on the current plan.",
        "automation_command_location_unavailable": "The selected location is not active and available for workflow commands.",
        "automation_report_not_found": "That report was not found for the workflow key's location.",
        "automation_campaign_not_found": "That location setup was not found for this workflow key.",
        "automation_recommendation_not_found": "That recommendation was not found for the workflow key's location.",
        "automation_connection_not_found": "That connected source was not found for the workflow key's location.",
        "automation_connection_refresh_unsupported": "That connected source cannot be refreshed by a workflow yet.",
        "campaign_report_upgrade_required": "Report creation is not available on the current plan.",
        "daily_listing_discovery_limit_reached": "This location has reached today's public listing check limit.",
        "insufficient_credits": "This workspace does not have enough Insight Credits for this check.",
        "public_listing_check_unavailable": "The public listing check is not available right now.",
        "automation_content_brief_not_found": "That saved content brief was not found for this location.",
        "automation_content_brief_not_accepted": "An owner must accept that content brief before a workflow can start its draft.",
        "automation_content_draft_unavailable": "Working drafts are not available right now.",
        "automation_content_draft_not_found": "That private working draft was not found for this location.",
        "automation_review_not_found": "That saved review was not found for this location.",
        "automation_review_already_responded": "That saved review already has a response.",
        "automation_review_draft_not_allowed": "A private reply draft cannot be prepared for that review.",
        "automation_review_draft_unavailable": "Private reply drafting is not available right now.",
    }
    return messages.get(reason_code, "InsightOS safely declined this workflow command.")


def _invalid_token() -> AutomationCommandError:
    return AutomationCommandError(
        "The workflow command key is invalid, expired, or revoked.",
        reason_code="automation_service_account_token_invalid",
        status_code=401,
    )


def _normalized_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) < 2 or len(normalized) > 120:
        raise AutomationCommandError(
            "Enter a workflow key name between 2 and 120 characters.",
            reason_code="automation_service_account_name_invalid",
            status_code=422,
        )
    return normalized


def _new_token(account_id: str) -> str:
    return f"iosa_{account_id}_{secrets.token_urlsafe(32)}"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_payload(payload: dict[str, Any]) -> str:
    return _hash_text(_json(payload))


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
