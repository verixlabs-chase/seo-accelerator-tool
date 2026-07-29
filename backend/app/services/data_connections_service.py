from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credentials,
)


GOOGLE_SEARCH_CONSOLE_PROVIDER = "google_search_console"
CONNECTION_STATUS_CONNECTED = "connected"
CONNECTION_STATUS_SYNCING = "syncing"
CONNECTION_STATUS_CURRENT = "current"
CONNECTION_STATUS_STALE = "stale"
CONNECTION_STATUS_FAILED = "failed"
CONNECTION_STATUS_RECONNECT_REQUIRED = "reconnect_required"
CONNECTION_STATUS_DISCONNECTED = "disconnected"

_AUTH_REASON_CODES = {
    "org_oauth_credential_required",
    "oauth_refresh_failed",
    "oauth_refresh_token_required",
}


class DataConnectionError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def google_oauth_connection_summary(db: Session, organization_id: str) -> dict[str, Any]:
    row = (
        db.query(OrganizationProviderCredential)
        .filter(
            OrganizationProviderCredential.organization_id == organization_id,
            OrganizationProviderCredential.provider_name == "google",
            OrganizationProviderCredential.auth_mode == "oauth2",
        )
        .first()
    )
    return {
        "connected": row is not None,
        "provider_name": "google",
        "updated_at": row.updated_at.isoformat() if row is not None and row.updated_at else None,
    }


def list_connections(db: Session, organization_id: str) -> list[dict[str, Any]]:
    rows = (
        db.query(DataConnection, Campaign, BusinessLocation)
        .join(Campaign, Campaign.id == DataConnection.campaign_id)
        .join(BusinessLocation, BusinessLocation.id == DataConnection.business_location_id)
        .filter(DataConnection.organization_id == organization_id)
        .order_by(BusinessLocation.name.asc(), Campaign.name.asc(), DataConnection.created_at.asc())
        .all()
    )
    now = datetime.now(UTC)
    return [
        serialize_connection(connection, campaign=campaign, location=location, now=now)
        for connection, campaign, location in rows
    ]


def serialize_connection(
    connection: DataConnection,
    *,
    campaign: Campaign | None = None,
    location: BusinessLocation | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    status = effective_connection_status(connection, now=resolved_now)
    return {
        "id": connection.id,
        "tenant_id": connection.tenant_id,
        "organization_id": connection.organization_id,
        "provider_name": connection.provider_name,
        "business_location_id": connection.business_location_id,
        "business_location_name": location.name if location is not None else None,
        "campaign_id": connection.campaign_id,
        "campaign_name": campaign.name if campaign is not None else None,
        "campaign_domain": campaign.domain if campaign is not None else None,
        "external_resource_id": connection.external_resource_id,
        "external_resource_name": connection.external_resource_name,
        "resource_scope": connection.resource_scope,
        "status": status,
        "stored_status": connection.status,
        "last_sync_started_at": _iso(connection.last_sync_started_at),
        "last_sync_completed_at": _iso(connection.last_sync_completed_at),
        "last_success_at": _iso(connection.last_success_at),
        "next_sync_at": _iso(connection.next_sync_at),
        "last_error_code": connection.last_error_code,
        "last_error_message": connection.last_error_message,
        "sync_cursor": dict(connection.sync_cursor or {}),
        "source_truth": (
            "Website-property data from Google Search Console. If multiple locations share "
            "one property, the metrics describe that shared website property."
        ),
        "updated_at": _iso(connection.updated_at),
    }


def get_search_console_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    days: int = 28,
) -> dict[str, Any]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise DataConnectionError(
            "Campaign not found in this organization.",
            reason_code="campaign_not_found",
            status_code=404,
        )

    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == GOOGLE_SEARCH_CONSOLE_PROVIDER,
        )
        .first()
    )
    if connection is None:
        return {
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "provider_name": GOOGLE_SEARCH_CONSOLE_PROVIDER,
            "data_status": "not_connected",
            "connection": None,
            "date_from": None,
            "date_to": None,
            "days_requested": days,
            "data_days": 0,
            "summary": None,
            "comparison": None,
            "points": [],
        }

    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == connection.business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        .first()
    )
    rows = list(
        reversed(
            db.query(SearchConsoleDailyMetric)
            .filter(
                SearchConsoleDailyMetric.organization_id == organization_id,
                SearchConsoleDailyMetric.campaign_id == campaign_id,
            )
            .order_by(SearchConsoleDailyMetric.metric_date.desc())
            .limit(days)
            .all()
        )
    )
    summary = _summarize_search_console_rows(rows) if rows else None
    comparison = None
    comparison_period_days = len(rows) // 2
    if comparison_period_days > 0:
        previous_rows = rows[-comparison_period_days * 2 : -comparison_period_days]
        current_rows = rows[-comparison_period_days:]
        if len(previous_rows) == len(current_rows):
            previous = _summarize_search_console_rows(previous_rows)
            current = _summarize_search_console_rows(current_rows)
            comparison = {
                "period_days": comparison_period_days,
                "clicks_change_percent": _percent_change(
                    current["clicks"],
                    previous["clicks"],
                ),
                "impressions_change_percent": _percent_change(
                    current["impressions"],
                    previous["impressions"],
                ),
                "ctr_change_points": round(
                    current["ctr_percent"] - previous["ctr_percent"],
                    2,
                ),
                "position_improvement": (
                    round(previous["avg_position"] - current["avg_position"], 2)
                    if previous["avg_position"] is not None
                    and current["avg_position"] is not None
                    else None
                ),
            }

    return {
        "organization_id": organization_id,
        "campaign_id": campaign_id,
        "provider_name": GOOGLE_SEARCH_CONSOLE_PROVIDER,
        "data_status": "ready" if rows else "no_data",
        "connection": serialize_connection(
            connection,
            campaign=campaign,
            location=location,
        ),
        "date_from": rows[0].metric_date.isoformat() if rows else None,
        "date_to": rows[-1].metric_date.isoformat() if rows else None,
        "days_requested": days,
        "data_days": len(rows),
        "summary": summary,
        "comparison": comparison,
        "points": [
            {
                "date": row.metric_date.isoformat(),
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr_percent": (
                    round((row.clicks / row.impressions) * 100, 2)
                    if row.impressions > 0
                    else 0.0
                ),
                "avg_position": (
                    round(row.avg_position, 2)
                    if row.avg_position is not None
                    else None
                ),
            }
            for row in rows
        ],
    }


def _summarize_search_console_rows(
    rows: list[SearchConsoleDailyMetric],
) -> dict[str, int | float | None]:
    clicks = sum(row.clicks for row in rows)
    impressions = sum(row.impressions for row in rows)
    position_rows = [
        row
        for row in rows
        if row.avg_position is not None and row.impressions > 0
    ]
    position_impressions = sum(row.impressions for row in position_rows)
    avg_position = (
        sum(float(row.avg_position) * row.impressions for row in position_rows)
        / position_impressions
        if position_impressions > 0
        else None
    )
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr_percent": round((clicks / impressions) * 100, 2) if impressions > 0 else 0.0,
        "avg_position": round(avg_position, 2) if avg_position is not None else None,
    }


def _percent_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def effective_connection_status(connection: DataConnection, *, now: datetime | None = None) -> str:
    if connection.status in {
        CONNECTION_STATUS_SYNCING,
        CONNECTION_STATUS_FAILED,
        CONNECTION_STATUS_RECONNECT_REQUIRED,
        CONNECTION_STATUS_DISCONNECTED,
    }:
        return connection.status
    if connection.last_success_at is None:
        return CONNECTION_STATUS_CONNECTED
    resolved_now = now or datetime.now(UTC)
    last_success = _as_aware(connection.last_success_at)
    stale_after = timedelta(days=max(1, int(get_settings().traffic_fact_max_staleness_days)))
    if resolved_now - last_success > stale_after:
        return CONNECTION_STATUS_STALE
    return CONNECTION_STATUS_CURRENT


def discover_search_console_resources(db: Session, organization_id: str) -> list[dict[str, str]]:
    try:
        credentials = resolve_provider_credentials(
            db,
            organization_id,
            "google",
            required_credential_mode="byo_required",
            require_org_oauth=True,
        )
    except ProviderCredentialConfigurationError as exc:
        raise DataConnectionError(
            str(exc),
            reason_code=exc.reason_code,
            status_code=exc.status_code,
        ) from exc

    access_token = str(credentials.get("access_token", "")).strip()
    if not access_token:
        raise DataConnectionError(
            "Reconnect Google Search Console to continue.",
            reason_code="org_oauth_credential_required",
            status_code=409,
        )
    expected_scope = get_settings().google_oauth_scope_gsc.strip()
    granted_scopes = str(credentials.get("scope", "")).split()
    if expected_scope and granted_scopes and expected_scope not in granted_scopes:
        raise DataConnectionError(
            "Reconnect Google and approve Search Console access.",
            reason_code="oauth_scope_missing",
            status_code=409,
        )

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://www.googleapis.com/webmasters/v3/sites",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=float(get_settings().google_oauth_http_timeout_seconds),
            )
    except httpx.TimeoutException as exc:
        raise DataConnectionError(
            "Google Search Console took too long to respond.",
            reason_code="provider_timeout",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise DataConnectionError(
            "Google Search Console could not be reached.",
            reason_code="provider_unavailable",
            status_code=502,
        ) from exc

    if response.status_code in {401, 403}:
        raise DataConnectionError(
            "Google Search Console access needs to be reconnected.",
            reason_code="oauth_reconnect_required",
            status_code=409,
        )
    if response.status_code >= 400:
        raise DataConnectionError(
            "Google Search Console websites could not be loaded.",
            reason_code="provider_request_failed",
            status_code=502,
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise DataConnectionError(
            "Google Search Console returned an invalid response.",
            reason_code="provider_response_invalid",
            status_code=502,
        ) from exc

    entries = payload.get("siteEntry", []) if isinstance(payload, dict) else []
    resources: list[dict[str, str]] = []
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            site_url = str(entry.get("siteUrl", "")).strip()
            if not site_url:
                continue
            resources.append(
                {
                    "id": site_url,
                    "name": _resource_display_name(site_url),
                    "permission_level": str(entry.get("permissionLevel", "unknown")),
                    "resource_scope": _resource_scope(site_url),
                }
            )
    return sorted(resources, key=lambda item: item["name"].lower())


def upsert_search_console_mapping(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    external_resource_id: str,
    external_resource_name: str | None,
    actor_user_id: str,
) -> DataConnection:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise DataConnectionError(
            "Campaign not found in this organization.",
            reason_code="campaign_not_found",
            status_code=404,
        )
    if not campaign.business_location_id:
        raise DataConnectionError(
            "Assign this website to a business location before connecting Search Console.",
            reason_code="business_location_required",
            status_code=409,
        )
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == campaign.business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        .first()
    )
    if location is None:
        raise DataConnectionError(
            "The campaign location could not be verified.",
            reason_code="business_location_not_found",
            status_code=404,
        )

    resource_id = external_resource_id.strip()
    _validate_search_console_resource(resource_id)
    resource_name = (external_resource_name or "").strip() or _resource_display_name(resource_id)
    existing = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == GOOGLE_SEARCH_CONSOLE_PROVIDER,
            DataConnection.campaign_id == campaign.id,
        )
        .first()
    )
    now = datetime.now(UTC)
    if existing is None:
        existing = DataConnection(
            tenant_id=campaign.tenant_id,
            organization_id=organization_id,
            business_location_id=location.id,
            campaign_id=campaign.id,
            provider_name=GOOGLE_SEARCH_CONSOLE_PROVIDER,
            external_resource_id=resource_id,
            external_resource_name=resource_name,
            resource_scope=_resource_scope(resource_id),
            status=CONNECTION_STATUS_CONNECTED,
            next_sync_at=now,
            sync_cursor={},
            connection_metadata={"permission_verified": True},
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        if (
            existing.external_resource_id != resource_id
            and existing.last_success_at is not None
        ):
            raise DataConnectionError(
                "This location already has synchronized Search Console history. "
                "Changing its website property requires a separate data-reset workflow.",
                reason_code="mapping_change_requires_reset",
                status_code=409,
            )
        existing.tenant_id = campaign.tenant_id
        existing.business_location_id = location.id
        existing.external_resource_id = resource_id
        existing.external_resource_name = resource_name
        existing.resource_scope = _resource_scope(resource_id)
        existing.status = CONNECTION_STATUS_CONNECTED
        existing.next_sync_at = now
        existing.last_error_code = None
        existing.last_error_message = None
        existing.updated_at = now
    db.commit()
    db.refresh(existing)
    return existing


def mark_sync_started(db: Session, connection: DataConnection, *, now: datetime | None = None) -> None:
    resolved_now = now or datetime.now(UTC)
    connection.status = CONNECTION_STATUS_SYNCING
    connection.last_sync_started_at = resolved_now
    connection.last_error_code = None
    connection.last_error_message = None
    connection.updated_at = resolved_now
    db.commit()
    db.refresh(connection)


def mark_sync_succeeded(
    db: Session,
    connection: DataConnection,
    *,
    metric_end_date: str,
    now: datetime | None = None,
) -> None:
    resolved_now = now or datetime.now(UTC)
    connection.status = CONNECTION_STATUS_CURRENT
    connection.last_sync_completed_at = resolved_now
    connection.last_success_at = resolved_now
    connection.next_sync_at = resolved_now + timedelta(
        hours=max(1, int(get_settings().data_connection_sync_interval_hours))
    )
    connection.last_error_code = None
    connection.last_error_message = None
    connection.sync_cursor = {
        **dict(connection.sync_cursor or {}),
        "last_metric_date": metric_end_date,
    }
    connection.updated_at = resolved_now
    db.flush()


def mark_sync_failed(
    db: Session,
    *,
    connection_id: str,
    error: Exception,
    now: datetime | None = None,
) -> None:
    connection = db.get(DataConnection, connection_id)
    if connection is None:
        return
    reason_code = str(getattr(error, "reason_code", "") or "sync_failed")
    connection.status = (
        CONNECTION_STATUS_RECONNECT_REQUIRED
        if reason_code in _AUTH_REASON_CODES or "oauth" in reason_code or "auth" in reason_code
        else CONNECTION_STATUS_FAILED
    )
    connection.last_sync_completed_at = now or datetime.now(UTC)
    connection.last_error_code = reason_code[:120]
    connection.last_error_message = str(error)[:4000]
    connection.updated_at = now or datetime.now(UTC)
    db.flush()


def _validate_search_console_resource(resource_id: str) -> None:
    if resource_id.startswith("sc-domain:") and resource_id.removeprefix("sc-domain:").strip():
        return
    parsed = urlparse(resource_id)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return
    raise DataConnectionError(
        "Choose a valid Search Console website property.",
        reason_code="invalid_external_resource",
        status_code=400,
    )


def _resource_scope(site_url: str) -> str:
    return "domain_property" if site_url.startswith("sc-domain:") else "url_prefix_property"


def _resource_display_name(site_url: str) -> str:
    if site_url.startswith("sc-domain:"):
        return site_url.removeprefix("sc-domain:")
    parsed = urlparse(site_url)
    return parsed.netloc + parsed.path if parsed.netloc else site_url


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return _as_aware(value).isoformat() if value is not None else None
