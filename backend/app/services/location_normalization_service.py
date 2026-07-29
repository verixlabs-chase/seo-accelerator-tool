from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.location import Location
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credentials,
)


_US_REGIONS = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
_COUNTRY_NAMES = {
    "US": "United States",
    "CA": "Canada",
    "GB": "United Kingdom",
    "AU": "Australia",
    "NZ": "New Zealand",
}


class LocationContextError(RuntimeError):
    pass


def get_campaign_location_context(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, object]:
    campaign, location = _get_campaign_and_business_location(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    return _context_payload(campaign, location)


def normalize_campaign_location(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, object]:
    campaign, location = _get_campaign_and_business_location(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    attempts: list[dict[str, str]] = []

    if location.latitude is None or location.longitude is None:
        geocode = _resolve_coordinates(location)
        attempts.append(
            {
                "target": "coordinates",
                "status": geocode.get("status", "unavailable"),
                "message": geocode.get("message", "Coordinates could not be resolved."),
            }
        )
        if geocode.get("status") == "resolved":
            location.latitude = Decimal(str(geocode["latitude"]))
            location.longitude = Decimal(str(geocode["longitude"]))
            location.coordinate_precision = str(geocode["precision"])
            location.coordinate_source = "openstreetmap_nominatim"
    else:
        attempts.append(
            {
                "target": "coordinates",
                "status": "already_resolved",
                "message": "Stored coordinates were kept.",
            }
        )

    if not location.provider_location_code or not location.provider_location_name:
        provider = _resolve_dataforseo_location(
            db,
            organization_id=str(campaign.organization_id),
            location=location,
        )
        attempts.append(
            {
                "target": "provider_location",
                "status": provider.get("status", "unavailable"),
                "message": provider.get("message", "Provider location could not be resolved."),
            }
        )
        if provider.get("status") == "resolved":
            location.provider_location_code = str(provider["location_code"])
            location.provider_location_name = str(provider["location_name"])
            location.provider_location_type = str(provider.get("location_type") or "City")
            location.provider_location_resolved_at = datetime.now(UTC)
    else:
        attempts.append(
            {
                "target": "provider_location",
                "status": "already_resolved",
                "message": "Stored DataForSEO location was kept.",
            }
        )

    location.updated_at = datetime.now(UTC)
    _sync_execution_locations(db, location)
    db.flush()
    payload = _context_payload(campaign, location)
    payload["resolution_attempts"] = attempts
    return payload


def _resolve_coordinates(location: BusinessLocation) -> dict[str, Any]:
    city = (location.city or location.primary_city or "").strip()
    region = (location.region or "").strip()
    country_code = (location.country_code or "US").strip().upper()
    if not city:
        return {
            "status": "missing_input",
            "message": "Add a city before resolving the base-map pin.",
        }

    settings = get_settings()
    params: dict[str, str | int] = {
        "city": city,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": country_code.lower(),
    }
    if region:
        params["state"] = _expanded_region(region, country_code)
    if location.address_line1:
        params["street"] = location.address_line1
    if location.postal_code:
        params["postalcode"] = location.postal_code
    headers = {
        "User-Agent": (
            f"SEOAccelerator/1.0 (+{settings.public_base_url.rstrip('/')}; "
            "location setup; one-shot cached geocoding)"
        ),
        "Accept-Language": "en",
    }
    try:
        with httpx.Client(timeout=settings.location_resolver_timeout_seconds) as client:
            response = client.get(
                settings.location_geocoder_endpoint,
                params=params,
                headers=headers,
            )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return {
            "status": "unavailable",
            "message": "The coordinate lookup service is temporarily unavailable.",
        }
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {
            "status": "not_found",
            "message": "No coordinate match was found for the structured location.",
        }
    try:
        latitude = float(rows[0]["lat"])
        longitude = float(rows[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return {
            "status": "invalid_response",
            "message": "The coordinate lookup returned an unusable match.",
        }
    return {
        "status": "resolved",
        "message": "Base-map coordinates were resolved and cached.",
        "latitude": latitude,
        "longitude": longitude,
        "precision": "exact" if location.address_line1 else "city_center",
    }


def _resolve_dataforseo_location(
    db: Session,
    *,
    organization_id: str,
    location: BusinessLocation,
) -> dict[str, Any]:
    city = (location.city or location.primary_city or "").strip()
    region = (location.region or "").strip()
    country_code = (location.country_code or "US").strip().upper()
    if not city or not region:
        return {
            "status": "missing_input",
            "message": "Add both city and state/region before resolving DataForSEO.",
        }
    try:
        credentials = resolve_provider_credentials(
            db,
            organization_id,
            "dataforseo",
            required_credential_mode="byo_optional",
        )
    except ProviderCredentialConfigurationError as exc:
        return {
            "status": "credentials_missing",
            "message": str(exc),
        }
    login = str(credentials.get("login", "")).strip()
    password = str(credentials.get("password", "")).strip()
    if not login or not password:
        return {
            "status": "credentials_missing",
            "message": "Connect DataForSEO before resolving its location identifier.",
        }

    credential = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
    settings = get_settings()
    endpoint = f"{settings.dataforseo_locations_endpoint.rstrip('/')}/{country_code.lower()}"
    try:
        with httpx.Client(timeout=settings.location_resolver_timeout_seconds) as client:
            response = client.get(
                endpoint,
                headers={
                    "Authorization": f"Basic {credential}",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return {
            "status": "unavailable",
            "message": "DataForSEO location metadata is temporarily unavailable.",
        }
    rows = _dataforseo_result_rows(body)
    match = _select_dataforseo_location(
        rows,
        city=city,
        region=region,
        country_code=country_code,
    )
    if match is None:
        return {
            "status": "not_found",
            "message": "DataForSEO did not return an exact city and state/region match.",
        }
    return {
        "status": "resolved",
        "message": "DataForSEO location name and code were resolved and cached.",
        **match,
    }


def _dataforseo_result_rows(body: object) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    tasks = body.get("tasks")
    if not isinstance(tasks, list) or not tasks or not isinstance(tasks[0], dict):
        return []
    result = tasks[0].get("result")
    if not isinstance(result, list):
        return []
    return [row for row in result if isinstance(row, dict)]


def _select_dataforseo_location(
    rows: list[dict[str, Any]],
    *,
    city: str,
    region: str,
    country_code: str,
) -> dict[str, Any] | None:
    city_key = _key(city)
    region_keys = {_key(region), _key(_expanded_region(region, country_code))}
    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        if str(row.get("country_iso_code") or "").upper() != country_code.upper():
            continue
        location_name = str(row.get("location_name") or "").strip()
        parts = [part.strip() for part in location_name.split(",") if part.strip()]
        if not parts or _key(parts[0]) != city_key:
            continue
        middle_keys = {_key(part) for part in parts[1:-1]}
        if region_keys and not region_keys.intersection(middle_keys):
            continue
        location_type = str(row.get("location_type") or "")
        priority = 0 if location_type.casefold() == "city" else 1
        candidates.append((priority, row))
    if not candidates:
        return None
    selected = sorted(
        candidates,
        key=lambda item: (
            item[0],
            len(str(item[1].get("location_name") or "")),
            int(item[1].get("location_code") or 0),
        ),
    )[0][1]
    return {
        "location_code": str(selected.get("location_code")),
        "location_name": ", ".join(
            part.strip()
            for part in str(selected.get("location_name") or "").split(",")
            if part.strip()
        ),
        "location_type": str(selected.get("location_type") or "City"),
    }


def _get_campaign_and_business_location(
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
        raise LocationContextError("campaign_not_found")
    if not campaign.business_location_id:
        raise LocationContextError("business_location_not_assigned")
    location = (
        db.query(BusinessLocation)
        .filter(
            BusinessLocation.id == campaign.business_location_id,
            BusinessLocation.organization_id == campaign.organization_id,
        )
        .first()
    )
    if location is None:
        raise LocationContextError("business_location_not_found")
    return campaign, location


def _context_payload(campaign: Campaign, location: BusinessLocation) -> dict[str, object]:
    city = location.city or location.primary_city
    country_code = (location.country_code or "US").upper()
    address_parts = [
        location.address_line1,
        city,
        location.region,
        location.postal_code,
        _COUNTRY_NAMES.get(country_code, country_code),
    ]
    coordinates_ready = location.latitude is not None and location.longitude is not None
    provider_ready = bool(location.provider_location_code and location.provider_location_name)
    return {
        "campaign_id": campaign.id,
        "business_location_id": location.id,
        "name": location.name,
        "domain": location.domain or campaign.domain,
        "address": {
            "line1": location.address_line1,
            "city": city,
            "region": location.region,
            "postal_code": location.postal_code,
            "country_code": country_code,
            "country_name": _COUNTRY_NAMES.get(country_code, country_code),
            "formatted": ", ".join(str(part) for part in address_parts if part),
        },
        "coordinates": {
            "latitude": float(location.latitude) if location.latitude is not None else None,
            "longitude": float(location.longitude) if location.longitude is not None else None,
            "precision": location.coordinate_precision,
            "source": location.coordinate_source,
            "status": "ready" if coordinates_ready else "missing",
        },
        "provider_location": {
            "code": location.provider_location_code,
            "name": location.provider_location_name,
            "type": location.provider_location_type,
            "resolved_at": (
                location.provider_location_resolved_at.isoformat()
                if location.provider_location_resolved_at
                else None
            ),
            "status": "ready" if provider_ready else "missing",
        },
        "base_map": {
            "status": "ready" if coordinates_ready else "setup_required",
            "coverage_type": "reference_map",
            "message": (
                "Interactive reference map is centered on the stored location."
                if coordinates_ready
                else "Coordinates are required before the reference map can be shown."
            ),
        },
        "map_rank_coverage": {
            "status": "not_enabled",
            "coverage_type": "paid_geo_grid",
            "is_paid": True,
            "message": (
                "Paid geo-grid ranking coverage is not enabled. "
                "The base map does not represent search rankings."
            ),
        },
    }


def _sync_execution_locations(db: Session, location: BusinessLocation) -> None:
    rows = (
        db.query(Location)
        .filter(
            Location.organization_id == location.organization_id,
            Location.business_location_id == location.id,
        )
        .all()
    )
    for row in rows:
        row.country_code = location.country_code
        row.region = location.region
        row.city = location.city or location.primary_city
        row.lat = location.latitude
        row.lng = location.longitude
        row.updated_at = datetime.now(UTC)


def _expanded_region(region: str, country_code: str) -> str:
    normalized = region.strip()
    if country_code.upper() == "US":
        return _US_REGIONS.get(normalized.upper(), normalized)
    return normalized


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())
