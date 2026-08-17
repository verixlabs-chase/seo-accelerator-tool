from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.data_connection import DataConnection
from app.models.data_governance import ProviderDisconnectRequest
from app.models.google_business_profile import (
    GoogleBusinessProfileDailyMetric,
    GoogleBusinessProfileSearchKeyword,
    GoogleBusinessProfileSnapshot,
)
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.platform_job import PlatformJob
from app.models.reputation import ReputationReview
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_analytics import (
    AnalyticsLandingPageDailyMetric,
    AnalyticsTrafficSourceDailyMetric,
    WebsiteFormEvent,
)
from app.services.audit_service import write_audit_log
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    get_organization_provider_credentials,
)


GOOGLE_PROVIDER = "google"
GOOGLE_CONNECTION_PROVIDERS = (
    "google_search_console",
    "google_business_profile",
    "google_analytics",
)
GOOGLE_SYNC_JOB_TYPES = (
    "data_connections.search_console_sync",
    "data_connections.google_business_profile_sync",
    "data_connections.google_analytics_sync",
)
GOOGLE_CONFIRMATION = "DISCONNECT GOOGLE"


class ProviderDisconnectError(ValueError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def preview_google_disconnect(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> dict[str, Any]:
    connections = _google_connections(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
    )
    credential_present = (
        db.query(OrganizationProviderCredential.id)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == GOOGLE_PROVIDER,
        )
        .first()
        is not None
    )
    active_connections = [row for row in connections if row.status != "disconnected"]
    return {
        "provider_name": GOOGLE_PROVIDER,
        "connected": credential_present,
        "credential_present": credential_present,
        "connections_total": len(connections),
        "active_connections": len(active_connections),
        "affected_locations": len({row.business_location_id for row in active_connections}),
        "preserved_record_counts": _preserved_record_counts(
            db,
            organization_id=organization_id,
        ),
        "what_stops": [
            "Google Search Console updates",
            "Google business listing and review updates",
            "Google Analytics updates",
            "Private website inquiry collection tied to the Google Analytics connection",
        ],
        "what_stays": [
            "Saved locations and Google property mappings",
            "Previously collected measurements and reviews",
            "Reports, recommendations, and completed work based on saved evidence",
        ],
        "confirmation_text": GOOGLE_CONFIRMATION,
    }


def disconnect_google_provider(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    actor_user_id: str,
    client_request_id: str,
    confirmation: str,
) -> dict[str, Any]:
    if confirmation.strip() != GOOGLE_CONFIRMATION:
        raise ProviderDisconnectError(
            f'Type "{GOOGLE_CONFIRMATION}" to confirm this change.',
            reason_code="provider_disconnect_confirmation_required",
            status_code=400,
        )

    existing = (
        db.query(ProviderDisconnectRequest)
        .filter(
            ProviderDisconnectRequest.tenant_id == tenant_id,
            ProviderDisconnectRequest.organization_id == organization_id,
            ProviderDisconnectRequest.provider_name == GOOGLE_PROVIDER,
            ProviderDisconnectRequest.client_request_id == client_request_id,
        )
        .first()
    )
    if existing is not None:
        return serialize_provider_disconnect(existing)

    now = datetime.now(UTC)
    record = ProviderDisconnectRequest(
        tenant_id=tenant_id,
        organization_id=organization_id,
        provider_name=GOOGLE_PROVIDER,
        client_request_id=client_request_id,
        requested_by_user_id=actor_user_id,
        status="processing",
        credential_deleted=False,
        external_revocation_status="pending",
        external_revocation_code=None,
        connections_disconnected=0,
        queued_jobs_cancelled=0,
        preserved_record_counts={},
        requested_at=now,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()

    credential = (
        db.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == GOOGLE_PROVIDER,
        )
        .with_for_update()
        .first()
    )
    revocation_status = "not_needed"
    revocation_code: str | None = None
    credential_deleted = False
    if credential is not None:
        token = ""
        try:
            credentials = get_organization_provider_credentials(
                db,
                organization_id,
                GOOGLE_PROVIDER,
            )
            token = str(
                credentials.get("refresh_token") or credentials.get("access_token") or ""
            ).strip()
        except ProviderCredentialConfigurationError:
            revocation_status = "not_confirmed"
            revocation_code = "credential_unreadable"

        if token:
            revocation_status, revocation_code = _revoke_google_grant(token)
        elif revocation_status != "not_confirmed":
            revocation_status = "not_confirmed"
            revocation_code = "token_unavailable"

        db.delete(credential)
        credential_deleted = True

    connections = _google_connections(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        for_update=True,
    )
    disconnected_count = 0
    connection_ids: list[str] = []
    for connection in connections:
        connection_ids.append(connection.id)
        if connection.status != "disconnected":
            disconnected_count += 1
        connection.status = "disconnected"
        connection.next_sync_at = None
        connection.last_error_code = "provider_disconnected_by_owner"
        connection.last_error_message = None
        connection.sync_cursor = {}
        connection.connection_metadata = {}
        connection.updated_at = now

    cancelled_jobs = _cancel_queued_google_jobs(
        db,
        connection_ids=connection_ids,
        now=now,
    )
    preserved_counts = _preserved_record_counts(db, organization_id=organization_id)
    record.status = (
        "completed"
        if revocation_status in {"confirmed", "not_needed"}
        else "completed_external_action_required"
    )
    record.credential_deleted = credential_deleted
    record.external_revocation_status = revocation_status
    record.external_revocation_code = revocation_code
    record.connections_disconnected = disconnected_count
    record.queued_jobs_cancelled = cancelled_jobs
    record.preserved_record_counts = preserved_counts
    record.completed_at = now
    record.updated_at = now

    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="governance.provider_disconnected",
        payload={
            "organization_id": organization_id,
            "provider_name": GOOGLE_PROVIDER,
            "disconnect_request_id": record.id,
            "status": record.status,
            "credential_deleted": credential_deleted,
            "external_revocation_status": revocation_status,
            "external_revocation_code": revocation_code,
            "connections_disconnected": disconnected_count,
            "queued_jobs_cancelled": cancelled_jobs,
            "preserved_record_counts": preserved_counts,
        },
    )
    db.flush()
    return serialize_provider_disconnect(record)


def list_provider_disconnects(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
) -> list[dict[str, Any]]:
    rows = (
        db.query(ProviderDisconnectRequest)
        .filter(
            ProviderDisconnectRequest.tenant_id == tenant_id,
            ProviderDisconnectRequest.organization_id == organization_id,
        )
        .order_by(
            ProviderDisconnectRequest.created_at.desc(),
            ProviderDisconnectRequest.id.desc(),
        )
        .limit(25)
        .all()
    )
    return [serialize_provider_disconnect(row) for row in rows]


def serialize_provider_disconnect(row: ProviderDisconnectRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "provider_name": row.provider_name,
        "status": row.status,
        "credential_deleted": row.credential_deleted,
        "external_revocation_status": row.external_revocation_status,
        "external_revocation_code": row.external_revocation_code,
        "connections_disconnected": row.connections_disconnected,
        "queued_jobs_cancelled": row.queued_jobs_cancelled,
        "preserved_record_counts": row.preserved_record_counts or {},
        "requested_at": row.requested_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _google_connections(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    for_update: bool = False,
) -> list[DataConnection]:
    query = db.query(DataConnection).filter(
        DataConnection.tenant_id == tenant_id,
        DataConnection.organization_id == organization_id,
        DataConnection.provider_name.in_(GOOGLE_CONNECTION_PROVIDERS),
    )
    if for_update:
        query = query.with_for_update()
    return query.order_by(DataConnection.created_at.asc(), DataConnection.id.asc()).all()


def _preserved_record_counts(db: Session, *, organization_id: str) -> dict[str, int]:
    def count(model: Any, *filters: Any) -> int:
        return int(db.query(func.count(model.id)).filter(*filters).scalar() or 0)

    return {
        "search_console_measurements": count(
            SearchConsoleDailyMetric,
            SearchConsoleDailyMetric.organization_id == organization_id,
        ),
        "business_profile_snapshots": count(
            GoogleBusinessProfileSnapshot,
            GoogleBusinessProfileSnapshot.organization_id == organization_id,
        ),
        "business_profile_measurements": count(
            GoogleBusinessProfileDailyMetric,
            GoogleBusinessProfileDailyMetric.organization_id == organization_id,
        ),
        "business_profile_search_terms": count(
            GoogleBusinessProfileSearchKeyword,
            GoogleBusinessProfileSearchKeyword.organization_id == organization_id,
        ),
        "owned_reviews": count(
            ReputationReview,
            ReputationReview.organization_id == organization_id,
            ReputationReview.source_type == "owned_profile",
        ),
        "analytics_measurements": count(
            AnalyticsDailyMetric,
            AnalyticsDailyMetric.organization_id == organization_id,
        ),
        "analytics_landing_pages": count(
            AnalyticsLandingPageDailyMetric,
            AnalyticsLandingPageDailyMetric.organization_id == organization_id,
        ),
        "analytics_traffic_sources": count(
            AnalyticsTrafficSourceDailyMetric,
            AnalyticsTrafficSourceDailyMetric.organization_id == organization_id,
        ),
        "website_inquiry_events": count(
            WebsiteFormEvent,
            WebsiteFormEvent.organization_id == organization_id,
        ),
    }


def _cancel_queued_google_jobs(
    db: Session,
    *,
    connection_ids: list[str],
    now: datetime,
) -> int:
    if not connection_ids:
        return 0
    jobs = (
        db.query(PlatformJob)
        .filter(
            PlatformJob.entity_id.in_(connection_ids),
            PlatformJob.job_type.in_(GOOGLE_SYNC_JOB_TYPES),
            PlatformJob.status == "queued",
        )
        .with_for_update()
        .all()
    )
    for job in jobs:
        job.status = "cancelled"
        job.result = {
            "status": "cancelled",
            "reason_code": "provider_disconnected_by_owner",
        }
        job.error = None
        job.finished_at = now
        job.locked_at = None
        job.lease_expires_at = None
        job.locked_by = None
    return len(jobs)


def _revoke_google_grant(token: str) -> tuple[str, str | None]:
    settings = get_settings()
    try:
        response = httpx.post(
            settings.google_oauth_revoke_endpoint,
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=settings.google_oauth_http_timeout_seconds,
        )
    except httpx.HTTPError:
        return "not_confirmed", "google_revoke_unreachable"
    if 200 <= response.status_code < 300:
        return "confirmed", None
    return "not_confirmed", f"google_revoke_http_{response.status_code}"
