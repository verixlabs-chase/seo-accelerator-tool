from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.reporting import ReportRecipient, ReportShareLink
from app.services import reporting_service


def _now(value: datetime | None = None) -> datetime:
    resolved = value or datetime.now(UTC)
    return resolved if resolved.tzinfo else resolved.replace(tzinfo=UTC)


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def list_recipients(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> list[ReportRecipient]:
    reporting_service._campaign_or_404(db, tenant_id, campaign_id, organization_id)
    return (
        db.query(ReportRecipient)
        .filter(
            ReportRecipient.tenant_id == tenant_id,
            ReportRecipient.organization_id == organization_id,
            ReportRecipient.campaign_id == campaign_id,
        )
        .order_by(ReportRecipient.enabled.desc(), ReportRecipient.created_at.asc())
        .all()
    )


def upsert_recipient(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    email: str,
    display_name: str | None,
    recipient_role: str,
    enabled: bool,
) -> ReportRecipient:
    reporting_service._campaign_or_404(db, tenant_id, campaign_id, organization_id)
    normalized_email = email.strip().lower()
    row = (
        db.query(ReportRecipient)
        .filter(
            ReportRecipient.tenant_id == tenant_id,
            ReportRecipient.organization_id == organization_id,
            ReportRecipient.campaign_id == campaign_id,
            ReportRecipient.email == normalized_email,
        )
        .first()
    )
    if row is None:
        row = ReportRecipient(
            tenant_id=tenant_id,
            organization_id=organization_id,
            campaign_id=campaign_id,
            email=normalized_email,
        )
        db.add(row)
    row.display_name = display_name.strip() if display_name else None
    row.recipient_role = recipient_role
    row.enabled = enabled
    db.commit()
    db.refresh(row)
    return row


def set_recipient_enabled(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    recipient_id: str,
    enabled: bool,
) -> ReportRecipient:
    row = db.get(ReportRecipient, recipient_id)
    if row is None or row.tenant_id != tenant_id or row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report recipient not found")
    row.enabled = enabled
    db.commit()
    db.refresh(row)
    return row


def create_share_link(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    report_id: str,
    actor_user_id: str,
    expires_in_hours: int,
    now: datetime | None = None,
) -> tuple[ReportShareLink, str]:
    report = reporting_service.get_report(db, tenant_id, report_id, organization_id)
    token = secrets.token_urlsafe(32)
    row = ReportShareLink(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=report.campaign_id,
        report_id=report.id,
        token_hash=_token_hash(token),
        expires_at=_now(now) + timedelta(hours=expires_in_hours),
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, token


def list_share_links(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    report_id: str,
) -> list[ReportShareLink]:
    reporting_service.get_report(db, tenant_id, report_id, organization_id)
    return (
        db.query(ReportShareLink)
        .filter(
            ReportShareLink.tenant_id == tenant_id,
            ReportShareLink.organization_id == organization_id,
            ReportShareLink.report_id == report_id,
        )
        .order_by(ReportShareLink.created_at.desc())
        .all()
    )


def share_link_status(row: ReportShareLink, now: datetime | None = None) -> str:
    if row.revoked_at is not None:
        return "revoked"
    expires_at = _now(row.expires_at)
    if expires_at <= _now(now):
        return "expired"
    return "active"


def revoke_share_link(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    link_id: str,
    now: datetime | None = None,
) -> ReportShareLink:
    row = db.get(ReportShareLink, link_id)
    if row is None or row.tenant_id != tenant_id or row.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report link not found")
    if row.revoked_at is None:
        row.revoked_at = _now(now)
        db.commit()
        db.refresh(row)
    return row


def open_share_link(
    db: Session,
    *,
    token: str,
    now: datetime | None = None,
) -> tuple[ReportShareLink, bytes]:
    row = db.query(ReportShareLink).filter(ReportShareLink.token_hash == _token_hash(token)).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report link not found")
    link_status = share_link_status(row, now)
    if link_status == "revoked":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This report link was turned off")
    if link_status == "expired":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This report link has expired")

    artifacts = reporting_service.get_report_artifacts(
        db,
        tenant_id=row.tenant_id,
        report_id=row.report_id,
        organization_id=row.organization_id,
    )
    html_artifact = next((item for item in artifacts if item.artifact_type == "html"), None)
    if html_artifact is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The shared report is not available")
    _, content = reporting_service.read_report_artifact(
        db,
        tenant_id=row.tenant_id,
        report_id=row.report_id,
        artifact_id=html_artifact.id,
        organization_id=row.organization_id,
    )
    opened_at = _now(now)
    row.last_opened_at = opened_at
    row.open_count += 1
    db.commit()
    return row, content
