import hashlib
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit_event
from app.enums import StrategyRecommendationStatus
from app.models.authority import (
    AuthorityGapResearchRun,
    AuthorityInventoryLink,
    AuthorityInventoryRun,
    AuthorityLinkChange,
    AuthorityLinkChangeRun,
    AuthorityLinkGap,
    AuthorityOutreachDraft,
    AuthorityUnlinkedMention,
    Backlink,
    Citation,
    OutreachCampaign,
    OutreachContact,
)
from app.models.campaign import Campaign
from app.models.competitor import Competitor
from app.models.intelligence import StrategyRecommendation
from app.providers import get_authority_provider
from app.providers.authority import DataForSeoAuthorityProvider
from app.services.cost_economics_service import (
    CostEconomicsError,
    authorize_reserved_provider_dispatch,
    reconcile_provider_cost,
    release_provider_cost,
    reserve_provider_cost,
)
from app.services.commercial_plan_service import (
    FEATURE_LISTING_CORRECTION_SYNC,
    CommercialPlanFeatureDenied,
    require_commercial_feature,
)
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credential_owner,
    resolve_provider_credentials,
)
from app.services import business_service_area_service, business_service_service


AUTHORITY_GAP_CAPABILITY = "authority_research"
AUTHORITY_GAP_OPERATION = "page_intersection_live_limit_25"
AUTHORITY_GAP_LIMIT = 25
AUTHORITY_GAP_COMPETITOR_LIMIT = 5
AUTHORITY_LINK_CHANGE_CAPABILITY = "authority_research"
AUTHORITY_LINK_CHANGE_OPERATION = "backlink_changes_live_limit_12_each"
AUTHORITY_LINK_CHANGE_LIMIT = 12
AUTHORITY_INVENTORY_CAPABILITY = "authority_research"
AUTHORITY_INVENTORY_OPERATION = "inventory_and_mentions_live_limit_50_10"
AUTHORITY_INVENTORY_LINK_LIMIT = 50
AUTHORITY_INVENTORY_MENTION_LIMIT = 10
AUTHORITY_INTELLIGENCE_VERSION = "authority-intelligence-v1"
AUTHORITY_RELEVANCE_RULES_VERSION = "authority-local-relevance-v1"
AUTHORITY_LINK_METRIC_ID = "authority.referring_page_link_present"
AUTHORITY_GAP_ACTION_ID = "authority.build_relevant_mention"
AUTHORITY_RESTORE_ACTION_ID = "authority.restore_lost_link"
AUTHORITY_ACTION_FALLBACK_ID = "competitive.improve_intent_and_links"
_RELEVANCE_CLASSES = {
    "service_and_area_match",
    "service_match",
    "area_match",
    "needs_review",
}


def _authorize_authority_provider_dispatch(
    db: Session,
    *,
    reservation: Any,
    run: Any,
) -> None:
    try:
        authorize_reserved_provider_dispatch(db, reservation=reservation)
    except CostEconomicsError as exc:
        run.status = "failed"
        run.error_code = exc.reason_code
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


_GENERIC_MATCH_TERMS = {
    "business",
    "company",
    "local",
    "professional",
    "service",
    "services",
}


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def listing_correction_access(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, object]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    try:
        feature = require_commercial_feature(
            db,
            organization_id=campaign.organization_id,
            feature_code=FEATURE_LISTING_CORRECTION_SYNC,
        )
        plan_eligible = True
        required_plan = str(feature["required_plan"])
    except CommercialPlanFeatureDenied as exc:
        plan_eligible = False
        required_plan = exc.required_plan_name
    except CostEconomicsError:
        return {
            "plan_eligible": False,
            "correction_enabled": False,
            "required_plan": "Growth",
            "state": "plan_check_unavailable",
            "summary": (
                "Managed correction access could not be confirmed. Public listing checks, "
                "saved history, and manual correction guidance remain available."
            ),
        }

    return {
        "plan_eligible": plan_eligible,
        "correction_enabled": False,
        "required_plan": required_plan,
        "state": (
            "provider_approval_required" if plan_eligible else "plan_upgrade_required"
        ),
        "summary": (
            "Your plan is eligible for managed directory corrections, but live submission "
            "and synchronization are not available until a production correction provider "
            "is approved."
            if plan_eligible
            else "Managed directory corrections require Growth. Public listing checks and "
            "manual correction guidance remain available."
        ),
    }


def require_listing_correction_workflow(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> Campaign:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    require_commercial_feature(
        db,
        organization_id=campaign.organization_id,
        feature_code=FEATURE_LISTING_CORRECTION_SYNC,
    )
    raise CostEconomicsError(
        (
            "Managed directory corrections are not available yet. Public listing checks "
            "and manual corrections remain available."
        ),
        reason_code="listing_correction_provider_not_approved",
        status_code=409,
    )


def create_outreach_campaign(
    db: Session, tenant_id: str, campaign_id: str, name: str
) -> OutreachCampaign:
    _campaign_or_404(db, tenant_id, campaign_id)
    item = OutreachCampaign(tenant_id=tenant_id, campaign_id=campaign_id, name=name, status="draft")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_outreach_contact(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    outreach_campaign_id: str,
    full_name: str,
    email: str,
) -> OutreachContact:
    _campaign_or_404(db, tenant_id, campaign_id)
    oc = db.get(OutreachCampaign, outreach_campaign_id)
    if oc is None or oc.tenant_id != tenant_id or oc.campaign_id != campaign_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Outreach campaign not found"
        )
    contact = OutreachContact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        outreach_campaign_id=outreach_campaign_id,
        full_name=full_name,
        email=email,
        status="draft",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def sync_backlinks(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    existing = (
        db.query(Backlink)
        .filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id)
        .count()
    )
    if existing == 0:
        provider = get_authority_provider()
        backlinks = provider.fetch_backlinks(campaign_id=campaign_id)
        for item in backlinks:
            db.add(
                Backlink(
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    source_url=item["source_url"],
                    target_url=item["target_url"],
                    quality_score=float(item["quality_score"]),
                    status=item.get("status", "live"),
                )
            )
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="authority.backlinks.ingested",
            payload={"campaign_id": campaign_id, "count": len(backlinks)},
        )
        db.commit()
    count = (
        db.query(Backlink)
        .filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id)
        .count()
    )
    return {"campaign_id": campaign_id, "backlinks_synced": count}


def list_backlinks(db: Session, tenant_id: str, campaign_id: str) -> list[Backlink]:
    return (
        db.query(Backlink)
        .filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id)
        .order_by(Backlink.discovered_at.desc())
        .all()
    )


def refresh_authority_link_gaps(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    idempotency_key: str,
    provider: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save a bounded, evidence-backed set of competitor-only referring pages."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    existing = (
        db.query(AuthorityGapResearchRun)
        .filter(
            AuthorityGapResearchRun.organization_id == organization_id,
            AuthorityGapResearchRun.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        if existing.campaign_id != campaign_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That refresh key was already used for another location.",
            )
        return _serialize_authority_gap_result(db, run=existing, created=False)

    owner_domain = _normalized_domain(campaign.domain)
    if not owner_domain:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add a valid website before checking trusted-link opportunities.",
        )
    competitors = (
        db.query(Competitor)
        .filter(
            Competitor.tenant_id == tenant_id,
            Competitor.campaign_id == campaign_id,
            Competitor.review_status == "confirmed",
        )
        .order_by(Competitor.domain.asc())
        .limit(AUTHORITY_GAP_COMPETITOR_LIMIT)
        .all()
    )
    if not competitors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Confirm at least one real competitor before checking trusted-link opportunities.",
        )

    credential_owner: str | None = None
    live_provider = provider
    if live_provider is None:
        try:
            credentials = resolve_provider_credentials(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
            credential_owner = resolve_provider_credential_owner(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking trusted-link opportunities.",
            ) from exc
        login = str(credentials.get("login") or "").strip()
        password = str(credentials.get("password") or "")
        if not login or not password:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking trusted-link opportunities.",
            )
        live_provider = DataForSeoAuthorityProvider(login=login, password=password)

    checked_at = now or datetime.now(UTC)
    reservation = None
    if credential_owner is not None:
        try:
            reservation = reserve_provider_cost(
                db,
                organization_id=organization_id,
                business_location_id=campaign.business_location_id,
                campaign_id=campaign.id,
                provider_name="dataforseo",
                capability=AUTHORITY_GAP_CAPABILITY,
                operation=AUTHORITY_GAP_OPERATION,
                credential_owner=credential_owner,
                quantity=1,
                idempotency_key=f"authority-link-gap:{campaign.id}:{idempotency_key}",
            )
        except CostEconomicsError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    competitor_snapshot = [
        {"id": row.id, "domain": row.domain, "label": row.label} for row in competitors
    ]
    run = AuthorityGapResearchRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        idempotency_key=idempotency_key,
        status="running",
        owner_domain=owner_domain,
        competitors=competitor_snapshot,
        result_limit=AUTHORITY_GAP_LIMIT,
        source_kind="live_link_index",
        reservation_id=reservation.id if reservation is not None else None,
        created_at=checked_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if reservation is not None:
        _authorize_authority_provider_dispatch(db, reservation=reservation, run=run)

    try:
        result = live_provider.page_intersection(
            targets=[row.domain for row in competitors],
            exclude_target=owner_domain,
            limit=AUTHORITY_GAP_LIMIT,
        )
    except ValueError as exc:
        if reservation is not None:
            release_provider_cost(db, reservation=reservation)
        run.status = "failed"
        run.error_code = "link_research_unavailable"
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Trusted-link research is temporarily unavailable. Try again shortly.",
        ) from exc

    if reservation is not None:
        reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=result.get("cost"),
        )
    confirmed_services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
    )
    included_areas, excluded_areas = business_service_area_service.confirmed_areas_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
    )
    normalized_items = _normalize_authority_gap_items(
        result.get("items", []),
        competitors=competitors,
        confirmed_services=confirmed_services,
        included_areas=included_areas,
        excluded_areas=excluded_areas,
        observed_at=checked_at,
    )
    for item in normalized_items:
        db.add(
            AuthorityLinkGap(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign.id,
                run_id=run.id,
                referring_domain=item["referring_domain"],
                source_url=item["source_url"],
                source_page_title=item["source_page_title"],
                competitor_matches=item["competitor_matches"],
                relevance_classification=item["relevance_classification"],
                matched_services=item["matched_services"],
                matched_service_areas=item["matched_service_areas"],
                relevance_reasons=item["relevance_reasons"],
                first_seen_at=item["first_seen_at"],
                last_seen_at=item["last_seen_at"],
                observed_at=checked_at,
                evidence=item["evidence"],
            )
        )
    run.status = "complete"
    run.provider_reported_cost = Decimal(str(result.get("cost", 0) or 0))
    run.result_count = len(normalized_items)
    run.observed_at = checked_at
    run.completed_at = datetime.now(UTC)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="authority.link_gaps.refreshed",
        payload={
            "campaign_id": campaign.id,
            "run_id": run.id,
            "competitors_compared": len(competitors),
            "gaps_saved": len(normalized_items),
        },
    )
    db.commit()
    return _serialize_authority_gap_result(db, run=run, created=True)


def latest_authority_link_gaps(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    run = (
        db.query(AuthorityGapResearchRun)
        .filter(
            AuthorityGapResearchRun.tenant_id == tenant_id,
            AuthorityGapResearchRun.organization_id == organization_id,
            AuthorityGapResearchRun.campaign_id == campaign_id,
            AuthorityGapResearchRun.status.in_(("complete", "partial")),
        )
        .order_by(
            AuthorityGapResearchRun.observed_at.desc(),
            AuthorityGapResearchRun.created_at.desc(),
        )
        .first()
    )
    if run is None:
        return {
            "run": None,
            "summary": {
                "exact_pages": 0,
                "referring_domains": 0,
                "competitors_compared": 0,
                "service_and_area_matches": 0,
                "service_matches": 0,
                "area_matches": 0,
                "needs_review": 0,
            },
            "items": [],
            "truth": {
                "classification": "not_collected",
                "summary": "No trusted-link comparison has been run for this location yet.",
            },
        }
    return _serialize_authority_gap_result(db, run=run, created=False)


def _serialize_authority_gap_result(
    db: Session,
    *,
    run: AuthorityGapResearchRun,
    created: bool,
) -> dict[str, Any]:
    rows = (
        db.query(AuthorityLinkGap)
        .filter(
            AuthorityLinkGap.tenant_id == run.tenant_id,
            AuthorityLinkGap.run_id == run.id,
        )
        .order_by(AuthorityLinkGap.observed_at.desc(), AuthorityLinkGap.referring_domain.asc())
        .all()
    )
    items = [_serialize_authority_link_gap(row) for row in rows]
    return {
        "created": created,
        "run": {
            "id": run.id,
            "status": run.status,
            "owner_domain": run.owner_domain,
            "competitors": run.competitors if isinstance(run.competitors, list) else [],
            "result_limit": run.result_limit,
            "source_type": "live_link_index",
            "observed_at": _iso_utc(run.observed_at),
        },
        "summary": {
            "exact_pages": len(items),
            "referring_domains": len({row["referring_domain"] for row in items}),
            "competitors_compared": len(
                run.competitors if isinstance(run.competitors, list) else []
            ),
            "service_and_area_matches": sum(
                row["relevance_classification"] == "service_and_area_match" for row in items
            ),
            "service_matches": sum(
                row["relevance_classification"] == "service_match" for row in items
            ),
            "area_matches": sum(row["relevance_classification"] == "area_match" for row in items),
            "needs_review": sum(row["relevance_classification"] == "needs_review" for row in items),
        },
        "items": items,
        "truth": {
            "classification": "provider_backed",
            "summary": (
                "These are saved referring pages found in a live comparison. "
                "Each page linked to a confirmed competitor while no link to this business "
                "was found in the same check."
            ),
        },
    }


def _serialize_authority_link_gap(row: AuthorityLinkGap) -> dict[str, Any]:
    matches = row.competitor_matches if isinstance(row.competitor_matches, list) else []
    classification = (
        row.relevance_classification
        if row.relevance_classification in _RELEVANCE_CLASSES
        else "needs_review"
    )
    return {
        "id": row.id,
        "referring_domain": row.referring_domain,
        "source_url": row.source_url,
        "source_page_title": row.source_page_title,
        "competitor_matches": matches,
        "competitor_match_count": len(matches),
        "relevance_classification": classification,
        "matched_services": row.matched_services if isinstance(row.matched_services, list) else [],
        "matched_service_areas": (
            row.matched_service_areas if isinstance(row.matched_service_areas, list) else []
        ),
        "relevance_reasons": (
            row.relevance_reasons if isinstance(row.relevance_reasons, list) else []
        ),
        "relevance_label": _relevance_label(classification),
        "first_seen_at": _iso_utc(row.first_seen_at),
        "last_seen_at": _iso_utc(row.last_seen_at),
        "source_updated_at": _iso_utc(row.observed_at),
        "why_it_matters": (
            f"This page links to {len(matches)} confirmed competitor"
            f"{'s' if len(matches) != 1 else ''}, but no link to your site was found in the same check."
        ),
        "next_step": (
            "Open the page, confirm it is relevant to your customers, then decide whether a useful "
            "local partnership, resource, or mention would make sense."
        ),
    }


def _relevance_label(classification: str) -> str:
    return {
        "service_and_area_match": "Matches a service and service area",
        "service_match": "Matches a confirmed service",
        "area_match": "Matches a confirmed service area",
        "needs_review": "Needs a quick relevance check",
    }.get(classification, "Needs a quick relevance check")


def _normalize_match_text(value: Any) -> str:
    decoded = unquote(str(value or "")).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", decoded).split())


def _term_matches(haystack: str, raw_term: Any) -> bool:
    term = _normalize_match_text(raw_term)
    if not term or term in _GENERIC_MATCH_TERMS:
        return False
    tokens = [token for token in term.split() if token not in _GENERIC_MATCH_TERMS]
    if not tokens:
        return False
    if len(tokens) == 1:
        token = tokens[0]
        return len(token) >= 4 and re.search(rf"\b{re.escape(token)}\b", haystack) is not None
    return all(re.search(rf"\b{re.escape(token)}\b", haystack) is not None for token in tokens)


def _classify_authority_gap_relevance(
    item: dict[str, Any],
    *,
    confirmed_services: list[Any],
    included_areas: list[Any],
    excluded_areas: list[Any],
) -> dict[str, Any]:
    matches = (
        item.get("competitor_matches") if isinstance(item.get("competitor_matches"), list) else []
    )
    searchable_parts = [
        item.get("source_url"),
        item.get("source_page_title"),
        item.get("snippet"),
        item.get("referring_domain"),
        *[match.get("anchor") for match in matches if isinstance(match, dict)],
        *[match.get("target_url") for match in matches if isinstance(match, dict)],
    ]
    haystack = _normalize_match_text(" ".join(str(part or "") for part in searchable_parts))

    matched_services: list[dict[str, Any]] = []
    for service in confirmed_services:
        terms = [
            service.name,
            service.normalized_name,
            service.canonical_category,
            *list(service.aliases or []),
        ]
        if any(_term_matches(haystack, term) for term in terms):
            matched_services.append({"id": service.id, "name": service.name})

    matched_areas: list[dict[str, Any]] = []
    for area in included_areas:
        terms = [area.name, area.normalized_name]
        if area.region:
            terms.append(f"{area.name} {area.region}")
        if any(_term_matches(haystack, term) for term in terms):
            matched_areas.append({"id": area.id, "name": area.name, "region": area.region})

    excluded_matches = [
        area
        for area in excluded_areas
        if any(
            _term_matches(haystack, term)
            for term in (
                area.name,
                area.normalized_name,
                f"{area.name} {area.region}" if area.region else "",
            )
        )
    ]
    reasons: list[str] = []
    if excluded_matches:
        classification = "needs_review"
        reasons.append(
            "The page appears to name an area marked outside this location's service area."
        )
    elif matched_services and matched_areas:
        classification = "service_and_area_match"
        reasons.append("The page text matches a confirmed service and service area.")
    elif matched_services:
        classification = "service_match"
        reasons.append("The page text matches a confirmed service.")
    elif matched_areas:
        classification = "area_match"
        reasons.append("The page text matches a confirmed service area.")
    else:
        classification = "needs_review"
        reasons.append(
            "No confirmed service or service-area wording was found in the saved page evidence."
        )
    return {
        "relevance_classification": classification,
        "matched_services": matched_services,
        "matched_service_areas": matched_areas,
        "relevance_reasons": reasons,
    }


def _normalize_authority_gap_items(
    rows: Any,
    *,
    competitors: list[Competitor],
    confirmed_services: list[Any],
    included_areas: list[Any],
    excluded_areas: list[Any],
    observed_at: datetime,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    competitor_by_key = {
        str(index): competitor for index, competitor in enumerate(competitors, start=1)
    }
    by_source: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        intersections = raw.get("page_intersection")
        if not isinstance(intersections, dict):
            continue
        for key, link_rows in intersections.items():
            competitor = competitor_by_key.get(str(key))
            if competitor is None or not isinstance(link_rows, list):
                continue
            for link in link_rows:
                if not isinstance(link, dict) or bool(link.get("is_lost")):
                    continue
                source_url = str(link.get("url_from") or "").strip()
                target_url = str(link.get("url_to") or "").strip()
                referring_domain = _normalized_domain(link.get("domain_from"))
                if not source_url or not target_url or not referring_domain:
                    continue
                item = by_source.setdefault(
                    source_url,
                    {
                        "referring_domain": referring_domain,
                        "source_url": source_url,
                        "source_page_title": _optional_text(link.get("page_from_title")),
                        "competitor_matches": [],
                        "first_seen_values": [],
                        "last_seen_values": [],
                        "evidence": {
                            "source_type": "live_link_index",
                            "source_url": source_url,
                            "referring_domain": referring_domain,
                            "observed_at": observed_at.isoformat(),
                        },
                    },
                )
                first_seen = _provider_datetime(link.get("first_seen"))
                last_seen = _provider_datetime(link.get("last_seen"))
                item["competitor_matches"].append(
                    {
                        "competitor_id": competitor.id,
                        "competitor_domain": competitor.domain,
                        "competitor_label": competitor.label,
                        "target_url": target_url,
                        "link_type": _optional_text(link.get("item_type")),
                        "dofollow": bool(link.get("dofollow")),
                        "anchor": _optional_text(link.get("anchor")),
                        "first_seen_at": first_seen.isoformat() if first_seen else None,
                        "last_seen_at": last_seen.isoformat() if last_seen else None,
                    }
                )
                if first_seen is not None:
                    item["first_seen_values"].append(first_seen)
                if last_seen is not None:
                    item["last_seen_values"].append(last_seen)
    normalized: list[dict[str, Any]] = []
    for item in by_source.values():
        matches = item["competitor_matches"]
        deduped = {(match["competitor_id"], match["target_url"]): match for match in matches}
        item["competitor_matches"] = list(deduped.values())
        item["first_seen_at"] = min(item.pop("first_seen_values"), default=None)
        item["last_seen_at"] = max(item.pop("last_seen_values"), default=None)
        relevance = _classify_authority_gap_relevance(
            item,
            confirmed_services=confirmed_services,
            included_areas=included_areas,
            excluded_areas=excluded_areas,
        )
        item.update(relevance)
        item["evidence"]["relevance"] = relevance
        normalized.append(item)
    relevance_order = {
        "service_and_area_match": 3,
        "service_match": 2,
        "area_match": 1,
        "needs_review": 0,
    }
    normalized.sort(
        key=lambda item: (
            relevance_order[item["relevance_classification"]],
            len(item["competitor_matches"]),
            item["last_seen_at"] or datetime.min.replace(tzinfo=UTC),
            item["referring_domain"],
        ),
        reverse=True,
    )
    return normalized[:AUTHORITY_GAP_LIMIT]


def refresh_authority_link_changes(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    idempotency_key: str,
    provider: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save bounded exact owner backlinks explicitly reported as new or lost."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    existing = (
        db.query(AuthorityLinkChangeRun)
        .filter(
            AuthorityLinkChangeRun.organization_id == organization_id,
            AuthorityLinkChangeRun.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        if existing.campaign_id != campaign_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That refresh key was already used for another location.",
            )
        return _serialize_authority_link_change_result(db, run=existing, created=False)

    owner_domain = _normalized_domain(campaign.domain)
    if not owner_domain:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add a valid website before checking changes to website mentions.",
        )

    credential_owner: str | None = None
    live_provider = provider
    if live_provider is None:
        try:
            credentials = resolve_provider_credentials(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
            credential_owner = resolve_provider_credential_owner(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking website mentions.",
            ) from exc
        login = str(credentials.get("login") or "").strip()
        password = str(credentials.get("password") or "")
        if not login or not password:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking website mentions.",
            )
        live_provider = DataForSeoAuthorityProvider(login=login, password=password)

    checked_at = now or datetime.now(UTC)
    reservation = None
    if credential_owner is not None:
        try:
            reservation = reserve_provider_cost(
                db,
                organization_id=organization_id,
                business_location_id=campaign.business_location_id,
                campaign_id=campaign.id,
                provider_name="dataforseo",
                capability=AUTHORITY_LINK_CHANGE_CAPABILITY,
                operation=AUTHORITY_LINK_CHANGE_OPERATION,
                credential_owner=credential_owner,
                quantity=1,
                idempotency_key=f"authority-link-changes:{campaign.id}:{idempotency_key}",
            )
        except CostEconomicsError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    run = AuthorityLinkChangeRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        idempotency_key=idempotency_key,
        status="running",
        owner_domain=owner_domain,
        result_limit_per_state=AUTHORITY_LINK_CHANGE_LIMIT,
        source_kind="live_link_index",
        reservation_id=reservation.id if reservation is not None else None,
        created_at=checked_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if reservation is not None:
        _authorize_authority_provider_dispatch(db, reservation=reservation, run=run)

    try:
        result = live_provider.backlink_changes(
            target=owner_domain,
            limit_per_state=AUTHORITY_LINK_CHANGE_LIMIT,
        )
    except ValueError as exc:
        if reservation is not None:
            release_provider_cost(db, reservation=reservation)
        run.status = "failed"
        run.error_code = "link_changes_unavailable"
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Website mention history is temporarily unavailable. Try again shortly.",
        ) from exc

    if reservation is not None:
        reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=result.get("cost"),
        )
    new_items = _normalize_authority_link_changes(
        result.get("new_items", []),
        change_state="new",
        observed_at=checked_at,
    )
    lost_items = _normalize_authority_link_changes(
        result.get("lost_items", []),
        change_state="lost",
        observed_at=checked_at,
    )
    for item in [*new_items, *lost_items]:
        db.add(
            AuthorityLinkChange(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign.id,
                run_id=run.id,
                change_state=item["change_state"],
                referring_domain=item["referring_domain"],
                source_url=item["source_url"],
                source_page_title=item["source_page_title"],
                target_url=item["target_url"],
                link_type=item["link_type"],
                dofollow=item["dofollow"],
                anchor=item["anchor"],
                first_seen_at=item["first_seen_at"],
                last_seen_at=item["last_seen_at"],
                observed_at=checked_at,
                evidence=item["evidence"],
            )
        )
    run.status = "complete"
    run.provider_reported_cost = Decimal(str(result.get("cost", 0) or 0))
    run.new_count = len(new_items)
    run.lost_count = len(lost_items)
    run.observed_at = checked_at
    run.completed_at = datetime.now(UTC)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="authority.link_changes.refreshed",
        payload={
            "campaign_id": campaign.id,
            "run_id": run.id,
            "new_links_saved": len(new_items),
            "lost_links_saved": len(lost_items),
        },
    )
    db.commit()
    return _serialize_authority_link_change_result(db, run=run, created=True)


def latest_authority_link_changes(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    run = (
        db.query(AuthorityLinkChangeRun)
        .filter(
            AuthorityLinkChangeRun.tenant_id == tenant_id,
            AuthorityLinkChangeRun.organization_id == organization_id,
            AuthorityLinkChangeRun.campaign_id == campaign_id,
            AuthorityLinkChangeRun.status.in_(("complete", "partial")),
        )
        .order_by(
            AuthorityLinkChangeRun.observed_at.desc(),
            AuthorityLinkChangeRun.created_at.desc(),
        )
        .first()
    )
    if run is None:
        return {
            "run": None,
            "summary": {"new_links": 0, "lost_links": 0, "new_websites": 0, "lost_websites": 0},
            "new_items": [],
            "lost_items": [],
            "truth": {
                "classification": "not_collected",
                "summary": "No website mention history has been checked for this location yet.",
            },
        }
    return _serialize_authority_link_change_result(db, run=run, created=False)


def refresh_authority_inventory(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    business_name: str,
    idempotency_key: str,
    provider: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save bounded incoming links and exact-name mentions verified against the same link index."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    clean_business_name = " ".join(str(business_name or "").split()).strip()
    if len(clean_business_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter the exact business name customers see.",
        )
    existing = (
        db.query(AuthorityInventoryRun)
        .filter(
            AuthorityInventoryRun.organization_id == organization_id,
            AuthorityInventoryRun.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        if existing.campaign_id != campaign_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That refresh key was already used for another location.",
            )
        return _serialize_authority_inventory_result(db, run=existing, created=False)

    owner_domain = _normalized_domain(campaign.domain)
    if not owner_domain:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Add a valid website before checking websites that mention the business.",
        )

    credential_owner: str | None = None
    live_provider = provider
    if live_provider is None:
        try:
            credentials = resolve_provider_credentials(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
            credential_owner = resolve_provider_credential_owner(
                db,
                organization_id,
                "dataforseo",
                required_credential_mode="byo_optional",
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking website mentions.",
            ) from exc
        login = str(credentials.get("login") or "").strip()
        password = str(credentials.get("password") or "")
        if not login or not password:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connect the market research source before checking website mentions.",
            )
        live_provider = DataForSeoAuthorityProvider(login=login, password=password)

    checked_at = now or datetime.now(UTC)
    reservation = None
    if credential_owner is not None:
        try:
            reservation = reserve_provider_cost(
                db,
                organization_id=organization_id,
                business_location_id=campaign.business_location_id,
                campaign_id=campaign.id,
                provider_name="dataforseo",
                capability=AUTHORITY_INVENTORY_CAPABILITY,
                operation=AUTHORITY_INVENTORY_OPERATION,
                credential_owner=credential_owner,
                quantity=1,
                idempotency_key=f"authority-inventory:{campaign.id}:{idempotency_key}",
            )
        except CostEconomicsError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    run = AuthorityInventoryRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=campaign.business_location_id,
        idempotency_key=idempotency_key,
        status="running",
        owner_domain=owner_domain,
        business_name=clean_business_name,
        link_limit=AUTHORITY_INVENTORY_LINK_LIMIT,
        mention_limit=AUTHORITY_INVENTORY_MENTION_LIMIT,
        source_kind="live_web_index",
        reservation_id=reservation.id if reservation is not None else None,
        created_at=checked_at,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if reservation is not None:
        _authorize_authority_provider_dispatch(db, reservation=reservation, run=run)

    try:
        result = live_provider.authority_inventory(
            target=owner_domain,
            business_name=clean_business_name,
            link_limit=AUTHORITY_INVENTORY_LINK_LIMIT,
            mention_limit=AUTHORITY_INVENTORY_MENTION_LIMIT,
        )
    except ValueError as exc:
        if reservation is not None:
            release_provider_cost(db, reservation=reservation)
        run.status = "failed"
        run.error_code = "authority_inventory_unavailable"
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Website mention research is temporarily unavailable. Try again shortly.",
        ) from exc

    if reservation is not None:
        reconcile_provider_cost(
            db,
            reservation=reservation,
            provider_reported_cost=result.get("cost"),
        )
    links = _normalize_authority_inventory_links(
        result.get("link_items", []),
        observed_at=checked_at,
    )
    confirmed_services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
    )
    included_areas, excluded_areas = business_service_area_service.confirmed_areas_for_campaign(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
    )
    mentions, checked_candidate_count = _normalize_authority_unlinked_mentions(
        result.get("mention_items", []),
        linked_rows=result.get("mention_link_items", []),
        owner_domain=owner_domain,
        business_name=clean_business_name,
        confirmed_services=confirmed_services,
        included_areas=included_areas,
        excluded_areas=excluded_areas,
        observed_at=checked_at,
    )
    for item in links:
        db.add(
            AuthorityInventoryLink(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign.id,
                run_id=run.id,
                referring_domain=item["referring_domain"],
                source_url=item["source_url"],
                source_page_title=item["source_page_title"],
                target_url=item["target_url"],
                link_type=item["link_type"],
                dofollow=item["dofollow"],
                anchor=item["anchor"],
                first_seen_at=item["first_seen_at"],
                last_seen_at=item["last_seen_at"],
                observed_at=checked_at,
                evidence=item["evidence"],
            )
        )
    for item in mentions:
        db.add(
            AuthorityUnlinkedMention(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign.id,
                run_id=run.id,
                referring_domain=item["referring_domain"],
                source_url=item["source_url"],
                source_page_title=item["source_page_title"],
                snippet=item["snippet"],
                mentioned_name=clean_business_name,
                relevance_classification=item["relevance_classification"],
                matched_services=item["matched_services"],
                matched_service_areas=item["matched_service_areas"],
                relevance_reasons=item["relevance_reasons"],
                observed_at=checked_at,
                evidence=item["evidence"],
            )
        )
    run.status = "complete"
    run.provider_reported_cost = Decimal(str(result.get("cost", 0) or 0))
    run.link_count = len(links)
    run.mention_candidate_count = checked_candidate_count
    run.unlinked_mention_count = len(mentions)
    run.observed_at = checked_at
    run.completed_at = datetime.now(UTC)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="authority.inventory.refreshed",
        payload={
            "campaign_id": campaign.id,
            "run_id": run.id,
            "links_saved": len(links),
            "exact_name_pages_checked": checked_candidate_count,
            "unlinked_mentions_saved": len(mentions),
        },
    )
    db.commit()
    return _serialize_authority_inventory_result(db, run=run, created=True)


def latest_authority_inventory(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    run = (
        db.query(AuthorityInventoryRun)
        .filter(
            AuthorityInventoryRun.tenant_id == tenant_id,
            AuthorityInventoryRun.organization_id == organization_id,
            AuthorityInventoryRun.campaign_id == campaign_id,
            AuthorityInventoryRun.status.in_(("complete", "partial")),
        )
        .order_by(AuthorityInventoryRun.observed_at.desc(), AuthorityInventoryRun.created_at.desc())
        .first()
    )
    if run is None:
        return {
            "run": None,
            "summary": {
                "incoming_links": 0,
                "linking_websites": 0,
                "exact_name_pages_checked": 0,
                "unlinked_mentions": 0,
            },
            "links": [],
            "unlinked_mentions": [],
            "truth": {
                "classification": "not_collected",
                "summary": "No complete website mention inventory has been saved for this location yet.",
            },
        }
    return _serialize_authority_inventory_result(db, run=run, created=False)


def _serialize_authority_inventory_result(
    db: Session,
    *,
    run: AuthorityInventoryRun,
    created: bool,
) -> dict[str, Any]:
    link_rows = (
        db.query(AuthorityInventoryLink)
        .filter(
            AuthorityInventoryLink.tenant_id == run.tenant_id,
            AuthorityInventoryLink.run_id == run.id,
        )
        .order_by(AuthorityInventoryLink.last_seen_at.desc(), AuthorityInventoryLink.referring_domain.asc())
        .all()
    )
    mention_rows = (
        db.query(AuthorityUnlinkedMention)
        .filter(
            AuthorityUnlinkedMention.tenant_id == run.tenant_id,
            AuthorityUnlinkedMention.run_id == run.id,
        )
        .order_by(AuthorityUnlinkedMention.relevance_classification.asc(), AuthorityUnlinkedMention.referring_domain.asc())
        .all()
    )
    links = [_serialize_authority_inventory_link(row) for row in link_rows]
    mentions = [_serialize_authority_unlinked_mention(row) for row in mention_rows]
    return {
        "created": created,
        "run": {
            "id": run.id,
            "status": run.status,
            "owner_domain": run.owner_domain,
            "business_name": run.business_name,
            "link_limit": run.link_limit,
            "mention_limit": run.mention_limit,
            "observed_at": _iso_utc(run.observed_at),
        },
        "summary": {
            "incoming_links": len(links),
            "linking_websites": len({row["referring_domain"] for row in links}),
            "exact_name_pages_checked": run.mention_candidate_count,
            "unlinked_mentions": len(mentions),
        },
        "links": links,
        "unlinked_mentions": mentions,
        "truth": {
            "classification": "provider_backed",
            "summary": (
                "Incoming links are exact saved source and destination pages. A page appears under "
                "possible unlinked mentions only when the saved page evidence contains the exact "
                "business name and the same check found no link from that exact page to this website."
            ),
        },
    }


def _serialize_authority_inventory_link(row: AuthorityInventoryLink) -> dict[str, Any]:
    return {
        "id": row.id,
        "referring_domain": row.referring_domain,
        "source_url": row.source_url,
        "source_page_title": row.source_page_title,
        "target_url": row.target_url,
        "link_type": row.link_type,
        "dofollow": row.dofollow,
        "anchor": row.anchor,
        "first_seen_at": _iso_utc(row.first_seen_at),
        "last_seen_at": _iso_utc(row.last_seen_at),
        "source_updated_at": _iso_utc(row.observed_at),
    }


def _serialize_authority_unlinked_mention(row: AuthorityUnlinkedMention) -> dict[str, Any]:
    return {
        "id": row.id,
        "referring_domain": row.referring_domain,
        "source_url": row.source_url,
        "source_page_title": row.source_page_title,
        "snippet": row.snippet,
        "mentioned_name": row.mentioned_name,
        "relevance_classification": row.relevance_classification,
        "relevance_label": _relevance_label(row.relevance_classification),
        "matched_services": list(row.matched_services or []),
        "matched_service_areas": list(row.matched_service_areas or []),
        "relevance_reasons": list(row.relevance_reasons or []),
        "source_updated_at": _iso_utc(row.observed_at),
        "status_label": "Business name found; no website link found in this check",
        "why_it_matters": (
            "This page already names the business, so confirming the listing and adding a useful "
            "website link may help customers reach the right page."
        ),
        "next_step": (
            "Open the page, confirm the mention is accurate and relevant, then ask the site owner "
            "to add the most useful business page only if it helps their visitors."
        ),
    }


def create_authority_action(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    source_type: str,
    source_id: str,
    owner_confirmed_relevant: bool,
) -> dict[str, Any]:
    """Promote exact link evidence into one review-only, measurable Next Step."""

    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    source_url: str
    target_url: str
    source_title: str | None
    referring_domain: str
    source_run_id: str
    source_observed_at: datetime
    action_id: str
    source_record: AuthorityLinkGap | AuthorityLinkChange | AuthorityUnlinkedMention
    relevance: dict[str, Any]
    if source_type == "competitor_gap":
        gap = (
            db.query(AuthorityLinkGap)
            .filter(
                AuthorityLinkGap.id == source_id,
                AuthorityLinkGap.tenant_id == tenant_id,
                AuthorityLinkGap.organization_id == organization_id,
                AuthorityLinkGap.campaign_id == campaign_id,
            )
            .first()
        )
        if gap is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That website opportunity is no longer available.",
            )
        if gap.relevance_classification == "needs_review" and not owner_confirmed_relevant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Confirm that this page is useful to your customers before adding it.",
            )
        source_record = gap
        source_url = gap.source_url
        target_url = str(campaign.domain or "")
        source_title = gap.source_page_title
        referring_domain = gap.referring_domain
        source_run_id = gap.run_id
        source_observed_at = gap.observed_at
        action_id = AUTHORITY_GAP_ACTION_ID
        relevance = {
            "classification": gap.relevance_classification,
            "owner_confirmed": bool(owner_confirmed_relevant),
            "matched_services": list(gap.matched_services or []),
            "matched_service_areas": list(gap.matched_service_areas or []),
            "reasons": list(gap.relevance_reasons or []),
        }
        rationale = (
            f"Review whether a useful, truthful mention on {referring_domain} would help customers "
            "find the business. The exact page already links to a confirmed competitor, and its "
            "relevance was checked against the business's saved services and service areas."
        )
        confidence = _authority_relevance_confidence(
            gap.relevance_classification,
            owner_confirmed=owner_confirmed_relevant,
        )
    elif source_type == "lost_link":
        link_change = (
            db.query(AuthorityLinkChange)
            .filter(
                AuthorityLinkChange.id == source_id,
                AuthorityLinkChange.tenant_id == tenant_id,
                AuthorityLinkChange.organization_id == organization_id,
                AuthorityLinkChange.campaign_id == campaign_id,
                AuthorityLinkChange.change_state == "lost",
            )
            .first()
        )
        if link_change is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That lost website mention is no longer available.",
            )
        source_record = link_change
        source_url = link_change.source_url
        target_url = link_change.target_url
        source_title = link_change.source_page_title
        referring_domain = link_change.referring_domain
        source_run_id = link_change.run_id
        source_observed_at = link_change.observed_at
        action_id = AUTHORITY_RESTORE_ACTION_ID
        relevance = {
            "classification": "previously_linked",
            "owner_confirmed": False,
            "matched_services": [],
            "matched_service_areas": [],
            "reasons": ["This exact page previously linked to the business website."],
        }
        rationale = (
            f"Check the exact page on {referring_domain}. If the business still belongs there, "
            "ask the site owner to restore or update the link to the most useful page."
        )
        confidence = 0.84
    elif source_type == "unlinked_mention":
        mention = (
            db.query(AuthorityUnlinkedMention)
            .filter(
                AuthorityUnlinkedMention.id == source_id,
                AuthorityUnlinkedMention.tenant_id == tenant_id,
                AuthorityUnlinkedMention.organization_id == organization_id,
                AuthorityUnlinkedMention.campaign_id == campaign_id,
            )
            .first()
        )
        if mention is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That business mention is no longer available.",
            )
        if mention.relevance_classification == "needs_review" and not owner_confirmed_relevant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Confirm that this page is useful to your customers before adding it.",
            )
        source_record = mention
        source_url = mention.source_url
        target_url = _absolute_url(campaign.domain)
        source_title = mention.source_page_title
        referring_domain = mention.referring_domain
        source_run_id = mention.run_id
        source_observed_at = mention.observed_at
        action_id = AUTHORITY_GAP_ACTION_ID
        relevance = {
            "classification": mention.relevance_classification,
            "owner_confirmed": bool(owner_confirmed_relevant),
            "matched_services": list(mention.matched_services or []),
            "matched_service_areas": list(mention.matched_service_areas or []),
            "reasons": list(mention.relevance_reasons or []),
        }
        rationale = (
            f"The exact page on {referring_domain} contains the saved business name, while the "
            "same check found no link from that exact page to the business website. Confirm the "
            "mention is accurate, then request a useful link only if it helps the page's visitors."
        )
        confidence = _authority_relevance_confidence(
            mention.relevance_classification,
            owner_confirmed=owner_confirmed_relevant,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a competitor opportunity, an unlinked mention, or a lost website mention.",
        )

    canonical_source_url = _canonical_url(source_url)
    canonical_target_url = _canonical_url(target_url)
    evidence_key = json.dumps(
        {
            "action_id": action_id,
            "source_url": canonical_source_url,
            "target_url": canonical_target_url,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    idempotency_key = "authority:" + hashlib.sha256(evidence_key.encode("utf-8")).hexdigest()[:32]
    existing = (
        db.query(StrategyRecommendation)
        .filter(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.campaign_id == campaign_id,
            StrategyRecommendation.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        existing_status = (
            existing.status.value if hasattr(existing.status, "value") else str(existing.status)
        )
        active_statuses = {"GENERATED", "VALIDATED", "APPROVED", "SCHEDULED"}
        return {
            "created": False,
            "message": (
                "This website follow-up is already in Next Steps."
                if existing_status in active_statuses
                else "This website follow-up was already handled. Its history remains in Next Steps."
            ),
            "item": _serialize_authority_action(existing),
        }

    evidence = {
        "source": "authority_research",
        "source_type": source_type,
        "source_record_id": source_record.id,
        "source_run_id": source_run_id,
        "source_url": source_url,
        "source_page_title": source_title,
        "referring_domain": referring_domain,
        "target_url": target_url,
        "source_observed_at": _iso_utc(source_observed_at),
        "action_id": action_id,
        "recommended_actions": [action_id, AUTHORITY_ACTION_FALLBACK_ID],
        "relevance": relevance,
        "affected_urls": list(dict.fromkeys([source_url, target_url])),
        "evidence": [
            f"Exact source page: {source_url}",
            f"Business destination: {target_url}",
            "The saved check does not promise a ranking improvement.",
        ],
        "measurement_contract": {
            "metric_id": AUTHORITY_LINK_METRIC_ID,
            "plain_language": "Whether this exact page links to the business website.",
            "source_url": source_url,
            "owner_domain": _normalized_domain(campaign.domain),
            "baseline": 0,
            "target": 1,
            "direction": "higher_is_better",
            "check": "Run a fresh website-mention check after the follow-up.",
        },
    }
    recommendation = StrategyRecommendation(
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        recommendation_type=action_id,
        rationale=rationale,
        confidence=confidence,
        confidence_score=confidence,
        evidence_json=json.dumps(evidence, sort_keys=True),
        risk_tier=1,
        rollback_plan_json=json.dumps(
            {"steps": ["archive_recommendation_without_changing_the_website"]}
        ),
        status=StrategyRecommendationStatus.GENERATED,
        engine_version=AUTHORITY_INTELLIGENCE_VERSION,
        threshold_bundle_version=AUTHORITY_RELEVANCE_RULES_VERSION,
        idempotency_key=idempotency_key,
    )
    db.add(recommendation)
    db.flush()
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="recommendation.generated",
        payload={
            "campaign_id": campaign.id,
            "recommendation_id": recommendation.id,
            "status": recommendation.status.value,
            "source": "authority_research",
            "source_type": source_type,
        },
    )
    db.commit()
    db.refresh(recommendation)
    return {
        "created": True,
        "message": "Added to Next Steps for review. No website changes were made.",
        "item": _serialize_authority_action(recommendation),
    }


def _serialize_authority_action(item: StrategyRecommendation) -> dict[str, Any]:
    try:
        evidence = json.loads(item.evidence_json or "{}")
    except json.JSONDecodeError:
        evidence = {}
    return {
        "id": item.id,
        "action_id": evidence.get("action_id") or item.recommendation_type,
        "source_type": evidence.get("source_type"),
        "source_url": evidence.get("source_url"),
        "target_url": evidence.get("target_url"),
        "status": item.status.value if hasattr(item.status, "value") else str(item.status),
    }


def create_authority_outreach_draft(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    source_type: str,
    source_id: str,
    owner_confirmed_relevant: bool,
    actor_user_id: str,
) -> dict[str, Any]:
    """Prepare one evidence-backed message that the owner must review and send manually."""

    action = create_authority_action(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        source_type=source_type,
        source_id=source_id,
        owner_confirmed_relevant=owner_confirmed_relevant,
    )
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if source_type == "competitor_gap":
        source = (
            db.query(AuthorityLinkGap)
            .filter(
                AuthorityLinkGap.id == source_id,
                AuthorityLinkGap.tenant_id == tenant_id,
                AuthorityLinkGap.organization_id == organization_id,
                AuthorityLinkGap.campaign_id == campaign_id,
            )
            .first()
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That website opportunity is no longer available.",
            )
        source_url = source.source_url
        target_url = _absolute_url(campaign.domain)
        referring_domain = source.referring_domain
        source_title = source.source_page_title
        relevance = {
            "classification": source.relevance_classification,
            "matched_services": list(source.matched_services or []),
            "matched_service_areas": list(source.matched_service_areas or []),
            "reasons": list(source.relevance_reasons or []),
        }
    elif source_type == "lost_link":
        source = (
            db.query(AuthorityLinkChange)
            .filter(
                AuthorityLinkChange.id == source_id,
                AuthorityLinkChange.tenant_id == tenant_id,
                AuthorityLinkChange.organization_id == organization_id,
                AuthorityLinkChange.campaign_id == campaign_id,
                AuthorityLinkChange.change_state == "lost",
            )
            .first()
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That lost website mention is no longer available.",
            )
        source_url = source.source_url
        target_url = _absolute_url(source.target_url)
        referring_domain = source.referring_domain
        source_title = source.source_page_title
        relevance = {
            "classification": "previously_linked",
            "matched_services": [],
            "matched_service_areas": [],
            "reasons": ["This exact page previously linked to the business website."],
        }
    elif source_type == "unlinked_mention":
        source = (
            db.query(AuthorityUnlinkedMention)
            .filter(
                AuthorityUnlinkedMention.id == source_id,
                AuthorityUnlinkedMention.tenant_id == tenant_id,
                AuthorityUnlinkedMention.organization_id == organization_id,
                AuthorityUnlinkedMention.campaign_id == campaign_id,
            )
            .first()
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="That business mention is no longer available.",
            )
        source_url = source.source_url
        target_url = _absolute_url(campaign.domain)
        referring_domain = source.referring_domain
        source_title = source.source_page_title
        relevance = {
            "classification": source.relevance_classification,
            "matched_services": list(source.matched_services or []),
            "matched_service_areas": list(source.matched_service_areas or []),
            "reasons": list(source.relevance_reasons or []),
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a competitor opportunity, an unlinked mention, or a lost website mention.",
        )

    evidence_key = json.dumps(
        {
            "recommendation_id": action["item"]["id"],
            "source_type": source_type,
            "source_url": _canonical_url(source_url),
            "target_url": _canonical_url(target_url),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    idempotency_key = (
        "authority-outreach:" + hashlib.sha256(evidence_key.encode("utf-8")).hexdigest()[:32]
    )
    existing = (
        db.query(AuthorityOutreachDraft)
        .filter(
            AuthorityOutreachDraft.tenant_id == tenant_id,
            AuthorityOutreachDraft.organization_id == organization_id,
            AuthorityOutreachDraft.campaign_id == campaign_id,
            AuthorityOutreachDraft.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return {
            "created": False,
            "message": "This message is already saved below.",
            "item": _serialize_authority_outreach_draft(existing),
        }

    subject, message_body = _authority_outreach_copy(
        campaign=campaign,
        source_type=source_type,
        referring_domain=referring_domain,
        source_title=source_title,
        target_url=target_url,
        relevance=relevance,
    )
    now = datetime.now(UTC)
    draft = AuthorityOutreachDraft(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        business_location_id=campaign.business_location_id,
        recommendation_id=action["item"]["id"],
        source_type=source_type,
        source_record_id=source_id,
        source_url=source_url,
        target_url=target_url,
        referring_domain=referring_domain,
        subject=subject,
        message_body=message_body,
        status="draft",
        owner_confirmed_recipient=False,
        evidence={
            "source_url": source_url,
            "target_url": target_url,
            "source_page_title": source_title,
            "relevance": relevance,
            "recommendation_id": action["item"]["id"],
            "manual_send_only": True,
            "ranking_promise": False,
        },
        idempotency_key=idempotency_key,
        created_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    db.flush()
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="authority.outreach_draft.created",
        payload={
            "campaign_id": campaign_id,
            "outreach_draft_id": draft.id,
            "recommendation_id": draft.recommendation_id,
            "source_type": source_type,
            "status": draft.status,
            "manual_send_only": True,
        },
    )
    db.commit()
    db.refresh(draft)
    return {
        "created": True,
        "message": "A review-only message is ready below. Nothing was sent.",
        "item": _serialize_authority_outreach_draft(draft),
    }


def list_authority_outreach_drafts(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    rows = (
        db.query(AuthorityOutreachDraft)
        .filter(
            AuthorityOutreachDraft.tenant_id == tenant_id,
            AuthorityOutreachDraft.organization_id == organization_id,
            AuthorityOutreachDraft.campaign_id == campaign_id,
        )
        .order_by(AuthorityOutreachDraft.updated_at.desc())
        .all()
    )
    return {
        "items": [_serialize_authority_outreach_draft(row) for row in rows],
        "summary": {
            "drafts": sum(row.status == "draft" for row in rows),
            "reviewed": sum(row.status == "reviewed" for row in rows),
            "closed": sum(row.status == "closed" for row in rows),
        },
        "truth": {
            "classification": "owner_reviewed_workflow",
            "summary": (
                "Messages use saved page evidence. InsightOS does not find or invent recipients, "
                "send email, or promise a ranking result."
            ),
        },
    }


def update_authority_outreach_draft(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    draft_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    if str(campaign.organization_id or "") != str(organization_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    draft = (
        db.query(AuthorityOutreachDraft)
        .filter(
            AuthorityOutreachDraft.id == draft_id,
            AuthorityOutreachDraft.tenant_id == tenant_id,
            AuthorityOutreachDraft.organization_id == organization_id,
            AuthorityOutreachDraft.campaign_id == campaign_id,
        )
        .first()
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That saved message was not found.",
        )

    cleaned_email = (
        _optional_text(updates.get("contact_email"))
        if "contact_email" in updates
        else draft.contact_email
    )
    cleaned_contact_page = (
        _optional_text(updates.get("contact_page_url"))
        if "contact_page_url" in updates
        else draft.contact_page_url
    )
    if cleaned_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid contact email address or leave it blank.",
        )
    if cleaned_contact_page and not _is_http_url(cleaned_contact_page):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a complete contact-page address beginning with http:// or https://.",
        )

    if "contact_name" in updates:
        draft.contact_name = _optional_text(updates.get("contact_name"))
    draft.contact_email = cleaned_email
    draft.contact_page_url = cleaned_contact_page
    if "subject" in updates and updates.get("subject") is not None:
        draft.subject = str(updates["subject"]).strip()
    if "message_body" in updates and updates.get("message_body") is not None:
        draft.message_body = str(updates["message_body"]).strip()
    if not draft.subject or not draft.message_body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Keep both the subject and message before saving.",
        )
    draft_status = str(updates.get("status") or draft.status)
    owner_confirmed_recipient = bool(
        updates.get("owner_confirmed_recipient", draft.owner_confirmed_recipient)
    )
    if draft_status == "reviewed":
        if not owner_confirmed_recipient:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Confirm that you checked the recipient before marking this ready.",
            )
        if not (cleaned_email or cleaned_contact_page):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Add a verified email address or the site's contact page first.",
            )

    draft.status = draft_status
    draft.owner_confirmed_recipient = bool(owner_confirmed_recipient)
    draft.updated_at = datetime.now(UTC)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="authority.outreach_draft.reviewed"
        if draft_status == "reviewed"
        else "authority.outreach_draft.updated",
        payload={
            "campaign_id": campaign_id,
            "outreach_draft_id": draft.id,
            "status": draft.status,
            "recipient_confirmed": draft.owner_confirmed_recipient,
            "manual_send_only": True,
        },
    )
    db.commit()
    db.refresh(draft)
    return {
        "message": (
            "Marked ready for you to copy and send manually."
            if draft.status == "reviewed"
            else "The message was saved. Nothing was sent."
        ),
        "item": _serialize_authority_outreach_draft(draft),
    }


def _authority_outreach_copy(
    *,
    campaign: Campaign,
    source_type: str,
    referring_domain: str,
    source_title: str | None,
    target_url: str,
    relevance: dict[str, Any],
) -> tuple[str, str]:
    business_name = str(campaign.name or _normalized_domain(campaign.domain) or "our business")
    page_name = str(source_title or referring_domain).strip()
    if source_type == "lost_link":
        subject = f"Possible link update on {referring_domain}"[:180]
        message = (
            f"Hello,\n\nI noticed that the link to {business_name} on {page_name} may no longer "
            "be working or may have been removed. If the mention still belongs on the page, would "
            f"you be open to updating it to {target_url}?\n\nIf it no longer fits the page, no "
            "action is needed.\n\nThank you,"
        )
        return subject, message

    if source_type == "unlinked_mention":
        subject = f"Website link for {business_name}"[:180]
        message = (
            f"Hello,\n\nI found the mention of {business_name} on {page_name}. Thank you for "
            "including the business. If it would help people using the page, would you be open "
            f"to linking the mention to {target_url}?\n\nPlease only add the link if it is useful "
            "and fits the page. If not, no action is needed.\n\nThank you,"
        )
        return subject, message

    service_names = [
        str(item.get("name"))
        for item in relevance.get("matched_services", [])
        if isinstance(item, dict) and item.get("name")
    ]
    area_names = [
        str(item.get("name"))
        for item in relevance.get("matched_service_areas", [])
        if isinstance(item, dict) and item.get("name")
    ]
    service_phrase = service_names[0] if service_names else "services related to this page"
    area_phrase = f" in {area_names[0]}" if area_names else ""
    subject = f"Possible resource for {page_name}"[:180]
    message = (
        f"Hello,\n\nI found your page, {page_name}, while looking at resources for "
        f"{service_phrase}{area_phrase}. {business_name} provides this service and may be useful "
        "to people using the page.\n\nIf it would genuinely help your visitors, would you be open "
        f"to reviewing the business for inclusion? Business website: {target_url}\n\nPlease only "
        "add it if it belongs on the page. I can provide any details you need.\n\nThank you,"
    )
    return subject, message


def _serialize_authority_outreach_draft(item: AuthorityOutreachDraft) -> dict[str, Any]:
    evidence = item.evidence if isinstance(item.evidence, dict) else {}
    return {
        "id": item.id,
        "campaign_id": item.campaign_id,
        "business_location_id": item.business_location_id,
        "recommendation_id": item.recommendation_id,
        "source_type": item.source_type,
        "source_record_id": item.source_record_id,
        "source_url": item.source_url,
        "target_url": item.target_url,
        "referring_domain": item.referring_domain,
        "source_page_title": evidence.get("source_page_title"),
        "contact_name": item.contact_name,
        "contact_email": item.contact_email,
        "contact_page_url": item.contact_page_url,
        "subject": item.subject,
        "message_body": item.message_body,
        "status": item.status,
        "status_label": {
            "draft": "Needs your review",
            "reviewed": "Ready for you to send",
            "closed": "Closed",
        }.get(item.status, "Needs your review"),
        "owner_confirmed_recipient": item.owner_confirmed_recipient,
        "manual_send_only": True,
        "send_available": False,
        "review_checklist": [
            "Open the exact source page and confirm the request still belongs there.",
            "Use only a recipient or contact page you personally verified.",
            "Edit the message so it is accurate for the relationship.",
            "Do not offer payment, trade links, or promise a ranking result.",
        ],
        "evidence": evidence,
        "created_at": _iso_utc(item.created_at),
        "updated_at": _iso_utc(item.updated_at),
    }


def _authority_relevance_confidence(
    classification: str,
    *,
    owner_confirmed: bool,
) -> float:
    if classification == "service_and_area_match":
        return 0.82
    if classification == "service_match":
        return 0.75
    if classification == "area_match":
        return 0.66
    return 0.62 if owner_confirmed else 0.5


def _serialize_authority_link_change_result(
    db: Session,
    *,
    run: AuthorityLinkChangeRun,
    created: bool,
) -> dict[str, Any]:
    rows = (
        db.query(AuthorityLinkChange)
        .filter(
            AuthorityLinkChange.tenant_id == run.tenant_id,
            AuthorityLinkChange.run_id == run.id,
        )
        .order_by(AuthorityLinkChange.change_state.asc(), AuthorityLinkChange.last_seen_at.desc())
        .all()
    )
    serialized = [_serialize_authority_link_change(row) for row in rows]
    new_items = [row for row in serialized if row["change_state"] == "new"]
    lost_items = [row for row in serialized if row["change_state"] == "lost"]
    return {
        "created": created,
        "run": {
            "id": run.id,
            "status": run.status,
            "owner_domain": run.owner_domain,
            "result_limit_per_state": run.result_limit_per_state,
            "source_type": "live_link_index",
            "observed_at": _iso_utc(run.observed_at),
        },
        "summary": {
            "new_links": len(new_items),
            "lost_links": len(lost_items),
            "new_websites": len({row["referring_domain"] for row in new_items}),
            "lost_websites": len({row["referring_domain"] for row in lost_items}),
        },
        "new_items": new_items,
        "lost_items": lost_items,
        "truth": {
            "classification": "provider_backed",
            "summary": (
                "These are exact pages reported as newly found or no longer linking. "
                "The check is bounded and keeps the page, destination, and observation dates together."
            ),
        },
    }


def _serialize_authority_link_change(row: AuthorityLinkChange) -> dict[str, Any]:
    is_new = row.change_state == "new"
    return {
        "id": row.id,
        "change_state": row.change_state,
        "referring_domain": row.referring_domain,
        "source_url": row.source_url,
        "source_page_title": row.source_page_title,
        "target_url": row.target_url,
        "link_type": row.link_type,
        "dofollow": row.dofollow,
        "anchor": row.anchor,
        "first_seen_at": _iso_utc(row.first_seen_at),
        "last_seen_at": _iso_utc(row.last_seen_at),
        "source_updated_at": _iso_utc(row.observed_at),
        "status_label": "New website mention" if is_new else "Link no longer found",
        "why_it_matters": (
            "A website has recently started sending visitors to this business."
            if is_new
            else "A website that previously sent visitors to this business is reported as no longer linking."
        ),
        "next_step": (
            "Open both pages and confirm the business information and destination are accurate."
            if is_new
            else "Open the source page and destination. If the mention still belongs there, ask the site owner to restore or update it."
        ),
        "verification_goal": (
            "Keep the link live and pointing to the most useful page."
            if is_new
            else "Check again after outreach and confirm whether the link returns."
        ),
    }


def _normalize_authority_link_changes(
    rows: Any,
    *,
    change_state: str,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or change_state not in {"new", "lost"}:
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        if change_state == "new" and not bool(raw.get("is_new")):
            continue
        if change_state == "lost" and not bool(raw.get("is_lost")):
            continue
        source_url = str(raw.get("url_from") or "").strip()
        target_url = str(raw.get("url_to") or "").strip()
        referring_domain = _normalized_domain(raw.get("domain_from"))
        if not source_url or not target_url or not referring_domain:
            continue
        dedupe_key = (source_url, target_url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        first_seen = _provider_datetime(raw.get("first_seen"))
        last_seen = _provider_datetime(raw.get("last_seen"))
        normalized.append(
            {
                "change_state": change_state,
                "referring_domain": referring_domain,
                "source_url": source_url,
                "source_page_title": _optional_text(raw.get("page_from_title")),
                "target_url": target_url,
                "link_type": _optional_text(raw.get("item_type")),
                "dofollow": bool(raw.get("dofollow")),
                "anchor": _optional_text(raw.get("anchor")),
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "evidence": {
                    "source_type": "live_link_index",
                    "reported_state": change_state,
                    "is_new": bool(raw.get("is_new")),
                    "is_lost": bool(raw.get("is_lost")),
                    "source_url": source_url,
                    "target_url": target_url,
                    "observed_at": observed_at.isoformat(),
                },
            }
        )
    normalized.sort(
        key=lambda item: (item["first_seen_at"] if change_state == "new" else item["last_seen_at"])
        or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return normalized[:AUTHORITY_LINK_CHANGE_LIMIT]


def _normalize_authority_inventory_links(
    rows: Any,
    *,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in rows:
        if not isinstance(raw, dict) or bool(raw.get("is_lost")):
            continue
        source_url = str(raw.get("url_from") or "").strip()
        target_url = str(raw.get("url_to") or "").strip()
        referring_domain = _normalized_domain(raw.get("domain_from") or source_url)
        if not source_url or not target_url or not referring_domain:
            continue
        dedupe_key = (_canonical_url(source_url), _canonical_url(target_url))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        first_seen = _provider_datetime(raw.get("first_seen"))
        last_seen = _provider_datetime(raw.get("last_seen"))
        normalized.append(
            {
                "referring_domain": referring_domain,
                "source_url": source_url,
                "source_page_title": _optional_text(raw.get("page_from_title")),
                "target_url": target_url,
                "link_type": _optional_text(raw.get("item_type")),
                "dofollow": bool(raw.get("dofollow")),
                "anchor": _optional_text(raw.get("anchor")),
                "first_seen_at": first_seen,
                "last_seen_at": last_seen,
                "evidence": {
                    "source_type": "live_link_index",
                    "source_url": source_url,
                    "target_url": target_url,
                    "observed_at": observed_at.isoformat(),
                },
            }
        )
    normalized.sort(
        key=lambda item: item["last_seen_at"] or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return normalized[:AUTHORITY_INVENTORY_LINK_LIMIT]


def _normalize_authority_unlinked_mentions(
    rows: Any,
    *,
    linked_rows: Any,
    owner_domain: str,
    business_name: str,
    confirmed_services: list[Any],
    included_areas: list[Any],
    excluded_areas: list[Any],
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(rows, list):
        return [], 0
    linked_urls = {
        _canonical_url(raw.get("url_from"))
        for raw in (linked_rows if isinstance(linked_rows, list) else [])
        if isinstance(raw, dict) and raw.get("url_from") and not bool(raw.get("is_lost"))
    }
    normalized_name = _normalize_match_text(business_name)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        content_info = raw.get("content_info") if isinstance(raw.get("content_info"), dict) else {}
        source_url = str(raw.get("url") or raw.get("url_normalized") or "").strip()
        referring_domain = _normalized_domain(
            raw.get("main_domain") or raw.get("domain") or source_url
        )
        canonical_source = _canonical_url(source_url)
        if (
            not source_url
            or not referring_domain
            or referring_domain == owner_domain
            or referring_domain.endswith(f".{owner_domain}")
            or not canonical_source
            or canonical_source in seen
        ):
            continue
        title = _optional_text(
            raw.get("title")
            or raw.get("main_title")
            or content_info.get("title")
            or content_info.get("main_title")
        )
        snippet = _optional_text(raw.get("snippet") or content_info.get("snippet"))
        previous_title = _optional_text(raw.get("previous_title") or content_info.get("previous_title"))
        saved_text = _normalize_match_text(" ".join([title or "", previous_title or "", snippet or ""]))
        if not normalized_name or normalized_name not in saved_text:
            continue
        seen.add(canonical_source)
        item: dict[str, Any] = {
            "referring_domain": referring_domain,
            "source_url": source_url,
            "source_page_title": title,
            "snippet": snippet,
            "competitor_matches": [],
        }
        relevance = _classify_authority_gap_relevance(
            item,
            confirmed_services=confirmed_services,
            included_areas=included_areas,
            excluded_areas=excluded_areas,
        )
        item.update(relevance)
        item["evidence"] = {
            "source_type": "live_content_and_link_index",
            "source_url": source_url,
            "business_name": business_name,
            "exact_name_found_in_saved_text": True,
            "owner_link_found_for_exact_source_url": canonical_source in linked_urls,
            "same_run_link_check": True,
            "observed_at": observed_at.isoformat(),
            "relevance": relevance,
        }
        candidates.append(item)
    checked_count = len(candidates)
    unlinked = [
        item
        for item in candidates
        if not bool(item["evidence"]["owner_link_found_for_exact_source_url"])
    ]
    relevance_order = {
        "service_and_area_match": 3,
        "service_match": 2,
        "area_match": 1,
        "needs_review": 0,
    }
    unlinked.sort(
        key=lambda item: (
            relevance_order[item["relevance_classification"]],
            item["referring_domain"],
        ),
        reverse=True,
    )
    return unlinked[:AUTHORITY_INVENTORY_MENTION_LIMIT], checked_count


def _normalized_domain(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip().lower()
    return host[4:] if host.startswith("www.") else host


def _absolute_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw if "://" in raw else f"https://{raw}"


def _is_http_url(value: Any) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _canonical_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip().casefold()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return f"{host}{path}" + (f"?{parsed.query}" if parsed.query else "")


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _provider_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


def submit_citation(db: Session, tenant_id: str, campaign_id: str, directory_name: str) -> Citation:
    require_listing_correction_workflow(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    citation = Citation(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        directory_name=directory_name,
        submission_status="submitted",
        updated_at=datetime.now(UTC),
    )
    db.add(citation)
    db.commit()
    db.refresh(citation)
    return citation


def refresh_citation_status(db: Session, tenant_id: str, campaign_id: str) -> list[Citation]:
    require_listing_correction_workflow(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    provider = get_authority_provider()
    rows = (
        db.query(Citation)
        .filter(Citation.tenant_id == tenant_id, Citation.campaign_id == campaign_id)
        .all()
    )
    for row in rows:
        payload = provider.refresh_citation_status(
            campaign_id=campaign_id,
            directory_name=row.directory_name,
            current_status=row.submission_status,
        )
        row.submission_status = payload["submission_status"]
        row.listing_url = payload.get("listing_url")
        row.updated_at = payload.get("updated_at", datetime.now(UTC))
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="citation.status.refreshed",
        payload={"campaign_id": campaign_id, "count": len(rows)},
    )
    db.commit()
    return rows


def enrich_outreach_contacts(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    contacts = (
        db.query(OutreachContact)
        .filter(OutreachContact.tenant_id == tenant_id, OutreachContact.campaign_id == campaign_id)
        .all()
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="outreach.automatic_enrichment.blocked",
        payload={"campaign_id": campaign_id, "reason": "owner_verified_recipients_required"},
    )
    db.commit()
    return {
        "campaign_id": campaign_id,
        "status": "blocked",
        "reason_code": "automatic_contact_enrichment_disabled",
        "contacts_enriched": 0,
        "contacts_total": len(contacts),
    }


def execute_outreach_sequence_step(db: Session, tenant_id: str, outreach_campaign_id: str) -> dict:
    campaign = db.get(OutreachCampaign, outreach_campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        return {
            "outreach_campaign_id": outreach_campaign_id,
            "status": "failed",
            "reason_code": "outreach_campaign_not_found",
            "contacts_advanced": 0,
        }
    contacts = (
        db.query(OutreachContact)
        .filter(
            OutreachContact.tenant_id == tenant_id,
            OutreachContact.outreach_campaign_id == outreach_campaign_id,
        )
        .all()
    )
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="outreach.automatic_sequence.blocked",
        payload={
            "outreach_campaign_id": outreach_campaign_id,
            "reason": "manual_send_only",
        },
    )
    db.commit()
    return {
        "outreach_campaign_id": outreach_campaign_id,
        "status": "blocked",
        "reason_code": "automatic_outreach_disabled",
        "contacts_advanced": 0,
        "contacts_total": len(contacts),
    }


def submit_citation_batch(db: Session, tenant_id: str, campaign_id: str) -> dict:
    require_listing_correction_workflow(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    rows = (
        db.query(Citation)
        .filter(Citation.tenant_id == tenant_id, Citation.campaign_id == campaign_id)
        .all()
    )
    now = datetime.now(UTC)
    submitted = 0
    for row in rows:
        if row.submission_status in {"pending", "draft"}:
            row.submission_status = "submitted"
            row.updated_at = now
            submitted += 1
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="citation.batch.submitted",
        payload={"campaign_id": campaign_id, "submitted_count": submitted},
    )
    db.commit()
    return {
        "campaign_id": campaign_id,
        "status": "success",
        "submitted_count": submitted,
        "citations_total": len(rows),
    }
