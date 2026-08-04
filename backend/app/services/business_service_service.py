from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.business_service import BusinessService
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, Page


SERVICE_STATUSES = {"suggested", "confirmed", "rejected"}
_GENERIC_PAGE_NAMES = {
    "about",
    "about us",
    "blog",
    "contact",
    "contact us",
    "faq",
    "home",
    "locations",
    "our team",
    "privacy policy",
    "service areas",
    "services",
    "terms",
}
_SERVICE_HINTS = {
    "cleaning",
    "cleanup",
    "cleanout",
    "concrete",
    "demolition",
    "drain",
    "electrical",
    "excavation",
    "fencing",
    "flooring",
    "hauling",
    "hvac",
    "installation",
    "junk",
    "landscaping",
    "locksmith",
    "maintenance",
    "moving",
    "painting",
    "pest",
    "plumbing",
    "remodeling",
    "removal",
    "repair",
    "replacement",
    "restoration",
    "roofing",
    "sewer",
    "towing",
    "washing",
}
_MATCH_STOPWORDS = {
    "a",
    "and",
    "best",
    "company",
    "contractor",
    "for",
    "in",
    "local",
    "me",
    "near",
    "of",
    "professional",
    "service",
    "services",
    "the",
}


def _campaign_or_404(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    if not campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business is not assigned to an organization yet.",
        )
    return campaign


def get_profile(db: Session, *, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    rows = _effective_rows(db, campaign=campaign)
    items = [_serialize(row, campaign=campaign) for row in rows]
    return {
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "items": items,
        "summary": {
            "confirmed": sum(item["status"] == "confirmed" for item in items),
            "suggested": sum(item["status"] == "suggested" for item in items),
            "rejected": sum(item["status"] == "rejected" for item in items),
        },
    }


def add_manual_service(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    clean_name = _display_name(name)
    normalized = _normalize(clean_name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a service.")
    resolved_now = now or datetime.now(UTC)
    scope_type, scope_key = _scope(campaign)
    row = (
        db.query(BusinessService)
        .filter(
            BusinessService.organization_id == campaign.organization_id,
            BusinessService.scope_type == scope_type,
            BusinessService.scope_key == scope_key,
            BusinessService.normalized_name == normalized,
        )
        .first()
    )
    if row is None:
        row = BusinessService(
            tenant_id=tenant_id,
            organization_id=str(campaign.organization_id),
            business_location_id=campaign.business_location_id,
            scope_type=scope_type,
            scope_key=scope_key,
            name=clean_name,
            normalized_name=normalized,
            aliases=[],
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
        row.name = clean_name
        row.status = "confirmed"
        row.source = "manual"
        row.confidence = 1.0
        row.reviewed_at = resolved_now
        row.updated_at = resolved_now
    db.commit()
    return get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)


def discover_from_website(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    location = (
        db.get(BusinessLocation, campaign.business_location_id)
        if campaign.business_location_id
        else None
    )
    rows = (
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
    resolved_now = now or datetime.now(UTC)
    candidates: dict[str, dict[str, Any]] = {}
    seen_pages: set[str] = set()
    for result, page in rows:
        if page.url in seen_pages:
            continue
        seen_pages.add(page.url)
        for candidate in _page_candidates(
            title=result.title,
            heading_text=result.heading_text,
            meta_description=result.meta_description,
            body_text_excerpt=result.body_text_excerpt,
            url=page.url,
            campaign=campaign,
            location=location,
        ):
            normalized = _normalize(candidate["name"])
            current = candidates.get(normalized)
            evidence = {
                "source": "website",
                "url": page.url,
                "title": result.title,
                "heading": (result.heading_text or "")[:320] or None,
                "description": (result.meta_description or "")[:320] or None,
            }
            if current is None:
                candidates[normalized] = {
                    "name": candidate["name"],
                    "confidence": candidate["confidence"],
                    "evidence": [evidence],
                }
            else:
                current["confidence"] = max(current["confidence"], candidate["confidence"])
                if evidence not in current["evidence"]:
                    current["evidence"].append(evidence)

    scope_type, scope_key = _scope(campaign)
    created_count = 0
    updated_count = 0
    for normalized, candidate in candidates.items():
        row = (
            db.query(BusinessService)
            .filter(
                BusinessService.organization_id == campaign.organization_id,
                BusinessService.scope_type == scope_type,
                BusinessService.scope_key == scope_key,
                BusinessService.normalized_name == normalized,
            )
            .first()
        )
        if row is None:
            db.add(
                BusinessService(
                    tenant_id=tenant_id,
                    organization_id=str(campaign.organization_id),
                    business_location_id=campaign.business_location_id,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    name=candidate["name"],
                    normalized_name=normalized,
                    aliases=[],
                    status="suggested",
                    source="website",
                    confidence=candidate["confidence"],
                    evidence=candidate["evidence"][:8],
                    created_at=resolved_now,
                    updated_at=resolved_now,
                )
            )
            created_count += 1
            continue
        if row.status == "suggested":
            row.confidence = max(float(row.confidence or 0), candidate["confidence"])
            row.evidence = _merge_evidence(row.evidence, candidate["evidence"])
            row.updated_at = resolved_now
            updated_count += 1
    db.commit()
    payload = get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)
    payload["discovery"] = {
        "pages_reviewed": len(seen_pages),
        "created": created_count,
        "updated": updated_count,
        "message": (
            "Review the services found on your website. Nothing is treated as a service until you confirm it."
            if candidates
            else "No clear services were found in the saved website scan. Add the services you provide below."
        ),
    }
    return payload


def review_service(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    service_id: str,
    next_status: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if next_status not in {"confirmed", "rejected"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid review choice")
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    source_row = (
        db.query(BusinessService)
        .filter(
            BusinessService.id == service_id,
            BusinessService.tenant_id == tenant_id,
            BusinessService.organization_id == campaign.organization_id,
        )
        .first()
    )
    if source_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    if source_row.business_location_id not in {None, campaign.business_location_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    resolved_now = now or datetime.now(UTC)
    if source_row.scope_type == "organization" and campaign.business_location_id:
        scope_type, scope_key = _scope(campaign)
        row = (
            db.query(BusinessService)
            .filter(
                BusinessService.organization_id == campaign.organization_id,
                BusinessService.scope_type == scope_type,
                BusinessService.scope_key == scope_key,
                BusinessService.normalized_name == source_row.normalized_name,
            )
            .first()
        )
        if row is None:
            row = BusinessService(
                tenant_id=tenant_id,
                organization_id=str(campaign.organization_id),
                business_location_id=campaign.business_location_id,
                scope_type=scope_type,
                scope_key=scope_key,
                name=source_row.name,
                normalized_name=source_row.normalized_name,
                aliases=list(source_row.aliases or []),
                canonical_category=source_row.canonical_category,
                status=next_status,
                source="inherited",
                confidence=float(source_row.confidence or 0),
                evidence=list(source_row.evidence or []),
                reviewed_at=resolved_now,
                created_at=resolved_now,
                updated_at=resolved_now,
            )
            db.add(row)
        else:
            row.status = next_status
            row.reviewed_at = resolved_now
            row.updated_at = resolved_now
    else:
        source_row.status = next_status
        source_row.reviewed_at = resolved_now
        source_row.updated_at = resolved_now
    db.commit()
    return get_profile(db, tenant_id=tenant_id, campaign_id=campaign_id)


def confirmed_services_for_campaign(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> list[BusinessService]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    return [row for row in _effective_rows(db, campaign=campaign) if row.status == "confirmed"]


def match_keyword_to_service(
    keyword: str,
    services: list[BusinessService],
) -> tuple[BusinessService | None, float]:
    keyword_normalized = _normalize(keyword)
    keyword_tokens = _match_tokens(keyword_normalized)
    best: BusinessService | None = None
    best_score = 0.0
    for service in services:
        names = [service.normalized_name, *[str(alias) for alias in (service.aliases or [])]]
        for raw_name in names:
            normalized_name = _normalize(raw_name)
            service_tokens = _match_tokens(normalized_name)
            if not service_tokens:
                continue
            if normalized_name in keyword_normalized:
                score = 1.0
            else:
                overlap = len(service_tokens & keyword_tokens)
                ratio = overlap / len(service_tokens)
                if overlap == len(service_tokens):
                    score = 0.9
                elif overlap >= 2 and ratio >= 0.6:
                    score = 0.75
                elif overlap >= 1:
                    score = 0.45
                else:
                    score = 0.0
            if score > best_score:
                best = service
                best_score = score
    return best, best_score


def _effective_rows(db: Session, *, campaign: Campaign) -> list[BusinessService]:
    query = db.query(BusinessService).filter(
        BusinessService.tenant_id == campaign.tenant_id,
        BusinessService.organization_id == campaign.organization_id,
    )
    if campaign.business_location_id:
        query = query.filter(
            or_(
                BusinessService.scope_type == "organization",
                BusinessService.business_location_id == campaign.business_location_id,
            )
        )
    else:
        query = query.filter(BusinessService.scope_type == "organization")
    rows = query.all()
    resolved: dict[str, BusinessService] = {}
    for row in sorted(rows, key=lambda item: item.scope_type == "location"):
        resolved[row.normalized_name] = row
    status_order = {"confirmed": 0, "suggested": 1, "rejected": 2}
    return sorted(
        resolved.values(),
        key=lambda row: (status_order.get(row.status, 9), row.name.casefold()),
    )


def _scope(campaign: Campaign) -> tuple[str, str]:
    if campaign.business_location_id:
        return "location", campaign.business_location_id
    return "organization", str(campaign.organization_id)


def _page_candidates(
    *,
    title: str | None,
    heading_text: str | None,
    meta_description: str | None,
    body_text_excerpt: str | None,
    url: str,
    campaign: Campaign,
    location: BusinessLocation | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if title:
        title_phrase = re.split(r"\s+[|–—-]\s+", html.unescape(title), maxsplit=1)[0]
        cleaned = _clean_candidate(title_phrase, campaign=campaign, location=location)
        if cleaned and _looks_like_service(cleaned, from_service_path=False):
            candidates.append({"name": cleaned, "confidence": 0.76})

    for heading in re.split(r"\s+\|\s+", heading_text or ""):
        cleaned = _clean_candidate(heading, campaign=campaign, location=location)
        if cleaned and _looks_like_service(cleaned, from_service_path=False):
            candidates.append({"name": cleaned, "confidence": 0.84})

    parsed = urlparse(url)
    segments = [unquote(part).replace("-", " ").replace("_", " ") for part in parsed.path.split("/") if part]
    service_markers = {"service", "services", "what we do", "what-we-do"}
    from_service_path = any(segment.casefold() in service_markers for segment in segments[:-1])
    if segments:
        cleaned = _clean_candidate(segments[-1], campaign=campaign, location=location)
        if cleaned and _looks_like_service(cleaned, from_service_path=from_service_path):
            candidates.append({"name": cleaned, "confidence": 0.9 if from_service_path else 0.7})
    unique: dict[str, dict[str, Any]] = {}
    supporting_text = _normalize(
        " ".join(item for item in (meta_description, body_text_excerpt) if item)
    )
    for candidate in candidates:
        normalized_name = _normalize(candidate["name"])
        if normalized_name and normalized_name in supporting_text:
            candidate["confidence"] = min(0.97, candidate["confidence"] + 0.08)
        current = unique.get(normalized_name)
        if current is None or candidate["confidence"] > current["confidence"]:
            unique[normalized_name] = candidate
    return list(unique.values())


def _clean_candidate(
    raw: str,
    *,
    campaign: Campaign,
    location: BusinessLocation | None,
) -> str | None:
    value = re.sub(r"\s+", " ", html.unescape(str(raw))).strip(" -|,:/")
    if not value:
        return None
    removable = [campaign.name]
    if location:
        removable.extend(
            item
            for item in (location.name, location.city, location.primary_city, location.region)
            if item
        )
    for item in removable:
        value = re.sub(rf"\b{re.escape(str(item))}\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:in|near|serving)\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" -|,:/")
    normalized = _normalize(value)
    if not normalized or normalized in _GENERIC_PAGE_NAMES:
        return None
    words = value.split()
    if len(words) > 9 or len(value) > 160:
        return None
    return _display_name(value)


def _looks_like_service(value: str, *, from_service_path: bool) -> bool:
    normalized = _normalize(value)
    if normalized in _GENERIC_PAGE_NAMES:
        return False
    words = set(normalized.split())
    if from_service_path and 1 <= len(words) <= 9:
        return True
    return bool(words & _SERVICE_HINTS) or normalized.endswith(" services")


def _display_name(value: str) -> str:
    clean = re.sub(r"\s+", " ", str(value)).strip()
    if clean.islower() or clean.isupper():
        return clean.title()
    return clean


def _normalize(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", " ", str(value).casefold())
    return re.sub(r"\s+", " ", clean).strip()


def _match_tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if token not in _MATCH_STOPWORDS}


def _merge_evidence(existing: list | None, incoming: list) -> list:
    merged: list = []
    for item in [*(existing or []), *incoming]:
        if item not in merged:
            merged.append(item)
    return merged[:8]


def _serialize(row: BusinessService, *, campaign: Campaign) -> dict[str, Any]:
    return {
        "id": row.id,
        "business_location_id": row.business_location_id,
        "scope": row.scope_type,
        "inherited": row.scope_type == "organization" and bool(campaign.business_location_id),
        "name": row.name,
        "aliases": row.aliases or [],
        "status": row.status,
        "source": row.source,
        "confidence": round(float(row.confidence or 0), 2),
        "evidence": row.evidence or [],
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "updated_at": row.updated_at.isoformat(),
    }
