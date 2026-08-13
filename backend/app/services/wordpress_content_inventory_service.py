from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intelligence.executors import wordpress_plugin
from app.models.campaign import Campaign
from app.models.wordpress_content_inventory import (
    WordPressContentItem,
    WordPressContentSyncRun,
)
from app.services.wordpress_connection_service import get_site_connection


class WordPressContentInventoryError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def sync_wordpress_content(db: Session, *, campaign: Campaign) -> dict[str, Any]:
    if not campaign.organization_id:
        raise WordPressContentInventoryError(
            "Finish setting up this business before syncing WordPress pages.",
            reason_code="wordpress_organization_required",
        )
    connection = get_site_connection(db, campaign_id=campaign.id)
    if connection is None or connection.status != "connected":
        raise WordPressContentInventoryError(
            "Connect this website with a pairing code before syncing its pages.",
            reason_code="wordpress_site_connection_required",
        )
    running = (
        db.query(WordPressContentSyncRun.id)
        .filter(
            WordPressContentSyncRun.campaign_id == campaign.id,
            WordPressContentSyncRun.status == "running",
        )
        .first()
    )
    if running is not None:
        raise WordPressContentInventoryError(
            "A website page sync is already running.",
            reason_code="wordpress_content_sync_running",
        )

    now = datetime.now(UTC)
    run = WordPressContentSyncRun(
        id=str(uuid.uuid4()),
        tenant_id=campaign.tenant_id,
        organization_id=campaign.organization_id,
        campaign_id=campaign.id,
        wordpress_site_connection_id=connection.id,
        status="running",
        item_count=0,
        source_total_count=0,
        truncated=False,
        seo_plugins=[],
        started_at=now,
    )
    db.add(run)
    db.commit()
    try:
        inventory = wordpress_plugin.fetch_content_inventory(db, campaign_id=campaign.id)
        observed_at = datetime.now(UTC)
        for item in inventory.get("items") or []:
            db.add(
                WordPressContentItem(
                    id=str(uuid.uuid4()),
                    tenant_id=campaign.tenant_id,
                    organization_id=campaign.organization_id,
                    campaign_id=campaign.id,
                    sync_run_id=run.id,
                    wp_post_id=int(item["wp_post_id"]),
                    post_type=str(item["post_type"]),
                    publication_status=str(item["publication_status"]),
                    slug=str(item["slug"]),
                    url=str(item["url"]),
                    title=str(item["title"]),
                    meta_title=item.get("meta_title"),
                    meta_description=item.get("meta_description"),
                    canonical_url=item.get("canonical_url"),
                    headings=list(item.get("headings") or []),
                    internal_links=list(item.get("internal_links") or []),
                    schema_types=list(item.get("schema_types") or []),
                    schema_present=bool(item.get("schema_present")),
                    word_count=max(0, int(item.get("word_count") or 0)),
                    revision_id=str(item["revision_id"]),
                    content_hash=str(item["content_hash"]),
                    modified_at=_parse_datetime(item.get("modified_at")),
                    observed_at=observed_at,
                )
            )
        run.status = "complete"
        run.item_count = len(inventory.get("items") or [])
        run.source_total_count = max(
            run.item_count, int(inventory.get("total_items") or run.item_count)
        )
        run.truncated = bool(inventory.get("truncated"))
        run.plugin_version = str(inventory.get("plugin_version") or "") or None
        run.wordpress_version = str(inventory.get("wordpress_version") or "") or None
        run.php_version = str(inventory.get("php_version") or "") or None
        run.seo_plugins = [
            item for item in (inventory.get("seo_plugins") or []) if isinstance(item, dict)
        ][:10]
        run.completed_at = observed_at
        db.commit()
    except wordpress_plugin.WordPressExecutionError as exc:
        db.rollback()
        _mark_failed(db, run_id=run.id, error_code=exc.reason_code)
        raise
    except Exception as exc:
        db.rollback()
        _mark_failed(db, run_id=run.id, error_code="wordpress_content_sync_failed")
        raise WordPressContentInventoryError(
            "The website page list could not be saved. Nothing on the website was changed.",
            reason_code="wordpress_content_sync_failed",
            status_code=500,
        ) from exc
    return get_wordpress_content_inventory(db, campaign=campaign)


def get_wordpress_content_inventory(
    db: Session,
    *,
    campaign: Campaign,
    limit: int = 100,
) -> dict[str, Any]:
    run = (
        db.query(WordPressContentSyncRun)
        .filter(
            WordPressContentSyncRun.tenant_id == campaign.tenant_id,
            WordPressContentSyncRun.organization_id == campaign.organization_id,
            WordPressContentSyncRun.campaign_id == campaign.id,
            WordPressContentSyncRun.status == "complete",
        )
        .order_by(WordPressContentSyncRun.completed_at.desc())
        .first()
    )
    if run is None:
        return {
            "campaign_id": campaign.id,
            "has_inventory": False,
            "summary": _empty_summary(),
            "items": [],
            "last_synced_at": None,
        }
    items = (
        db.query(WordPressContentItem)
        .filter(
            WordPressContentItem.tenant_id == campaign.tenant_id,
            WordPressContentItem.organization_id == campaign.organization_id,
            WordPressContentItem.campaign_id == campaign.id,
            WordPressContentItem.sync_run_id == run.id,
        )
        .order_by(
            WordPressContentItem.publication_status.asc(),
            WordPressContentItem.title.asc(),
        )
        .limit(min(max(limit, 1), 500))
        .all()
    )
    all_items = (
        db.query(WordPressContentItem)
        .filter(WordPressContentItem.sync_run_id == run.id)
        .all()
    )
    return {
        "campaign_id": campaign.id,
        "has_inventory": True,
        "sync_run_id": run.id,
        "last_synced_at": run.completed_at.isoformat() if run.completed_at else None,
        "plugin_version": run.plugin_version,
        "wordpress_version": run.wordpress_version,
        "seo_plugins": run.seo_plugins,
        "truncated": run.truncated,
        "source_total_count": run.source_total_count,
        "summary": _summary(all_items),
        "items": [_serialize_item(item) for item in items],
    }


def latest_sync_summary(db: Session, *, campaign_id: str) -> dict[str, Any]:
    run = (
        db.query(WordPressContentSyncRun)
        .filter(
            WordPressContentSyncRun.campaign_id == campaign_id,
            WordPressContentSyncRun.status == "complete",
        )
        .order_by(WordPressContentSyncRun.completed_at.desc())
        .first()
    )
    return {
        "content_item_count": run.item_count if run is not None else 0,
        "content_source_total_count": run.source_total_count if run is not None else 0,
        "content_inventory_truncated": bool(run.truncated) if run is not None else False,
        "last_content_sync_at": (
            run.completed_at.isoformat() if run is not None and run.completed_at else None
        ),
    }


def _summary(items: list[WordPressContentItem]) -> dict[str, int]:
    return {
        "pages_found": len(items),
        "published": sum(1 for item in items if item.publication_status == "publish"),
        "drafts": sum(1 for item in items if item.publication_status != "publish"),
        "missing_description": sum(1 for item in items if not item.meta_description),
        "with_schema": sum(1 for item in items if item.schema_present),
        "without_internal_links": sum(1 for item in items if not item.internal_links),
    }


def _empty_summary() -> dict[str, int]:
    return {
        "pages_found": 0,
        "published": 0,
        "drafts": 0,
        "missing_description": 0,
        "with_schema": 0,
        "without_internal_links": 0,
    }


def _serialize_item(item: WordPressContentItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "wp_post_id": item.wp_post_id,
        "post_type": item.post_type,
        "publication_status": item.publication_status,
        "slug": item.slug,
        "url": item.url,
        "title": item.title,
        "meta_title": item.meta_title,
        "meta_description": item.meta_description,
        "canonical_url": item.canonical_url,
        "headings": item.headings,
        "internal_links": item.internal_links,
        "schema_types": item.schema_types,
        "schema_present": item.schema_present,
        "word_count": item.word_count,
        "revision_id": item.revision_id,
        "content_hash": item.content_hash,
        "modified_at": item.modified_at.isoformat() if item.modified_at else None,
        "observed_at": item.observed_at.isoformat(),
    }


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _mark_failed(db: Session, *, run_id: str, error_code: str) -> None:
    failed_run = db.get(WordPressContentSyncRun, run_id)
    if failed_run is None:
        return
    failed_run.status = "failed"
    failed_run.error_code = error_code
    failed_run.completed_at = datetime.now(UTC)
    db.commit()
