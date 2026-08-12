from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.website_analytics import WebsiteFormEvent
from app.services.data_connections_service import (
    CONNECTION_STATUS_DISCONNECTED,
    GOOGLE_ANALYTICS_PROVIDER,
)


ALLOWED_EVENT_NAMES = {"form_submitted", "inquiry_confirmed"}
TOKEN_HASH_KEY = "website_event_token_hash"
TOKEN_CREATED_AT_KEY = "website_event_token_created_at"


class WebsiteEventError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def rotate_ingest_token(
    db: Session,
    *,
    organization_id: str,
    connection_id: str,
) -> dict[str, str]:
    connection = _analytics_connection(
        db,
        connection_id=connection_id,
        organization_id=organization_id,
    )
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    connection.connection_metadata = {
        **dict(connection.connection_metadata or {}),
        TOKEN_HASH_KEY: _token_hash(raw_token),
        TOKEN_CREATED_AT_KEY: now.isoformat(),
    }
    connection.updated_at = now
    db.commit()
    return {
        "token": raw_token,
        "created_at": now.isoformat(),
        "connection_id": connection.id,
        "event_path": f"/api/v1/website-events/forms/{connection.id}",
    }


def ingest_form_event(
    db: Session,
    *,
    connection_id: str,
    bearer_token: str,
    event_id: str,
    event_name: str,
    page_url: str,
    form_id: str | None,
    occurred_at: datetime,
) -> dict[str, object]:
    connection = _analytics_connection(db, connection_id=connection_id)
    expected_hash = str((connection.connection_metadata or {}).get(TOKEN_HASH_KEY) or "")
    supplied_hash = _token_hash(bearer_token)
    if not expected_hash or not secrets.compare_digest(expected_hash, supplied_hash):
        raise WebsiteEventError(
            "The website event connection key is invalid.",
            reason_code="website_event_key_invalid",
            status_code=401,
        )
    normalized_event_name = event_name.strip().lower()
    if normalized_event_name not in ALLOWED_EVENT_NAMES:
        raise WebsiteEventError(
            "This website event type is not allowed.",
            reason_code="website_event_type_not_allowed",
        )
    campaign = db.get(Campaign, connection.campaign_id)
    if campaign is None or campaign.organization_id != connection.organization_id:
        raise WebsiteEventError(
            "The website event connection is no longer mapped to a business.",
            reason_code="website_event_mapping_invalid",
            status_code=409,
        )

    normalized_occurred_at = _normalize_occurred_at(occurred_at)
    normalized_page_url = _normalize_page_url(page_url, campaign.domain)
    normalized_event_id = event_id.strip()
    normalized_form_id = (form_id or "").strip() or None
    existing = (
        db.query(WebsiteFormEvent)
        .filter(
            WebsiteFormEvent.data_connection_id == connection.id,
            WebsiteFormEvent.event_id == normalized_event_id,
        )
        .first()
    )
    if existing is not None:
        if (
            existing.event_name != normalized_event_name
            or existing.page_url != normalized_page_url
            or existing.form_id != normalized_form_id
            or _as_aware(existing.occurred_at) != normalized_occurred_at
        ):
            raise WebsiteEventError(
                "This event identifier was already used for different website activity.",
                reason_code="website_event_id_conflict",
                status_code=409,
            )
        return {"accepted": True, "duplicate": True, "event_id": normalized_event_id}

    row = WebsiteFormEvent(
        tenant_id=connection.tenant_id,
        organization_id=connection.organization_id,
        business_location_id=connection.business_location_id,
        campaign_id=connection.campaign_id,
        data_connection_id=connection.id,
        event_id=normalized_event_id,
        event_name=normalized_event_name,
        website=_normalize_website(campaign.domain),
        page_url=normalized_page_url,
        form_id=normalized_form_id,
        occurred_at=normalized_occurred_at,
        received_at=datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return {"accepted": True, "duplicate": False, "event_id": normalized_event_id}


def _analytics_connection(
    db: Session,
    *,
    connection_id: str,
    organization_id: str | None = None,
) -> DataConnection:
    query = db.query(DataConnection).filter(
        DataConnection.id == connection_id,
        DataConnection.provider_name == GOOGLE_ANALYTICS_PROVIDER,
    )
    if organization_id is not None:
        query = query.filter(DataConnection.organization_id == organization_id)
    connection = query.first()
    if connection is None:
        raise WebsiteEventError(
            "Website analytics connection not found.",
            reason_code="website_event_connection_not_found",
            status_code=404,
        )
    if connection.status == CONNECTION_STATUS_DISCONNECTED:
        raise WebsiteEventError(
            "Website analytics connection is disconnected.",
            reason_code="website_event_connection_disconnected",
            status_code=409,
        )
    return connection


def _token_hash(raw_token: str) -> str:
    return sha256(raw_token.strip().encode("utf-8")).hexdigest()


def _normalize_occurred_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise WebsiteEventError(
            "Website event time must include a time zone.",
            reason_code="website_event_timezone_required",
        )
    normalized = value.astimezone(UTC)
    now = datetime.now(UTC)
    if normalized < now - timedelta(days=7) or normalized > now + timedelta(minutes=5):
        raise WebsiteEventError(
            "Website event time is outside the accepted delivery window.",
            reason_code="website_event_time_out_of_range",
        )
    return normalized


def _normalize_page_url(page_url: str, campaign_domain: str) -> str:
    parsed = urlparse(page_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WebsiteEventError(
            "Website event page must be a valid website URL.",
            reason_code="website_event_page_invalid",
        )
    page_host = (parsed.hostname or "").lower().removeprefix("www.")
    campaign_host = _campaign_host(campaign_domain)
    if page_host != campaign_host and not page_host.endswith(f".{campaign_host}"):
        raise WebsiteEventError(
            "Website event page does not belong to this business website.",
            reason_code="website_event_page_mismatch",
        )
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", "", ""))


def _normalize_website(campaign_domain: str) -> str:
    return f"https://{_campaign_host(campaign_domain)}"


def _campaign_host(campaign_domain: str) -> str:
    raw = campaign_domain.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        raise WebsiteEventError(
            "The mapped business website is invalid.",
            reason_code="website_event_mapping_invalid",
            status_code=409,
        )
    return host


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
