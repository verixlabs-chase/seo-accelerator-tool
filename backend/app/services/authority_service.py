from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit_event
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
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="authority.backlinks.ingested",
            payload={"campaign_id": campaign_id, "count": len(backlinks)},
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
    enriched = 0
    for contact in contacts:
        if contact.status in {"pending", "enrichment_pending"}:
            contact.status = "enriched"
            enriched += 1
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="outreach.contacts.enriched",
        payload={"campaign_id": campaign_id, "contacts_enriched": enriched},
    )
    db.commit()
    return {
        "campaign_id": campaign_id,
        "status": "success",
        "contacts_enriched": enriched,
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
        .filter(OutreachContact.tenant_id == tenant_id, OutreachContact.outreach_campaign_id == outreach_campaign_id)
        .all()
    )
    advanced = 0
    for contact in contacts:
        if contact.status == "enriched":
            contact.status = "queued"
            advanced += 1
        elif contact.status == "queued":
            contact.status = "sent"
            advanced += 1
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="outreach.sequence.executed",
        payload={"outreach_campaign_id": outreach_campaign_id, "contacts_advanced": advanced},
    )
    db.commit()
    return {
        "outreach_campaign_id": outreach_campaign_id,
        "status": "success",
        "contacts_advanced": advanced,
        "contacts_total": len(contacts),
    }


def submit_citation_batch(db: Session, tenant_id: str, campaign_id: str) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    rows = db.query(Citation).filter(Citation.tenant_id == tenant_id, Citation.campaign_id == campaign_id).all()
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
