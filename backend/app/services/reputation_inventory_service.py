from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.events import emit_event
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.data_connection import DataConnection
from app.models.reputation import ReputationReview, ReputationReviewObservation
from app.providers.google_reviews import GoogleBusinessProfileReviewsProvider
from app.services import data_connections_service
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credentials,
)


SOURCE_TYPES = {"owned_profile", "public_competitor"}
RESPONSE_STATUSES = {"unanswered", "responded", "removed", "unavailable"}
SNAPSHOT_FIELDS = (
    "rating",
    "body",
    "author_name",
    "author_is_anonymous",
    "response_status",
    "response_text",
    "response_updated_at",
    "reviewed_at",
    "provider_updated_at",
)
OWNED_PROFILE_PROVIDER = "google_business_profile"
MAX_OWNED_REVIEW_PAGES = 20
OWNED_REVIEW_PAGE_SIZE = 50


def sync_owned_profile_reviews(
    db: Session,
    *,
    connection: DataConnection,
) -> dict[str, Any]:
    """Collect owned-profile reviews without enabling drafting or reply mutations."""
    if (
        connection.provider_name != OWNED_PROFILE_PROVIDER
        or connection.status == data_connections_service.CONNECTION_STATUS_DISCONNECTED
    ):
        raise ValueError("The connected business listing is not available for review updates.")

    campaign, location = _campaign_context(
        db,
        tenant_id=connection.tenant_id,
        organization_id=connection.organization_id,
        campaign_id=connection.campaign_id,
    )
    if location.id != connection.business_location_id:
        raise ValueError("The business listing is no longer matched to this location.")

    metadata = dict(connection.connection_metadata or {})
    account_id = str(metadata.get("account_id") or "").strip().strip("/")
    location_id = str(connection.external_resource_id or "").strip().strip("/")
    if not account_id.startswith("accounts/") or not location_id.startswith("locations/"):
        raise ValueError(
            "Match this location to its Google business listing again before reviews can update."
        )

    provider = GoogleBusinessProfileReviewsProvider(
        access_token=_google_access_token(db, connection.organization_id),
        timeout_seconds=float(get_settings().google_oauth_http_timeout_seconds),
    )
    parent = f"{account_id}/{location_id}"
    page_token: str | None = None
    records: list[dict[str, Any]] = []
    provider_total: int | None = None
    provider_average: float | None = None
    pages_received = 0
    truncated = False

    for _page_number in range(MAX_OWNED_REVIEW_PAGES):
        page = provider.list_reviews(
            parent=parent,
            page_size=OWNED_REVIEW_PAGE_SIZE,
            page_token=page_token,
        )
        pages_received += 1
        records.extend(page["items"])
        if provider_total is None:
            provider_total = page.get("total_review_count")
            provider_average = page.get("average_rating")
        page_token = page.get("next_page_token")
        if not page_token:
            break
    else:
        truncated = bool(page_token)

    saved = upsert_reviews(
        db,
        tenant_id=connection.tenant_id,
        organization_id=connection.organization_id,
        campaign_id=campaign.id,
        records=records,
    )
    synced_at = datetime.now(UTC)
    cursor = dict(connection.sync_cursor or {})
    cursor["owned_reviews"] = {
        "synced_at": synced_at.isoformat(),
        "reviews_received": len(records),
        "pages_received": pages_received,
        "truncated": truncated,
    }
    connection.sync_cursor = cursor
    connection.connection_metadata = {
        **metadata,
        "owned_reviews": {
            "last_success_at": synced_at.isoformat(),
            "provider_total": provider_total,
            "provider_average_rating": provider_average,
            "saved_count": len(saved),
            "truncated": truncated,
            "reply_mutations_enabled": False,
        },
    }
    connection.updated_at = synced_at
    db.commit()
    return {
        "connection_id": connection.id,
        "campaign_id": campaign.id,
        "business_location_id": location.id,
        "reviews_received": len(records),
        "reviews_saved": len(saved),
        "pages_received": pages_received,
        "provider_total": provider_total,
        "provider_average_rating": provider_average,
        "truncated": truncated,
        "synced_at": synced_at.isoformat(),
        "reply_mutations_enabled": False,
    }


def _campaign_context(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.tenant_id == tenant_id,
            Campaign.organization_id == organization_id,
        )
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None or location.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a business location before loading reviews.",
        )
    return campaign, location


def upsert_reviews(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    records: list[dict[str, Any]],
    captured_at: datetime | None = None,
) -> list[ReputationReview]:
    campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    capture_time = _as_utc(captured_at or datetime.now(UTC))
    saved: list[ReputationReview] = []
    for record in records:
        normalized = _normalize_record(record)
        row = (
            db.query(ReputationReview)
            .filter(
                ReputationReview.tenant_id == tenant_id,
                ReputationReview.business_location_id == location.id,
                ReputationReview.source_key == normalized["source_key"],
                ReputationReview.external_review_id == normalized["external_review_id"],
            )
            .first()
        )
        if row is None:
            row = ReputationReview(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign.id,
                business_location_id=location.id,
                source_key=normalized["source_key"],
                source_name=normalized["source_name"],
                source_type=normalized["source_type"],
                provider_name=normalized["provider_name"],
                external_review_id=normalized["external_review_id"],
                reviewed_at=normalized["reviewed_at"],
                first_seen_at=capture_time,
                last_seen_at=capture_time,
                created_at=capture_time,
                updated_at=capture_time,
                rating=normalized["rating"],
            )
            db.add(row)
            db.flush()

        for field, value in normalized.items():
            if field not in {"source_key", "external_review_id"}:
                setattr(row, field, value)
        row.last_seen_at = capture_time
        row.updated_at = capture_time
        snapshot = {key: _json_value(getattr(row, key)) for key in SNAPSHOT_FIELDS}
        digest = sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        observation = (
            db.query(ReputationReviewObservation)
            .filter(
                ReputationReviewObservation.review_id == row.id,
                ReputationReviewObservation.evidence_digest == digest,
            )
            .first()
        )
        if observation is None:
            db.add(
                ReputationReviewObservation(
                    tenant_id=tenant_id,
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    business_location_id=location.id,
                    review_id=row.id,
                    snapshot=snapshot,
                    evidence_digest=digest,
                    captured_at=capture_time,
                )
            )
        saved.append(row)

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="reputation.reviews.inventory.updated",
        payload={
            "campaign_id": campaign.id,
            "business_location_id": location.id,
            "records_received": len(records),
            "records_saved": len(saved),
        },
    )
    db.commit()
    for row in saved:
        db.refresh(row)
    return saved


def list_reviews(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    source_type: str | None = None,
    response_status: str | None = None,
    rating_lte: float | None = None,
    limit: int = 100,
) -> list[ReputationReview]:
    _campaign_context(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    query = db.query(ReputationReview).filter(
        ReputationReview.tenant_id == tenant_id,
        ReputationReview.organization_id == organization_id,
        ReputationReview.campaign_id == campaign_id,
    )
    if source_type:
        if source_type not in SOURCE_TYPES:
            raise HTTPException(status_code=400, detail="Review source filter is invalid.")
        query = query.filter(ReputationReview.source_type == source_type)
    if response_status:
        if response_status not in RESPONSE_STATUSES:
            raise HTTPException(status_code=400, detail="Review response filter is invalid.")
        query = query.filter(ReputationReview.response_status == response_status)
    if rating_lte is not None:
        query = query.filter(ReputationReview.rating <= max(1.0, min(float(rating_lte), 5.0)))
    return (
        query.order_by(ReputationReview.reviewed_at.desc())
        .limit(max(1, min(int(limit), 250)))
        .all()
    )


def inventory_summary(rows: list[ReputationReview]) -> dict[str, Any]:
    total = len(rows)
    unanswered = sum(row.response_status == "unanswered" for row in rows)
    responded = sum(row.response_status == "responded" for row in rows)
    low_rating = sum(row.rating <= 3 for row in rows)
    average = round(sum(row.rating for row in rows) / total, 2) if total else None
    newest = max((row.last_seen_at for row in rows), default=None)
    return {
        "total": total,
        "unanswered": unanswered,
        "responded": responded,
        "rating_three_or_lower": low_rating,
        "average_rating": average,
        "newest_observation_at": newest,
    }


def google_access_token(db: Session, organization_id: str) -> str:
    """Return the scoped Google token used by owned-profile review operations."""
    return _google_access_token(db, organization_id)


def record_owned_reply(
    db: Session,
    *,
    review: ReputationReview,
    response_text: str,
    response_updated_at: datetime | None,
    captured_at: datetime | None = None,
) -> ReputationReviewObservation:
    """Record a provider-confirmed reply and its immutable evidence snapshot."""
    capture_time = _as_utc(captured_at or datetime.now(UTC))
    review.response_status = "responded"
    review.response_text = response_text.strip()
    review.response_updated_at = _as_utc(response_updated_at or capture_time)
    review.provider_updated_at = review.response_updated_at
    review.last_seen_at = capture_time
    review.updated_at = capture_time

    snapshot = {key: _json_value(getattr(review, key)) for key in SNAPSHOT_FIELDS}
    digest = sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    observation = (
        db.query(ReputationReviewObservation)
        .filter(
            ReputationReviewObservation.review_id == review.id,
            ReputationReviewObservation.evidence_digest == digest,
        )
        .first()
    )
    if observation is None:
        observation = ReputationReviewObservation(
            tenant_id=review.tenant_id,
            organization_id=review.organization_id,
            campaign_id=review.campaign_id,
            business_location_id=review.business_location_id,
            review_id=review.id,
            snapshot=snapshot,
            evidence_digest=digest,
            captured_at=capture_time,
        )
        db.add(observation)
    emit_event(
        db,
        tenant_id=review.tenant_id,
        event_type="reputation.review.reply.confirmed",
        payload={
            "organization_id": review.organization_id,
            "campaign_id": review.campaign_id,
            "business_location_id": review.business_location_id,
            "review_id": review.id,
            "evidence_digest": digest,
        },
    )
    db.flush()
    return observation


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    source_type = str(record.get("source_type") or "").strip().lower()
    response_status = str(record.get("response_status") or "unanswered").strip().lower()
    if source_type not in SOURCE_TYPES:
        raise ValueError("Review source type is invalid.")
    if response_status not in RESPONSE_STATUSES:
        raise ValueError("Review response status is invalid.")
    rating = float(record.get("rating") or 0)
    if rating < 1 or rating > 5:
        raise ValueError("Review rating must be between 1 and 5.")
    response_text = _text(record.get("response_text"))
    if response_status == "responded" and not response_text:
        response_status = "unanswered"
    reviewed_at = _datetime(record.get("reviewed_at"))
    if reviewed_at is None:
        raise ValueError("Review date is required.")
    return {
        "source_key": _required_text(record, "source_key", 100),
        "source_name": _required_text(record, "source_name", 160),
        "source_type": source_type,
        "provider_name": _required_text(record, "provider_name", 100),
        "external_review_id": _required_text(record, "external_review_id", 255),
        "external_resource_name": _text(record.get("external_resource_name")),
        "review_url": _text(record.get("review_url")),
        "rating": rating,
        "body": _text(record.get("body")),
        "author_name": _text(record.get("author_name"), maximum=255),
        "author_is_anonymous": bool(record.get("author_is_anonymous")),
        "response_status": response_status,
        "response_text": response_text,
        "response_updated_at": _datetime(record.get("response_updated_at")),
        "reviewed_at": reviewed_at,
        "provider_updated_at": _datetime(record.get("provider_updated_at")),
    }


def _required_text(record: dict[str, Any], key: str, maximum: int) -> str:
    value = str(record.get(key) or "").strip()
    if not value:
        raise ValueError(f"Review field '{key}' is required.")
    return value[:maximum]


def _text(value: Any, maximum: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:maximum] if maximum else text


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _google_access_token(db: Session, organization_id: str) -> str:
    try:
        credentials = resolve_provider_credentials(
            db,
            organization_id,
            "google",
            required_credential_mode="byo_required",
            require_org_oauth=True,
        )
    except ProviderCredentialConfigurationError as exc:
        raise ValueError(str(exc)) from exc
    access_token = str(credentials.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Reconnect Google before reviews can update.")
    expected_scope = get_settings().google_oauth_scope_gbp.strip()
    granted_scopes = str(credentials.get("scope") or "").split()
    if expected_scope and granted_scopes and expected_scope not in granted_scopes:
        raise ValueError("Approve business listing access before reviews can update.")
    return access_token
