from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult
from app.models.data_connection import DataConnection
from app.models.keyword_research import KeywordResearchRun, KeywordResearchSuggestion
from app.models.rank import CampaignKeyword
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_search_console import SearchConsoleProviderAdapter
from app.providers.keyword_research import DataForSeoKeywordResearchProvider
from app.services import rank_service
from app.services import business_service_service
from app.services import business_service_area_service
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


CAPABILITY = "keyword_research"
RANKED_OPERATION = "ranked_keywords_live"
IDEAS_OPERATION = "keyword_ideas_live"
VOLUME_OPERATION = "google_ads_search_volume_live"


def _campaign_or_404(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if not campaign.organization_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This business is not assigned to an organization yet.",
        )
    return campaign


def get_latest(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    run = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign_id,
        )
        .order_by(KeywordResearchRun.created_at.desc())
        .first()
    )
    if run is None:
        return {"run": None, "items": [], "summary": _summary([])}
    items = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.run_id == run.id,
            KeywordResearchSuggestion.tenant_id == tenant_id,
            KeywordResearchSuggestion.dismissed_at.is_(None),
        )
        .order_by(
            KeywordResearchSuggestion.opportunity_score.desc(),
            KeywordResearchSuggestion.search_volume.desc(),
            KeywordResearchSuggestion.keyword.asc(),
        )
        .all()
    )
    serialized = [_serialize_suggestion(item) for item in items]
    return {"run": _serialize_run(run), "items": serialized, "summary": _summary(serialized)}


def discover(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    max_suggestions: int = 75,
    provider: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    resolved_now = now or datetime.now(UTC)
    location = (
        db.get(BusinessLocation, campaign.business_location_id)
        if campaign.business_location_id
        else None
    )
    location_name = rank_service.resolve_location_code(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    run = KeywordResearchRun(
        tenant_id=tenant_id,
        organization_id=str(campaign.organization_id),
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        status="running",
        location_name=location_name,
        language_code="en",
        sources=[],
        warnings=[],
        started_at=resolved_now,
        created_at=resolved_now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    candidates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    sources: set[str] = set()
    provider_cost = Decimal("0")
    confirmed_services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    confirmed_areas, excluded_areas = (
        business_service_area_service.confirmed_areas_for_campaign(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
        )
    )

    tracked = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
        )
        .all()
    )
    for item in tracked:
        _merge_candidate(
            candidates,
            item.keyword,
            source="tracked_rankings",
            tracked=True,
        )
    if tracked:
        sources.add("tracked_rankings")

    gsc_rows, gsc_warning = _load_search_console_queries(
        db,
        campaign=campaign,
        now=resolved_now,
    )
    if gsc_warning:
        warnings.append(gsc_warning)
    for item in gsc_rows:
        _merge_candidate(
            candidates,
            str(item.get("query", "")),
            source="google_search_console",
            gsc_clicks=_number(item.get("clicks")),
            gsc_impressions=_number(item.get("impressions")),
            gsc_position=_number(item.get("position")),
        )
    if gsc_rows:
        sources.add("google_search_console")

    live_provider = provider
    credential_owner: str | None = None
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
            login = str(credentials.get("login", "")).strip()
            password = str(credentials.get("password", ""))
            if not login or not password:
                raise ProviderCredentialConfigurationError(
                    "DataForSEO credentials are missing.",
                    reason_code="provider_credentials_missing",
                    status_code=409,
                )
            live_provider = DataForSeoKeywordResearchProvider(login=login, password=password)
        except ProviderCredentialConfigurationError:
            warnings.append(
                "Connect the market research source to add local demand and competition data."
            )

    target = _domain(campaign.domain)
    ranked_items: list[dict[str, Any]] = []
    if live_provider is not None and target:
        try:
            result = _run_provider_call(
                db,
                campaign=campaign,
                run_id=run.id,
                credential_owner=credential_owner,
                operation=RANKED_OPERATION,
                call=lambda: live_provider.ranked_keywords(
                    target=target,
                    location_name=location_name,
                    language_code="en",
                    limit=max_suggestions,
                ),
            )
            ranked_items = list(result.get("items", []))
            provider_cost += Decimal(str(result.get("cost", 0) or 0))
            for item in ranked_items:
                parsed = _parse_labs_item(item)
                _merge_candidate(candidates, source="dataforseo_ranked", **parsed)
            if ranked_items:
                sources.add("dataforseo_ranked")
        except (CostEconomicsError, ValueError) as exc:
            warnings.append(_plain_provider_warning(exc, "ranked searches"))

    website_seeds = (
        []
        if confirmed_services
        else _website_seeds(db, tenant_id=tenant_id, campaign_id=campaign_id)
    )
    if website_seeds:
        sources.add("website_content")
    service_seeds = [service.name for service in confirmed_services]
    area_terms = business_service_area_service.search_terms(confirmed_areas)
    service_area_seeds = [
        f"{service.name} {area}"
        for service in confirmed_services[:8]
        for area in area_terms[:8]
    ][:20]
    seeds = list(
        dict.fromkeys(
            [
                *service_area_seeds,
                *service_seeds,
                *_choose_seeds(candidates, location_terms=area_terms),
                *website_seeds,
            ]
        )
    )[:20]
    if live_provider is not None and seeds:
        try:
            result = _run_provider_call(
                db,
                campaign=campaign,
                run_id=run.id,
                credential_owner=credential_owner,
                operation=IDEAS_OPERATION,
                call=lambda: live_provider.keyword_ideas(
                    keywords=seeds,
                    location_name=location_name,
                    language_code="en",
                    limit=max_suggestions,
                ),
            )
            idea_items = list(result.get("items", []))
            provider_cost += Decimal(str(result.get("cost", 0) or 0))
            for item in idea_items:
                parsed = _parse_labs_item(item)
                _merge_candidate(candidates, source="dataforseo_ideas", **parsed)
            if idea_items:
                sources.add("dataforseo_ideas")
        except (CostEconomicsError, ValueError) as exc:
            warnings.append(_plain_provider_warning(exc, "related search ideas"))

    preliminary = sorted(
        candidates.values(),
        key=lambda item: (
            _number(item.get("gsc_impressions")) or 0,
            int(item.get("search_volume") or 0),
        ),
        reverse=True,
    )[: max(1, min(max_suggestions * 2, 200))]
    if live_provider is not None and preliminary:
        try:
            result = _run_provider_call(
                db,
                campaign=campaign,
                run_id=run.id,
                credential_owner=credential_owner,
                operation=VOLUME_OPERATION,
                call=lambda: live_provider.search_volume(
                    keywords=[item["keyword"] for item in preliminary[:50]],
                    location_name=location_name,
                    language_code="en",
                    location_code=location.provider_location_code if location else None,
                ),
            )
            volume_items = list(result.get("items", []))
            provider_cost += Decimal(str(result.get("cost", 0) or 0))
            for item in volume_items:
                _merge_candidate(
                    candidates,
                    source="dataforseo_volume",
                    **_parse_volume_item(item),
                )
            if volume_items:
                sources.add("dataforseo_volume")
        except (CostEconomicsError, ValueError) as exc:
            warnings.append(_plain_provider_warning(exc, "local search demand"))

    scored = [
        _score_candidate(
            value,
            location=location,
            confirmed_services=confirmed_services,
            confirmed_service_areas=confirmed_areas,
            excluded_service_areas=excluded_areas,
        )
        for value in candidates.values()
    ]
    scored.sort(
        key=lambda item: (
            {"relevant": 2, "needs_review": 1, "unrelated": 0}.get(
                item["relevance_status"], 0
            ),
            item["opportunity_score"],
            item.get("search_volume") or 0,
        ),
        reverse=True,
    )
    scored = scored[: max(1, min(max_suggestions, 100))]

    for item in scored:
        db.add(
            KeywordResearchSuggestion(
                run_id=run.id,
                tenant_id=tenant_id,
                organization_id=str(campaign.organization_id),
                campaign_id=campaign.id,
                business_location_id=campaign.business_location_id,
                keyword=item["keyword"],
                normalized_keyword=item["normalized_keyword"],
                source_types=item["source_types"],
                evidence=item["evidence"],
                search_volume=item.get("search_volume"),
                cpc=item.get("cpc"),
                competition=item.get("competition"),
                competition_level=item.get("competition_level"),
                keyword_difficulty=item.get("keyword_difficulty"),
                monthly_searches=item.get("monthly_searches", []),
                current_position=item.get("current_position"),
                gsc_clicks=item.get("gsc_clicks"),
                gsc_impressions=item.get("gsc_impressions"),
                gsc_position=item.get("gsc_position"),
                intent=item["intent"],
                opportunity_group=item["opportunity_group"],
                relevance_score=item["relevance_score"],
                relevance_status=item["relevance_status"],
                matched_service_id=item.get("matched_service_id"),
                matched_service_name=item.get("matched_service_name"),
                matched_service_area_id=item.get("matched_service_area_id"),
                matched_service_area_name=item.get("matched_service_area_name"),
                area_match_type=item.get("area_match_type"),
                relevance_reason=item.get("relevance_reason"),
                opportunity_score=item["opportunity_score"],
                recommended_action=item["recommended_action"],
                recommendation_reason=item["recommendation_reason"],
                tracked_at=resolved_now if item.get("tracked") else None,
                source_updated_at=resolved_now,
                created_at=resolved_now,
            )
        )

    run.status = "unavailable" if not scored else ("partial" if warnings else "complete")
    run.sources = sorted(sources)
    run.warnings = list(dict.fromkeys(warnings))
    run.suggestion_count = len(scored)
    run.provider_reported_cost = provider_cost
    run.completed_at = resolved_now
    db.commit()
    return get_latest(db, tenant_id=tenant_id, campaign_id=campaign_id)


def track_suggestions(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    suggestion_ids: list[str],
) -> dict[str, Any]:
    _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    rows = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.tenant_id == tenant_id,
            KeywordResearchSuggestion.campaign_id == campaign_id,
            KeywordResearchSuggestion.id.in_(suggestion_ids),
            KeywordResearchSuggestion.dismissed_at.is_(None),
        )
        .all()
    )
    if len(rows) != len(set(suggestion_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more search ideas were not found for this location.",
        )
    result = rank_service.add_keywords_bulk(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cluster_name="Discovered Searches",
        keywords=[row.keyword for row in rows],
        location_code=None,
    )
    tracked_at = datetime.now(UTC)
    for row in rows:
        row.tracked_at = tracked_at
    db.commit()
    return {
        "created_count": len(result["created"]),
        "already_tracked_count": len(result["skipped"]),
        "location_code": result["location_code"],
        "tracked_ids": [row.id for row in rows],
    }


def reclassify_latest(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> None:
    campaign = _campaign_or_404(db, tenant_id=tenant_id, campaign_id=campaign_id)
    run = (
        db.query(KeywordResearchRun)
        .filter(
            KeywordResearchRun.tenant_id == tenant_id,
            KeywordResearchRun.campaign_id == campaign_id,
        )
        .order_by(KeywordResearchRun.created_at.desc())
        .first()
    )
    if run is None:
        return
    services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    confirmed_areas, excluded_areas = (
        business_service_area_service.confirmed_areas_for_campaign(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
        )
    )
    location = (
        db.get(BusinessLocation, campaign.business_location_id)
        if campaign.business_location_id
        else None
    )
    rows = (
        db.query(KeywordResearchSuggestion)
        .filter(
            KeywordResearchSuggestion.run_id == run.id,
            KeywordResearchSuggestion.tenant_id == tenant_id,
        )
        .all()
    )
    for row in rows:
        item = {
            "keyword": row.keyword,
            "normalized_keyword": row.normalized_keyword,
            "source_types": set(row.source_types or []),
            "monthly_searches": row.monthly_searches or [],
            "tracked": row.tracked_at is not None,
            "search_volume": row.search_volume,
            "cpc": row.cpc,
            "competition": row.competition,
            "competition_level": row.competition_level,
            "keyword_difficulty": row.keyword_difficulty,
            "current_position": row.current_position,
            "gsc_clicks": row.gsc_clicks,
            "gsc_impressions": row.gsc_impressions,
            "gsc_position": row.gsc_position,
        }
        scored = _score_candidate(
            item,
            location=location,
            confirmed_services=services,
            confirmed_service_areas=confirmed_areas,
            excluded_service_areas=excluded_areas,
        )
        row.intent = scored["intent"]
        row.opportunity_group = scored["opportunity_group"]
        row.relevance_score = scored["relevance_score"]
        row.relevance_status = scored["relevance_status"]
        row.matched_service_id = scored.get("matched_service_id")
        row.matched_service_name = scored.get("matched_service_name")
        row.matched_service_area_id = scored.get("matched_service_area_id")
        row.matched_service_area_name = scored.get("matched_service_area_name")
        row.area_match_type = scored.get("area_match_type")
        row.ai_review_status = "not_requested"
        row.ai_relevance_status = None
        row.ai_confidence = None
        row.ai_reason = None
        row.ai_run_id = None
        row.ai_reviewed_at = None
        row.relevance_reason = scored.get("relevance_reason")
        row.opportunity_score = scored["opportunity_score"]
        row.recommended_action = scored["recommended_action"]
        row.recommendation_reason = scored["recommendation_reason"]
        row.evidence = scored["evidence"]
    db.commit()


def _run_provider_call(
    db: Session,
    *,
    campaign: Campaign,
    run_id: str,
    credential_owner: str | None,
    operation: str,
    call: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if credential_owner is None:
        # Tests and internal deterministic adapters can be injected without charging a provider.
        return call()
    reservation = reserve_provider_cost(
        db,
        organization_id=str(campaign.organization_id),
        business_location_id=campaign.business_location_id,
        campaign_id=campaign.id,
        provider_name="dataforseo",
        capability=CAPABILITY,
        operation=operation,
        credential_owner=credential_owner,
        quantity=1,
        idempotency_key=f"keyword-research:{run_id}:{operation}",
    )
    try:
        result = call()
    except Exception:
        release_provider_cost(db, reservation=reservation)
        raise
    reconcile_provider_cost(
        db,
        reservation=reservation,
        provider_reported_cost=result.get("cost"),
    )
    return result


def _load_search_console_queries(
    db: Session,
    *,
    campaign: Campaign,
    now: datetime,
) -> tuple[list[dict[str, Any]], str | None]:
    connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.organization_id == campaign.organization_id,
            DataConnection.campaign_id == campaign.id,
            DataConnection.provider_name == "google_search_console",
            DataConnection.status != "disconnected",
        )
        .first()
    )
    if connection is None:
        return [], None
    end_date = now.date() - timedelta(days=2)
    start_date = end_date - timedelta(days=89)
    result = SearchConsoleProviderAdapter(db=db).execute(
        ProviderExecutionRequest(
            operation="search_console_query",
            payload={
                "organization_id": str(campaign.organization_id),
                "site_url": connection.external_resource_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "dimensions": ["query"],
                "row_limit": 250,
            },
        )
    )
    if not result.success:
        return [], "Search Console query details could not be refreshed, so saved sources were used."
    payload = result.raw_payload or {}
    rows = payload.get("rows", [])
    return ([row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []), None


def _merge_candidate(
    candidates: dict[str, dict[str, Any]],
    keyword: str = "",
    *,
    source: str,
    **values: Any,
) -> None:
    clean = re.sub(r"\s+", " ", str(keyword or values.pop("keyword", "")).strip())
    if not clean or len(clean) > 255:
        return
    normalized = clean.casefold()
    current = candidates.setdefault(
        normalized,
        {
            "keyword": clean,
            "normalized_keyword": normalized,
            "source_types": set(),
            "monthly_searches": [],
            "tracked": False,
        },
    )
    current["source_types"].add(source)
    for key, value in values.items():
        if value is None or value == []:
            continue
        if key == "tracked":
            current[key] = bool(current.get(key)) or bool(value)
        elif key == "monthly_searches":
            current[key] = value
        elif current.get(key) in (None, "", 0):
            current[key] = value
        elif key in {"search_volume", "gsc_clicks", "gsc_impressions"}:
            current[key] = max(current[key], value)


def _parse_labs_item(item: dict[str, Any]) -> dict[str, Any]:
    keyword_data = item.get("keyword_data", {})
    if not isinstance(keyword_data, dict):
        keyword_data = {}
    info = keyword_data.get("keyword_info", {})
    if not isinstance(info, dict):
        info = {}
    properties = keyword_data.get("keyword_properties", {})
    if not isinstance(properties, dict):
        properties = {}
    ranked = item.get("ranked_serp_element", {})
    serp_item = ranked.get("serp_item", {}) if isinstance(ranked, dict) else {}
    if not isinstance(serp_item, dict):
        serp_item = {}
    return {
        "keyword": str(keyword_data.get("keyword") or item.get("keyword") or ""),
        "search_volume": _integer(info.get("search_volume")),
        "cpc": _decimal(info.get("cpc")),
        "competition": _number(info.get("competition")),
        "competition_level": _text(info.get("competition_level")),
        "keyword_difficulty": _integer(properties.get("keyword_difficulty")),
        "monthly_searches": info.get("monthly_searches", []),
        "current_position": _number(
            serp_item.get("rank_absolute") or serp_item.get("rank_group")
        ),
    }


def _parse_volume_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "keyword": str(item.get("keyword", "")),
        "search_volume": _integer(item.get("search_volume")),
        "cpc": _decimal(item.get("cpc")),
        "competition": _number(item.get("competition")),
        "competition_level": _text(item.get("competition_level")),
        "monthly_searches": item.get("monthly_searches", []),
    }


def _choose_seeds(
    candidates: dict[str, dict[str, Any]],
    *,
    location_terms: list[str] | None = None,
) -> list[str]:
    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            bool(item.get("tracked")),
            _number(item.get("gsc_impressions")) or 0,
            int(item.get("search_volume") or 0),
        ),
        reverse=True,
    )
    seeds = [item["keyword"] for item in ranked[:10]]
    for area in (location_terms or [])[:5]:
        for item in list(seeds[:5]):
            if area.casefold() not in item.casefold():
                seeds.append(f"{item} {area}")
    return list(dict.fromkeys(seeds))[:20]


def _website_seeds(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> list[str]:
    rows = (
        db.query(CrawlPageResult.title)
        .filter(
            CrawlPageResult.tenant_id == tenant_id,
            CrawlPageResult.campaign_id == campaign_id,
            CrawlPageResult.is_indexable == 1,
            CrawlPageResult.title.isnot(None),
        )
        .order_by(CrawlPageResult.crawled_at.desc())
        .limit(30)
        .all()
    )
    seeds: list[str] = []
    for (raw_title,) in rows:
        title = re.sub(r"\s+", " ", str(raw_title or "")).strip()
        if not title:
            continue
        # Page titles commonly end with a brand after a pipe or dash. The first
        # phrase is safer discovery evidence than sending the whole title.
        phrase = re.split(r"\s+[|–—-]\s+", title, maxsplit=1)[0].strip()
        if 2 <= len(phrase.split()) <= 12 and len(phrase) <= 120:
            seeds.append(phrase)
    return list(dict.fromkeys(seeds))[:10]


def _score_candidate(
    item: dict[str, Any],
    *,
    location: BusinessLocation | None,
    confirmed_services: list[Any] | None = None,
    confirmed_service_areas: list[Any] | None = None,
    excluded_service_areas: list[Any] | None = None,
) -> dict[str, Any]:
    sources = sorted(item["source_types"])
    tracked = bool(item.get("tracked"))
    position = _number(item.get("current_position"))
    gsc_position = _number(item.get("gsc_position"))
    effective_position = position or gsc_position
    volume = int(item.get("search_volume") or 0)
    impressions = float(item.get("gsc_impressions") or 0)

    city = ((location.city or location.primary_city) if location else None) or ""
    services = confirmed_services or []
    matched_service, service_match = business_service_service.match_keyword_to_service(
        item["normalized_keyword"],
        services,
    )
    included_areas = confirmed_service_areas or []
    excluded_areas = excluded_service_areas or []
    matched_area, area_match_type = business_service_area_service.match_keyword_to_area(
        item["normalized_keyword"],
        included_areas,
        excluded_areas,
    )
    if tracked:
        relevance_status = "relevant"
        relevance = 100
        relevance_reason = "You already chose to track this search."
    elif matched_service is not None and service_match >= 0.75:
        if area_match_type == "excluded":
            relevance_status = "unrelated"
            relevance = 3
            relevance_reason = (
                f"Matches {matched_service.name}, but {matched_area.name} is marked outside your service area."
            )
        elif area_match_type == "missing":
            relevance_status = "needs_review"
            relevance = 55
            relevance_reason = (
                f"Matches {matched_service.name}. Confirm where this location takes jobs before treating it as a best match."
            )
        else:
            relevance_status = "relevant"
            relevance = 95 if service_match >= 0.9 else 82
            relevance_reason = (
                f"Matches {matched_service.name} in {matched_area.name}, which you confirmed you serve."
                if matched_area is not None
                else f"Matches {matched_service.name} and this location's confirmed service market."
            )
    elif matched_service is not None and service_match > 0:
        relevance_status = "needs_review"
        relevance = 52
        relevance_reason = (
            f"May relate to {matched_service.name}, but the match is not clear enough yet."
        )
    elif services and ({"google_search_console", "dataforseo_ranked"} & set(sources)):
        relevance_status = "needs_review"
        relevance = 28
        relevance_reason = (
            "Your business has appeared for this search, but it does not match a confirmed service."
        )
    elif services:
        relevance_status = "unrelated"
        relevance = 5
        relevance_reason = "Does not match a service confirmed for this location."
    else:
        relevance_status = "needs_review"
        relevance = 35
        relevance_reason = "Confirm your services so this search can be checked for business fit."

    demand_points = min(30, int(math.log10(max(1, volume) + 1) * 12))
    evidence_points = 15 if impressions > 0 else (10 if position else 4)
    if tracked:
        opportunity_group = "tracked"
        position_points = 5
        action = "Keep tracking this search"
        reason = "This search is already in your ranking watch list."
    elif effective_position and effective_position <= 3:
        opportunity_group = "already_found"
        position_points = 10
        action = "Protect this strong result"
        reason = f"Your business already appears around position {round(effective_position)}."
    elif effective_position and effective_position <= 20:
        opportunity_group = "quick_win"
        position_points = 30
        action = "Improve the page already showing"
        reason = f"Your business is already near position {round(effective_position)}, so a focused improvement may help."
    elif impressions > 0:
        opportunity_group = "already_found"
        position_points = 20
        action = "Track this search"
        reason = "Google already shows your website for this search, but it is not near the top yet."
    else:
        opportunity_group = "new_opportunity"
        position_points = 24
        action = "Track this search"
        reason = "This search has local demand but is not yet in your watch list. Confirm that it matches a service you sell."

    score = min(100, round((relevance * 0.35) + demand_points + position_points + evidence_points))
    keyword = item["normalized_keyword"]
    if any(token in keyword for token in ("near me", "emergency", "hire", "service", "company")):
        intent = "Ready to hire"
    elif any(token in keyword for token in ("best", "cost", "price", "reviews", "vs")):
        intent = "Comparing options"
    else:
        intent = "Researching"

    return {
        **item,
        "source_types": sources,
        "evidence": {
            "sources": sources,
            "location": city or None,
            "has_real_demand": volume > 0,
            "has_existing_visibility": effective_position is not None or impressions > 0,
            "matched_service": matched_service.name if matched_service else None,
            "service_match": round(service_match, 2),
            "matched_service_area": matched_area.name if matched_area else None,
            "area_match_type": area_match_type,
        },
        "intent": intent,
        "opportunity_group": opportunity_group,
        "relevance_score": relevance,
        "relevance_status": relevance_status,
        "matched_service_id": matched_service.id if matched_service else None,
        "matched_service_name": matched_service.name if matched_service else None,
        "matched_service_area_id": matched_area.id if matched_area else None,
        "matched_service_area_name": matched_area.name if matched_area else None,
        "area_match_type": area_match_type,
        "relevance_reason": relevance_reason,
        "opportunity_score": score,
        "recommended_action": action,
        "recommendation_reason": reason,
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "quick_wins": sum(item.get("opportunity_group") == "quick_win" for item in items),
        "new_opportunities": sum(
            item.get("opportunity_group") == "new_opportunity" for item in items
        ),
        "already_found": sum(
            item.get("opportunity_group") == "already_found" for item in items
        ),
        "tracked": sum(item.get("tracked_at") is not None for item in items),
        "best_matches": sum(item.get("relevance_status") == "relevant" for item in items),
        "needs_review": sum(item.get("relevance_status") == "needs_review" for item in items),
        "hidden_unrelated": sum(item.get("relevance_status") == "unrelated" for item in items),
    }


def _serialize_run(run: KeywordResearchRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "campaign_id": run.campaign_id,
        "business_location_id": run.business_location_id,
        "status": run.status,
        "location_name": run.location_name,
        "language_code": run.language_code,
        "sources": run.sources,
        "warnings": run.warnings,
        "suggestion_count": run.suggestion_count,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _serialize_suggestion(item: KeywordResearchSuggestion) -> dict[str, Any]:
    return {
        "id": item.id,
        "keyword": item.keyword,
        "source_types": item.source_types,
        "search_volume": item.search_volume,
        "cpc": float(item.cpc) if item.cpc is not None else None,
        "competition": item.competition,
        "competition_level": item.competition_level,
        "keyword_difficulty": item.keyword_difficulty,
        "monthly_searches": item.monthly_searches,
        "current_position": item.current_position,
        "gsc_clicks": item.gsc_clicks,
        "gsc_impressions": item.gsc_impressions,
        "gsc_position": item.gsc_position,
        "intent": item.intent,
        "opportunity_group": item.opportunity_group,
        "relevance_score": item.relevance_score,
        "relevance_status": item.relevance_status,
        "matched_service_id": item.matched_service_id,
        "matched_service_name": item.matched_service_name,
        "matched_service_area_id": item.matched_service_area_id,
        "matched_service_area_name": item.matched_service_area_name,
        "area_match_type": item.area_match_type,
        "ai_review_status": item.ai_review_status,
        "ai_relevance_status": item.ai_relevance_status,
        "ai_confidence": item.ai_confidence,
        "ai_reason": item.ai_reason,
        "ai_reviewed_at": item.ai_reviewed_at.isoformat() if item.ai_reviewed_at else None,
        "relevance_reason": item.relevance_reason,
        "opportunity_score": item.opportunity_score,
        "recommended_action": item.recommended_action,
        "recommendation_reason": item.recommendation_reason,
        "evidence": item.evidence,
        "tracked_at": item.tracked_at.isoformat() if item.tracked_at else None,
        "source_updated_at": item.source_updated_at.isoformat() if item.source_updated_at else None,
    }


def _plain_provider_warning(exc: Exception, label: str) -> str:
    if isinstance(exc, CostEconomicsError):
        return f"{label.capitalize()} were skipped because this account's data allowance or price setup needs attention."
    return f"Fresh {label} are temporarily unavailable. Saved search data is still shown."


def _domain(value: str) -> str:
    candidate = value.strip().lower()
    if not candidate:
        return ""
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = parsed.netloc or parsed.path
    return host.removeprefix("www.").split("/")[0]


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (ValueError, TypeError):
        return None


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
