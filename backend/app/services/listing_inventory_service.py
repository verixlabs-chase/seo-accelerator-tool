from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.authority import DirectoryListing, DirectoryListingObservation
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign


PUBLIC_LISTING_FIELDS = (
    "business_name",
    "address_line1",
    "city",
    "region",
    "postal_code",
    "country_code",
    "phone",
    "website_url",
    "primary_category",
)
ALLOWED_STATUSES = {
    "correct",
    "inconsistent",
    "missing",
    "duplicate",
    "submitted",
    "live",
    "verified",
    "unavailable",
}
ALLOWED_IMPORTANCE = {"essential", "important", "standard", "unknown"}


def _campaign_context(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> tuple[Campaign, BusinessLocation]:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .first()
    )
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.organization_id or not campaign.business_location_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose a business location before checking directory listings.",
        )
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None or location.organization_id != campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The business location for this campaign is unavailable.",
        )
    return campaign, location


def list_inventory(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> list[DirectoryListing]:
    _campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    return (
        db.query(DirectoryListing)
        .filter(
            DirectoryListing.tenant_id == tenant_id,
            DirectoryListing.business_location_id == location.id,
        )
        .order_by(
            DirectoryListing.status.asc(),
            DirectoryListing.directory_importance.asc(),
            DirectoryListing.source_name.asc(),
        )
        .all()
    )


def inventory_summary(rows: list[DirectoryListing]) -> dict[str, Any]:
    counts = {item: 0 for item in sorted(ALLOWED_STATUSES)}
    fresh_rows = [row for row in rows if row.source_type != "imported"]
    imported_rows = [row for row in rows if row.source_type == "imported"]
    for row in fresh_rows:
        if row.status in counts:
            counts[row.status] += 1
    needs_attention = counts["inconsistent"] + counts["missing"] + counts["duplicate"]
    latest = max((row.last_seen_at for row in fresh_rows), default=None)
    return {
        "total": len(rows),
        "freshly_checked": len(fresh_rows),
        "imported_history": len(imported_rows),
        "needs_attention": needs_attention,
        "confirmed": counts["correct"] + counts["verified"],
        "counts": counts,
        "newest_observation_at": latest,
    }


def upsert_discovered_listings(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    records: list[dict[str, Any]],
    observed_at: datetime | None = None,
) -> list[DirectoryListing]:
    campaign, location = _campaign_context(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    observation_time = _as_utc(observed_at or datetime.now(UTC))
    saved: list[DirectoryListing] = []

    for raw_record in records:
        record = _sanitize_record(raw_record)
        source_key = _required_text(record, "source_key", maximum=100)
        source_name = _required_text(record, "source_name", maximum=160)
        provider_name = _required_text(record, "provider_name", maximum=100)
        external_id = _external_id(record, source_key=source_key)
        observed_fields = {
            key: record.get(key)
            for key in (*PUBLIC_LISTING_FIELDS, "listing_url")
            if record.get(key) not in (None, "")
        }
        differences, comparable_fields = compare_listing_fields(
            location=location,
            observed_fields=observed_fields,
        )
        listing_status = classify_listing(
            requested_status=str(record.get("status") or "").strip().lower(),
            differences=differences,
            comparable_fields=comparable_fields,
        )
        confidence = _confidence(record.get("confidence"), differences, comparable_fields)
        importance = str(record.get("directory_importance") or "unknown").strip().lower()
        if importance not in ALLOWED_IMPORTANCE:
            importance = "unknown"

        row = (
            db.query(DirectoryListing)
            .filter(
                DirectoryListing.tenant_id == tenant_id,
                DirectoryListing.business_location_id == location.id,
                DirectoryListing.source_key == source_key,
                DirectoryListing.external_id == external_id,
            )
            .first()
        )
        if row is None:
            row = DirectoryListing(
                tenant_id=tenant_id,
                organization_id=str(campaign.organization_id),
                campaign_id=campaign.id,
                business_location_id=location.id,
                source_key=source_key,
                source_name=source_name,
                provider_name=provider_name,
                external_id=external_id,
                first_seen_at=observation_time,
                created_at=observation_time,
                last_seen_at=observation_time,
                updated_at=observation_time,
            )
            db.add(row)
            db.flush()

        row.source_name = source_name
        row.provider_name = provider_name
        row.listing_url = _optional_text(record.get("listing_url"))
        row.status = listing_status
        for key in PUBLIC_LISTING_FIELDS:
            setattr(row, key, _optional_text(record.get(key)))
        row.observed_fields = observed_fields
        row.field_differences = differences
        row.directory_importance = importance
        row.confidence = confidence
        row.last_seen_at = observation_time
        row.last_verified_at = observation_time if listing_status in {"correct", "verified"} else None
        row.updated_at = observation_time

        evidence_digest = _evidence_digest(
            status=listing_status,
            observed_fields=observed_fields,
            differences=differences,
        )
        existing_observation = (
            db.query(DirectoryListingObservation)
            .filter(
                DirectoryListingObservation.listing_id == row.id,
                DirectoryListingObservation.evidence_digest == evidence_digest,
            )
            .first()
        )
        if existing_observation is None:
            db.add(
                DirectoryListingObservation(
                    tenant_id=tenant_id,
                    organization_id=str(campaign.organization_id),
                    campaign_id=campaign.id,
                    business_location_id=location.id,
                    listing_id=row.id,
                    status=listing_status,
                    observed_fields=observed_fields,
                    field_differences=differences,
                    confidence=confidence,
                    evidence_digest=evidence_digest,
                    observed_at=observation_time,
                )
            )
        saved.append(row)

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="directory_listings.inventory.updated",
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


def compare_listing_fields(
    *,
    location: BusinessLocation,
    observed_fields: dict[str, Any],
) -> tuple[list[dict[str, str]], int]:
    expected = {
        "business_name": location.name,
        "address_line1": location.address_line1,
        "city": location.city or location.primary_city,
        "region": location.region,
        "postal_code": location.postal_code,
        "country_code": location.country_code,
        "website_url": location.domain,
    }
    differences: list[dict[str, str]] = []
    comparable = 0
    for field, expected_value in expected.items():
        observed_value = observed_fields.get(field)
        if expected_value in (None, "") or observed_value in (None, ""):
            continue
        comparable += 1
        if _comparison_value(field, expected_value) != _comparison_value(field, observed_value):
            differences.append(
                {
                    "field": field,
                    "expected": str(expected_value).strip(),
                    "found": str(observed_value).strip(),
                }
            )
    return differences, comparable


def classify_listing(
    *,
    requested_status: str,
    differences: list[dict[str, str]],
    comparable_fields: int,
) -> str:
    if requested_status in {"missing", "duplicate", "submitted", "unavailable"}:
        return requested_status
    if differences:
        return "inconsistent"
    if requested_status == "verified":
        return "verified"
    if comparable_fields > 0:
        return "correct"
    return "live"


def _comparison_value(field: str, value: Any) -> str:
    text = str(value or "").strip()
    if field == "website_url":
        candidate = text if "://" in text else f"https://{text}"
        parsed = urlparse(candidate)
        host = (parsed.netloc or parsed.path).lower().split(":", 1)[0]
        return host[4:] if host.startswith("www.") else host
    if field == "country_code":
        return text.upper()
    if field == "address_line1":
        suffixes = {
            "street": "st",
            "st": "st",
            "road": "rd",
            "rd": "rd",
            "avenue": "ave",
            "ave": "ave",
            "boulevard": "blvd",
            "blvd": "blvd",
            "drive": "dr",
            "dr": "dr",
            "lane": "ln",
            "ln": "ln",
            "court": "ct",
            "ct": "ct",
            "highway": "hwy",
            "hwy": "hwy",
            "parkway": "pkwy",
            "pkwy": "pkwy",
        }
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        return "".join(suffixes.get(token, token) for token in tokens)
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "source_key",
        "source_name",
        "provider_name",
        "external_id",
        "listing_url",
        "status",
        "directory_importance",
        "confidence",
        *PUBLIC_LISTING_FIELDS,
    }
    return {key: value for key, value in record.items() if key in allowed}


def _required_text(record: dict[str, Any], key: str, *, maximum: int) -> str:
    value = str(record.get(key) or "").strip()
    if not value:
        raise ValueError(f"Listing record requires {key}.")
    return value[:maximum]


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _external_id(record: dict[str, Any], *, source_key: str) -> str:
    explicit = str(record.get("external_id") or "").strip()
    if explicit:
        return explicit[:255]
    identity = "|".join(
        str(record.get(key) or "").strip().casefold()
        for key in ("listing_url", "business_name", "address_line1", "city", "region")
    )
    if not identity.replace("|", ""):
        raise ValueError("Listing record requires an external identifier or public business details.")
    return sha256(f"{source_key}|{identity}".encode("utf-8")).hexdigest()


def _confidence(value: Any, differences: list[dict[str, str]], comparable_fields: int) -> float:
    if value not in (None, ""):
        try:
            return round(max(0.0, min(float(value), 1.0)), 4)
        except (TypeError, ValueError):
            pass
    if comparable_fields == 0:
        return 0.5
    return round(max(0.0, (comparable_fields - len(differences)) / comparable_fields), 4)


def _evidence_digest(
    *,
    status: str,
    observed_fields: dict[str, Any],
    differences: list[dict[str, str]],
) -> str:
    payload = json.dumps(
        {"status": status, "observed_fields": observed_fields, "field_differences": differences},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
