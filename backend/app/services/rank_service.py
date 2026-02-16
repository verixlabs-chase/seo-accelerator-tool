from datetime import UTC, datetime
from random import randint, uniform

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.rank import CampaignKeyword, KeywordCluster, Ranking, RankingSnapshot


def _get_campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


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
    _get_campaign_or_404(db, tenant_id, campaign_id)
    keywords = (
        db.query(CampaignKeyword)
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign_id,
            CampaignKeyword.location_code == location_code,
        )
        .all()
    )
    now = datetime.now(UTC)
    month_partition = now.strftime("%Y-%m")
    created = 0
    for kw in keywords:
        position = randint(1, 100)
        confidence = round(uniform(0.6, 0.99), 2)
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

        snapshot = RankingSnapshot(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            keyword_id=kw.id,
            position=position,
            confidence=confidence,
            captured_at=now,
            month_partition=month_partition,
        )
        db.add(snapshot)
        created += 1
    db.commit()
    return {"campaign_id": campaign_id, "location_code": location_code, "snapshots_created": created}


def get_snapshots(db: Session, tenant_id: str, campaign_id: str) -> list[RankingSnapshot]:
    return (
        db.query(RankingSnapshot)
        .filter(RankingSnapshot.tenant_id == tenant_id, RankingSnapshot.campaign_id == campaign_id)
        .order_by(RankingSnapshot.captured_at.desc())
        .all()
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

