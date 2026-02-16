from datetime import UTC, datetime
from random import randint, uniform

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def create_competitor(db: Session, tenant_id: str, campaign_id: str, domain: str, label: str | None) -> Competitor:
    _campaign_or_404(db, tenant_id, campaign_id)
    item = Competitor(tenant_id=tenant_id, campaign_id=campaign_id, domain=domain, label=label)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_competitors(db: Session, tenant_id: str, campaign_id: str) -> list[Competitor]:
    return (
        db.query(Competitor)
        .filter(Competitor.tenant_id == tenant_id, Competitor.campaign_id == campaign_id)
        .order_by(Competitor.created_at.desc())
        .all()
    )


def collect_snapshot(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    competitors = list_competitors(db, tenant_id, campaign_id)
    now = datetime.now(UTC)
    for comp in competitors:
        db.add(
            CompetitorRanking(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                keyword="best local seo agency",
                position=randint(1, 100),
                captured_at=now,
            )
        )
        db.add(
            CompetitorPage(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                url=f"https://{comp.domain}/services",
                visibility_score=round(uniform(0.1, 1.0), 2),
                captured_at=now,
            )
        )
        db.add(
            CompetitorSignal(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                competitor_id=comp.id,
                signal_key="content_velocity",
                signal_value="weekly",
                score=round(uniform(0.1, 1.0), 2),
                captured_at=now,
            )
        )
    db.commit()
    return {"campaign_id": campaign_id, "snapshots_collected": len(competitors)}


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
    rows = (
        db.query(Competitor, CompetitorRanking)
        .join(CompetitorRanking, CompetitorRanking.competitor_id == Competitor.id)
        .filter(Competitor.tenant_id == tenant_id, Competitor.campaign_id == campaign_id)
        .all()
    )
    gaps = []
    for comp, ranking in rows:
        gaps.append(
            {
                "competitor_id": comp.id,
                "domain": comp.domain,
                "gap_score": max(0, 100 - ranking.position),
                "position": ranking.position,
            }
        )
    return gaps

