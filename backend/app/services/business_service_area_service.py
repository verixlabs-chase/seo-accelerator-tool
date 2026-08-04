from __future__ import annotations

import html
import math
import re
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.business_location import BusinessLocation
from app.models.business_service_area import BusinessServiceArea
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, Page


AREA_TYPES = {"city", "postal_code", "county", "radius"}
AREA_RELATIONSHIPS = {"included", "excluded"}
MAX_NEARBY_COMMUNITIES = 30
NearbyCommunityResolver = Callable[[float, float, float], list[dict[str, Any]]]
_AREA_PATH_MARKERS = {
    "areas-we-serve",
    "locations",
    "service-area",
    "service-areas",
    "service-locations",
}
_NON_AREA_WORDS = {
    "about",
    "blog",
    "contact",
    "home",
    "location",
    "locations",
    "service area",
    "service areas",
}


def _campaign_or_404(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if not campaign.organization_id or not campaign.business_location_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assign this business to a location before adding service areas.",
        )
    return campaign


def get_profile(db: Session, *, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    location = db.get(BusinessLocation, campaign.business_location_id)
    rows = (
        db.query(BusinessServiceArea)
        .filter(
            BusinessServiceArea.tenant_id == tenant_id,
            BusinessServiceArea.organization_id == campaign.organization_id,
            BusinessServiceArea.business_location_id == campaign.business_location_id,
        )
        .all()
    )
    status_order = {"confirmed": 0, "suggested": 1, "rejected": 2}
    rows.sort(
        key=lambda row: (
            status_order.get(row.status, 9),
            row.relationship != "included",
            row.name.casefold(),
        )
    )
    items = [_serialize(row) for row in rows]
    active_radius = next(
        (
            row
            for row in sorted(
                rows,
                key=lambda item: item.reviewed_at or item.updated_at or item.created_at,
                reverse=True,
            )
            if row.area_type == "radius"
            and row.relationship == "included"
            and row.status == "confirmed"
        ),
        None,
    )
    return {
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "items": items,
        "summary": {
            "confirmed_included": sum(
                item["status"] == "confirmed" and item["relationship"] == "included"
                for item in items
            ),
            "confirmed_excluded": sum(
                item["status"] == "confirmed" and item["relationship"] == "excluded"
                for item in items
            ),
            "suggested": sum(item["status"] == "suggested" for item in items),
        },
        "map": {
            "status": (
                "ready"
                if location is not None
                and location.latitude is not None
                and location.longitude is not None
                else "setup_required"
            ),
            "center_latitude": (
                float(location.latitude)
                if location is not None and location.latitude is not None
                else None
            ),
            "center_longitude": (
                float(location.longitude)
                if location is not None and location.longitude is not None
                else None
            ),
            "radius_miles": float(active_radius.radius_miles) if active_radius else 25.0,
            "radius_saved": active_radius is not None,
        },
    }


def add_manual_area(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    area_type: str,
    name: str | None,
    region: str | None,
    country_code: str,
    radius_miles: float | None,
    relationship: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if area_type not in AREA_TYPES or relationship not in AREA_RELATIONSHIPS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid service area")
    if area_type == "radius":
        if radius_miles is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a service radius")
        if location.latitude is None or location.longitude is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Add this location's map position before using a mileage radius.",
            )
        display_name = f"Within {float(radius_miles):g} miles"
        normalized_name = f"radius:{float(radius_miles):g}"
    else:
        display_name = _display_name(name or "")
        normalized_name = _normalize(display_name)
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Enter the city, ZIP code, or county.",
            )
    resolved_now = now or datetime.now(UTC)
    if area_type == "radius" and relationship == "included":
        previous_radii = (
            db.query(BusinessServiceArea)
            .filter(
                BusinessServiceArea.business_location_id == campaign.business_location_id,
                BusinessServiceArea.area_type == "radius",
                BusinessServiceArea.relationship == "included",
                BusinessServiceArea.status == "confirmed",
                BusinessServiceArea.normalized_name != normalized_name,
            )
            .all()
        )
        for previous in previous_radii:
            previous.status = "rejected"
            previous.reviewed_at = resolved_now
            previous.updated_at = resolved_now
    row = _find_area(
        db,
        business_location_id=str(campaign.business_location_id),
        area_type=area_type,
        normalized_name=normalized_name,
        relationship=relationship,
    )
    if row is None:
        row = BusinessServiceArea(
            tenant_id=tenant_id,
            organization_id=str(campaign.organization_id),
            business_location_id=str(campaign.business_location_id),
            area_type=area_type,
            name=display_name,
            normalized_name=normalized_name,
            region=_optional(region),
            country_code=country_code.strip().upper(),
            radius_miles=radius_miles,
            center_latitude=float(location.latitude) if location.latitude is not None else None,
            center_longitude=float(location.longitude) if location.longitude is not None else None,
            relationship=relationship,
            status="confirmed",
            source="manual",
            confidence=1.0,
            evidence=[{"source": "owner", "note": "Added by the business"}],
            reviewed_at=resolved_now,
            created_at=resolved_now,
            updated_at=resolved_now,
        )
        db.add(row)
    else:
        row.name = display_name
        row.region = _optional(region)
        row.country_code = country_code.strip().upper()
        row.radius_miles = radius_miles
        row.center_latitude = float(location.latitude) if location.latitude is not None else None
        row.center_longitude = float(location.longitude) if location.longitude is not None else None
        row.status = "confirmed"
        row.source = "manual"
        row.confidence = 1.0
        row.reviewed_at = resolved_now
        row.updated_at = resolved_now
    db.commit()
    return get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)


def suggest_areas(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    resolved_now = now or datetime.now(UTC)
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    if location.city or location.primary_city:
        city = _display_name(location.city or location.primary_city or "")
        candidates[("city", _normalize(city))] = {
            "area_type": "city",
            "name": city,
            "region": location.region,
            "country_code": location.country_code,
            "confidence": 0.7,
            "evidence": [{"source": "location", "note": "This is the location's city"}],
        }
    if location.postal_code:
        postal = location.postal_code.strip().upper()
        candidates[("postal_code", _normalize(postal))] = {
            "area_type": "postal_code",
            "name": postal,
            "region": location.region,
            "country_code": location.country_code,
            "confidence": 0.7,
            "evidence": [{"source": "location", "note": "This is the location's ZIP or postal code"}],
        }

    crawl_rows = (
        db.query(CrawlPageResult, Page)
        .join(Page, Page.id == CrawlPageResult.page_id)
        .filter(
            CrawlPageResult.tenant_id == tenant_id,
            CrawlPageResult.campaign_id == campaign.id,
            CrawlPageResult.is_indexable == 1,
        )
        .order_by(CrawlPageResult.crawled_at.desc())
        .limit(160)
        .all()
    )
    seen_pages: set[str] = set()
    for result, page in crawl_rows:
        if page.url in seen_pages:
            continue
        seen_pages.add(page.url)
        for candidate_name in _page_area_candidates(
            result.title,
            page.url,
            heading_text=result.heading_text,
        ):
            normalized = _normalize(candidate_name)
            if not normalized or normalized in _NON_AREA_WORDS:
                continue
            key = ("city", normalized)
            evidence = {
                "source": "website",
                "url": page.url,
                "title": result.title,
                "heading": (result.heading_text or "")[:320] or None,
            }
            current = candidates.get(key)
            if current is None:
                candidates[key] = {
                    "area_type": "city",
                    "name": candidate_name,
                    "region": location.region,
                    "country_code": location.country_code,
                    "confidence": 0.65,
                    "evidence": [evidence],
                }
            elif evidence not in current["evidence"]:
                current["evidence"].append(evidence)

    created_count = 0
    updated_count = 0
    for (area_type, normalized_name), candidate in candidates.items():
        row = _find_area(
            db,
            business_location_id=str(campaign.business_location_id),
            area_type=area_type,
            normalized_name=normalized_name,
            relationship="included",
        )
        if row is None:
            db.add(
                BusinessServiceArea(
                    tenant_id=tenant_id,
                    organization_id=str(campaign.organization_id),
                    business_location_id=str(campaign.business_location_id),
                    area_type=area_type,
                    name=candidate["name"],
                    normalized_name=normalized_name,
                    region=candidate["region"],
                    country_code=candidate["country_code"],
                    relationship="included",
                    status="suggested",
                    source="website" if any(
                        item.get("source") == "website" for item in candidate["evidence"]
                    ) else "location",
                    confidence=candidate["confidence"],
                    evidence=candidate["evidence"][:8],
                    created_at=resolved_now,
                    updated_at=resolved_now,
                )
            )
            created_count += 1
        elif row.status == "suggested":
            row.evidence = _merge_evidence(row.evidence, candidate["evidence"])
            row.confidence = max(float(row.confidence or 0), candidate["confidence"])
            row.updated_at = resolved_now
            updated_count += 1
    db.commit()
    payload = get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)
    payload["discovery"] = {
        "pages_reviewed": len(seen_pages),
        "created": created_count,
        "updated": updated_count,
        "message": (
            "Review the places we found. A place will not affect search ideas until you confirm it."
            if candidates
            else "No clear service areas were found. Add the cities, ZIP codes, or counties you serve."
        ),
    }
    return payload


def suggest_nearby_communities(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    radius_miles: float,
    resolver: NearbyCommunityResolver | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if radius_miles < 1 or radius_miles > 75:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a radius from 1 to 75 miles.",
        )
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    location = db.get(BusinessLocation, campaign.business_location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if location.latitude is None or location.longitude is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add this location's map position before finding nearby communities.",
        )

    resolved_now = now or datetime.now(UTC)
    add_manual_area(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        area_type="radius",
        name=None,
        region=location.region,
        country_code=location.country_code,
        radius_miles=radius_miles,
        relationship="included",
        now=resolved_now,
    )

    center_latitude = float(location.latitude)
    center_longitude = float(location.longitude)
    lookup = resolver or _load_nearby_communities
    try:
        raw_candidates = lookup(center_latitude, center_longitude, radius_miles)
    except (httpx.HTTPError, ValueError, TypeError):
        payload = get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)
        payload["discovery"] = {
            "created": 0,
            "updated": 0,
            "reviewed": 0,
            "radius_miles": radius_miles,
            "message": (
                "Your mileage range was saved, but nearby communities could not be checked right now. "
                "Try again later or add a city by hand."
            ),
        }
        return payload

    prepared: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        name = _display_name(candidate.get("name") or "")
        normalized_name = _normalize(name)
        try:
            latitude = float(candidate["latitude"])
            longitude = float(candidate["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not normalized_name or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        distance_miles = _distance_miles(
            center_latitude,
            center_longitude,
            latitude,
            longitude,
        )
        if distance_miles > radius_miles + 0.05:
            continue
        region = _optional(candidate.get("region"))
        key = (normalized_name, _normalize(region or ""))
        if key in seen:
            continue
        seen.add(key)
        prepared.append(
            {
                "name": name,
                "normalized_name": normalized_name,
                "region": region,
                "country_code": str(
                    candidate.get("country_code") or location.country_code or "US"
                ).upper()[:2],
                "latitude": latitude,
                "longitude": longitude,
                "distance_miles": round(distance_miles, 1),
                "place_type": str(candidate.get("place_type") or "community"),
                "source_id": candidate.get("source_id"),
            }
        )
    prepared.sort(key=lambda item: (item["distance_miles"], item["name"].casefold()))
    prepared = prepared[:MAX_NEARBY_COMMUNITIES]

    created_count = 0
    updated_count = 0
    for candidate in prepared:
        evidence = {
            "source": "map",
            "note": f"About {candidate['distance_miles']:g} miles from this location",
            "distance_miles": candidate["distance_miles"],
            "radius_miles": float(radius_miles),
            "place_type": candidate["place_type"],
            "source_id": candidate["source_id"],
        }
        row = _find_area(
            db,
            business_location_id=str(campaign.business_location_id),
            area_type="city",
            normalized_name=candidate["normalized_name"],
            relationship="included",
        )
        if row is None:
            db.add(
                BusinessServiceArea(
                    tenant_id=tenant_id,
                    organization_id=str(campaign.organization_id),
                    business_location_id=str(campaign.business_location_id),
                    area_type="city",
                    name=candidate["name"],
                    normalized_name=candidate["normalized_name"],
                    region=candidate["region"],
                    country_code=candidate["country_code"],
                    center_latitude=candidate["latitude"],
                    center_longitude=candidate["longitude"],
                    relationship="included",
                    status="suggested",
                    source="map",
                    confidence=0.85,
                    evidence=[evidence],
                    created_at=resolved_now,
                    updated_at=resolved_now,
                )
            )
            created_count += 1
        elif row.status != "rejected":
            row.center_latitude = candidate["latitude"]
            row.center_longitude = candidate["longitude"]
            row.evidence = _merge_evidence(row.evidence, [evidence])
            row.confidence = max(float(row.confidence or 0), 0.85)
            if row.status == "suggested" and row.source == "location":
                row.source = "map"
            row.updated_at = resolved_now
            updated_count += 1
    db.commit()

    payload = get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)
    payload["discovery"] = {
        "created": created_count,
        "updated": updated_count,
        "reviewed": len(prepared),
        "radius_miles": float(radius_miles),
        "message": (
            "Review the nearby communities on the map. They will not affect search ideas until you confirm them."
            if prepared
            else "No named communities were found in this range. Try a larger radius or add a city by hand."
        ),
    }
    return payload


def review_area(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    area_id: str,
    next_status: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if next_status not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review choice")
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    row = (
        db.query(BusinessServiceArea)
        .filter(
            BusinessServiceArea.id == area_id,
            BusinessServiceArea.tenant_id == tenant_id,
            BusinessServiceArea.organization_id == campaign.organization_id,
            BusinessServiceArea.business_location_id == campaign.business_location_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service area not found")
    resolved_now = now or datetime.now(UTC)
    row.status = next_status
    row.reviewed_at = resolved_now
    row.updated_at = resolved_now
    db.commit()
    return get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)


def confirmed_areas_for_campaign(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> tuple[list[BusinessServiceArea], list[BusinessServiceArea]]:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if not campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business is not assigned to an organization yet.",
        )
    if not campaign.business_location_id:
        return [], []
    rows = (
        db.query(BusinessServiceArea)
        .filter(
            BusinessServiceArea.tenant_id == tenant_id,
            BusinessServiceArea.organization_id == campaign.organization_id,
            BusinessServiceArea.business_location_id == campaign.business_location_id,
            BusinessServiceArea.status == "confirmed",
        )
        .all()
    )
    return (
        [row for row in rows if row.relationship == "included"],
        [row for row in rows if row.relationship == "excluded"],
    )


def search_terms(areas: list[BusinessServiceArea]) -> list[str]:
    terms: list[str] = []
    for area in areas:
        if area.area_type == "radius":
            continue
        terms.append(area.name)
        if area.region and area.area_type != "postal_code":
            terms.append(f"{area.name} {area.region}")
    return list(dict.fromkeys(terms))


def match_keyword_to_area(
    keyword: str,
    included: list[BusinessServiceArea],
    excluded: list[BusinessServiceArea],
) -> tuple[BusinessServiceArea | None, str]:
    normalized_keyword = _normalize(keyword)
    for area in excluded:
        if _area_in_keyword(area, normalized_keyword):
            return area, "excluded"
    for area in included:
        if _area_in_keyword(area, normalized_keyword):
            return area, "included"
    if included:
        return None, "confirmed_market"
    return None, "missing"


def _area_in_keyword(area: BusinessServiceArea, normalized_keyword: str) -> bool:
    if area.area_type == "radius":
        return False
    area_name = _normalize(area.name)
    return bool(area_name) and re.search(rf"\b{re.escape(area_name)}\b", normalized_keyword) is not None


def _page_area_candidates(
    title: str | None,
    url: str,
    *,
    heading_text: str | None = None,
) -> list[str]:
    candidates: list[str] = []
    for source_text in [title, *re.split(r"\s+\|\s+", heading_text or "")]:
        if not source_text:
            continue
        title_text = html.unescape(source_text)
        match = re.search(
            r"\b(?:in|near|serving)\s+([A-Za-z][A-Za-z .'\-]{1,60}?)(?=\s*[|–—]|$)",
            title_text,
            flags=re.IGNORECASE,
        )
        if match:
            candidate = _clean_area_candidate(match.group(1))
            if candidate:
                candidates.append(candidate)

    parsed = urlparse(url)
    raw_segments = [segment for segment in parsed.path.split("/") if segment]
    lowered = [segment.casefold() for segment in raw_segments]
    for marker in _AREA_PATH_MARKERS:
        if marker not in lowered:
            continue
        index = lowered.index(marker)
        if index + 1 < len(raw_segments):
            candidate = _clean_area_candidate(
                unquote(raw_segments[index + 1]).replace("-", " ").replace("_", " ")
            )
            if candidate:
                candidates.append(candidate)
        break
    return list(dict.fromkeys(candidates))


def _clean_area_candidate(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" -|,./")
    cleaned = re.sub(r",?\s+(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)$", "", cleaned, flags=re.IGNORECASE)
    if not cleaned or len(cleaned.split()) > 6 or len(cleaned) > 100:
        return None
    return _display_name(cleaned)


def _find_area(
    db: Session,
    *,
    business_location_id: str,
    area_type: str,
    normalized_name: str,
    relationship: str,
) -> BusinessServiceArea | None:
    return (
        db.query(BusinessServiceArea)
        .filter(
            BusinessServiceArea.business_location_id == business_location_id,
            BusinessServiceArea.area_type == area_type,
            BusinessServiceArea.normalized_name == normalized_name,
            BusinessServiceArea.relationship == relationship,
        )
        .first()
    )


def _serialize(row: BusinessServiceArea) -> dict[str, Any]:
    return {
        "id": row.id,
        "business_location_id": row.business_location_id,
        "area_type": row.area_type,
        "name": row.name,
        "region": row.region,
        "country_code": row.country_code,
        "radius_miles": row.radius_miles,
        "center_latitude": row.center_latitude,
        "center_longitude": row.center_longitude,
        "relationship": row.relationship,
        "status": row.status,
        "source": row.source,
        "confidence": round(float(row.confidence or 0), 2),
        "evidence": list(row.evidence or []),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


def _load_nearby_communities(
    latitude: float,
    longitude: float,
    radius_miles: float,
) -> list[dict[str, Any]]:
    settings = get_settings()
    radius_meters = min(int(radius_miles * 1609.344), int(75 * 1609.344))
    query = (
        "[out:json][timeout:15];"
        "("
        f'nwr["place"~"^(city|town|village|hamlet)$"](around:{radius_meters},{latitude},{longitude});'
        ");"
        "out center tags;"
    )
    headers = {
        "User-Agent": (
            f"SEOAccelerator/1.0 (+{settings.public_base_url.rstrip('/')}; "
            "owner-requested service-area review)"
        )
    }
    with httpx.Client(timeout=settings.service_area_places_timeout_seconds) as client:
        response = client.post(
            settings.service_area_places_endpoint,
            data={"data": query},
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        raise ValueError("Nearby-community response did not contain a place list")
    communities: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
        center = element.get("center") if isinstance(element.get("center"), dict) else {}
        name = tags.get("name")
        item_latitude = element.get("lat", center.get("lat"))
        item_longitude = element.get("lon", center.get("lon"))
        if not name or item_latitude is None or item_longitude is None:
            continue
        country_code = tags.get("addr:country") or tags.get("ISO3166-1")
        communities.append(
            {
                "name": name,
                "region": tags.get("addr:state") or tags.get("is_in:state"),
                "country_code": country_code,
                "latitude": item_latitude,
                "longitude": item_longitude,
                "place_type": tags.get("place"),
                "source_id": f"{element.get('type', 'place')}:{element.get('id', '')}",
            }
        )
    return communities


def _distance_miles(
    start_latitude: float,
    start_longitude: float,
    end_latitude: float,
    end_longitude: float,
) -> float:
    earth_radius_miles = 3958.7613
    start_latitude_radians = math.radians(start_latitude)
    end_latitude_radians = math.radians(end_latitude)
    latitude_delta = math.radians(end_latitude - start_latitude)
    longitude_delta = math.radians(end_longitude - start_longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(start_latitude_radians)
        * math.cos(end_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    haversine = max(0.0, min(1.0, haversine))
    return earth_radius_miles * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


def _display_name(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value)).strip()
    if clean.islower() or clean.isupper():
        return clean.title()
    return clean


def _optional(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized or None


def _merge_evidence(existing: list | None, additions: list) -> list:
    merged = list(existing or [])
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged[:8]
