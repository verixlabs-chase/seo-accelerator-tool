from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.competitor import Competitor, CompetitorPage, CompetitorRanking, CompetitorSignal
from app.providers import get_competitor_provider_for_organization


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
    if not competitors:
        return {"campaign_id": campaign_id, "status": "no_data", "reason_code": "no_competitors", "snapshots_collected": 0}
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
