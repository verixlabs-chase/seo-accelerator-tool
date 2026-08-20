from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.portfolio_targeting import (
    PortfolioLocationAccessGrant,
    PortfolioLocationGroup,
    PortfolioLocationGroupMember,
)
from app.models.reporting import MonthlyReport
from app.services import reporting_service
from app.services.enterprise_branding_service import get_client_portal_identity
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    require_commercial_feature,
)


READY_REPORT_STATUSES = {"generated", "delivered"}
MAX_CLIENT_PDF_BYTES = 20 * 1024 * 1024


class EnterpriseClientReportError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(message)


def list_client_reports(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
) -> dict[str, Any]:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    identity = get_client_portal_identity(db, organization_id=organization_id)
    locations = _accessible_locations(
        db,
        organization_id=organization_id,
        user_id=user_id,
    )
    if not locations:
        return _list_contract([], identity=identity)

    location_names = {row.id: row.name for row in locations}
    rows = (
        db.query(MonthlyReport, Campaign)
        .join(Campaign, Campaign.id == MonthlyReport.campaign_id)
        .filter(
            MonthlyReport.tenant_id == tenant_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id.in_(location_names),
            MonthlyReport.report_status.in_(READY_REPORT_STATUSES),
        )
        .order_by(MonthlyReport.generated_at.desc(), MonthlyReport.id.desc())
        .limit(100)
        .all()
    )
    items: list[dict[str, Any]] = []
    for report, campaign in rows:
        if _ready_artifact_id(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            report_id=report.id,
            artifact_type="html",
        ) is None:
            continue
        generated_at = _utc_datetime(report.generated_at)
        items.append(
            {
                "id": report.id,
                "location_name": location_names[str(campaign.business_location_id)],
                "period_label": _period_label(report.month_number),
                "status": "ready",
                "generated_at": generated_at.isoformat(),
                "freshness": "current" if generated_at >= datetime.now(UTC) - timedelta(days=31) else "older_saved_report",
                "pdf_available": _ready_artifact_id(
                    db,
                    tenant_id=tenant_id,
                    organization_id=organization_id,
                    report_id=report.id,
                    artifact_type="pdf",
                )
                is not None,
            }
        )
    return _list_contract(items, identity=identity)


def read_client_report_html(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    report_id: str,
) -> bytes:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    _assert_client_report_access(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        user_id=user_id,
        report_id=report_id,
    )
    artifact_id = _ready_artifact_id(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        report_id=report_id,
        artifact_type="html",
    )
    if artifact_id is None:
        raise EnterpriseClientReportError(
            "This saved report is not ready to open.",
            reason_code="client_report_unavailable",
            status_code=409,
        )
    _, content = reporting_service.read_report_artifact(
        db,
        tenant_id,
        report_id,
        artifact_id,
        organization_id,
    )
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=user_id,
        event_type="report.client_portal.opened",
        payload={"report_id": report_id},
    )
    db.flush()
    return content


def read_client_report_pdf(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    report_id: str,
) -> bytes:
    _assert_scope(tenant_id=tenant_id, organization_id=organization_id)
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_AUTHENTICATED_CLIENT_REPORTS,
    )
    _assert_client_report_access(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        user_id=user_id,
        report_id=report_id,
    )
    artifact_id = _ready_artifact_id(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        report_id=report_id,
        artifact_type="pdf",
    )
    if artifact_id is None:
        raise EnterpriseClientReportError(
            "This saved report does not have a verified PDF to download.",
            reason_code="client_report_pdf_unavailable",
            status_code=409,
        )
    try:
        artifact, content = reporting_service.read_report_artifact(
            db,
            tenant_id,
            report_id,
            artifact_id,
            organization_id,
        )
    except HTTPException as exc:
        raise EnterpriseClientReportError(
            "This saved report PDF did not pass its file check.",
            reason_code="client_report_pdf_invalid",
            status_code=409,
        ) from exc
    if (
        artifact.content_type != "application/pdf"
        or not content.startswith(b"%PDF-")
        or len(content) > MAX_CLIENT_PDF_BYTES
    ):
        raise EnterpriseClientReportError(
            "This saved report PDF did not pass its file check.",
            reason_code="client_report_pdf_invalid",
            status_code=409,
        )
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=user_id,
        event_type="report.client_portal.pdf_downloaded",
        payload={"report_id": report_id},
    )
    db.flush()
    return content


def _assert_client_report_access(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    user_id: str,
    report_id: str,
) -> None:
    location_ids = {
        row.id
        for row in _accessible_locations(
            db,
            organization_id=organization_id,
            user_id=user_id,
        )
    }
    report_row = (
        db.query(MonthlyReport.id)
        .join(Campaign, Campaign.id == MonthlyReport.campaign_id)
        .filter(
            MonthlyReport.id == report_id,
            MonthlyReport.tenant_id == tenant_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
            Campaign.business_location_id.in_(location_ids),
            MonthlyReport.report_status.in_(READY_REPORT_STATUSES),
        )
        .first()
    )
    if report_row is None:
        raise EnterpriseClientReportError(
            "That report is not available in your assigned client view.",
            reason_code="client_report_not_found",
            status_code=404,
        )


def _accessible_locations(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
) -> list[BusinessLocation]:
    group_ids = {
        str(row[0])
        for row in (
            db.query(PortfolioLocationAccessGrant.location_group_id)
            .join(
                PortfolioLocationGroup,
                PortfolioLocationGroup.id == PortfolioLocationAccessGrant.location_group_id,
            )
            .filter(
                PortfolioLocationAccessGrant.organization_id == organization_id,
                PortfolioLocationAccessGrant.user_id == user_id,
                PortfolioLocationAccessGrant.status == "active",
                PortfolioLocationGroup.organization_id == organization_id,
                PortfolioLocationGroup.status == "active",
            )
            .all()
        )
    }
    if not group_ids:
        return []
    location_ids = {
        str(row[0])
        for row in (
            db.query(PortfolioLocationGroupMember.business_location_id)
            .filter(
                PortfolioLocationGroupMember.organization_id == organization_id,
                PortfolioLocationGroupMember.location_group_id.in_(group_ids),
            )
            .all()
        )
    }
    if not location_ids:
        return []
    return (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.organization_id == organization_id,
            BusinessLocation.id.in_(location_ids),
        )
        .order_by(BusinessLocation.name.asc(), BusinessLocation.id.asc())
        .all()
    )


def _ready_artifact_id(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    report_id: str,
    artifact_type: str,
) -> str | None:
    artifacts = reporting_service.get_report_artifacts(
        db,
        tenant_id,
        report_id,
        organization_id,
    )
    for artifact in artifacts:
        contract = reporting_service.artifact_contract(artifact)
        if artifact.artifact_type == artifact_type and bool(contract["ready"]):
            return artifact.id
    return None


def _assert_scope(*, tenant_id: str, organization_id: str) -> None:
    if tenant_id != organization_id:
        raise EnterpriseClientReportError(
            "Organization context does not match this request.",
            reason_code="organization_scope_mismatch",
            status_code=404,
        )


def _period_label(month_number: int) -> str:
    return "Onboarding baseline" if month_number <= 0 else f"Month {month_number}"


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _list_contract(
    items: list[dict[str, Any]],
    *,
    identity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "items": items,
        "count": len(items),
        "identity": identity,
        "truth": {
            "scope": "assigned_locations_only",
            "identity_scope": "current_portal_only",
            "summary": (
                "These are verified saved reports for the locations assigned to this client sign-in."
                if items
                else "No verified saved reports are assigned to this client sign-in yet."
            ),
            "limitations": [
                "Reports reflect saved evidence as of their displayed date.",
                "This client view cannot change workspace data or settings.",
                "Portal styling may change; each saved report keeps its original identity and evidence.",
            ],
        },
    }
