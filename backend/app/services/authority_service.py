from datetime import UTC, datetime
from random import uniform

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.authority import Backlink, Citation, OutreachCampaign, OutreachContact
from app.models.campaign import Campaign


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
        db.add(
            Backlink(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                source_url="https://example-partner.com/local-seo-resource",
                target_url=f"https://{campaign_id}.example.com/",
                quality_score=round(uniform(0.5, 0.95), 2),
                status="live",
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
    rows = db.query(Citation).filter(Citation.tenant_id == tenant_id, Citation.campaign_id == campaign_id).all()
    for row in rows:
        if row.submission_status == "submitted":
            row.submission_status = "verified"
            row.listing_url = f"https://directory.example/{row.directory_name.lower().replace(' ', '-')}"
            row.updated_at = datetime.now(UTC)
    db.commit()
    return rows

