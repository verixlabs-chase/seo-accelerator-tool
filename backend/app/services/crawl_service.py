from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.crawl import CrawlRun, TechnicalIssue


def schedule_crawl(db: Session, tenant_id: str, campaign_id: str, crawl_type: str, seed_url: str) -> CrawlRun:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if crawl_type not in {"deep", "delta"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid crawl_type")

    run = CrawlRun(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        crawl_type=crawl_type,
        seed_url=seed_url,
        status="scheduled",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def list_runs(db: Session, tenant_id: str, campaign_id: str | None = None) -> list[CrawlRun]:
    query = db.query(CrawlRun).filter(CrawlRun.tenant_id == tenant_id)
    if campaign_id:
        query = query.filter(CrawlRun.campaign_id == campaign_id)
    return query.order_by(CrawlRun.created_at.desc()).all()


def list_issues(db: Session, tenant_id: str, campaign_id: str | None = None, severity: str | None = None) -> list[TechnicalIssue]:
    query = db.query(TechnicalIssue).filter(TechnicalIssue.tenant_id == tenant_id)
    if campaign_id:
        query = query.filter(TechnicalIssue.campaign_id == campaign_id)
    if severity:
        query = query.filter(TechnicalIssue.severity == severity)
    return query.order_by(TechnicalIssue.detected_at.desc()).all()

