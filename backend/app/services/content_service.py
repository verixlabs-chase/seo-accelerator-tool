import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from app.models.campaign import Campaign
from app.models.content import ContentAsset, ContentQcEvent, EditorialCalendar, InternalLinkMap


_ALLOWED_TRANSITIONS = {
    "planned": {"draft"},
    "draft": {"approved"},
    "approved": {"published"},
    "published": set(),
}


def _campaign_or_404(db: Session, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


def create_asset(db: Session, tenant_id: str, campaign_id: str, cluster_name: str, title: str, planned_month: int) -> ContentAsset:
    _campaign_or_404(db, tenant_id, campaign_id)
    asset = ContentAsset(
        tenant_id=tenant_id,
        campaign_id=campaign_id,
        cluster_name=cluster_name,
        title=title,
        planned_month=planned_month,
        status="planned",
    )
    db.add(asset)
    db.flush()
    db.add(
        EditorialCalendar(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            content_asset_id=asset.id,
            month_number=planned_month,
        )
    )
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(db: Session, tenant_id: str, asset_id: str, status_value: str | None, title: str | None, target_url: str | None) -> ContentAsset:
    asset = db.get(ContentAsset, asset_id)
    if asset is None or asset.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content asset not found")

    if status_value is not None and status_value != asset.status:
        allowed = _ALLOWED_TRANSITIONS.get(asset.status, set())
        if status_value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid lifecycle transition {asset.status} -> {status_value}",
            )
        asset.status = status_value
    if title is not None:
        asset.title = title
    if target_url is not None:
        asset.target_url = target_url
    asset.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(asset)
    return asset


def get_plan(db: Session, tenant_id: str, campaign_id: str, month_number: int | None = None) -> list[ContentAsset]:
    query = db.query(ContentAsset).filter(ContentAsset.tenant_id == tenant_id, ContentAsset.campaign_id == campaign_id)
    if month_number is not None:
        query = query.filter(ContentAsset.planned_month == month_number)
    return query.order_by(ContentAsset.created_at.desc()).all()


def generate_plan(db: Session, tenant_id: str, campaign_id: str, month_number: int) -> dict:
    _campaign_or_404(db, tenant_id, campaign_id)
    existing = (
        db.query(ContentAsset)
        .filter(
            ContentAsset.tenant_id == tenant_id,
            ContentAsset.campaign_id == campaign_id,
            ContentAsset.planned_month == month_number,
        )
        .count()
    )
    if existing == 0:
        for i in range(3):
            create_asset(
                db,
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                cluster_name=f"Cluster {month_number}",
                title=f"Planned Topic {month_number}-{i+1}",
                planned_month=month_number,
            )
    items = get_plan(db, tenant_id=tenant_id, campaign_id=campaign_id, month_number=month_number)
    return {"campaign_id": campaign_id, "month_number": month_number, "items_count": len(items)}


def run_qc_checks(db: Session, tenant_id: str, asset_id: str) -> dict:
    asset = db.get(ContentAsset, asset_id)
    if asset is None or asset.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content asset not found")

    checks = [
        ("has_title", bool(asset.title), 1.0),
        ("has_target_url_when_published", (asset.status != "published" or bool(asset.target_url)), 1.0),
        ("title_min_length", len(asset.title or "") >= 15, 0.8),
    ]
    passed_count = 0
    for name, passed, score in checks:
        if passed:
            passed_count += 1
        db.add(
            ContentQcEvent(
                tenant_id=tenant_id,
                campaign_id=asset.campaign_id,
                content_asset_id=asset.id,
                check_name=name,
                passed=1 if passed else 0,
                score=score if passed else 0.0,
                details_json=json.dumps({"asset_status": asset.status}),
            )
        )
    db.commit()
    return {"asset_id": asset.id, "checks": len(checks), "passed": passed_count}


def refresh_internal_link_map(db: Session, tenant_id: str, campaign_id: str) -> dict:
    published_assets = (
        db.query(ContentAsset)
        .filter(
            ContentAsset.tenant_id == tenant_id,
            ContentAsset.campaign_id == campaign_id,
            ContentAsset.status == "published",
        )
        .order_by(ContentAsset.updated_at.desc())
        .all()
    )
    db.query(InternalLinkMap).filter(
        InternalLinkMap.tenant_id == tenant_id,
        InternalLinkMap.campaign_id == campaign_id,
    ).delete()

    link_count = 0
    for i, source in enumerate(published_assets):
        for j, target in enumerate(published_assets):
            if i == j:
                continue
            anchor = target.cluster_name.lower()
            db.add(
                InternalLinkMap(
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    source_asset_id=source.id,
                    target_asset_id=target.id,
                    anchor_text=anchor[:255],
                    confidence=0.8,
                )
            )
            link_count += 1
    db.commit()
    return {"campaign_id": campaign_id, "link_recommendations": link_count}


def get_link_recommendations(db: Session, tenant_id: str, campaign_id: str) -> list[dict]:
    source_asset = aliased(ContentAsset)
    target_asset = aliased(ContentAsset)
    rows = (
        db.query(InternalLinkMap, source_asset, target_asset)
        .join(source_asset, source_asset.id == InternalLinkMap.source_asset_id)
        .join(target_asset, target_asset.id == InternalLinkMap.target_asset_id)
        .filter(InternalLinkMap.tenant_id == tenant_id, InternalLinkMap.campaign_id == campaign_id)
        .all()
    )
    items: list[dict] = []
    for link, source, target in rows:
        items.append(
            {
                "source_asset_id": source.id,
                "source_title": source.title,
                "target_asset_id": target.id,
                "target_title": target.title,
                "anchor_text": link.anchor_text,
                "confidence": link.confidence,
            }
        )
    return items
