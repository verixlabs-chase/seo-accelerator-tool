from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automation.n8n_starter_workflow import build_n8n_report_ready_workflow
from app.core.config import get_settings
from app.db.session import set_session_security_context
from app.models.automation_command import (
    AutomationCommandReceipt,
    AutomationServiceAccount,
)
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.reporting import MonthlyReport, ReportArtifact
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_EXTERNAL_AUTOMATION,
    require_commercial_feature,
)
from app.services.cost_economics_service import CostEconomicsError
from app.services import reporting_service


COMMAND_SCHEMA_VERSION = "insightos.automation.command.v1"
COMMAND_REPORT_RETRIEVE = "report.retrieve"
ALLOWED_COMMANDS = (COMMAND_REPORT_RETRIEVE,)
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
    expires_in_days: int,
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
        allowed_commands_json=_json(list(ALLOWED_COMMANDS)),
        expires_at=now + timedelta(days=expires_in_days),
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    write_audit_log(
        db,
        tenant_id=organization.id,
        actor_user_id=actor_user_id,
        event_type="automation.service_account.created",
        payload={
            "service_account_id": row.id,
            "business_location_id": row.business_location_id,
            "allowed_commands": list(ALLOWED_COMMANDS),
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


def rotate_service_account_token(
    db: Session,
    *,
    organization_id: str,
    service_account_id: str,
    actor_user_id: str,
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
        "items": [_receipt_contract(row, created=False) for row in rows],
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
        return _receipt_contract(existing, created=False)

    now = datetime.now(UTC)
    account.last_used_at = now
    account.updated_at = now
    report_id = str(request_payload["target"]["report_id"])
    denial_reason: str | None = None
    campaign: Campaign | None = None
    report: MonthlyReport | None = None

    if request_payload["schema_version"] != COMMAND_SCHEMA_VERSION:
        denial_reason = "automation_command_schema_unsupported"
    elif request_payload["command_type"] not in _allowed_commands(account):
        denial_reason = "automation_command_not_allowed"
    elif request_payload["organization_id"] != account.organization_id:
        denial_reason = "automation_command_scope_mismatch"
    elif request_payload["location_id"] != account.business_location_id:
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

    location = db.get(BusinessLocation, account.business_location_id)
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
                Campaign.business_location_id == account.business_location_id,
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
        business_location_id=account.business_location_id,
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
        return _receipt_contract(existing, created=False)

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
    return _receipt_contract(receipt, created=True)


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
    return _receipt_contract(row, created=False)


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


def _account_contract(db: Session, row: AutomationServiceAccount) -> dict[str, Any]:
    location = db.get(BusinessLocation, row.business_location_id)
    command_count = (
        db.query(AutomationCommandReceipt)
        .filter(AutomationCommandReceipt.service_account_id == row.id)
        .count()
    )
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "location_id": row.business_location_id,
        "location_name": location.name if location is not None else "Saved location",
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


def _receipt_contract(row: AutomationCommandReceipt, *, created: bool) -> dict[str, Any]:
    result = json.loads(row.result_json)
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
        }
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
