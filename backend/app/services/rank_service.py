import math
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain import entitlement_codes
from app.events import emit_event
from app.models.business_location import BusinessLocation
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot
from app.providers import get_rank_provider_for_organization
from app.services.cost_economics_service import (
    CostEconomicsError,
    reconcile_provider_cost,
    release_provider_cost,
    reserve_provider_cost,
)
from app.services.entitlement_service import EntitlementNotFoundError, check_and_consume
from app.services.provider_credentials_service import (
    ProviderCredentialConfigurationError,
    resolve_provider_credential_owner,
    resolve_provider_credentials,
)
from app.services.runtime_truth_service import build_truth, freshness_state_from_timestamp


def _get_campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def build_rank_truth(
    db: Session,
    *,
    organization_id: str | None,
    tracked_keywords: int,
    snapshot_count: int,
    latest_captured_at: str | datetime | None = None,
    job_queued: bool = False,
) -> dict:
    settings = get_settings()
    backend = getattr(settings, "rank_provider_backend", "synthetic").strip().lower()
    environment = getattr(settings, "app_env", "").strip().lower()

    states: list[str] = []
    reasons: list[str] = []
    provider_state = backend or "unknown"
    setup_state = "configured"
    operator_state = "self_serve"

    if tracked_keywords == 0:
        states.append("unavailable")
        setup_state = "keywords_missing"
        reasons.append("no_rank_keywords_configured")

    if backend == "synthetic":
        if environment == "test":
            states.append("synthetic")
            reasons.append("rank_runtime_uses_test_fixture_provider")
            summary = "Ranking data is coming from a synthetic fixture provider in test mode."
        else:
            states.append("unavailable")
            provider_state = "synthetic_disabled_outside_test"
            setup_state = "provider_unavailable"
            operator_state = "operator_assisted"
            reasons.append("rank_provider_not_available_in_this_runtime")
            summary = "Ranking collection is not provider-backed in this runtime. The configured synthetic provider is disabled outside test mode."
    elif backend in {"dataforseo", "serpapi"}:
        provider_name = "dataforseo"
        if organization_id is None:
            states.append("unavailable")
            setup_state = "organization_missing"
            reasons.append("campaign_missing_organization_scope")
            summary = "Ranking collection cannot run because the campaign is missing organization scope."
        else:
            try:
                credentials = resolve_provider_credentials(
                    db,
                    organization_id,
                    provider_name,
                    required_credential_mode="byo_optional",
                )
            except ProviderCredentialConfigurationError as exc:
                states.append("unavailable")
                setup_state = "credentials_missing"
                operator_state = "operator_assisted"
                reasons.append(exc.reason_code)
                summary = "Ranking collection requires operator-configured provider credentials before live checks are reliable."
            else:
                credentials_ready = (
                    bool(str(credentials.get("login", "")).strip())
                    and bool(str(credentials.get("password", "")).strip())
                    if backend == "dataforseo"
                    else bool(str(credentials.get("api_key", "")).strip())
                )
                if credentials_ready:
                    states.append("provider_backed")
                    summary = f"Ranking collection is configured against {provider_name}."
                else:
                    states.append("unavailable")
                    setup_state = "credentials_missing"
                    operator_state = "operator_assisted"
                    reasons.append(
                        "rank_provider_credentials_missing"
                        if backend == "dataforseo"
                        else "rank_provider_api_key_missing"
                    )
                    summary = "Ranking collection is not configured with live provider credentials yet."
    elif backend == "http_json":
        endpoint = getattr(settings, "rank_provider_http_endpoint", "").strip()
        if not endpoint:
            states.append("unavailable")
            setup_state = "provider_endpoint_missing"
            operator_state = "operator_assisted"
            reasons.append("rank_provider_http_endpoint_missing")
            summary = "Ranking collection is not configured with a live HTTP provider endpoint."
        else:
            states.append("operator_assisted")
            reasons.append("rank_provider_depends_on_manual_http_endpoint_setup")
            summary = "Ranking collection depends on a manually configured HTTP provider endpoint and should be treated as setup-sensitive."
    else:
        states.append("unavailable")
        setup_state = "provider_unknown"
        reasons.append("rank_provider_backend_unsupported")
        summary = "Ranking collection is not configured with a supported provider backend."

    freshness_state = freshness_state_from_timestamp(latest_captured_at, stale_after=timedelta(days=7))
    if freshness_state == "stale":
        states.append("stale")
        reasons.append("ranking_snapshot_is_stale")
    if job_queued:
        states.append("in_progress")
        reasons.append("ranking_refresh_queued")
    if snapshot_count == 0 and tracked_keywords > 0 and "provider_backed" not in states and "synthetic" not in states:
        states.append("operator_assisted")
        reasons.append("rankings_have_no_recent_snapshots")

    return build_truth(
        states=states,
        summary=summary,
        provider_state=provider_state,
        setup_state=setup_state,
        operator_state=operator_state,
        freshness_state=freshness_state,
        reasons=reasons,
    )



def resolve_location_code(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    requested_location_code: str | None = None,
) -> str:
    campaign = _get_campaign_or_404(db, tenant_id, campaign_id)
    requested = (requested_location_code or "").strip()
    if requested:
        return requested
    if campaign.business_location_id:
        location = db.get(BusinessLocation, campaign.business_location_id)
        if location is not None and location.organization_id == campaign.organization_id:
            provider_name = (location.provider_location_name or "").strip()
            if provider_name:
                return provider_name
            city = (location.city or location.primary_city or "").strip()
            if city:
                region = (location.region or "").strip()
                country_code = (location.country_code or "US").strip().upper()
                country_name = {
                    "US": "United States",
                    "CA": "Canada",
                    "GB": "United Kingdom",
                    "AU": "Australia",
                    "NZ": "New Zealand",
                }.get(country_code, country_code)
                parts = [city, region, country_name]
                return ", ".join(part for part in parts if part)
    return "United States"


def _get_or_create_cluster(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    cluster_name: str,
) -> KeywordCluster:
    cluster = (
        db.query(KeywordCluster)
        .filter(
            KeywordCluster.tenant_id == tenant_id,
            KeywordCluster.campaign_id == campaign_id,
            KeywordCluster.name == cluster_name,
        )
        .first()
    )
    if cluster is None:
        cluster = KeywordCluster(tenant_id=tenant_id, campaign_id=campaign_id, name=cluster_name)
        db.add(cluster)
        db.flush()
    return cluster


def add_keywords_bulk(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    cluster_name: str,
    keywords: list[str],
    location_code: str | None,
) -> dict:
    _get_campaign_or_404(db, tenant_id, campaign_id)
    effective_location = resolve_location_code(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        requested_location_code=location_code,
    )
    normalized_cluster = cluster_name.strip() or "Core Terms"
    cluster = _get_or_create_cluster(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cluster_name=normalized_cluster,
    )
    existing_rows = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
            CampaignKeyword.location_code == effective_location,
        )
        .all()
    )
    existing_by_keyword = {row.keyword.casefold(): row for row in existing_rows}
    created: list[CampaignKeyword] = []
    skipped: list[CampaignKeyword] = []
    for raw_keyword in keywords:
        keyword = raw_keyword.strip()
        if not keyword:
            continue
        existing = existing_by_keyword.get(keyword.casefold())
        if existing is not None:
            skipped.append(existing)
            continue
        record = CampaignKeyword(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            cluster_id=cluster.id,
            keyword=keyword,
            location_code=effective_location,
        )
        db.add(record)
        db.flush()
        existing_by_keyword[keyword.casefold()] = record
        created.append(record)
    db.commit()
    for row in created:
        db.refresh(row)
    return {
        "created": created,
        "skipped": skipped,
        "location_code": effective_location,
    }


def add_keyword(
    db: Session,
    tenant_id: str,
    campaign_id: str,
    cluster_name: str,
    keyword: str,
    location_code: str | None,
) -> CampaignKeyword:
    result = add_keywords_bulk(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cluster_name=cluster_name,
        keywords=[keyword],
        location_code=location_code,
    )
    rows = [*result["created"], *result["skipped"]]
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Keyword is required")
    return rows[0]


def list_keywords(db: Session, *, tenant_id: str, campaign_id: str) -> list[dict]:
    _get_campaign_or_404(db, tenant_id, campaign_id)
    rows = (
        db.query(CampaignKeyword, KeywordCluster)
        .join(KeywordCluster, KeywordCluster.id == CampaignKeyword.cluster_id)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
        )
        .order_by(KeywordCluster.name.asc(), CampaignKeyword.keyword.asc())
        .all()
    )
    return [
        {
            "id": keyword.id,
            "campaign_id": keyword.campaign_id,
            "keyword": keyword.keyword,
            "cluster": cluster.name,
            "location_code": keyword.location_code,
            "created_at": keyword.created_at.isoformat(),
        }
        for keyword, cluster in rows
    ]


def delete_keyword(db: Session, *, tenant_id: str, keyword_id: str) -> None:
    row = (
        db.query(CampaignKeyword)
        .filter(CampaignKeyword.id == keyword_id, CampaignKeyword.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked keyword not found")
    db.delete(row)
    db.commit()



def run_snapshot_collection(db: Session, tenant_id: str, campaign_id: str, location_code: str) -> dict:
    campaign = _get_campaign_or_404(db, tenant_id, campaign_id)
    if campaign.organization_id is None:
        raise EntitlementNotFoundError(
            f"Campaign missing organization_id for rank snapshot enforcement: {campaign_id}"
        )
    organization = db.get(Organization, campaign.organization_id)
    if organization is None:
        raise ValueError(f"Organization not found for campaign: {campaign_id}")
    if organization.status.strip().lower() != "active":
        return {
            "campaign_id": campaign_id,
            "location_code": location_code,
            "snapshots_created": 0,
            "status": "failed",
            "reason_code": "ORG_INACTIVE",
        }

    keywords = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
            CampaignKeyword.location_code == location_code,
        )
        .all()
    )
    if not keywords:
        return {
            "campaign_id": campaign_id,
            "location_code": location_code,
            "snapshots_created": 0,
            "status": "no_keywords",
        }

    allowed = check_and_consume(
        db,
        str(campaign.organization_id),
        entitlement_codes.LIMIT_RANK_KEYWORD_SNAPSHOTS_MONTHLY,
        amount=len(keywords),
    )
    if not allowed:
        return {
            "campaign_id": campaign_id,
            "location_code": location_code,
            "snapshots_created": 0,
            "status": "failed",
            "reason_code": "ENTITLEMENT_EXCEEDED",
        }

    try:
        provider = get_rank_provider_for_organization(db, str(campaign.organization_id))
    except ProviderCredentialConfigurationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": str(exc),
                "reason_code": exc.reason_code,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": str(exc),
                "reason_code": "provider_unavailable",
            },
        ) from exc
    now = datetime.now(UTC)
    month_partition = now.strftime("%Y-%m")
    collection_id = str(uuid.uuid4())
    settings = get_settings()
    provider_backend = getattr(settings, "rank_provider_backend", "synthetic").strip().lower()
    credential_owner: str | None = None
    provider_cost_identity: tuple[str, str, str, int] | None = None
    if provider_backend == "dataforseo":
        try:
            credential_owner = resolve_provider_credential_owner(
                db,
                str(campaign.organization_id),
                "dataforseo",
                required_credential_mode="byo_optional",
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"message": str(exc), "reason_code": exc.reason_code},
            ) from exc
        depth = int(getattr(settings, "rank_provider_dataforseo_depth", 100))
        provider_cost_identity = (
            "dataforseo",
            "rank_tracking",
            "google_organic_live_advanced",
            max(1, math.ceil(depth / 10)),
        )
    elif provider_backend in {"serpapi", "http_json"}:
        # These are paid-capable backends. They intentionally fail closed until
        # a matching, versioned price card and credential owner are configured.
        credential_provider = "dataforseo" if provider_backend == "serpapi" else "rank_http"
        try:
            credential_owner = resolve_provider_credential_owner(
                db,
                str(campaign.organization_id),
                credential_provider,
            )
        except ProviderCredentialConfigurationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"message": str(exc), "reason_code": exc.reason_code},
            ) from exc
        provider_cost_identity = (
            provider_backend,
            "rank_tracking",
            "keyword_snapshot",
            1,
        )
    created = 0
    for kw in keywords:
        reservation = None
        if provider_cost_identity is not None and credential_owner is not None:
            provider_name, capability, operation, quantity = provider_cost_identity
            if provider_name == "dataforseo":
                quantity *= _dataforseo_keyword_cost_multiplier(kw.keyword)
            try:
                reservation = reserve_provider_cost(
                    db,
                    organization_id=str(campaign.organization_id),
                    business_location_id=campaign.business_location_id,
                    campaign_id=campaign.id,
                    provider_name=provider_name,
                    capability=capability,
                    operation=operation,
                    credential_owner=credential_owner,
                    quantity=quantity,
                    idempotency_key=f"rank:{collection_id}:{kw.id}",
                )
            except CostEconomicsError as exc:
                raise HTTPException(
                    status_code=exc.status_code,
                    detail={"message": str(exc), "reason_code": exc.reason_code},
                ) from exc
        try:
            snapshot_payload = provider.collect_keyword_snapshot(
                keyword=kw.keyword,
                location_code=kw.location_code,
                target_domain=campaign.domain,
            )
        except Exception:
            if reservation is not None:
                release_provider_cost(db, reservation=reservation)
            raise
        if reservation is not None:
            reconcile_provider_cost(
                db,
                reservation=reservation,
                provider_reported_cost=snapshot_payload.get("provider_reported_cost"),
            )
        position = int(snapshot_payload["position"])
        confidence = float(snapshot_payload["confidence"])
        previous = (
            db.query(RankingSnapshot)
            .filter(
                RankingSnapshot.tenant_id == tenant_id,
                RankingSnapshot.campaign_id == campaign_id,
                RankingSnapshot.keyword_id == kw.id,
            )
            .order_by(RankingSnapshot.captured_at.desc())
            .first()
        )
        delta = None if previous is None else previous.position - position
        ranking = (
            db.query(Ranking)
            .filter(Ranking.tenant_id == tenant_id, Ranking.campaign_id == campaign_id, Ranking.keyword_id == kw.id)
            .first()
        )
        if ranking is None:
            ranking = Ranking(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                keyword_id=kw.id,
                current_position=position,
                previous_position=previous.position if previous else None,
                delta=delta,
                confidence=confidence,
            )
            db.add(ranking)
        else:
            ranking.previous_position = ranking.current_position
            ranking.current_position = position
            ranking.delta = (ranking.previous_position - ranking.current_position) if ranking.previous_position else None
            ranking.confidence = confidence
            ranking.updated_at = now

        snapshot_row = RankingSnapshot(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            keyword_id=kw.id,
            position=position,
            confidence=confidence,
            captured_at=now,
            month_partition=month_partition,
        )
        db.add(snapshot_row)
        created += 1
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="rank.snapshot.created",
        payload={"campaign_id": campaign_id, "location_code": location_code, "snapshots_created": created},
    )
    db.commit()
    return {
        "campaign_id": campaign_id,
        "location_code": location_code,
        "snapshots_created": created,
        "status": "success",
    }


_DATAFORSEO_MULTIPLIED_OPERATORS = (
    "allinanchor:",
    "allintext:",
    "allintitle:",
    "allinurl:",
    "cache:",
    "define:",
    "filetype:",
    "id:",
    "inanchor:",
    "info:",
    "intext:",
    "intitle:",
    "inurl:",
    "link:",
    "site:",
)


def _dataforseo_keyword_cost_multiplier(keyword: str) -> int:
    """Reserve the documented 5x multiplier for every advanced search operator."""
    normalized = keyword.casefold()
    operator_names = sorted(
        (operator.removesuffix(":") for operator in _DATAFORSEO_MULTIPLIED_OPERATORS),
        key=len,
        reverse=True,
    )
    pattern = rf"(?<![a-z0-9_])(?:{'|'.join(re.escape(name) for name in operator_names)}):"
    operator_count = len(re.findall(pattern, normalized))
    return 5**operator_count



def normalize_snapshot(db: Session, snapshot_id: str) -> dict:
    snapshot = db.get(RankingSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking snapshot not found")
    snapshot.position = max(1, int(snapshot.position))
    snapshot.confidence = round(max(0.0, min(float(snapshot.confidence), 1.0)), 2)
    db.commit()
    return {"snapshot_id": snapshot.id, "normalized": True}



def recompute_deltas(db: Session, tenant_id: str, campaign_id: str) -> dict:
    rankings = (
        db.query(Ranking)
        .filter(Ranking.tenant_id == tenant_id, Ranking.campaign_id == campaign_id)
        .all()
    )
    updated = 0
    for row in rankings:
        latest_two = (
            db.query(RankingSnapshot)
            .filter(
                RankingSnapshot.tenant_id == tenant_id,
                RankingSnapshot.campaign_id == campaign_id,
                RankingSnapshot.keyword_id == row.keyword_id,
            )
            .order_by(RankingSnapshot.captured_at.desc())
            .limit(2)
            .all()
        )
        if not latest_two:
            continue
        current = latest_two[0]
        previous = latest_two[1] if len(latest_two) > 1 else None
        row.current_position = current.position
        row.previous_position = previous.position if previous else None
        row.delta = (row.previous_position - row.current_position) if row.previous_position is not None else None
        row.confidence = current.confidence
        row.updated_at = datetime.now(UTC)
        updated += 1
    db.commit()
    return {"campaign_id": campaign_id, "tenant_id": tenant_id, "rankings_recomputed": updated}



def get_snapshots(db: Session, tenant_id: str, campaign_id: str) -> list[RankingSnapshot]:
    return (
        db.query(RankingSnapshot)
        .filter(RankingSnapshot.tenant_id == tenant_id, RankingSnapshot.campaign_id == campaign_id)
        .order_by(RankingSnapshot.captured_at.desc())
        .all()
    )


def get_tracked_keyword_count(db: Session, tenant_id: str, campaign_id: str) -> int:
    return (
        db.query(CampaignKeyword)
        .filter(CampaignKeyword.tenant_id == tenant_id, CampaignKeyword.campaign_id == campaign_id)
        .count()
    )



def get_trends(db: Session, tenant_id: str, campaign_id: str) -> list[dict]:
    rows = (
        db.query(Ranking, CampaignKeyword, KeywordCluster)
        .join(CampaignKeyword, CampaignKeyword.id == Ranking.keyword_id)
        .join(KeywordCluster, KeywordCluster.id == CampaignKeyword.cluster_id)
        .filter(Ranking.tenant_id == tenant_id, Ranking.campaign_id == campaign_id)
        .all()
    )
    trends: list[dict] = []
    for ranking, keyword, cluster in rows:
        trends.append(
            {
                "keyword_id": keyword.id,
                "keyword": keyword.keyword,
                "cluster": cluster.name,
                "location_code": keyword.location_code,
                "position": ranking.current_position,
                "delta": ranking.delta,
                "confidence": ranking.confidence,
            }
        )
    return trends


def get_portfolio_summary(db: Session, *, tenant_id: str) -> dict:
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == tenant_id)
        .order_by(Campaign.created_at.asc())
        .all()
    )
    grouped: dict[str, dict] = {}
    latest_captured_at: datetime | None = None
    organization_id: str | None = None
    total_snapshots = 0
    for campaign in campaigns:
        organization_id = organization_id or campaign.organization_id
        location = db.get(BusinessLocation, campaign.business_location_id) if campaign.business_location_id else None
        group_key = location.id if location is not None else f"unassigned:{campaign.id}"
        group = grouped.setdefault(
            group_key,
            {
                "business_location_id": location.id if location is not None else None,
                "location_name": location.name if location is not None else campaign.name,
                "primary_city": location.primary_city if location is not None else None,
                "status": location.status if location is not None else "unassigned",
                "campaign_ids": [],
                "campaign_names": [],
                "domains": [],
                "tracked_keywords": 0,
                "ranked_keywords": 0,
                "position_sum": 0,
                "top_10_keywords": 0,
                "improved_keywords": 0,
                "declined_keywords": 0,
                "latest_captured_at": None,
            },
        )
        group["campaign_ids"].append(campaign.id)
        group["campaign_names"].append(campaign.name)
        group["domains"].append(campaign.domain)
        keyword_count = get_tracked_keyword_count(db, tenant_id=tenant_id, campaign_id=campaign.id)
        rankings = (
            db.query(Ranking)
            .filter(Ranking.tenant_id == tenant_id, Ranking.campaign_id == campaign.id)
            .all()
        )
        latest = (
            db.query(func.max(RankingSnapshot.captured_at), func.count(RankingSnapshot.id))
            .filter(
                RankingSnapshot.tenant_id == tenant_id,
                RankingSnapshot.campaign_id == campaign.id,
            )
            .one()
        )
        campaign_latest = latest[0]
        total_snapshots += int(latest[1] or 0)
        group["tracked_keywords"] += keyword_count
        group["ranked_keywords"] += len(rankings)
        group["position_sum"] += sum(int(row.current_position) for row in rankings)
        group["top_10_keywords"] += sum(1 for row in rankings if row.current_position <= 10)
        group["improved_keywords"] += sum(1 for row in rankings if (row.delta or 0) > 0)
        group["declined_keywords"] += sum(1 for row in rankings if (row.delta or 0) < 0)
        if campaign_latest is not None:
            if latest_captured_at is None or campaign_latest > latest_captured_at:
                latest_captured_at = campaign_latest
            current_group_latest = group["latest_captured_at"]
            if current_group_latest is None or campaign_latest > current_group_latest:
                group["latest_captured_at"] = campaign_latest

    items: list[dict] = []
    for group in grouped.values():
        ranked_keywords = int(group.pop("ranked_keywords"))
        position_sum = int(group.pop("position_sum"))
        group["ranked_keywords"] = ranked_keywords
        group["average_position"] = round(position_sum / ranked_keywords, 1) if ranked_keywords else None
        if isinstance(group["latest_captured_at"], datetime):
            group["latest_captured_at"] = group["latest_captured_at"].isoformat()
        items.append(group)
    items.sort(key=lambda item: (str(item["location_name"]).casefold(), str(item["business_location_id"] or "")))
    tracked_keywords = sum(int(item["tracked_keywords"]) for item in items)
    ranked_keywords = sum(int(item["ranked_keywords"]) for item in items)
    position_weighted_sum = sum(
        float(item["average_position"]) * int(item["ranked_keywords"])
        for item in items
        if item["average_position"] is not None
    )
    return {
        "items": items,
        "summary": {
            "locations": len(items),
            "campaigns": len(campaigns),
            "tracked_keywords": tracked_keywords,
            "ranked_keywords": ranked_keywords,
            "average_position": round(position_weighted_sum / ranked_keywords, 1) if ranked_keywords else None,
            "top_10_keywords": sum(int(item["top_10_keywords"]) for item in items),
            "improved_keywords": sum(int(item["improved_keywords"]) for item in items),
            "declined_keywords": sum(int(item["declined_keywords"]) for item in items),
            "latest_captured_at": latest_captured_at.isoformat() if latest_captured_at else None,
        },
        "truth": build_rank_truth(
            db,
            organization_id=organization_id,
            tracked_keywords=tracked_keywords,
            snapshot_count=total_snapshots,
            latest_captured_at=latest_captured_at,
        ),
    }
