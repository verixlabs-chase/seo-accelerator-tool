from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.business_location import BusinessLocation
from app.models.data_connection import DataConnection
from app.models.data_governance import (
    OrganizationClosureRequest,
    OrganizationDeletionTombstone,
    OrganizationLegalHold,
)
from app.models.organization import Organization
from app.models.organization_oauth_client import OrganizationOAuthClient
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_job import PlatformJob
from app.models.reporting import ReportSchedule, ReportShareLink
from app.models.wordpress_site_connection import WordPressSiteConnection
from app.services.audit_service import write_audit_log
from app.services.provider_disconnect_service import disconnect_google_provider


CLOSURE_CONFIRMATION = "CLOSE WORKSPACE"
CLOSURE_RECOVERY_WINDOW = timedelta(days=30)
ACTIVE_CLOSURE_STATUSES = {"recovery_window", "on_hold"}
BLOCKING_BILLING_STATUSES = {"active", "trialing", "past_due", "unpaid"}


class OrganizationClosureError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def preview_organization_closure(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> dict[str, Any]:
    organization = _organization(db, tenant_id=tenant_id, organization_id=organization_id)
    current = _current_closure(db, tenant_id=tenant_id, organization_id=organization_id)
    active_hold = _active_hold(db, tenant_id=tenant_id, organization_id=organization_id)
    billing_blocks = bool(
        organization.stripe_subscription_id
        and str(organization.billing_status or "").lower() in BLOCKING_BILLING_STATUSES
    )
    counts = {
        "locations": db.query(BusinessLocation).filter(
            BusinessLocation.organization_id == organization_id,
        ).count(),
        "active_connections": db.query(DataConnection).filter(
            DataConnection.organization_id == organization_id,
            DataConnection.status.notin_(["disconnected", "paused_closure"]),
        ).count(),
        "connected_accounts": db.query(OrganizationProviderCredential).filter(
            OrganizationProviderCredential.organization_id == organization_id,
        ).count(),
        "wordpress_connections": db.query(WordPressSiteConnection).filter(
            WordPressSiteConnection.organization_id == organization_id,
            WordPressSiteConnection.status == "connected",
        ).count(),
        "scheduled_reports": db.query(ReportSchedule).filter(
            ReportSchedule.organization_id == organization_id,
            ReportSchedule.enabled.is_(True),
        ).count(),
        "active_share_links": db.query(ReportShareLink).filter(
            ReportShareLink.organization_id == organization_id,
            ReportShareLink.revoked_at.is_(None),
        ).count(),
        "queued_jobs": db.query(PlatformJob).filter(
            PlatformJob.tenant_id == tenant_id,
            PlatformJob.status.in_(["queued", "retrying"]),
        ).count(),
    }
    blockers: list[dict[str, str]] = []
    if billing_blocks:
        blockers.append(
            {
                "code": "active_subscription",
                "message": "End the paid subscription from billing before scheduling closure.",
            }
        )
    return {
        "organization_name": organization.name,
        "organization_status": organization.status,
        "recovery_days": CLOSURE_RECOVERY_WINDOW.days,
        "active_legal_hold": active_hold is not None,
        "can_request": current is None and not billing_blocks and organization.status == "active",
        "blockers": blockers,
        "affected_counts": counts,
        "what_stops": [
            "New provider updates and background work",
            "Scheduled reports and public report links",
            "WordPress changes and other connected-account actions",
            "Changes to workspace data during the recovery window",
        ],
        "what_stays": [
            "Saved business results remain readable during the 30-day recovery window",
            "Account exports remain available under their normal seven-day limit",
            "Security and audit evidence remains under its approved retention policy",
            "A restore-safe tombstone is required before verified deletion can finish",
        ],
        "confirmation_text": CLOSURE_CONFIRMATION,
        "current_request": serialize_closure(current) if current is not None else None,
    }


def request_organization_closure(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    client_request_id: str,
    confirmation: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    existing = db.query(OrganizationClosureRequest).filter(
        OrganizationClosureRequest.tenant_id == tenant_id,
        OrganizationClosureRequest.organization_id == organization_id,
        OrganizationClosureRequest.client_request_id == client_request_id,
    ).first()
    if existing is not None:
        return serialize_closure(existing)
    if confirmation != CLOSURE_CONFIRMATION:
        raise OrganizationClosureError(
            f"Type {CLOSURE_CONFIRMATION} exactly to schedule closure.",
            reason_code="closure_confirmation_mismatch",
        )

    organization = _organization(db, tenant_id=tenant_id, organization_id=organization_id)
    active = _current_closure(db, tenant_id=tenant_id, organization_id=organization_id)
    if active is not None:
        raise OrganizationClosureError(
            "This workspace already has a closure request.",
            reason_code="closure_already_requested",
            status_code=409,
        )
    if organization.status != "active":
        raise OrganizationClosureError(
            "This workspace cannot start another closure request in its current state.",
            reason_code="closure_invalid_organization_state",
            status_code=409,
        )
    if (
        organization.stripe_subscription_id
        and str(organization.billing_status or "").lower() in BLOCKING_BILLING_STATUSES
    ):
        raise OrganizationClosureError(
            "End the paid subscription from billing before scheduling closure.",
            reason_code="closure_active_subscription",
            status_code=409,
        )

    requested_at = now or datetime.now(UTC)
    snapshot = _pause_workspace(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        now=requested_at,
    )
    active_hold = _active_hold(db, tenant_id=tenant_id, organization_id=organization_id)
    row = OrganizationClosureRequest(
        tenant_id=tenant_id,
        organization_id=organization_id,
        client_request_id=client_request_id,
        requested_by_user_id=actor_user_id,
        status="recovery_window",
        hold_status="active" if active_hold is not None else "clear",
        operational_snapshot=snapshot["restore_snapshot"],
        action_counts=snapshot["action_counts"],
        requested_at=requested_at,
        recovery_until=requested_at + CLOSURE_RECOVERY_WINDOW,
        created_at=requested_at,
        updated_at=requested_at,
    )
    organization.status = "closure_pending"
    organization.updated_at = requested_at
    db.add(row)
    db.flush()
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.organization_closure.requested",
        payload={
            "organization_id": organization_id,
            "closure_request_id": row.id,
            "recovery_until": row.recovery_until.isoformat(),
            "hold_active": active_hold is not None,
            "action_counts": row.action_counts,
        },
    )
    db.flush()
    return serialize_closure(row)


def cancel_organization_closure(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    closure_request_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    row = _closure_row(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        closure_request_id=closure_request_id,
        for_update=True,
    )
    if row.status == "cancelled":
        return serialize_closure(row)
    cancellation_time = now or datetime.now(UTC)
    if row.status not in ACTIVE_CLOSURE_STATUSES or cancellation_time >= _as_utc(row.recovery_until):
        raise OrganizationClosureError(
            "The recovery window has ended, so this closure cannot be reopened here.",
            reason_code="closure_recovery_window_ended",
            status_code=409,
        )
    organization = _organization(db, tenant_id=tenant_id, organization_id=organization_id)
    restored = _restore_workspace(db, row=row)
    organization.status = "active"
    organization.updated_at = cancellation_time
    row.status = "cancelled"
    row.cancelled_at = cancellation_time
    row.updated_at = cancellation_time
    counts = dict(row.action_counts or {})
    counts["connections_restored"] = restored["connections_restored"]
    counts["report_schedules_restored"] = restored["report_schedules_restored"]
    counts["wordpress_connections_restored"] = restored["wordpress_connections_restored"]
    row.action_counts = counts
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.organization_closure.cancelled",
        payload={
            "organization_id": organization_id,
            "closure_request_id": row.id,
            "restored_counts": restored,
            "non_restored_security_actions": ["revoked share links", "cancelled queued jobs"],
        },
    )
    db.flush()
    return serialize_closure(row)


def list_organization_closures(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> list[dict[str, Any]]:
    rows = db.query(OrganizationClosureRequest).filter(
        OrganizationClosureRequest.tenant_id == tenant_id,
        OrganizationClosureRequest.organization_id == organization_id,
    ).order_by(
        OrganizationClosureRequest.created_at.desc(),
        OrganizationClosureRequest.id.desc(),
    ).limit(25).all()
    return [serialize_closure(row) for row in rows]


def place_organization_legal_hold(
    db: Session,
    *,
    organization_id: str,
    actor_user_id: str,
    hold_reference: str,
    reason_summary: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise OrganizationClosureError(
            "The workspace could not be found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    if _active_hold(db, tenant_id=organization_id, organization_id=organization_id) is not None:
        raise OrganizationClosureError(
            "This workspace already has an active retention hold.",
            reason_code="legal_hold_already_active",
            status_code=409,
        )
    if not hold_reference.strip() or not reason_summary.strip():
        raise OrganizationClosureError(
            "A hold reference and restricted reason are required.",
            reason_code="legal_hold_details_required",
        )
    placed_at = now or datetime.now(UTC)
    hold = OrganizationLegalHold(
        tenant_id=organization_id,
        organization_id=organization_id,
        status="active",
        hold_reference=hold_reference.strip(),
        reason_summary=reason_summary.strip(),
        placed_by_user_id=actor_user_id,
        placed_at=placed_at,
        created_at=placed_at,
        updated_at=placed_at,
    )
    db.add(hold)
    closure = _current_closure(db, tenant_id=organization_id, organization_id=organization_id)
    if closure is not None:
        closure.hold_status = "active"
        if placed_at >= _as_utc(closure.recovery_until):
            closure.status = "on_hold"
        closure.updated_at = placed_at
    write_audit_log(
        db,
        tenant_id=organization_id,
        actor_user_id=actor_user_id,
        event_type="governance.legal_hold.placed",
        payload={"organization_id": organization_id, "legal_hold_id": hold.id},
    )
    db.flush()
    return _serialize_hold(hold)


def release_organization_legal_hold(
    db: Session,
    *,
    legal_hold_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    hold = db.query(OrganizationLegalHold).filter(
        OrganizationLegalHold.id == legal_hold_id,
    ).with_for_update().first()
    if hold is None:
        raise OrganizationClosureError(
            "The retention hold could not be found.",
            reason_code="legal_hold_not_found",
            status_code=404,
        )
    if hold.status == "released":
        return _serialize_hold(hold)
    released_at = now or datetime.now(UTC)
    hold.status = "released"
    hold.released_by_user_id = actor_user_id
    hold.released_at = released_at
    hold.updated_at = released_at
    closure = _current_closure(
        db,
        tenant_id=hold.tenant_id,
        organization_id=hold.organization_id,
    )
    if closure is not None:
        closure.hold_status = "clear"
        if closure.status == "on_hold":
            closure.status = "recovery_window"
        closure.updated_at = released_at
    write_audit_log(
        db,
        tenant_id=hold.tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.legal_hold.released",
        payload={"organization_id": hold.organization_id, "legal_hold_id": hold.id},
    )
    db.flush()
    return _serialize_hold(hold)


def finalize_due_organization_closures(
    db: Session,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff = now or datetime.now(UTC)
    rows = db.query(OrganizationClosureRequest).filter(
        OrganizationClosureRequest.status.in_(list(ACTIVE_CLOSURE_STATUSES)),
        OrganizationClosureRequest.recovery_until <= cutoff,
    ).order_by(OrganizationClosureRequest.recovery_until.asc()).all()
    finalized = 0
    held = 0
    for row in rows:
        hold = _active_hold(
            db,
            tenant_id=row.tenant_id,
            organization_id=row.organization_id,
        )
        if hold is not None:
            row.status = "on_hold"
            row.hold_status = "active"
            row.updated_at = cutoff
            held += 1
            continue
        _finalize_workspace_closure(db, row=row, now=cutoff)
        finalized += 1
    db.flush()
    return {"closures_finalized": finalized, "closures_held": held}


def serialize_closure(row: OrganizationClosureRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "hold_status": row.hold_status,
        "action_counts": row.action_counts or {},
        "requested_at": row.requested_at.isoformat(),
        "recovery_until": row.recovery_until.isoformat(),
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "deletion_ready_at": row.deletion_ready_at.isoformat() if row.deletion_ready_at else None,
        "can_cancel": row.status in ACTIVE_CLOSURE_STATUSES
        and datetime.now(UTC) < _as_utc(row.recovery_until),
        "primary_data_deleted": False,
    }


def _pause_workspace(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    now: datetime,
) -> dict[str, Any]:
    connections = db.query(DataConnection).filter(
        DataConnection.organization_id == organization_id,
    ).all()
    schedules = db.query(ReportSchedule).filter(
        ReportSchedule.organization_id == organization_id,
    ).all()
    wordpress_connections = db.query(WordPressSiteConnection).filter(
        WordPressSiteConnection.organization_id == organization_id,
    ).all()
    restore_snapshot = {
        "connections": [
            {
                "id": item.id,
                "status": item.status,
                "next_sync_at": item.next_sync_at.isoformat() if item.next_sync_at else None,
            }
            for item in connections
        ],
        "report_schedules": [
            {
                "id": item.id,
                "enabled": item.enabled,
                "next_run_at": item.next_run_at.isoformat(),
            }
            for item in schedules
        ],
        "wordpress_connections": [
            {"id": item.id, "status": item.status}
            for item in wordpress_connections
        ],
    }
    for item in connections:
        if item.status != "disconnected":
            item.status = "paused_closure"
            item.next_sync_at = None
            item.updated_at = now
    for item in schedules:
        item.enabled = False
    for item in wordpress_connections:
        if item.status != "disconnected":
            item.status = "disconnected"
            item.disconnected_at = now
            item.updated_at = now
    queued_jobs = db.query(PlatformJob).filter(
        PlatformJob.tenant_id == tenant_id,
        PlatformJob.status.in_(["queued", "retrying"]),
    ).all()
    for job in queued_jobs:
        job.status = "cancelled"
        job.result = {"reason_code": "organization_closure_requested"}
        job.finished_at = now
        job.locked_at = None
        job.lease_expires_at = None
        job.locked_by = None
    share_links = db.query(ReportShareLink).filter(
        ReportShareLink.organization_id == organization_id,
        ReportShareLink.revoked_at.is_(None),
    ).all()
    for link in share_links:
        link.revoked_at = now
    return {
        "restore_snapshot": restore_snapshot,
        "action_counts": {
            "connections_paused": sum(1 for item in connections if item.status == "paused_closure"),
            "report_schedules_disabled": sum(1 for item in schedules if not item.enabled),
            "wordpress_connections_paused": sum(
                1 for item in wordpress_connections if item.status == "disconnected"
            ),
            "queued_jobs_cancelled": len(queued_jobs),
            "share_links_revoked": len(share_links),
        },
    }


def _restore_workspace(db: Session, *, row: OrganizationClosureRequest) -> dict[str, int]:
    snapshot = row.operational_snapshot or {}
    connections_restored = 0
    for saved in snapshot.get("connections", []):
        item = db.get(DataConnection, saved.get("id"))
        if item is None or item.organization_id != row.organization_id or item.status != "paused_closure":
            continue
        item.status = str(saved.get("status") or "connected")
        item.next_sync_at = _parse_datetime(saved.get("next_sync_at"))
        item.updated_at = datetime.now(UTC)
        connections_restored += 1
    schedules_restored = 0
    for saved in snapshot.get("report_schedules", []):
        item = db.get(ReportSchedule, saved.get("id"))
        if item is None or item.organization_id != row.organization_id:
            continue
        item.enabled = bool(saved.get("enabled"))
        saved_next_run = _parse_datetime(saved.get("next_run_at"))
        if saved_next_run is not None:
            item.next_run_at = saved_next_run
        schedules_restored += int(item.enabled)
    wordpress_restored = 0
    for saved in snapshot.get("wordpress_connections", []):
        item = db.get(WordPressSiteConnection, saved.get("id"))
        if item is None or item.organization_id != row.organization_id:
            continue
        saved_status = str(saved.get("status") or "disconnected")
        if saved_status == "connected" and item.encrypted_secret_blob:
            item.status = "connected"
            item.disconnected_at = None
            item.updated_at = datetime.now(UTC)
            wordpress_restored += 1
    return {
        "connections_restored": connections_restored,
        "report_schedules_restored": schedules_restored,
        "wordpress_connections_restored": wordpress_restored,
    }


def _finalize_workspace_closure(
    db: Session,
    *,
    row: OrganizationClosureRequest,
    now: datetime,
) -> None:
    organization = db.get(Organization, row.organization_id)
    if organization is None:
        row.status = "ready_for_verified_deletion"
        row.closed_at = row.closed_at or now
        row.deletion_ready_at = row.deletion_ready_at or now
        row.updated_at = now
        return

    google_credential = db.query(OrganizationProviderCredential).filter(
        OrganizationProviderCredential.organization_id == row.organization_id,
        OrganizationProviderCredential.provider_name == "google",
    ).first()
    if google_credential is not None and row.requested_by_user_id:
        disconnect_google_provider(
            db,
            tenant_id=row.tenant_id,
            organization_id=row.organization_id,
            actor_user_id=row.requested_by_user_id,
            client_request_id=row.id,
            confirmation="DISCONNECT GOOGLE",
        )

    credentials_deleted = db.query(OrganizationProviderCredential).filter(
        OrganizationProviderCredential.organization_id == row.organization_id,
    ).delete(synchronize_session=False)
    oauth_clients_deleted = db.query(OrganizationOAuthClient).filter(
        OrganizationOAuthClient.organization_id == row.organization_id,
    ).delete(synchronize_session=False)
    connections = db.query(DataConnection).filter(
        DataConnection.organization_id == row.organization_id,
    ).all()
    for item in connections:
        item.status = "disconnected"
        item.next_sync_at = None
        item.sync_cursor = {}
        item.connection_metadata = {}
        item.last_error_code = "organization_closed"
        item.last_error_message = "Updates stopped because the workspace was closed."
        item.updated_at = now
    wordpress_connections = db.query(WordPressSiteConnection).filter(
        WordPressSiteConnection.organization_id == row.organization_id,
    ).all()
    for item in wordpress_connections:
        item.status = "disconnected"
        item.encrypted_secret_blob = None
        item.key_reference = None
        item.key_version = None
        item.pairing_code_hash = None
        item.pairing_expires_at = None
        item.disconnected_at = now
        item.updated_at = now
    sessions = db.query(AuthSession).filter(
        AuthSession.organization_id == row.organization_id,
        AuthSession.status == "active",
    ).all()
    for session in sessions:
        session.status = "revoked"
        session.revoked_at = now
    schedules = db.query(ReportSchedule).filter(
        ReportSchedule.organization_id == row.organization_id,
    ).all()
    for schedule in schedules:
        schedule.enabled = False
    share_links = db.query(ReportShareLink).filter(
        ReportShareLink.organization_id == row.organization_id,
        ReportShareLink.revoked_at.is_(None),
    ).all()
    for link in share_links:
        link.revoked_at = now
    queued_jobs = db.query(PlatformJob).filter(
        PlatformJob.tenant_id == row.tenant_id,
        PlatformJob.status.in_(["queued", "retrying"]),
    ).all()
    for job in queued_jobs:
        job.status = "cancelled"
        job.result = {"reason_code": "organization_closed"}
        job.finished_at = now

    organization.status = "closed"
    organization.updated_at = now
    row.status = "ready_for_verified_deletion"
    row.hold_status = "clear"
    row.closed_at = now
    row.deletion_ready_at = now
    row.updated_at = now
    counts = dict(row.action_counts or {})
    counts.update(
        {
            "credentials_deleted": credentials_deleted,
            "oauth_clients_deleted": oauth_clients_deleted,
            "wordpress_secrets_deleted": len(wordpress_connections),
            "sessions_revoked": len(sessions),
        }
    )
    row.action_counts = counts
    tombstone = db.query(OrganizationDeletionTombstone).filter(
        OrganizationDeletionTombstone.organization_id == row.organization_id,
    ).first()
    if tombstone is None:
        tombstone = OrganizationDeletionTombstone(
            tenant_id=row.tenant_id,
            organization_id=row.organization_id,
            closure_request_id=row.id,
            state="pending_primary_erasure",
            primary_store_status="retained_pending_verification",
            backup_reapply_required=True,
            delete_not_before=now,
            created_at=now,
            updated_at=now,
        )
        db.add(tombstone)
    else:
        tombstone.closure_request_id = row.id
        tombstone.state = "pending_primary_erasure"
        tombstone.primary_store_status = "retained_pending_verification"
        tombstone.backup_reapply_required = True
        tombstone.delete_not_before = now
        tombstone.updated_at = now
    write_audit_log(
        db,
        tenant_id=row.tenant_id,
        actor_user_id=row.requested_by_user_id,
        event_type="governance.organization_closure.ready_for_verified_deletion",
        payload={
            "organization_id": row.organization_id,
            "closure_request_id": row.id,
            "tombstone_state": "pending_primary_erasure",
            "primary_store_deleted": False,
            "backup_reapply_required": True,
            "action_counts": counts,
        },
    )


def _organization(db: Session, *, tenant_id: str, organization_id: str) -> Organization:
    row = db.query(Organization).filter(Organization.id == organization_id).first()
    if row is None or tenant_id != organization_id:
        raise OrganizationClosureError(
            "This workspace could not be found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    return row


def _current_closure(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> OrganizationClosureRequest | None:
    return db.query(OrganizationClosureRequest).filter(
        OrganizationClosureRequest.tenant_id == tenant_id,
        OrganizationClosureRequest.organization_id == organization_id,
        OrganizationClosureRequest.status.in_(
            ["recovery_window", "on_hold", "ready_for_verified_deletion"]
        ),
    ).order_by(OrganizationClosureRequest.created_at.desc()).first()


def _closure_row(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    closure_request_id: str,
    for_update: bool = False,
) -> OrganizationClosureRequest:
    query = db.query(OrganizationClosureRequest).filter(
        OrganizationClosureRequest.id == closure_request_id,
        OrganizationClosureRequest.tenant_id == tenant_id,
        OrganizationClosureRequest.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise OrganizationClosureError(
            "This closure request could not be found.",
            reason_code="closure_request_not_found",
            status_code=404,
        )
    return row


def _active_hold(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> OrganizationLegalHold | None:
    return db.query(OrganizationLegalHold).filter(
        OrganizationLegalHold.tenant_id == tenant_id,
        OrganizationLegalHold.organization_id == organization_id,
        OrganizationLegalHold.status == "active",
    ).order_by(OrganizationLegalHold.created_at.desc()).first()


def _serialize_hold(row: OrganizationLegalHold) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "status": row.status,
        "placed_at": row.placed_at.isoformat(),
        "released_at": row.released_at.isoformat() if row.released_at else None,
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
