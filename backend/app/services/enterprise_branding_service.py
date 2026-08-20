from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.enterprise_branding import OrganizationReportBrand
from app.models.organization import Organization
from app.services.audit_service import write_audit_log
from app.services.commercial_plan_service import (
    FEATURE_WHITE_LABEL_REPORTING,
    require_commercial_feature,
)
from app.services.cost_economics_service import resolve_plan_economics


DEFAULT_REPORT_TITLE = "Business progress report"
DEFAULT_FOOTER = "Created from the saved information available for this report. Open InsightOS to see newer results."
DEFAULT_ACCENT = "#E85D19"


class EnterpriseBrandingError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def _organization_or_error(db: Session, organization_id: str) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise EnterpriseBrandingError(
            "Organization not found.", reason_code="organization_not_found", status_code=404
        )
    return organization


def _clean(value: str, *, label: str, maximum: int) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise EnterpriseBrandingError(
            f"{label} is required.", reason_code="report_branding_value_required"
        )
    if len(normalized) > maximum:
        raise EnterpriseBrandingError(
            f"{label} is too long.", reason_code="report_branding_value_too_long"
        )
    if any(ord(character) < 32 for character in normalized):
        raise EnterpriseBrandingError(
            f"{label} contains unsupported characters.",
            reason_code="report_branding_value_invalid",
        )
    return normalized


def _clean_accent(value: str) -> str:
    normalized = value.strip().upper()
    if re.fullmatch(r"#[0-9A-F]{6}", normalized) is None:
        raise EnterpriseBrandingError(
            "Choose a valid six-digit report accent color.",
            reason_code="report_branding_accent_invalid",
        )
    return normalized


def _plan_allows_branding(organization: Organization) -> bool:
    return resolve_plan_economics(organization.plan_type).code == "enterprise"


def get_report_branding(
    db: Session,
    *,
    organization_id: str,
) -> dict[str, Any]:
    organization = _organization_or_error(db, organization_id)
    row = (
        db.query(OrganizationReportBrand)
        .filter(OrganizationReportBrand.organization_id == organization_id)
        .one_or_none()
    )
    plan_eligible = _plan_allows_branding(organization)
    return {
        "plan_eligible": plan_eligible,
        "required_plan": "Enterprise",
        "configured": row is not None,
        "applied_to_new_reports": bool(row and row.enabled and plan_eligible),
        "saved_for_recovery": bool(row and not plan_eligible),
        "brand_name": row.brand_name if row else organization.name,
        "report_title": row.report_title if row else DEFAULT_REPORT_TITLE,
        "footer_text": row.footer_text if row else DEFAULT_FOOTER,
        "accent_color": row.accent_color if row else DEFAULT_ACCENT,
        "hide_platform_attribution": bool(row.hide_platform_attribution) if row else False,
        "enabled": bool(row.enabled) if row else False,
        "version": row.version if row else None,
        "updated_at": row.updated_at.isoformat() if row else None,
        "truth": {
            "existing_reports_unchanged": True,
            "future_reports_only": True,
            "saved_on_downgrade": True,
            "logo_upload_available": False,
            "accent_color_available": True,
            "custom_colors_available": False,
        },
    }


def save_report_branding(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    brand_name: str,
    report_title: str,
    footer_text: str,
    accent_color: str,
    hide_platform_attribution: bool,
    enabled: bool,
) -> dict[str, Any]:
    if tenant_id != organization_id:
        raise EnterpriseBrandingError(
            "Organization context does not match this request.",
            reason_code="organization_scope_mismatch",
            status_code=404,
        )
    require_commercial_feature(
        db,
        organization_id=organization_id,
        feature_code=FEATURE_WHITE_LABEL_REPORTING,
    )
    now = datetime.now(UTC)
    row = (
        db.query(OrganizationReportBrand)
        .filter(OrganizationReportBrand.organization_id == organization_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = OrganizationReportBrand(
            tenant_id=tenant_id,
            organization_id=organization_id,
            brand_name=_clean(brand_name, label="Brand name", maximum=120),
            report_title=_clean(report_title, label="Report title", maximum=120),
            footer_text=_clean(footer_text, label="Footer", maximum=240),
            accent_color=_clean_accent(accent_color),
            hide_platform_attribution=bool(hide_platform_attribution),
            enabled=bool(enabled),
            version=1,
            updated_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.brand_name = _clean(brand_name, label="Brand name", maximum=120)
        row.report_title = _clean(report_title, label="Report title", maximum=120)
        row.footer_text = _clean(footer_text, label="Footer", maximum=240)
        row.accent_color = _clean_accent(accent_color)
        row.hide_platform_attribution = bool(hide_platform_attribution)
        row.enabled = bool(enabled)
        row.version += 1
        row.updated_by_user_id = actor_user_id
        row.updated_at = now
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="enterprise.report_branding.updated",
        payload={
            "organization_id": organization_id,
            "version": row.version,
            "enabled": row.enabled,
            "hide_platform_attribution": row.hide_platform_attribution,
            "accent_color": row.accent_color,
        },
    )
    db.commit()
    return get_report_branding(db, organization_id=organization_id)


def frozen_report_brand(
    db: Session,
    *,
    organization_id: str,
    prepared_for: str,
) -> dict[str, Any]:
    organization = _organization_or_error(db, organization_id)
    row = (
        db.query(OrganizationReportBrand)
        .filter(OrganizationReportBrand.organization_id == organization_id)
        .one_or_none()
    )
    active = bool(row and row.enabled and _plan_allows_branding(organization))
    if not active:
        return {
            "brand_name": "InsightOS",
            "product_name": "InsightOS",
            "publisher": "VerixLabs",
            "report_title": DEFAULT_REPORT_TITLE,
            "footer_text": DEFAULT_FOOTER,
            "accent_color": DEFAULT_ACCENT,
            "prepared_for": prepared_for,
            "show_platform_attribution": True,
            "custom_branding_applied": False,
            "branding_version": None,
        }
    return {
        "brand_name": row.brand_name,
        "product_name": row.brand_name,
        "publisher": row.brand_name,
        "report_title": row.report_title,
        "footer_text": row.footer_text,
        "accent_color": row.accent_color,
        "prepared_for": prepared_for,
        "show_platform_attribution": not row.hide_platform_attribution,
        "custom_branding_applied": True,
        "branding_version": row.version,
    }
