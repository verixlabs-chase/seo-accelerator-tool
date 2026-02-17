from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.authority import Backlink, Citation, OutreachCampaign, OutreachContact
from app.models.campaign import Campaign
from app.providers import get_authority_provider


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def create_outreach_campaign(db: Session, tenant_id: str, campaign_id: str, name: str) -> OutreachCampaign:
    _campaign_or_404(db, tenant_id, campaign_id)
    item = OutreachCampaign(tenant_id=tenant_id, campaign_id=campaign_id, name=name, status="active")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_outreach_contact(db: Session, tenant_id: str, campaign_id: str, outreach_campaign_id: str, full_name: str, email: str) -> OutreachContact:
    _campaign_or_404(db, tenant_id, campaign_id)
    oc = db.get(OutreachCampaign, outreach_campaign_id)
    if oc is None or oc.tenant_id != tenant_id or oc.campaign_id != campaign_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outreach campaign not found")
    contact = OutreachContact(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        outreach_campaign_id=outreach_campaign_id,
        full_name=full_name,
        email=email,
        status="pending",
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def sync_backlinks(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    existing = db.query(Backlink).filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id).count()
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
        db.commit()
    count = db.query(Backlink).filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id).count()
    return {"campaign_id": campaign_id, "backlinks_synced": count}


def list_backlinks(db: Session, tenant_id: str, campaign_id: str) -> list[Backlink]:
    return (
        db.query(Backlink)
        .filter(Backlink.tenant_id == tenant_id, Backlink.campaign_id == campaign_id)
        .order_by(Backlink.discovered_at.desc())
        .all()
    )


def submit_citation(db: Session, tenant_id: str, campaign_id: str, directory_name: str) -> Citation:
    _campaign_or_404(db, tenant_id, campaign_id)
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
    provider = get_authority_provider()
    rows = db.query(Citation).filter(Citation.tenant_id == tenant_id, Citation.campaign_id == campaign_id).all()
    for row in rows:
        payload = provider.refresh_citation_status(
            campaign_id=campaign_id,
            directory_name=row.directory_name,
            current_status=row.submission_status,
        )
        row.submission_status = payload["submission_status"]
        row.listing_url = payload.get("listing_url")
        row.updated_at = payload.get("updated_at", datetime.now(UTC))
    db.commit()
    return rows
