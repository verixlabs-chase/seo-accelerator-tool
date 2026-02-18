from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.campaign import Campaign
from app.models.tenant import Tenant

TENANT_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Active": {"Suspended", "Cancelled"},
    "Suspended": {"Active", "Cancelled"},
    "Cancelled": {"Archived"},
    "Archived": set(),
}

CAMPAIGN_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Configured"},
    "Configured": {"BaselineRunning"},
    "BaselineRunning": {"Active"},
    "Active": {"Paused"},
    "Paused": {"Active"},
}


def create_tenant(db: Session, name: str) -> Tenant:
    row = Tenant(name=name, status="Active")
    db.add(row)
    db.flush()
    emit_event(db, tenant_id=row.id, event_type="tenant.created", payload={"name": name, "status": "Active"})
    db.commit()
    db.refresh(row)
    return row


def list_tenants(db: Session) -> list[Tenant]:
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


def transition_tenant_status(db: Session, tenant_id: str, target_status: str) -> Tenant:
    row = db.get(Tenant, tenant_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    allowed = TENANT_ALLOWED_TRANSITIONS.get(row.status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tenant transition: {row.status} -> {target_status}",
        )
    previous = row.status
    row.status = target_status
    emit_event(
        db,
        tenant_id=row.id,
        event_type="tenant.status.changed",
        payload={"from": previous, "to": target_status},
    )
    db.commit()
    db.refresh(row)
    return row


def transition_campaign_setup_state(db: Session, tenant_id: str, campaign_id: str, target_state: str) -> Campaign:
    row = db.get(Campaign, campaign_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    allowed = CAMPAIGN_ALLOWED_TRANSITIONS.get(row.setup_state, set())
    if target_state not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid campaign transition: {row.setup_state} -> {target_state}",
        )
    previous = row.setup_state
    row.setup_state = target_state
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="campaign.setup_state.changed",
        payload={"campaign_id": campaign_id, "from": previous, "to": target_state},
    )
    db.commit()
    db.refresh(row)
    return row
