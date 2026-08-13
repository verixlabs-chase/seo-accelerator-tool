from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
import uuid

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.crawl import CrawlRun
from app.models.data_connection import DataConnection
from app.models.organization import Organization
from app.models.reporting import MonthlyReport
from app.models.support import SupportRequest


ACTIVE_STATUSES = {"received", "investigating", "waiting_for_customer", "escalated"}
PROHIBITED_DIAGNOSTIC_KEYS = {
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "api_key",
    "credential",
    "provider_payload",
    "page_content",
    "page_text",
    "review_text",
    "prompt",
    "response",
}


class SupportRequestError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _plan_response_policy(plan_type: str) -> tuple[str, timedelta, str]:
    normalized = (plan_type or "standard").strip().lower()
    if normalized == "enterprise":
        return "managed", timedelta(hours=4), "Usually within 4 hours"
    if normalized in {"pro", "growth", "multi_location"}:
        return "priority", timedelta(hours=24), "Usually within 1 business day"
    return "standard", timedelta(hours=48), "Usually within 2 business days"


def _campaign_for_scope(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str | None,
) -> Campaign | None:
    if not campaign_id:
        return None
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise SupportRequestError(
            "The selected location is not available in this organization.",
            reason_code="campaign_scope_mismatch",
            status_code=404,
        )
    return campaign


def build_safe_diagnostic_bundle(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign: Campaign | None,
    page_path: str,
    collected_at: datetime,
) -> dict[str, Any]:
    connection_query = db.query(DataConnection).filter(
        DataConnection.tenant_id == tenant_id,
        DataConnection.organization_id == organization_id,
    )
    if campaign is not None:
        connection_query = connection_query.filter(DataConnection.campaign_id == campaign.id)
    connections = connection_query.order_by(DataConnection.provider_name.asc()).all()

    latest_crawl = None
    latest_report = None
    if campaign is not None:
        latest_crawl = (
            db.query(CrawlRun)
            .filter(CrawlRun.tenant_id == tenant_id, CrawlRun.campaign_id == campaign.id)
            .order_by(CrawlRun.created_at.desc())
            .first()
        )
        latest_report = (
            db.query(MonthlyReport)
            .filter(MonthlyReport.tenant_id == tenant_id, MonthlyReport.campaign_id == campaign.id)
            .order_by(MonthlyReport.generated_at.desc())
            .first()
        )

    return {
        "schema_version": "1.0",
        "collected_at": collected_at.isoformat(),
        "scope": {
            "organization_id": organization_id,
            "campaign_id": campaign.id if campaign else None,
            "business_location_id": campaign.business_location_id if campaign else None,
            "page_path": page_path,
        },
        "setup": {
            "campaign_setup_state": campaign.setup_state if campaign else None,
            "has_location_mapping": bool(campaign and campaign.business_location_id),
        },
        "connections": [
            {
                "provider": item.provider_name,
                "status": item.status,
                "last_success_at": _iso(item.last_success_at),
                "last_sync_started_at": _iso(item.last_sync_started_at),
                "last_sync_completed_at": _iso(item.last_sync_completed_at),
                "last_error_code": item.last_error_code,
            }
            for item in connections
        ],
        "latest_checks": {
            "website_scan": None
            if latest_crawl is None
            else {
                "status": latest_crawl.status,
                "pages_discovered": latest_crawl.pages_discovered,
                "started_at": _iso(latest_crawl.started_at),
                "finished_at": _iso(latest_crawl.finished_at),
            },
            "report": None
            if latest_report is None
            else {
                "status": latest_report.report_status,
                "generated_at": _iso(latest_report.generated_at),
            },
        },
        "privacy": {
            "included": [
                "record identifiers",
                "setup state",
                "connection status and timestamps",
                "provider error codes",
                "latest scan and report status",
            ],
            "content_policy": "operational_metadata_only",
        },
    }


def assert_bundle_is_safe(bundle: dict[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized = key.lower()
                if any(prohibited in normalized for prohibited in PROHIBITED_DIAGNOSTIC_KEYS):
                    raise SupportRequestError(
                        "The diagnostic summary included a prohibited field.",
                        reason_code="unsafe_diagnostic_field",
                        status_code=500,
                    )
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(bundle)


def create_support_request(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    category: str,
    page_path: str,
    customer_summary: str,
    campaign_id: str | None,
    diagnostic_consent: bool,
    operator_access_consent: bool,
    now: datetime | None = None,
) -> SupportRequest:
    created_at = now or datetime.now(UTC)
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise SupportRequestError(
            "Organization not found.", reason_code="organization_not_found", status_code=404
        )
    campaign = _campaign_for_scope(
        db, organization_id=organization_id, campaign_id=campaign_id
    )
    priority, response_delta, _label = _plan_response_policy(organization.plan_type)
    diagnostic_bundle = None
    if diagnostic_consent:
        diagnostic_bundle = build_safe_diagnostic_bundle(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign=campaign,
            page_path=page_path,
            collected_at=created_at,
        )
        assert_bundle_is_safe(diagnostic_bundle)

    request_id = str(uuid.uuid4())
    row = SupportRequest(
        id=request_id,
        reference_code=f"IOS-{request_id[:8].upper()}",
        tenant_id=tenant_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        campaign_id=campaign.id if campaign else None,
        category=category,
        page_path=page_path,
        customer_summary=customer_summary.strip(),
        priority=priority,
        status="received",
        diagnostic_consent=diagnostic_consent,
        operator_access_consent=operator_access_consent,
        operator_access_expires_at=(created_at + timedelta(hours=72))
        if operator_access_consent
        else None,
        diagnostic_bundle=diagnostic_bundle,
        status_history=[
            {
                "status": "received",
                "changed_at": created_at.isoformat(),
                "changed_by": "customer",
                "note_code": "request_received",
            }
        ],
        response_target_at=created_at + response_delta,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def list_support_requests(db: Session, *, organization_id: str) -> list[SupportRequest]:
    return (
        db.query(SupportRequest)
        .filter(SupportRequest.organization_id == organization_id)
        .order_by(SupportRequest.created_at.desc())
        .limit(50)
        .all()
    )


def list_platform_support_requests(
    db: Session,
    *,
    organization_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[SupportRequest]:
    query = db.query(SupportRequest)
    if organization_id:
        query = query.filter(SupportRequest.organization_id == organization_id)
    if status:
        query = query.filter(SupportRequest.status == status)
    return (
        query.order_by(
            SupportRequest.response_target_at.asc(),
            SupportRequest.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def escalate_support_request(
    db: Session,
    *,
    organization_id: str,
    request_id: str,
    reason: str,
    actor: str = "customer",
    now: datetime | None = None,
) -> SupportRequest:
    row = (
        db.query(SupportRequest)
        .filter(
            SupportRequest.id == request_id,
            SupportRequest.organization_id == organization_id,
        )
        .first()
    )
    if row is None:
        raise SupportRequestError(
            "Support request not found.", reason_code="support_request_not_found", status_code=404
        )
    if row.status not in ACTIVE_STATUSES:
        raise SupportRequestError(
            "Resolved requests cannot be escalated.",
            reason_code="support_request_closed",
            status_code=409,
        )
    changed_at = now or datetime.now(UTC)
    row.status = "escalated"
    row.escalated_at = row.escalated_at or changed_at
    row.status_history = [
        *(row.status_history or []),
        {
            "status": "escalated",
            "changed_at": changed_at.isoformat(),
            "changed_by": actor,
            "note_code": reason,
        },
    ]
    row.updated_at = changed_at
    db.flush()
    return row


def update_support_request_status(
    db: Session,
    *,
    request_id: str,
    status: str,
    note_code: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> SupportRequest:
    row = db.get(SupportRequest, request_id)
    if row is None:
        raise SupportRequestError(
            "Support request not found.", reason_code="support_request_not_found", status_code=404
        )
    changed_at = now or datetime.now(UTC)
    row.status = status
    if status == "escalated":
        row.escalated_at = row.escalated_at or changed_at
    if status == "resolved":
        row.resolved_at = changed_at
    row.status_history = [
        *(row.status_history or []),
        {
            "status": status,
            "changed_at": changed_at.isoformat(),
            "changed_by": "support",
            "actor_user_id": actor_user_id,
            "note_code": note_code,
        },
    ]
    row.updated_at = changed_at
    db.flush()
    return row


def serialize_support_request(row: SupportRequest, *, include_diagnostics: bool = False) -> dict[str, Any]:
    organization_plan = "standard"
    priority_labels = {
        "standard": "Usually within 2 business days",
        "priority": "Usually within 1 business day",
        "managed": "Usually within 4 hours",
    }
    payload = {
        "id": row.id,
        "reference_code": row.reference_code,
        "campaign_id": row.campaign_id,
        "category": row.category,
        "page_path": row.page_path,
        "customer_summary": row.customer_summary,
        "priority": row.priority,
        "status": row.status,
        "status_label": row.status.replace("_", " ").title(),
        "response_expectation": priority_labels.get(row.priority, priority_labels[organization_plan]),
        "response_target_at": _iso(row.response_target_at),
        "diagnostic_consent": row.diagnostic_consent,
        "diagnostic_attached": bool(row.diagnostic_bundle),
        "operator_access_consent": row.operator_access_consent,
        "operator_access_expires_at": _iso(row.operator_access_expires_at),
        "status_history": row.status_history or [],
        "escalated_at": _iso(row.escalated_at),
        "resolved_at": _iso(row.resolved_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if include_diagnostics:
        payload["diagnostic_bundle"] = row.diagnostic_bundle
    return payload
