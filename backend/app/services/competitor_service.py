from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal
from app.models.content import ContentBrief
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.providers import get_competitor_provider_for_organization
from app.providers.keyword_research import DataForSeoKeywordResearchProvider
from app.services import keyword_research_service, rank_service
from app.services.cost_economics_service import (
    CostEconomicsError,
    reconcile_provider_cost,
    release_provider_cost,
    reserve_provider_cost,
)
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credential_owner,
    resolve_provider_credentials,
)


DISCOVERY_CAPABILITY = "competitor_research"
DISCOVERY_OPERATION = "competitors_domain_live"
DISCOVERY_VERSION = "competitor-discovery-2026-08-v1"


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def create_competitor(
    db: Session, tenant_id: str, campaign_id: str, domain: str, label: str | None
) -> Competitor:
    _campaign_or_404(db, tenant_id, campaign_id)
    normalized = _domain(domain)
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid competitor website.",
        )
    item = (
        db.query(Competitor)
        .filter(
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
            Competitor.domain == normalized,
        )
        .first()
    )
    if item is not None:
        item.review_status = "confirmed"
        item.label = label or item.label
        db.commit()
        db.refresh(item)
        return item
    item = Competitor(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        domain=normalized,
        label=label,
        discovery_source="manual",
        review_status="confirmed",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_competitors(db: Session, tenant_id: str, campaign_id: str) -> list[Competitor]:
    return (
        db.query(Competitor)
        .filter(
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
            Competitor.review_status != "dismissed",
        )
        .order_by(Competitor.created_at.desc())
        .all()
    )


def review_competitor(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    competitor_id: str,
    decision: str,
) -> Competitor:
    _campaign_or_404(db, tenant_id, campaign_id)
    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"confirmed", "dismissed"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose whether this is a real competitor.",
        )
    item = (
        db.query(Competitor)
        .filter(
            Competitor.id == competitor_id,
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Competitor not found")
    item.review_status = normalized_decision
    db.commit()
    db.refresh(item)
    return item


def discover_competitors(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    provider: Any | None = None,
    limit: int = 12,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Find likely competitors while leaving the owner in control of confirmation."""
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if not campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business is not assigned to an organization yet.",
        )
    target = _domain(campaign.domain)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add a valid website to this location before finding competitors.",
        )

    credential_owner: str | None = None
    live_provider = provider
    if live_provider is None:
        try:
            credentials = resolve_provider_credentials(
                db,
                str(campaign.organization_id),
                "dataforseo",
                required_credential_mode="byo_optional",
            )
            credential_owner = resolve_provider_credential_owner(
                db,
                str(campaign.organization_id),
                "dataforseo",
                required_credential_mode="byo_optional",
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before finding competitors.",
            ) from exc
        login = str(credentials.get("login") or "").strip()
        password = str(credentials.get("password") or "")
        if not login or not password:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before finding competitors.",
            )
        live_provider = DataForSeoKeywordResearchProvider(login=login, password=password)

    observed_at = now or datetime.now(UTC)
    location_name = rank_service.resolve_location_code(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    reservation = None
    if credential_owner is not None:
        try:
            reservation = reserve_provider_cost(
                db,
                organization_id=str(campaign.organization_id),
                business_location_id=campaign.business_location_id,
                campaign_id=campaign.id,
                provider_name="dataforseo",
                capability=DISCOVERY_CAPABILITY,
                operation=DISCOVERY_OPERATION,
                credential_owner=credential_owner,
                quantity=1,
                idempotency_key=f"competitor-discovery:{campaign.id}:{observed_at.isoformat()}",
            )
        except CostEconomicsError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    try:
        result = live_provider.competitor_domains(
            target=target,
            location_name=location_name,
            language_code="en",
            limit=max(1, min(limit, 25)),
        )
    except ValueError as exc:
        if reservation is not None:
            release_provider_cost(db, reservation=reservation)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Competitor research is temporarily unavailable. Try again shortly.",
        ) from exc
    if reservation is not None:
        reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=result.get("cost"),
        )

    saved = {
        row.domain: row
        for row in db.query(Competitor)
        .filter(
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
        )
        .all()
    }
    suggested_count = 0
    observed_count = 0
    for raw in result.get("items", []):
        if not isinstance(raw, dict):
            continue
        domain = _domain(str(raw.get("domain") or ""))
        intersections = _safe_int(raw.get("intersections"))
        if not domain or domain == target or intersections < 2:
            continue
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        organic = metrics.get("organic") if isinstance(metrics.get("organic"), dict) else {}
        row = saved.get(domain)
        if row is None:
            row = Competitor(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                domain=domain,
                discovery_source="search_overlap",
                review_status="suggested",
            )
            db.add(row)
            saved[domain] = row
        row.overlap_count = intersections
        row.average_position = _safe_float(raw.get("avg_position"))
        row.estimated_traffic = _safe_float(organic.get("etv"))
        row.discovery_evidence = json.dumps(
            {
                "version": DISCOVERY_VERSION,
                "location_name": location_name,
                "overlap_count": intersections,
                "average_position": row.average_position,
                "estimated_traffic": row.estimated_traffic,
            },
            sort_keys=True,
        )
        row.last_observed_at = observed_at
        observed_count += 1
        if row.review_status == "suggested":
            suggested_count += 1
    db.commit()
    return {
        "status": "complete",
        "suggestions_found": suggested_count,
        "domains_observed": observed_count,
        "items": [
            _serialize_competitor(row) for row in list_competitors(db, tenant_id, campaign_id)
        ],
        "source_updated_at": observed_at.isoformat(),
    }


def competitor_research(db: Session, *, tenant_id: str, campaign_id: str) -> dict[str, Any]:
    """Build exact, owner-friendly gaps from the latest immutable keyword research run."""
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    competitors = list_competitors(db, tenant_id, campaign_id)
    confirmed = {row.domain: row for row in competitors if row.review_status == "confirmed"}
    run = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign_id,
            KeywordResearchRun.status.in_(("complete", "partial")),
        )
        .order_by(KeywordResearchRun.created_at.desc(), KeywordResearchRun.id.desc())
        .first()
    )
    if run is None:
        return _empty_research(campaign=campaign, competitors=competitors)
    previous_run = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign_id,
            KeywordResearchRun.status.in_(("complete", "partial")),
            KeywordResearchRun.id != run.id,
        )
        .order_by(KeywordResearchRun.created_at.desc(), KeywordResearchRun.id.desc())
        .first()
    )
    suggestions = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.tenant_id == tenant_id,
            KeywordResearchSuggestion.campaign_id == campaign_id,
            KeywordResearchSuggestion.run_id == run.id,
            KeywordResearchSuggestion.dismissed_at.is_(None),
            KeywordResearchSuggestion.relevance_status == "relevant",
        )
        .order_by(
            KeywordResearchSuggestion.opportunity_score.desc(),
            KeywordResearchSuggestion.keyword.asc(),
        )
        .all()
    )
    previous_suggestions = _previous_suggestions_by_keyword(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        previous_run=previous_run,
        normalized_keywords=[row.normalized_keyword for row in suggestions],
    )
    planning = keyword_research_service.planning_context_by_suggestion(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        suggestions=suggestions,
    )
    items: list[dict[str, Any]] = []
    for suggestion in suggestions:
        evidence = suggestion.evidence if isinstance(suggestion.evidence, dict) else {}
        owner_position = _first_number(suggestion.current_position, suggestion.gsc_position)
        target_page = planning.get(suggestion.id, {}).get("target_page") or {}
        owner_url = _text(target_page.get("url")) or _text(evidence.get("ranked_url"))
        page_status = str(target_page.get("status") or "review")
        page_reason = _text(target_page.get("reason"))
        competitor_rows = evidence.get("competitors")
        if not isinstance(competitor_rows, list):
            continue
        for competitor_evidence in competitor_rows:
            if not isinstance(competitor_evidence, dict):
                continue
            domain = _domain(str(competitor_evidence.get("domain") or ""))
            competitor = confirmed.get(domain)
            if competitor is None:
                continue
            competitor_position = _safe_float(competitor_evidence.get("position"))
            if competitor_position is None:
                continue
            movement = _competitor_movement(
                current_position=competitor_position,
                competitor_domain=competitor.domain,
                previous_suggestion=previous_suggestions.get(suggestion.normalized_keyword),
                previous_run=previous_run,
            )
            if owner_position is None:
                gap_type = "not_showing"
                next_step = (
                    "Check whether an existing page fully answers this search before creating a new page."
                    if owner_url is None
                    else "Improve the page already tied to this search and check the ranking again."
                )
            elif owner_position >= competitor_position + 2:
                gap_type = "competitor_ahead"
                next_step = "Compare the two pages, then strengthen the useful details missing from your page."
            else:
                continue
            items.append(
                {
                    "id": f"{suggestion.id}:{competitor.id}",
                    "suggestion_id": suggestion.id,
                    "competitor_id": competitor.id,
                    "competitor_domain": competitor.domain,
                    "competitor_label": competitor.label,
                    "keyword": suggestion.keyword,
                    "gap_type": gap_type,
                    "competitor_position": competitor_position,
                    **movement,
                    "competitor_url": _text(competitor_evidence.get("url")),
                    "owner_position": owner_position,
                    "owner_url": owner_url,
                    "page_status": page_status,
                    "page_reason": page_reason,
                    "search_volume": suggestion.search_volume,
                    "matched_service_name": suggestion.matched_service_name,
                    "matched_service_area_name": suggestion.matched_service_area_name,
                    "opportunity_score": suggestion.opportunity_score,
                    "next_step": next_step,
                    "source_updated_at": (
                        suggestion.source_updated_at.isoformat()
                        if suggestion.source_updated_at
                        else run.completed_at.isoformat()
                        if run.completed_at
                        else None
                    ),
                }
            )
    items.sort(
        key=lambda row: (
            1 if row["gap_type"] == "not_showing" else 0,
            row["opportunity_score"],
            row["search_volume"] or 0,
        ),
        reverse=True,
    )
    brief_rows = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.campaign_id == campaign_id,
            ContentBrief.suggestion_id.in_([str(row["suggestion_id"]) for row in items]),
        )
        .all()
        if items
        else []
    )
    briefs_by_gap = {(row.suggestion_id, row.competitor_id): row for row in brief_rows}
    for item in items:
        saved_brief = briefs_by_gap.get((str(item["suggestion_id"]), str(item["competitor_id"])))
        item["content_brief"] = _serialize_content_brief(saved_brief) if saved_brief else None
    domains_with_gaps = {str(row["competitor_domain"]) for row in items}
    return {
        "location": {
            "campaign_id": campaign.id,
            "business_location_id": campaign.business_location_id,
            "name": campaign.name,
            "domain": campaign.domain,
        },
        "run": {
            "id": run.id,
            "status": run.status,
            "location_name": run.location_name,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "previous_run_id": previous_run.id if previous_run else None,
            "previous_completed_at": (
                previous_run.completed_at.isoformat()
                if previous_run and previous_run.completed_at
                else None
            ),
        },
        "summary": {
            "confirmed_competitors": len(confirmed),
            "suggested_competitors": sum(row.review_status == "suggested" for row in competitors),
            "competitors_with_gaps": len(domains_with_gaps),
            "exact_gaps": len(items),
            "not_showing": sum(row["gap_type"] == "not_showing" for row in items),
            "competitor_ahead": sum(row["gap_type"] == "competitor_ahead" for row in items),
            "movement_alerts": sum(bool(row["movement_alert"]) for row in items),
        },
        "items": items,
    }


def create_content_brief(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    suggestion_id: str,
    competitor_id: str,
) -> dict[str, Any]:
    """Create a deterministic, review-only draft from one exact competitor gap."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    research = competitor_research(db, tenant_id=tenant_id, campaign_id=campaign_id)
    gap = next(
        (
            row
            for row in research["items"]
            if row["suggestion_id"] == suggestion_id and row["competitor_id"] == competitor_id
        ),
        None,
    )
    if gap is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Refresh competitor research and choose an exact saved gap first.",
        )
    idempotency_source = json.dumps(
        {
            "campaign_id": campaign_id,
            "suggestion_id": suggestion_id,
            "competitor_id": competitor_id,
            "target_url": gap.get("owner_url"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    idempotency_key = (
        "competitor-gap:" + hashlib.sha256(idempotency_source.encode("utf-8")).hexdigest()[:40]
    )
    existing = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return {
            "created": False,
            "message": "This draft brief is already saved.",
            "item": _serialize_content_brief(existing),
        }

    service_name = _text(gap.get("matched_service_name"))
    area_name = _text(gap.get("matched_service_area_name"))
    subject = service_name or str(gap["keyword"]).title()
    title = f"Improve {subject}"
    if area_name:
        title += f" for {area_name}"
    page_action = "improve_existing_page" if gap.get("owner_url") else "create_service_page"
    outline = _content_brief_outline(
        service_name=service_name,
        area_name=area_name,
        page_action=page_action,
    )
    evidence = {
        "research_run_id": (research.get("run") or {}).get("id"),
        "keyword": gap["keyword"],
        "search_volume": gap.get("search_volume"),
        "owner_position": gap.get("owner_position"),
        "competitor_position": gap.get("competitor_position"),
        "owner_url": gap.get("owner_url"),
        "competitor_domain": gap["competitor_domain"],
        "competitor_url": gap.get("competitor_url"),
        "service_name": service_name,
        "service_area_name": area_name,
        "source_updated_at": gap.get("source_updated_at"),
        "evidence_note": (
            "This draft comes from one owner-confirmed competitor and one exact saved search result."
        ),
    }
    created_at = datetime.now(UTC)
    brief = ContentBrief(
        tenant_id=tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        suggestion_id=suggestion_id,
        competitor_id=competitor_id,
        idempotency_key=idempotency_key,
        status="draft",
        title=title,
        primary_keyword=str(gap["keyword"]),
        recommended_page_action=page_action,
        target_url=_text(gap.get("owner_url")),
        competitor_domain=str(gap["competitor_domain"]),
        competitor_url=_text(gap.get("competitor_url")),
        service_name=service_name,
        service_area_name=area_name,
        evidence=evidence,
        outline=outline,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return {
        "created": True,
        "message": "Draft brief saved for review. Nothing was published.",
        "item": _serialize_content_brief(brief),
    }


def _content_brief_outline(
    *, service_name: str | None, area_name: str | None, page_action: str
) -> list[dict[str, Any]]:
    service = service_name or "the service"
    area = area_name or "the local service area"
    opening = (
        "Clarify the page's main promise and who this service helps."
        if page_action == "improve_existing_page"
        else "Introduce the service, the customer problem it solves, and who it helps."
    )
    return [
        {"order": 1, "heading": "Make the service clear", "guidance": opening},
        {
            "order": 2,
            "heading": "Explain what customers receive",
            "guidance": f"Describe what is included in {service}, the basic process, and important limits.",
        },
        {
            "order": 3,
            "heading": "Show why the business is a local fit",
            "guidance": f"Add honest service-area details, proof, and practical expectations for customers in {area}.",
        },
        {
            "order": 4,
            "heading": "Answer buying questions",
            "guidance": "Answer the questions customers commonly ask before calling, including timing, pricing factors, preparation, and what happens next.",
        },
        {
            "order": 5,
            "heading": "Give one clear next step",
            "guidance": "End with the most useful way to request service. Do not promise rankings or copy a competitor's wording.",
        },
    ]


def _serialize_content_brief(row: ContentBrief) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "title": row.title,
        "primary_keyword": row.primary_keyword,
        "recommended_page_action": row.recommended_page_action,
        "target_url": row.target_url,
        "competitor_domain": row.competitor_domain,
        "competitor_url": row.competitor_url,
        "service_name": row.service_name,
        "service_area_name": row.service_area_name,
        "evidence": dict(row.evidence or {}),
        "outline": list(row.outline or []),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _empty_research(*, campaign: Campaign, competitors: list[Competitor]) -> dict[str, Any]:
    return {
        "location": {
            "campaign_id": campaign.id,
            "business_location_id": campaign.business_location_id,
            "name": campaign.name,
            "domain": campaign.domain,
        },
        "run": None,
        "summary": {
            "confirmed_competitors": sum(row.review_status == "confirmed" for row in competitors),
            "suggested_competitors": sum(row.review_status == "suggested" for row in competitors),
            "competitors_with_gaps": 0,
            "exact_gaps": 0,
            "not_showing": 0,
            "competitor_ahead": 0,
            "movement_alerts": 0,
        },
        "items": [],
    }


def _previous_suggestions_by_keyword(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    previous_run: KeywordResearchRun | None,
    normalized_keywords: list[str],
) -> dict[str, KeywordResearchSuggestion]:
    if previous_run is None or not normalized_keywords:
        return {}
    rows = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.tenant_id == tenant_id,
            KeywordResearchSuggestion.campaign_id == campaign_id,
            KeywordResearchSuggestion.run_id == previous_run.id,
            KeywordResearchSuggestion.normalized_keyword.in_(tuple(set(normalized_keywords))),
        )
        .all()
    )
    return {row.normalized_keyword: row for row in rows}


def _competitor_movement(
    *,
    current_position: float,
    competitor_domain: str,
    previous_suggestion: KeywordResearchSuggestion | None,
    previous_run: KeywordResearchRun | None,
) -> dict[str, Any]:
    previous_position: float | None = None
    if previous_suggestion is not None:
        evidence = (
            previous_suggestion.evidence if isinstance(previous_suggestion.evidence, dict) else {}
        )
        competitor_rows = evidence.get("competitors")
        if isinstance(competitor_rows, list):
            for row in competitor_rows:
                if not isinstance(row, dict):
                    continue
                if _domain(str(row.get("domain") or "")) != competitor_domain:
                    continue
                previous_position = _safe_float(row.get("position"))
                break

    previous_updated_at = None
    if previous_suggestion and previous_suggestion.source_updated_at:
        previous_updated_at = previous_suggestion.source_updated_at.isoformat()
    elif previous_run and previous_run.completed_at:
        previous_updated_at = previous_run.completed_at.isoformat()

    if previous_position is None:
        return {
            "previous_competitor_position": None,
            "competitor_position_change": None,
            "movement_direction": "unavailable",
            "movement_label": "No earlier matching result is available yet.",
            "movement_alert": False,
            "previous_source_updated_at": previous_updated_at,
        }

    change = round(previous_position - current_position, 1)
    places = f"{abs(change):g}"
    if change >= 1:
        direction = "up"
        label = f"Moved up {places} place{'s' if abs(change) != 1 else ''} since the earlier check."
    elif change <= -1:
        direction = "down"
        label = (
            f"Moved down {places} place{'s' if abs(change) != 1 else ''} since the earlier check."
        )
    else:
        direction = "steady"
        label = "Stayed about the same since the earlier check."
    return {
        "previous_competitor_position": previous_position,
        "competitor_position_change": change,
        "movement_direction": direction,
        "movement_label": label,
        "movement_alert": abs(change) >= 3,
        "previous_source_updated_at": previous_updated_at,
    }


def _serialize_competitor(row: Competitor) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "domain": row.domain,
        "label": row.label,
        "discovery_source": row.discovery_source,
        "review_status": row.review_status,
        "overlap_count": row.overlap_count,
        "average_position": row.average_position,
        "estimated_traffic": row.estimated_traffic,
        "last_observed_at": row.last_observed_at.isoformat() if row.last_observed_at else None,
    }


def _domain(value: str) -> str:
    raw = re.sub(r"\s+", "", str(value or "").strip().casefold())
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").removeprefix("www.").rstrip(".")
    return host if "." in host else ""


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def collect_snapshot(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    competitors = [
        item
        for item in list_competitors(db, tenant_id, campaign_id)
        if item.review_status == "confirmed"
    ]
    if not competitors:
        return {
            "campaign_id": campaign_id,
            "status": "no_data",
            "reason_code": "no_competitors",
            "snapshots_collected": 0,
        }
    try:
        provider = get_competitor_provider_for_organization(db, tenant_id)
    except ValueError:
        return {
            "campaign_id": campaign_id,
            "status": "provider_unavailable",
            "reason_code": "provider_unavailable",
            "snapshots_collected": 0,
        }

    now = datetime.now(UTC)
    created = 0
    missing_competitors = 0
    for comp in competitors:
        payload = provider.collect_competitor_snapshot(
            db=db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            competitor_id=comp.id,
            domain=comp.domain,
        )
        if payload is None:
            missing_competitors += 1
            continue
        db.add(
            CompetitorRanking(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                keyword=str(payload["keyword"]),
                position=int(payload["position"]),
                captured_at=now,
            )
        )
        db.add(
            CompetitorPage(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                url=str(payload["url"]),
                visibility_score=float(payload["visibility_score"]),
                captured_at=now,
            )
        )
        db.add(
            CompetitorSignal(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                signal_key=str(payload["signal_key"]),
                signal_value=str(payload["signal_value"]),
                score=float(payload["signal_score"]),
                captured_at=now,
            )
        )
        created += 1
    db.commit()
    if created == 0:
        return {
            "campaign_id": campaign_id,
            "status": "no_data",
            "reason_code": "dataset_unavailable",
            "snapshots_collected": 0,
            "missing_competitors": missing_competitors,
        }
    return {
        "campaign_id": campaign_id,
        "status": "success",
        "snapshots_collected": created,
        "missing_competitors": missing_competitors,
    }


def list_snapshots(db: Session, tenant_id: str, campaign_id: str) -> list[dict]:
    rows = (
        db.query(Competitor, CompetitorRanking, CompetitorPage, CompetitorSignal)
        .join(CompetitorRanking, CompetitorRanking.competitor_id == Competitor.id)
        .join(CompetitorPage, CompetitorPage.competitor_id == Competitor.id)
        .join(CompetitorSignal, CompetitorSignal.competitor_id == Competitor.id)
        .filter(Competitor.tenant_id == tenant_id, Competitor.campaign_id == campaign_id)
        .all()
    )
    result = []
    for comp, ranking, page, signal in rows:
        result.append(
            {
                "competitor_id": comp.id,
                "domain": comp.domain,
                "keyword": ranking.keyword,
                "position": ranking.position,
                "visibility_score": page.visibility_score,
                "signal_key": signal.signal_key,
                "signal_value": signal.signal_value,
                "signal_score": signal.score,
                "captured_at": ranking.captured_at.isoformat(),
            }
        )
    return result


def compute_gaps(db: Session, tenant_id: str, campaign_id: str) -> list[dict]:
    return competitor_research(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )["items"]
