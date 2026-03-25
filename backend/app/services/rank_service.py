from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.domain import entitlement_codes
from app.core.config import get_settings
from app.events import emit_event
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot
from app.providers import get_rank_provider_for_organization
from app.services.entitlement_service import EntitlementNotFoundError, check_and_consume
from app.services.provider_credentials_service import ProviderCredentialConfigurationError, resolve_provider_credentials
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
    elif backend == "serpapi":
        provider_name = "dataforseo"
        if organization_id is None:
            states.append("unavailable")
            setup_state = "organization_missing"
            reasons.append("campaign_missing_organization_scope")
            summary = "Ranking collection cannot run because the campaign is missing organization scope."
        else:
            try:
                credentials = resolve_provider_credentials(db, organization_id, provider_name)
            except ProviderCredentialConfigurationError as exc:
                states.append("unavailable")
                setup_state = "credentials_missing"
                operator_state = "operator_assisted"
                reasons.append(exc.reason_code)
                summary = "Ranking collection requires operator-configured provider credentials before live checks are reliable."
            else:
                if str(credentials.get("api_key", "")).strip():
                    states.append("provider_backed")
                    summary = "Ranking collection is configured against a credentialed provider."
                else:
                    states.append("unavailable")
                    setup_state = "credentials_missing"
                    operator_state = "operator_assisted"
                    reasons.append("rank_provider_api_key_missing")
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



def add_keyword(db: Session, tenant_id: str, campaign_id: str, cluster_name: str, keyword: str, location_code: str) -> CampaignKeyword:
    _get_campaign_or_404(db, tenant_id, campaign_id)
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

    record = CampaignKeyword(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cluster_id=cluster.id,
        keyword=keyword,
        location_code=location_code,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record



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
    created = 0
    for kw in keywords:
        snapshot_payload = provider.collect_keyword_snapshot(
            keyword=kw.keyword,
            location_code=location_code,
            target_domain=campaign.domain,
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


