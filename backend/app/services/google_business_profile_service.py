from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.google_business_profile import (
    GoogleBusinessProfileDailyMetric,
    GoogleBusinessProfileSearchKeyword,
    GoogleBusinessProfileSnapshot,
)
from app.providers import google_business_profile as provider
from app.services import data_connections_service, metric_contract_service, standards_source_service
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credentials,
)


GOOGLE_BUSINESS_PROFILE_PROVIDER = "google_business_profile"
MAX_PROFILE_METRIC_DAYS = 180
PROFILE_SYNC_BACKFILL_DAYS = 90
PROFILE_KEYWORD_MONTHS = 3

METRIC_LABELS = {
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS": "Map appearances on computers",
    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH": "Search appearances on computers",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS": "Map appearances on phones",
    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH": "Search appearances on phones",
    "BUSINESS_DIRECTION_REQUESTS": "Direction requests",
    "CALL_CLICKS": "Call button clicks",
    "WEBSITE_CLICKS": "Website clicks",
    "BUSINESS_BOOKINGS": "Bookings",
}


def discover_profiles(db: Session, organization_id: str) -> list[dict[str, Any]]:
    _assert_provider_contract_ready(db)
    credentials = _resolve_credentials(db, organization_id)
    try:
        return provider.discover_profiles(
            access_token=str(credentials["access_token"]),
            timeout_seconds=float(get_settings().google_oauth_http_timeout_seconds),
        )
    except provider.GoogleBusinessProfileProviderError as exc:
        raise _connection_error(exc) from exc


def upsert_mapping(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    external_resource_id: str,
    actor_user_id: str,
) -> DataConnection:
    campaign, location = _campaign_and_location(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    resource_id = external_resource_id.strip()
    if not resource_id.startswith("locations/") or len(resource_id.split("/")) != 2:
        raise data_connections_service.DataConnectionError(
            "Choose a valid Google business listing.",
            reason_code="invalid_external_resource",
            status_code=400,
        )
    available = discover_profiles(db, organization_id)
    selected = next((item for item in available if item["id"] == resource_id), None)
    if selected is None:
        raise data_connections_service.DataConnectionError(
            "That Google business listing is not available to the connected account.",
            reason_code="profile_not_authorized",
            status_code=403,
        )

    conflicting = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == GOOGLE_BUSINESS_PROFILE_PROVIDER,
            DataConnection.external_resource_id == resource_id,
            DataConnection.campaign_id != campaign.id,
            DataConnection.status != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )
    if conflicting is not None:
        raise data_connections_service.DataConnectionError(
            "That Google business listing is already matched to another location.",
            reason_code="profile_already_mapped",
            status_code=409,
        )

    existing = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.provider_name == GOOGLE_BUSINESS_PROFILE_PROVIDER,
            DataConnection.campaign_id == campaign.id,
        )
        .first()
    )
    now = datetime.now(UTC)
    metadata = {
        "account_id": selected.get("account_id"),
        "account_name": selected.get("account_name"),
        "account_role": selected.get("account_role"),
        "permission_level": selected.get("permission_level"),
        "profile_verified": bool(selected.get("verified")),
        "permission_verified": True,
        "mutation_enabled": False,
    }
    if existing is None:
        existing = DataConnection(
            tenant_id=campaign.tenant_id,
            organization_id=organization_id,
            business_location_id=location.id,
            campaign_id=campaign.id,
            provider_name=GOOGLE_BUSINESS_PROFILE_PROVIDER,
            external_resource_id=resource_id,
            external_resource_name=str(selected.get("name") or resource_id),
            resource_scope="owned_business_profile",
            status=data_connections_service.CONNECTION_STATUS_CONNECTED,
            next_sync_at=now,
            sync_cursor={},
            connection_metadata=metadata,
            created_by_user_id=actor_user_id,
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
    else:
        if existing.external_resource_id != resource_id and existing.last_success_at is not None:
            raise data_connections_service.DataConnectionError(
                "This location already has saved profile history. Changing the listing requires a separate reset.",
                reason_code="mapping_change_requires_reset",
                status_code=409,
            )
        existing.business_location_id = location.id
        existing.external_resource_id = resource_id
        existing.external_resource_name = str(selected.get("name") or resource_id)
        existing.resource_scope = "owned_business_profile"
        existing.status = data_connections_service.CONNECTION_STATUS_CONNECTED
        existing.next_sync_at = now
        existing.connection_metadata = metadata
        existing.last_error_code = None
        existing.last_error_message = None
        existing.updated_at = now
    db.commit()
    db.refresh(existing)
    return existing


def sync_profile_connection(
    db: Session,
    *,
    connection: DataConnection,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    _assert_provider_contract_ready(db)
    campaign, location = _campaign_and_location(
        db,
        organization_id=connection.organization_id,
        campaign_id=connection.campaign_id,
    )
    if (
        campaign.tenant_id != connection.tenant_id
        or location.id != connection.business_location_id
        or connection.provider_name != GOOGLE_BUSINESS_PROFILE_PROVIDER
    ):
        raise ValueError("Google business listing mapping is no longer valid.")
    credentials = _resolve_credentials(db, connection.organization_id)
    access_token = str(credentials["access_token"])
    timeout = float(get_settings().google_oauth_http_timeout_seconds)
    try:
        profile = provider.get_profile(
            access_token=access_token,
            resource_id=connection.external_resource_id,
            timeout_seconds=timeout,
        )
        daily_rows = provider.fetch_daily_metrics(
            access_token=access_token,
            resource_id=connection.external_resource_id,
            date_from=date_from,
            date_to=date_to,
            timeout_seconds=timeout,
        )
        keyword_rows: list[tuple[date, dict[str, Any]]] = []
        keyword_month = _month_start(date_to)
        for offset in range(PROFILE_KEYWORD_MONTHS):
            month = _shift_month(keyword_month, -offset)
            rows = provider.fetch_search_keywords(
                access_token=access_token,
                resource_id=connection.external_resource_id,
                month_from=month,
                month_to=month,
                timeout_seconds=timeout,
            )
            keyword_rows.extend((month, row) for row in rows)
    except provider.GoogleBusinessProfileProviderError as exc:
        raise _connection_error(exc) from exc

    audit = build_profile_audit(profile=profile, campaign=campaign, location=location)
    snapshot, snapshot_created = _save_snapshot(
        db,
        connection=connection,
        profile=profile,
        audit=audit,
    )
    connection.connection_metadata = {
        **dict(connection.connection_metadata or {}),
        "profile_verified": bool((profile.get("metadata") or {}).get("hasVoiceOfMerchant")),
        "latest_profile_changed": snapshot_created,
        "latest_profile_hash": snapshot.profile_hash,
        "mutation_enabled": False,
    }
    connection.updated_at = datetime.now(UTC)
    metric_counts = _upsert_daily_metrics(
        db,
        connection=connection,
        date_from=date_from,
        date_to=date_to,
        rows=daily_rows,
    )
    keyword_count = _upsert_search_keywords(
        db,
        connection=connection,
        rows=keyword_rows,
    )
    db.flush()
    return {
        "connection_id": connection.id,
        "campaign_id": campaign.id,
        "business_location_id": location.id,
        "profile_snapshot_id": snapshot.id,
        "profile_changed": snapshot_created,
        "audit_score": audit["score"],
        "audit_items_needing_attention": audit["needs_attention"],
        "metric_rows_saved": metric_counts,
        "search_terms_saved": keyword_count,
        "start_date": date_from.isoformat(),
        "end_date": date_to.isoformat(),
    }


def _assert_provider_contract_ready(db: Session) -> None:
    try:
        standards_source_service.assert_provider_contract_ready(
            db,
            GOOGLE_BUSINESS_PROFILE_PROVIDER,
        )
    except standards_source_service.StandardsContractBlockedError as exc:
        raise data_connections_service.DataConnectionError(
            str(exc),
            reason_code="provider_contract_review_required",
            status_code=409,
        ) from exc


def get_profile_intelligence(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
    days: int = 90,
) -> dict[str, Any]:
    campaign, location = _campaign_and_location(
        db,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign_id,
            DataConnection.provider_name == GOOGLE_BUSINESS_PROFILE_PROVIDER,
        )
        .first()
    )
    if connection is None:
        return {
            "data_status": "not_connected",
            "campaign_id": campaign.id,
            "business_location_id": location.id,
            "connection": None,
            "profile": None,
            "audit": None,
            "changes": [],
            "summary": None,
            "points": [],
            "search_terms": [],
        }

    snapshots = (
        db.query(GoogleBusinessProfileSnapshot)
        .filter(
            GoogleBusinessProfileSnapshot.organization_id == organization_id,
            GoogleBusinessProfileSnapshot.connection_id == connection.id,
        )
        .order_by(GoogleBusinessProfileSnapshot.captured_at.desc())
        .limit(2)
        .all()
    )
    latest_metric_date = (
        db.query(GoogleBusinessProfileDailyMetric.metric_date)
        .filter(
            GoogleBusinessProfileDailyMetric.organization_id == organization_id,
            GoogleBusinessProfileDailyMetric.connection_id == connection.id,
        )
        .order_by(GoogleBusinessProfileDailyMetric.metric_date.desc())
        .limit(1)
        .scalar()
    )
    normalized_days = max(7, min(int(days), MAX_PROFILE_METRIC_DAYS))
    points: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    date_from: date | None = None
    if latest_metric_date is not None:
        date_from = latest_metric_date - timedelta(days=normalized_days - 1)
        metric_rows = (
            db.query(GoogleBusinessProfileDailyMetric)
            .filter(
                GoogleBusinessProfileDailyMetric.organization_id == organization_id,
                GoogleBusinessProfileDailyMetric.connection_id == connection.id,
                GoogleBusinessProfileDailyMetric.metric_date >= date_from,
                GoogleBusinessProfileDailyMetric.metric_date <= latest_metric_date,
            )
            .order_by(GoogleBusinessProfileDailyMetric.metric_date.asc())
            .all()
        )
        points = _metric_points(metric_rows)
        summary = _metric_summary(points)

    keyword_rows = (
        db.query(GoogleBusinessProfileSearchKeyword)
        .filter(
            GoogleBusinessProfileSearchKeyword.organization_id == organization_id,
            GoogleBusinessProfileSearchKeyword.connection_id == connection.id,
        )
        .order_by(
            GoogleBusinessProfileSearchKeyword.metric_month.desc(),
            GoogleBusinessProfileSearchKeyword.impressions.desc(),
        )
        .limit(50)
        .all()
    )
    latest = snapshots[0] if snapshots else None
    previous = snapshots[1] if len(snapshots) > 1 else None
    return {
        "data_status": "ready" if latest is not None else "no_data",
        "campaign_id": campaign.id,
        "business_location_id": location.id,
        "connection": data_connections_service.serialize_connection(
            connection,
            campaign=campaign,
            location=location,
        ),
        "profile": dict(latest.profile_data) if latest is not None else None,
        "audit": dict(latest.audit_summary) if latest is not None else None,
        "changes": (
            _profile_changes(previous.profile_data, latest.profile_data)
            if latest is not None
            and previous is not None
            and bool((connection.connection_metadata or {}).get("latest_profile_changed"))
            else []
        ),
        "captured_at": latest.captured_at.isoformat() if latest is not None else None,
        "checked_at": (
            connection.last_success_at.isoformat()
            if connection.last_success_at is not None
            else None
        ),
        "date_from": date_from.isoformat() if date_from is not None else None,
        "date_to": latest_metric_date.isoformat() if latest_metric_date is not None else None,
        "summary": summary,
        "points": points,
        "search_terms": [
            {
                "month": row.metric_month.isoformat(),
                "keyword": row.keyword,
                "impressions": row.impressions,
                "measurement_kind": row.measurement_kind,
                "metric_contract": {
                    "id": row.metric_contract_id,
                    "version": row.metric_contract_version,
                    "scope_key": row.scope_key,
                },
            }
            for row in keyword_rows
        ],
    }


def build_profile_audit(
    *,
    profile: dict[str, Any],
    campaign: Campaign,
    location: BusinessLocation,
) -> dict[str, Any]:
    categories = profile.get("categories") if isinstance(profile.get("categories"), dict) else {}
    primary_category = categories.get("primaryCategory") if isinstance(categories, dict) else None
    phone_numbers = profile.get("phoneNumbers") if isinstance(profile.get("phoneNumbers"), dict) else {}
    regular_hours = profile.get("regularHours") if isinstance(profile.get("regularHours"), dict) else {}
    profile_text = profile.get("profile") if isinstance(profile.get("profile"), dict) else {}
    has_address_or_area = bool(profile.get("storefrontAddress") or profile.get("serviceArea"))
    checks = (
        ("business_name", "Business name", bool(str(profile.get("title") or "").strip()), "Add the business name customers already know.", "Search and Maps appearances"),
        ("primary_category", "Main business category", bool(primary_category), "Choose the main category that best matches the work this location sells.", "Search and Maps appearances"),
        ("phone", "Phone number", bool(phone_numbers.get("primaryPhone")), "Add the main phone number customers should call.", "Call button clicks"),
        ("website", "Website", bool(str(profile.get("websiteUri") or "").strip()), "Add the website page that belongs to this location.", "Website clicks"),
        ("hours", "Regular hours", bool(regular_hours.get("periods")), "Add the normal hours so customers know when the business is open.", "Search and Maps appearances"),
        ("address_or_service_area", "Address or service area", has_address_or_area, "Add the storefront address or the area this business serves.", "Direction requests"),
        ("description", "Business description", bool(str(profile_text.get("description") or "").strip()), "Write a short description of the services customers can hire this business for.", "Search and Maps appearances"),
        ("services", "Services", bool(profile.get("serviceItems")), "Add the main services customers can buy from this location.", "Search and Maps appearances"),
    )
    items: list[dict[str, Any]] = []
    for field, label, complete, action, metric in checks:
        items.append(
            {
                "field": field,
                "label": label,
                "status": "complete" if complete else "needs_attention",
                "message": (
                    f"{label} is filled in."
                    if complete
                    else f"{label} is missing from the connected listing."
                ),
                "action": None if complete else action,
                "primary_metric": metric,
                "measurement_state": "Waiting for a later same-location measurement",
            }
        )

    profile_domain = _hostname(str(profile.get("websiteUri") or ""))
    campaign_domain = _hostname(campaign.domain)
    if profile_domain and campaign_domain and profile_domain != campaign_domain:
        items.append(
            {
                "field": "website_match",
                "label": "Website match",
                "status": "needs_attention",
                "message": "The listing points to a different website than the one saved for this location.",
                "action": "Confirm which website is correct before changing either one.",
                "primary_metric": "Website clicks",
                "measurement_state": "Accuracy check only — this does not prove lost traffic",
            }
        )

    items.extend(
        (
            {
                "field": "special_hours",
                "label": "Holiday and special hours",
                "status": "review" if not profile.get("specialHours") else "complete",
                "message": (
                    "Special hours are saved."
                    if profile.get("specialHours")
                    else "No special hours were returned. That may be correct if no holiday change is needed."
                ),
                "action": "Check upcoming holidays and add different hours only when needed.",
                "primary_metric": "Search and Maps appearances",
                "measurement_state": "Accuracy check only",
            },
            {
                "field": "photos",
                "label": "Photos",
                "status": "not_measured",
                "message": "Photo freshness is not available from this connection yet.",
                "action": None,
                "primary_metric": None,
                "measurement_state": "Not measured",
            },
            {
                "field": "posts",
                "label": "Posts",
                "status": "not_measured",
                "message": "Post activity is not available from this connection yet.",
                "action": None,
                "primary_metric": None,
                "measurement_state": "Not measured",
            },
        )
    )
    scored = [item for item in items if item["field"] in {check[0] for check in checks}]
    complete_count = sum(1 for item in scored if item["status"] == "complete")
    score = round((complete_count / len(scored)) * 100) if scored else None
    needs_attention = sum(1 for item in items if item["status"] == "needs_attention")
    return {
        "score": score,
        "complete": complete_count,
        "scored_fields": len(scored),
        "needs_attention": needs_attention,
        "items": items,
        "summary": (
            "The listing has the main information customers need."
            if needs_attention == 0
            else f"{needs_attention} listing {('detail needs' if needs_attention == 1 else 'details need')} attention."
        ),
        "truth_note": "This checks listing details. It does not claim that filling a field will automatically improve rankings.",
    }


def _save_snapshot(
    db: Session,
    *,
    connection: DataConnection,
    profile: dict[str, Any],
    audit: dict[str, Any],
) -> tuple[GoogleBusinessProfileSnapshot, bool]:
    profile_hash = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    existing = (
        db.query(GoogleBusinessProfileSnapshot)
        .filter(
            GoogleBusinessProfileSnapshot.connection_id == connection.id,
            GoogleBusinessProfileSnapshot.profile_hash == profile_hash,
        )
        .first()
    )
    if existing is not None:
        return existing, False
    captured_at = datetime.now(UTC)
    source_account_id = str(
        (connection.connection_metadata or {}).get("account_id") or "unknown"
    )
    contract_scope = metric_contract_service.scope_evidence(
        "gbp.profile.configuration",
        {
            "organization_id": connection.organization_id,
            "campaign_id": connection.campaign_id,
            "business_location_id": connection.business_location_id,
            "connection_id": connection.id,
            "external_resource_id": connection.external_resource_id,
            "source_account_id": source_account_id,
            "captured_at": captured_at,
            "available_fields": sorted(profile),
            "unavailable_fields": ["photos", "posts"],
        },
        db=db,
    )
    row = GoogleBusinessProfileSnapshot(
        connection_id=connection.id,
        tenant_id=connection.tenant_id,
        organization_id=connection.organization_id,
        campaign_id=connection.campaign_id,
        business_location_id=connection.business_location_id,
        external_resource_id=connection.external_resource_id,
        profile_hash=profile_hash,
        profile_data=profile,
        audit_summary=audit,
        metric_contract_id="gbp.profile.configuration",
        metric_contract_version=contract_scope["metric_contract_version"],
        source_account_id=source_account_id,
        scope_key=contract_scope["scope_key"],
        captured_at=captured_at,
    )
    db.add(row)
    db.flush()
    return row, True


def _upsert_daily_metrics(
    db: Session,
    *,
    connection: DataConnection,
    date_from: date,
    date_to: date,
    rows: list[dict[str, Any]],
) -> int:
    returned = {
        (row["metric_date"], str(row["metric_name"])): row
        for row in rows
        if isinstance(row.get("metric_date"), date)
    }
    saved = 0
    source_account_id = str(
        (connection.connection_metadata or {}).get("account_id") or "unknown"
    )
    current_date = date_from
    while current_date <= date_to:
        for metric_name in provider.DAILY_METRICS:
            key = (current_date, metric_name)
            source = returned.get(key)
            value = int(source["metric_value"]) if source is not None else None
            missing_reason = (
                None
                if source is not None
                else "Google did not return this measurement for this date."
            )
            contract_id = metric_contract_service.business_profile_contract_id(metric_name)
            contract_scope = metric_contract_service.scope_evidence(
                contract_id,
                {
                    "organization_id": connection.organization_id,
                    "campaign_id": connection.campaign_id,
                    "business_location_id": connection.business_location_id,
                    "connection_id": connection.id,
                    "external_resource_id": connection.external_resource_id,
                    "source_account_id": source_account_id,
                    "window_start": current_date,
                    "window_end": current_date,
                },
                db=db,
            )
            row = (
                db.query(GoogleBusinessProfileDailyMetric)
                .filter(
                    GoogleBusinessProfileDailyMetric.connection_id == connection.id,
                    GoogleBusinessProfileDailyMetric.metric_date == current_date,
                    GoogleBusinessProfileDailyMetric.metric_name == metric_name,
                )
                .first()
            )
            if row is None:
                row = GoogleBusinessProfileDailyMetric(
                    connection_id=connection.id,
                    tenant_id=connection.tenant_id,
                    organization_id=connection.organization_id,
                    campaign_id=connection.campaign_id,
                    business_location_id=connection.business_location_id,
                    metric_date=current_date,
                    metric_name=metric_name,
                    metric_value=value,
                    missing_reason=missing_reason,
                    metric_contract_id=contract_id,
                    metric_contract_version=contract_scope["metric_contract_version"],
                    source_account_id=source_account_id,
                    external_resource_id=connection.external_resource_id,
                    scope_key=contract_scope["scope_key"],
                    captured_at=datetime.now(UTC),
                )
                db.add(row)
            else:
                row.metric_value = value
                row.missing_reason = missing_reason
                row.metric_contract_id = contract_id
                row.metric_contract_version = contract_scope["metric_contract_version"]
                row.source_account_id = source_account_id
                row.external_resource_id = connection.external_resource_id
                row.scope_key = contract_scope["scope_key"]
                row.captured_at = datetime.now(UTC)
            saved += 1
        current_date += timedelta(days=1)
    return saved


def _upsert_search_keywords(
    db: Session,
    *,
    connection: DataConnection,
    rows: list[tuple[date, dict[str, Any]]],
) -> int:
    saved = 0
    source_account_id = str(
        (connection.connection_metadata or {}).get("account_id") or "unknown"
    )
    for month, source in rows:
        keyword = str(source.get("keyword") or "").strip().lower()
        if not keyword:
            continue
        measurement_kind = str(source.get("measurement") or "exact")
        contract_id = "gbp.search_terms.monthly_impressions"
        contract_scope = metric_contract_service.scope_evidence(
            contract_id,
            {
                "organization_id": connection.organization_id,
                "campaign_id": connection.campaign_id,
                "business_location_id": connection.business_location_id,
                "connection_id": connection.id,
                "external_resource_id": connection.external_resource_id,
                "source_account_id": source_account_id,
                "metric_month": month,
                "keyword": keyword,
                "measurement_kind": measurement_kind,
            },
            db=db,
        )
        row = (
            db.query(GoogleBusinessProfileSearchKeyword)
            .filter(
                GoogleBusinessProfileSearchKeyword.connection_id == connection.id,
                GoogleBusinessProfileSearchKeyword.metric_month == month,
                GoogleBusinessProfileSearchKeyword.keyword == keyword,
            )
            .first()
        )
        if row is None:
            row = GoogleBusinessProfileSearchKeyword(
                connection_id=connection.id,
                tenant_id=connection.tenant_id,
                organization_id=connection.organization_id,
                campaign_id=connection.campaign_id,
                business_location_id=connection.business_location_id,
                metric_month=month,
                keyword=keyword,
                impressions=int(source.get("impressions") or 0),
                measurement_kind=measurement_kind,
                metric_contract_id=contract_id,
                metric_contract_version=contract_scope["metric_contract_version"],
                source_account_id=source_account_id,
                external_resource_id=connection.external_resource_id,
                scope_key=contract_scope["scope_key"],
                captured_at=datetime.now(UTC),
            )
            db.add(row)
        else:
            row.impressions = int(source.get("impressions") or 0)
            row.measurement_kind = measurement_kind
            row.metric_contract_id = contract_id
            row.metric_contract_version = contract_scope["metric_contract_version"]
            row.source_account_id = source_account_id
            row.external_resource_id = connection.external_resource_id
            row.scope_key = contract_scope["scope_key"]
            row.captured_at = datetime.now(UTC)
        saved += 1
    return saved


def _metric_points(rows: list[GoogleBusinessProfileDailyMetric]) -> list[dict[str, Any]]:
    by_date: dict[date, dict[str, Any]] = defaultdict(dict)
    for row in rows:
        point = by_date[row.metric_date]
        point["date"] = row.metric_date.isoformat()
        point[row.metric_name] = row.metric_value
    points: list[dict[str, Any]] = []
    for metric_date in sorted(by_date):
        point = by_date[metric_date]
        search_impressions = sum(
            int(point.get(name) or 0)
            for name in (
                "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
                "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
            )
        )
        map_impressions = sum(
            int(point.get(name) or 0)
            for name in (
                "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
                "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
            )
        )
        points.append(
            {
                **point,
                "search_appearances": search_impressions,
                "map_appearances": map_impressions,
                "total_appearances": search_impressions + map_impressions,
                "website_clicks": point.get("WEBSITE_CLICKS"),
                "call_clicks": point.get("CALL_CLICKS"),
                "direction_requests": point.get("BUSINESS_DIRECTION_REQUESTS"),
                "bookings": point.get("BUSINESS_BOOKINGS"),
            }
        )
    return points


def _metric_summary(points: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_appearances": sum(int(point.get("total_appearances") or 0) for point in points),
        "search_appearances": sum(int(point.get("search_appearances") or 0) for point in points),
        "map_appearances": sum(int(point.get("map_appearances") or 0) for point in points),
        "website_clicks": sum(int(point.get("website_clicks") or 0) for point in points),
        "call_clicks": sum(int(point.get("call_clicks") or 0) for point in points),
        "direction_requests": sum(int(point.get("direction_requests") or 0) for point in points),
        "bookings": sum(int(point.get("bookings") or 0) for point in points),
        "days_with_data": sum(1 for point in points if int(point.get("total_appearances") or 0) > 0),
    }


def _profile_changes(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
    fields = {
        "title": "Business name",
        "phoneNumbers": "Phone number",
        "categories": "Business categories",
        "storefrontAddress": "Address",
        "websiteUri": "Website",
        "regularHours": "Regular hours",
        "specialHours": "Special hours",
        "serviceArea": "Service area",
        "profile": "Business description",
        "serviceItems": "Services",
        "attributes": "Business details",
    }
    return [
        {"field": field, "label": label, "message": f"{label} changed since the previous saved check."}
        for field, label in fields.items()
        if previous.get(field) != current.get(field)
    ]


def _campaign_and_location(
    db: Session,
    *,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == organization_id)
        .first()
    )
    if campaign is None:
        raise data_connections_service.DataConnectionError(
            "Business not found in this organization.",
            reason_code="campaign_not_found",
            status_code=404,
        )
    if not campaign.business_location_id:
        raise data_connections_service.DataConnectionError(
            "Assign this website to a business location before connecting its Google listing.",
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
        raise data_connections_service.DataConnectionError(
            "The business location could not be verified.",
            reason_code="business_location_not_found",
            status_code=404,
        )
    return campaign, location


def _resolve_credentials(db: Session, organization_id: str) -> dict[str, Any]:
    try:
        credentials = resolve_provider_credentials(
            db,
            organization_id,
            "google",
            required_credential_mode="byo_required",
            require_org_oauth=True,
        )
    except ProviderCredentialConfigurationError as exc:
        raise data_connections_service.DataConnectionError(
            str(exc), reason_code=exc.reason_code, status_code=exc.status_code
        ) from exc
    access_token = str(credentials.get("access_token") or "").strip()
    if not access_token:
        raise data_connections_service.DataConnectionError(
            "Reconnect Google to continue.",
            reason_code="org_oauth_credential_required",
            status_code=409,
        )
    expected_scope = get_settings().google_oauth_scope_gbp.strip()
    granted_scopes = str(credentials.get("scope") or "").split()
    if expected_scope and granted_scopes and expected_scope not in granted_scopes:
        raise data_connections_service.DataConnectionError(
            "Connect the Google business listing and approve access first.",
            reason_code="oauth_scope_missing",
            status_code=409,
        )
    return credentials


def _connection_error(
    exc: provider.GoogleBusinessProfileProviderError,
) -> data_connections_service.DataConnectionError:
    return data_connections_service.DataConnectionError(
        str(exc), reason_code=exc.reason_code, status_code=exc.status_code
    )


def _hostname(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized if "://" in normalized else f"https://{normalized}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + (value.month - 1) + offset
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)
