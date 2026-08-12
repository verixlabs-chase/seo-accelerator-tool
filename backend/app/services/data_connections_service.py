from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.google_business_profile import GoogleBusinessProfileDailyMetric
from app.models.organization_provider_credential import OrganizationProviderCredential
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_analytics import (
    AnalyticsLandingPageDailyMetric,
    AnalyticsTrafficSourceDailyMetric,
    WebsiteFormEvent,
)
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    get_organization_provider_credentials,
    resolve_provider_credentials,
)


GOOGLE_SEARCH_CONSOLE_PROVIDER = "google_search_console"
GOOGLE_ANALYTICS_PROVIDER = "google_analytics"
MAX_SEARCH_CONSOLE_RANGE_DAYS = 480
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
    scopes: list[str] = []
    if row is not None:
        try:
            credentials = get_organization_provider_credentials(db, organization_id, "google")
            scopes = sorted(set(str(credentials.get("scope") or "").split()))
        except ProviderCredentialConfigurationError:
            scopes = []
    settings = get_settings()
    return {
        "connected": row is not None,
        "provider_name": "google",
        "approved_access": {
            "search_console": bool(
                row is not None
                and (not scopes or settings.google_oauth_scope_gsc in scopes)
            ),
            "business_profile": bool(
                row is not None
                and settings.google_oauth_scope_gbp in scopes
            ),
            "website_analytics": bool(
                row is not None
                and settings.google_oauth_scope_analytics in scopes
            ),
        },
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


def get_connection_health(db: Session, organization_id: str) -> dict[str, Any]:
    """Build the owner-facing connection inventory from saved, scoped facts."""

    campaign_rows = (
        db.query(Campaign, BusinessLocation)
        .join(BusinessLocation, BusinessLocation.id == Campaign.business_location_id)
        .filter(
            Campaign.organization_id == organization_id,
            BusinessLocation.organization_id == organization_id,
        )
        .order_by(BusinessLocation.name.asc(), Campaign.name.asc())
        .all()
    )
    connections = (
        db.query(DataConnection)
        .filter(DataConnection.organization_id == organization_id)
        .all()
    )
    connection_by_scope = {
        (row.campaign_id, row.provider_name): row
        for row in connections
    }
    search_console_dates = dict(
        db.query(
            SearchConsoleDailyMetric.campaign_id,
            func.max(SearchConsoleDailyMetric.metric_date),
        )
        .filter(SearchConsoleDailyMetric.organization_id == organization_id)
        .group_by(SearchConsoleDailyMetric.campaign_id)
        .all()
    )
    business_profile_dates = dict(
        db.query(
            GoogleBusinessProfileDailyMetric.campaign_id,
            func.max(GoogleBusinessProfileDailyMetric.metric_date),
        )
        .filter(GoogleBusinessProfileDailyMetric.organization_id == organization_id)
        .group_by(GoogleBusinessProfileDailyMetric.campaign_id)
        .all()
    )
    analytics_dates = dict(
        db.query(
            AnalyticsDailyMetric.campaign_id,
            func.max(AnalyticsDailyMetric.metric_date),
        )
        .filter(AnalyticsDailyMetric.organization_id == organization_id)
        .group_by(AnalyticsDailyMetric.campaign_id)
        .all()
    )
    oauth = google_oauth_connection_summary(db, organization_id)
    approved_access = oauth.get("approved_access") or {}
    now = datetime.now(UTC)
    items: list[dict[str, Any]] = []

    providers: list[dict[str, Any]] = [
        {
            "provider_name": GOOGLE_SEARCH_CONSOLE_PROVIDER,
            "label": "Website search data",
            "mapping_anchor": "website-mappings",
            "features": ["Overview", "Search Rankings", "Search Value", "Reports", "Next Steps"],
            "approved": bool(approved_access.get("search_console")),
            "newest_dates": search_console_dates,
        },
        {
            "provider_name": "google_business_profile",
            "label": "Google business listing",
            "mapping_anchor": "profile-mappings",
            "features": ["Local Search", "Customer reviews", "Reports", "Next Steps"],
            "approved": bool(approved_access.get("business_profile")),
            "newest_dates": business_profile_dates,
        },
    ]
    analytics_is_in_use = bool(approved_access.get("website_analytics")) or any(
        row.provider_name == GOOGLE_ANALYTICS_PROVIDER for row in connections
    )
    if analytics_is_in_use:
        providers.append({
            "provider_name": GOOGLE_ANALYTICS_PROVIDER,
            "label": "Website visits and inquiries",
            "mapping_anchor": "analytics-mappings",
            "features": ["Overview", "Reports", "Next Steps"],
            "approved": bool(approved_access.get("website_analytics")),
            "newest_dates": analytics_dates,
        })

    for campaign, location in campaign_rows:
        for provider in providers:
            connection = connection_by_scope.get((campaign.id, provider["provider_name"]))
            status = (
                effective_connection_status(connection, now=now)
                if connection is not None
                else "not_connected"
            )
            newest_date = provider["newest_dates"].get(campaign.id)
            items.append(
                _serialize_connection_health_item(
                    connection=connection,
                    campaign=campaign,
                    location=location,
                    provider_name=str(provider["provider_name"]),
                    label=str(provider["label"]),
                    status=status,
                    oauth_connected=bool(oauth.get("connected")),
                    approved=bool(provider["approved"]),
                    mapping_anchor=str(provider["mapping_anchor"]),
                    affected_features=list(provider["features"]),
                    newest_usable_data_date=(
                        newest_date.isoformat() if newest_date is not None else None
                    ),
                )
            )

    attention_states = {"failed", "reconnect_required", "stale", "disconnected"}
    setup_states = {"not_connected", "connected"}
    counts = {
        "healthy": sum(item["status"] == "current" for item in items),
        "updating": sum(item["status"] == "syncing" for item in items),
        "needs_attention": sum(item["status"] in attention_states for item in items),
        "needs_setup": sum(item["status"] in setup_states for item in items),
    }
    if counts["needs_attention"]:
        headline = "Some business data needs attention"
        next_step = "Start with the first red or yellow connection below."
    elif counts["needs_setup"]:
        headline = "Finish connecting your business data"
        next_step = "Start with the first connection marked Finish setup."
    elif items:
        headline = "Your connected business data is healthy"
        next_step = "No action is needed right now."
    else:
        headline = "Add a business location to connect its data"
        next_step = "Create the first location, then return here to connect it."

    return {
        "organization_id": organization_id,
        "checked_at": now.isoformat(),
        "summary": {
            "headline": headline,
            "next_step": next_step,
            "locations": len(campaign_rows),
            "sources": len(items),
            **counts,
        },
        "items": sorted(
            items,
            key=lambda item: (
                {"needs_attention": 0, "needs_setup": 1, "updating": 2, "healthy": 3}[
                    item["display_state"]
                ],
                str(item["location_name"]).lower(),
                str(item["label"]).lower(),
            ),
        ),
    }


def _serialize_connection_health_item(
    *,
    connection: DataConnection | None,
    campaign: Campaign,
    location: BusinessLocation,
    provider_name: str,
    label: str,
    status: str,
    oauth_connected: bool,
    approved: bool,
    mapping_anchor: str,
    affected_features: list[str],
    newest_usable_data_date: str | None,
) -> dict[str, Any]:
    action = _connection_recovery_action(
        connection=connection,
        status=status,
        oauth_connected=oauth_connected,
        approved=approved,
        mapping_anchor=mapping_anchor,
    )
    display_state = (
        "healthy"
        if status == "current"
        else "updating"
        if status == "syncing"
        else "needs_attention"
        if status in {"failed", "reconnect_required", "stale", "disconnected"}
        else "needs_setup"
    )
    summary_by_status = {
        "current": "The latest automatic update finished and usable data is available.",
        "syncing": "InsightOS is checking for newer information now.",
        "stale": "The saved information is older than expected.",
        "failed": "The last automatic update did not finish. Previously saved data is still available.",
        "reconnect_required": "Google access expired or was removed.",
        "connected": "This location is matched and ready for its first update.",
        "not_connected": "This location has not been matched to this source yet.",
        "disconnected": "Automatic updates are turned off for this location.",
    }
    current_failure = {
        "failed": "The last update did not finish.",
        "reconnect_required": "Google access needs to be renewed.",
        "stale": "A newer successful update is needed.",
        "disconnected": "Automatic updates are off.",
    }.get(status)
    return {
        "id": connection.id if connection is not None else f"{provider_name}:{campaign.id}",
        "connection_id": connection.id if connection is not None else None,
        "provider_name": provider_name,
        "label": label,
        "status": status,
        "display_state": display_state,
        "summary": summary_by_status.get(status, "Connection status is not available yet."),
        "location_id": location.id,
        "location_name": location.name,
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "last_success_at": _iso(connection.last_success_at) if connection is not None else None,
        "newest_usable_data_date": newest_usable_data_date,
        "current_failure": current_failure,
        "affected_features": affected_features if display_state != "healthy" else [],
        "recovery_action": action,
    }


def _connection_recovery_action(
    *,
    connection: DataConnection | None,
    status: str,
    oauth_connected: bool,
    approved: bool,
    mapping_anchor: str,
) -> dict[str, Any]:
    if status == "current":
        return {"kind": "none", "label": "No action needed", "href": None}
    if status == "syncing":
        return {"kind": "wait", "label": "Update in progress", "href": None}
    if status == "reconnect_required" or not oauth_connected or not approved:
        return {"kind": "reconnect", "label": "Reconnect Google", "href": "/settings"}
    if connection is None:
        return {
            "kind": "map",
            "label": "Match this location",
            "href": f"/settings#{mapping_anchor}",
        }
    if status == "disconnected":
        return {
            "kind": "sync",
            "label": "Turn updates back on",
            "href": None,
            "connection_id": connection.id,
        }
    return {
        "kind": "sync",
        "label": "Try update again" if status == "failed" else "Check for updates",
        "href": None,
        "connection_id": connection.id,
    }


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
        "source_truth": _connection_source_truth(connection.provider_name),
        "website_event_key_configured": bool(
            connection.provider_name == GOOGLE_ANALYTICS_PROVIDER
            and (connection.connection_metadata or {}).get("website_event_token_hash")
        ),
        "website_event_key_created_at": (
            (connection.connection_metadata or {}).get("website_event_token_created_at")
            if connection.provider_name == GOOGLE_ANALYTICS_PROVIDER
            else None
        ),
        "updated_at": _iso(connection.updated_at),
    }


def get_google_analytics_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    days: int = 90,
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
            DataConnection.provider_name == GOOGLE_ANALYTICS_PROVIDER,
        )
        .first()
    )
    if connection is None:
        return {
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "provider_name": GOOGLE_ANALYTICS_PROVIDER,
            "data_status": "not_connected",
            "connection": None,
            "summary": None,
            "points": [],
        }
    latest_date = (
        db.query(func.max(AnalyticsDailyMetric.metric_date))
        .filter(
            AnalyticsDailyMetric.organization_id == organization_id,
            AnalyticsDailyMetric.campaign_id == campaign_id,
        )
        .scalar()
    )
    location = db.get(BusinessLocation, connection.business_location_id)
    latest_website_event_at = _latest_website_form_event_at(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if latest_date is None:
        return {
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "provider_name": GOOGLE_ANALYTICS_PROVIDER,
            "data_status": "no_data",
            "connection": serialize_connection(
                connection,
                campaign=campaign,
                location=location,
            ),
            "summary": None,
            "points": [],
            "top_landing_pages": [],
            "top_sources": [],
            "tracking_health": _website_event_tracking_health(
                connection=connection,
                last_event_at=latest_website_event_at,
                visits=0,
            ),
        }
    normalized_days = max(7, min(int(days), MAX_SEARCH_CONSOLE_RANGE_DAYS))
    start_date = latest_date - timedelta(days=normalized_days - 1)
    rows = (
        db.query(AnalyticsDailyMetric)
        .filter(
            AnalyticsDailyMetric.organization_id == organization_id,
            AnalyticsDailyMetric.campaign_id == campaign_id,
            AnalyticsDailyMetric.metric_date >= start_date,
            AnalyticsDailyMetric.metric_date <= latest_date,
        )
        .order_by(AnalyticsDailyMetric.metric_date.asc())
        .all()
    )
    sessions = sum(int(row.sessions or 0) for row in rows)
    engaged_sessions = sum(int(row.engaged_sessions or 0) for row in rows)
    inquiries = sum(int(row.conversions or 0) for row in rows)
    form_events = (
        db.query(WebsiteFormEvent)
        .filter(
            WebsiteFormEvent.organization_id == organization_id,
            WebsiteFormEvent.campaign_id == campaign_id,
            WebsiteFormEvent.occurred_at >= datetime.combine(start_date, datetime.min.time(), UTC),
            WebsiteFormEvent.occurred_at
            < datetime.combine(latest_date + timedelta(days=1), datetime.min.time(), UTC),
        )
        .order_by(WebsiteFormEvent.occurred_at.asc())
        .all()
    )
    form_events_by_date: dict[date, int] = {}
    for event in form_events:
        event_date = _as_aware(event.occurred_at).date()
        form_events_by_date[event_date] = form_events_by_date.get(event_date, 0) + 1
    landing_rows = (
        db.query(AnalyticsLandingPageDailyMetric)
        .filter(
            AnalyticsLandingPageDailyMetric.organization_id == organization_id,
            AnalyticsLandingPageDailyMetric.campaign_id == campaign_id,
            AnalyticsLandingPageDailyMetric.metric_date >= start_date,
            AnalyticsLandingPageDailyMetric.metric_date <= latest_date,
        )
        .all()
    )
    source_rows = (
        db.query(AnalyticsTrafficSourceDailyMetric)
        .filter(
            AnalyticsTrafficSourceDailyMetric.organization_id == organization_id,
            AnalyticsTrafficSourceDailyMetric.campaign_id == campaign_id,
            AnalyticsTrafficSourceDailyMetric.metric_date >= start_date,
            AnalyticsTrafficSourceDailyMetric.metric_date <= latest_date,
        )
        .all()
    )
    top_landing_pages = _summarize_analytics_dimensions(
        landing_rows,
        dimension_name="landing_page",
    )
    top_sources = _summarize_analytics_dimensions(
        source_rows,
        dimension_name="source_medium",
    )
    verified_inquiries = len(form_events)
    return {
        "organization_id": organization_id,
        "campaign_id": campaign_id,
        "provider_name": GOOGLE_ANALYTICS_PROVIDER,
        "data_status": "ready" if rows else "no_data",
        "connection": serialize_connection(
            connection,
            campaign=campaign,
            location=location,
        ),
        "date_from": start_date.isoformat(),
        "date_to": latest_date.isoformat(),
        "data_days": len(rows),
        "summary": {
            "visits": sessions,
            "engaged_visits": engaged_sessions,
            "important_actions": inquiries,
            "inquiries": verified_inquiries,
            "engagement_rate_percent": (
                round((engaged_sessions / sessions) * 100, 1) if sessions else 0.0
            ),
        },
        "points": [
            {
                "date": row.metric_date.isoformat(),
                "visits": int(row.sessions or 0),
                "engaged_visits": int(row.engaged_sessions or 0),
                "important_actions": int(row.conversions or 0),
                "verified_inquiries": form_events_by_date.get(row.metric_date, 0),
            }
            for row in rows
        ],
        "top_landing_pages": top_landing_pages,
        "top_sources": top_sources,
        "tracking_health": _website_event_tracking_health(
            connection=connection,
            last_event_at=latest_website_event_at,
            visits=sessions,
        ),
    }


def get_search_console_metrics(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    days: int = 90,
    date_from: date | None = None,
    date_to: date | None = None,
    comparison_mode: str = "previous_period",
    comparison_date_from: date | None = None,
    comparison_date_to: date | None = None,
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
            "comparison_points": [],
        }

    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == connection.business_location_id,
            BusinessLocation.organization_id == organization_id,
        )
        .first()
    )
    latest_metric_date = (
        db.query(SearchConsoleDailyMetric.metric_date)
        .filter(
            SearchConsoleDailyMetric.organization_id == organization_id,
            SearchConsoleDailyMetric.campaign_id == campaign_id,
        )
        .order_by(SearchConsoleDailyMetric.metric_date.desc())
        .limit(1)
        .scalar()
    )
    if latest_metric_date is None:
        return {
            "organization_id": organization_id,
            "campaign_id": campaign_id,
            "provider_name": GOOGLE_SEARCH_CONSOLE_PROVIDER,
            "data_status": "no_data",
            "connection": serialize_connection(
                connection,
                campaign=campaign,
                location=location,
            ),
            "date_from": None,
            "date_to": None,
            "days_requested": days,
            "data_days": 0,
            "summary": None,
            "comparison": None,
            "points": [],
            "comparison_points": [],
        }

    (
        primary_start,
        primary_end,
        comparison_start,
        comparison_end,
        normalized_comparison_mode,
    ) = _resolve_search_console_periods(
        latest_metric_date=latest_metric_date,
        days=days,
        date_from=date_from,
        date_to=date_to,
        comparison_mode=comparison_mode,
        comparison_date_from=comparison_date_from,
        comparison_date_to=comparison_date_to,
    )
    rows = _search_console_rows_for_period(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
        date_from=primary_start,
        date_to=primary_end,
    )
    primary_period_days = (primary_end - primary_start).days + 1
    summary = _summarize_search_console_rows(rows) if rows else None
    comparison = None
    comparison_rows: list[SearchConsoleDailyMetric] = []
    if comparison_start is not None and comparison_end is not None:
        comparison_rows = _search_console_rows_for_period(
            db,
            organization_id=organization_id,
            campaign_id=campaign_id,
            date_from=comparison_start,
            date_to=comparison_end,
        )
        comparison_summary = (
            _summarize_search_console_rows(comparison_rows)
            if comparison_rows
            else None
        )
        comparison_period_days = (comparison_end - comparison_start).days + 1
        change_is_comparable = (
            len(rows) == primary_period_days
            and len(comparison_rows) == comparison_period_days
            and primary_period_days == comparison_period_days
        )
        comparison = {
            "mode": normalized_comparison_mode,
            "label": _comparison_label(normalized_comparison_mode),
            "date_from": comparison_start.isoformat(),
            "date_to": comparison_end.isoformat(),
            "period_days": comparison_period_days,
            "data_days": len(comparison_rows),
            "coverage_percent": round(
                (len(comparison_rows) / comparison_period_days) * 100,
                1,
            ),
            "is_complete": len(comparison_rows) == comparison_period_days,
            "change_is_comparable": change_is_comparable,
            "change_unavailable_reason": (
                None
                if change_is_comparable
                else "The selected and comparison periods need the same complete set of days."
            ),
            "summary": comparison_summary,
            "clicks_change_percent": (
                _percent_change(summary["clicks"], comparison_summary["clicks"])
                if change_is_comparable
                and summary is not None
                and comparison_summary is not None
                else None
            ),
            "impressions_change_percent": (
                _percent_change(
                    summary["impressions"],
                    comparison_summary["impressions"],
                )
                if change_is_comparable
                and summary is not None
                and comparison_summary is not None
                else None
            ),
            "ctr_change_points": (
                round(
                    summary["ctr_percent"] - comparison_summary["ctr_percent"],
                    2,
                )
                if change_is_comparable
                and summary is not None
                and comparison_summary is not None
                else None
            ),
            "position_improvement": (
                round(
                    comparison_summary["avg_position"] - summary["avg_position"],
                    2,
                )
                if change_is_comparable
                and summary is not None
                and comparison_summary is not None
                and comparison_summary["avg_position"] is not None
                and summary["avg_position"] is not None
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
        "date_from": primary_start.isoformat(),
        "date_to": primary_end.isoformat(),
        "days_requested": primary_period_days,
        "data_days": len(rows),
        "coverage_percent": round(
            (len(rows) / primary_period_days) * 100,
            1,
        ),
        "summary": summary,
        "comparison": comparison,
        "points": [_serialize_search_console_point(row) for row in rows],
        "comparison_points": [
            _serialize_search_console_point(row)
            for row in comparison_rows
        ],
    }


def _resolve_search_console_periods(
    *,
    latest_metric_date: date,
    days: int,
    date_from: date | None,
    date_to: date | None,
    comparison_mode: str,
    comparison_date_from: date | None,
    comparison_date_to: date | None,
) -> tuple[date, date, date | None, date | None, str]:
    if (date_from is None) != (date_to is None):
        raise DataConnectionError(
            "Choose both a start date and an end date.",
            reason_code="incomplete_date_range",
        )
    if date_from is not None and date_to is not None:
        primary_start, primary_end = _validate_metric_period(
            date_from,
            date_to,
            label="selected",
        )
    else:
        normalized_days = max(7, min(int(days), MAX_SEARCH_CONSOLE_RANGE_DAYS))
        primary_end = latest_metric_date
        primary_start = primary_end - timedelta(days=normalized_days - 1)

    mode = str(comparison_mode or "previous_period").strip().lower()
    if mode == "none":
        return primary_start, primary_end, None, None, mode

    primary_period_days = (primary_end - primary_start).days + 1
    if mode == "previous_period":
        resolved_comparison_end = primary_start - timedelta(days=1)
        resolved_comparison_start = resolved_comparison_end - timedelta(
            days=primary_period_days - 1
        )
    elif mode == "previous_year":
        resolved_comparison_start = _shift_year(primary_start, years=-1)
        resolved_comparison_end = _shift_year(primary_end, years=-1)
    elif mode == "custom":
        if comparison_date_from is None or comparison_date_to is None:
            raise DataConnectionError(
                "Choose both comparison dates.",
                reason_code="incomplete_comparison_range",
            )
        resolved_comparison_start, resolved_comparison_end = _validate_metric_period(
            comparison_date_from,
            comparison_date_to,
            label="comparison",
        )
        comparison_period_days = (
            resolved_comparison_end - resolved_comparison_start
        ).days + 1
        if comparison_period_days != primary_period_days:
            raise DataConnectionError(
                "Choose comparison dates with the same number of days as the selected dates.",
                reason_code="comparison_period_length_mismatch",
            )
    else:
        raise DataConnectionError(
            "Choose a supported comparison option.",
            reason_code="invalid_comparison_mode",
        )

    return (
        primary_start,
        primary_end,
        resolved_comparison_start,
        resolved_comparison_end,
        mode,
    )


def _validate_metric_period(
    period_start: date,
    period_end: date,
    *,
    label: str,
) -> tuple[date, date]:
    if period_end < period_start:
        raise DataConnectionError(
            f"The {label} end date must be on or after its start date.",
            reason_code="invalid_date_range",
        )
    period_days = (period_end - period_start).days + 1
    if period_days > MAX_SEARCH_CONSOLE_RANGE_DAYS:
        raise DataConnectionError(
            f"The {label} date range cannot exceed {MAX_SEARCH_CONSOLE_RANGE_DAYS} days.",
            reason_code="date_range_too_large",
        )
    return period_start, period_end


def _shift_year(value: date, *, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def _comparison_label(mode: str) -> str:
    if mode == "previous_year":
        return "Same dates last year"
    if mode == "custom":
        return "Chosen comparison dates"
    return "Previous period"


def _search_console_rows_for_period(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    date_from: date,
    date_to: date,
) -> list[SearchConsoleDailyMetric]:
    return (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.organization_id == organization_id,
            SearchConsoleDailyMetric.campaign_id == campaign_id,
            SearchConsoleDailyMetric.metric_date >= date_from,
            SearchConsoleDailyMetric.metric_date <= date_to,
        )
        .order_by(SearchConsoleDailyMetric.metric_date.asc())
        .all()
    )


def _serialize_search_console_point(
    row: SearchConsoleDailyMetric,
) -> dict[str, str | int | float | None]:
    return {
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


def discover_google_analytics_resources(
    db: Session,
    organization_id: str,
) -> list[dict[str, str | bool]]:
    """Return GA4 properties available to the organization's read-only Google grant."""

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
            "Reconnect Google Analytics to continue.",
            reason_code="org_oauth_credential_required",
            status_code=409,
        )
    expected_scope = get_settings().google_oauth_scope_analytics.strip()
    granted_scopes = str(credentials.get("scope", "")).split()
    if expected_scope and granted_scopes and expected_scope not in granted_scopes:
        raise DataConnectionError(
            "Reconnect Google and approve read-only website analytics access.",
            reason_code="oauth_scope_missing",
            status_code=409,
        )

    resources: list[dict[str, str | bool]] = []
    page_token = ""
    try:
        with httpx.Client() as client:
            for _page in range(10):
                params: dict[str, str | int] = {"pageSize": 200}
                if page_token:
                    params["pageToken"] = page_token
                response = client.get(
                    "https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                    params=params,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=float(get_settings().google_oauth_http_timeout_seconds),
                )
                if response.status_code in {401, 403}:
                    raise DataConnectionError(
                        "Google Analytics access needs to be reconnected.",
                        reason_code="oauth_reconnect_required",
                        status_code=409,
                    )
                if response.status_code >= 400:
                    raise DataConnectionError(
                        "Google Analytics properties could not be loaded.",
                        reason_code="provider_request_failed",
                        status_code=502,
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise DataConnectionError(
                        "Google Analytics returned an invalid response.",
                        reason_code="provider_response_invalid",
                        status_code=502,
                    ) from exc
                summaries = payload.get("accountSummaries", []) if isinstance(payload, dict) else []
                for account in summaries if isinstance(summaries, list) else []:
                    if not isinstance(account, dict):
                        continue
                    account_name = str(account.get("displayName") or "Google Analytics account").strip()
                    properties = account.get("propertySummaries", [])
                    for item in properties if isinstance(properties, list) else []:
                        if not isinstance(item, dict):
                            continue
                        property_resource = str(item.get("property") or "").strip()
                        property_id = property_resource.removeprefix("properties/").strip()
                        if not property_id.isdigit():
                            continue
                        display_name = str(item.get("displayName") or property_id).strip()
                        resources.append(
                            {
                                "id": property_id,
                                "name": display_name,
                                "account_name": account_name,
                                "property_type": str(item.get("propertyType") or "PROPERTY_TYPE_ORDINARY"),
                                "can_edit": bool(item.get("canEdit")),
                                "resource_scope": "ga4_property",
                            }
                        )
                page_token = str(payload.get("nextPageToken") or "").strip() if isinstance(payload, dict) else ""
                if not page_token:
                    break
    except httpx.TimeoutException as exc:
        raise DataConnectionError(
            "Google Analytics took too long to respond.",
            reason_code="provider_timeout",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise DataConnectionError(
            "Google Analytics could not be reached.",
            reason_code="provider_unavailable",
            status_code=502,
        ) from exc

    return sorted(resources, key=lambda item: (str(item["account_name"]).lower(), str(item["name"]).lower()))


def upsert_google_analytics_mapping(
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
            "Assign this website to a business location before connecting website analytics.",
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

    property_id = external_resource_id.removeprefix("properties/").strip()
    if not property_id.isdigit():
        raise DataConnectionError(
            "Choose a valid Google Analytics property.",
            reason_code="invalid_external_resource",
            status_code=400,
        )
    resource_name = (external_resource_name or "").strip() or f"Property {property_id}"
    existing = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == GOOGLE_ANALYTICS_PROVIDER,
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
            provider_name=GOOGLE_ANALYTICS_PROVIDER,
            external_resource_id=property_id,
            external_resource_name=resource_name,
            resource_scope="ga4_property",
            status=CONNECTION_STATUS_CONNECTED,
            next_sync_at=now,
            sync_cursor={},
            connection_metadata={"read_only": True},
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        if existing.external_resource_id != property_id and existing.last_success_at is not None:
            raise DataConnectionError(
                "This location already has saved website analytics history. Changing its property "
                "requires a separate data-reset workflow.",
                reason_code="mapping_change_requires_reset",
                status_code=409,
            )
        existing.tenant_id = campaign.tenant_id
        existing.business_location_id = location.id
        existing.external_resource_id = property_id
        existing.external_resource_name = resource_name
        existing.resource_scope = "ga4_property"
        existing.status = CONNECTION_STATUS_CONNECTED
        existing.next_sync_at = now
        existing.last_error_code = None
        existing.last_error_message = None
        existing.updated_at = now
    db.commit()
    db.refresh(existing)
    return existing


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
    metric_start_date: str,
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
    sync_cursor = dict(connection.sync_cursor or {})
    previous_start_raw = str(sync_cursor.get("history_start_date") or "").strip()
    previous_end_raw = str(sync_cursor.get("last_metric_date") or "").strip()
    resolved_start = date.fromisoformat(metric_start_date)
    resolved_end = date.fromisoformat(metric_end_date)
    if previous_start_raw:
        resolved_start = min(resolved_start, date.fromisoformat(previous_start_raw))
    if previous_end_raw:
        resolved_end = max(resolved_end, date.fromisoformat(previous_end_raw))
    connection.sync_cursor = {
        **sync_cursor,
        "history_start_date": resolved_start.isoformat(),
        "last_metric_date": resolved_end.isoformat(),
        "history_days": (resolved_end - resolved_start).days + 1,
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


def _connection_source_truth(provider_name: str) -> str:
    if provider_name == "google_business_profile":
        return (
            "Authorized data for one Google business listing. Results stay tied to the "
            "matched business location and are never blended with another listing."
        )
    if provider_name == GOOGLE_ANALYTICS_PROVIDER:
        return (
            "Read-only website visit and inquiry totals from the Google Analytics property "
            "matched to this business location."
        )
    return (
        "Website-property data from Google Search Console. If multiple locations share "
        "one property, the metrics describe that shared website property."
    )


def _summarize_analytics_dimensions(
    rows: list[AnalyticsLandingPageDailyMetric] | list[AnalyticsTrafficSourceDailyMetric],
    *,
    dimension_name: str,
) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        dimension = str(getattr(row, dimension_name) or "").strip()
        if not dimension or dimension in {"/__no_activity__", "__no_activity__"}:
            continue
        values = totals.setdefault(
            dimension,
            {"visits": 0, "engaged_visits": 0, "important_actions": 0},
        )
        values["visits"] += int(row.sessions or 0)
        values["engaged_visits"] += int(row.engaged_sessions or 0)
        values["important_actions"] += int(row.key_events or 0)
    return [
        {"name": name, **values}
        for name, values in sorted(
            totals.items(),
            key=lambda item: (-item[1]["visits"], item[0].lower()),
        )[:5]
    ]


def _latest_website_form_event_at(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
) -> datetime | None:
    return (
        db.query(WebsiteFormEvent.occurred_at)
        .filter(
            WebsiteFormEvent.organization_id == organization_id,
            WebsiteFormEvent.campaign_id == campaign_id,
        )
        .order_by(WebsiteFormEvent.occurred_at.desc())
        .limit(1)
        .scalar()
    )


def _website_event_tracking_health(
    *,
    connection: DataConnection,
    last_event_at: datetime | None,
    visits: int,
) -> dict[str, Any]:
    metadata = dict(connection.connection_metadata or {})
    key_configured = bool(metadata.get("website_event_token_hash"))
    normalized_last_event_at = _as_aware(last_event_at) if last_event_at is not None else None
    now = datetime.now(UTC)
    if not key_configured:
        status = "setup_required"
        message = "Connect the website form before inquiry tracking can begin."
    elif normalized_last_event_at is None:
        status = "waiting_for_first_event"
        message = "The secure form connection is ready and waiting for its first inquiry."
    elif now - normalized_last_event_at <= timedelta(days=14):
        status = "active"
        message = "Website inquiry tracking has received recent activity."
    elif now - normalized_last_event_at > timedelta(days=30) and visits >= 100:
        status = "check_tracking"
        message = "Website visits continued, but no inquiry event arrived recently. Check the form connection."
    else:
        status = "quiet"
        message = "No recent inquiry was recorded. This does not prove the form is broken."
    return {
        "status": status,
        "message": message,
        "key_configured": key_configured,
        "last_event_at": (
            normalized_last_event_at.isoformat()
            if normalized_last_event_at is not None
            else None
        ),
    }
