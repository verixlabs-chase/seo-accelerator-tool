import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from app.models.campaign import Campaign
from app.models.content import (
    ContentAsset,
    ContentBrief,
    ContentQcEvent,
    EditorialCalendar,
    InternalLinkMap,
)
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.wordpress_content_inventory import (
    WordPressContentItem,
    WordPressContentSyncRun,
)


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


def get_content_workspace(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    page_limit: int = 200,
) -> dict:
    """Return saved page and brief facts without creating plans or provider work."""
    campaign = _campaign_or_404(db, tenant_id, campaign_id)
    bounded_limit = max(1, min(int(page_limit), 200))
    pages: list[dict] = []
    seen_urls: set[str] = set()

    wordpress_run = (
        db.query(WordPressContentSyncRun)
        .filter(
            WordPressContentSyncRun.tenant_id == tenant_id,
            WordPressContentSyncRun.campaign_id == campaign_id,
            WordPressContentSyncRun.status == "complete",
        )
        .order_by(
            WordPressContentSyncRun.completed_at.desc(),
            WordPressContentSyncRun.id.desc(),
        )
        .first()
    )
    wordpress_items = (
        db.query(WordPressContentItem)
        .filter(
            WordPressContentItem.tenant_id == tenant_id,
            WordPressContentItem.campaign_id == campaign_id,
            WordPressContentItem.sync_run_id == wordpress_run.id,
        )
        .order_by(WordPressContentItem.title.asc(), WordPressContentItem.id.asc())
        .limit(bounded_limit)
        .all()
        if wordpress_run is not None
        else []
    )
    for item in wordpress_items:
        normalized_url = _normalized_page_url(item.url)
        if normalized_url:
            seen_urls.add(normalized_url)
        attention: list[str] = []
        if not str(item.title or "").strip():
            attention.append("Add a clear page title")
        if not str(item.meta_description or "").strip():
            attention.append("Add a clear search description")
        if item.publication_status == "publish" and int(item.word_count or 0) < 150:
            attention.append("Review whether this page gives customers enough useful detail")
        pages.append(
            {
                "id": item.id,
                "title": str(item.title or "").strip() or "Untitled page",
                "url": item.url,
                "page_type": item.post_type,
                "publication_state": item.publication_status,
                "source": "connected_website",
                "source_label": "Connected website",
                "last_checked_at": item.observed_at.isoformat(),
                "word_count": int(item.word_count or 0),
                "attention": attention,
            }
        )

    crawl_run = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign_id,
            CrawlRun.status == "completed",
        )
        .order_by(CrawlRun.finished_at.desc(), CrawlRun.id.desc())
        .first()
    )
    crawl_rows = (
        db.query(CrawlPageResult, Page)
        .join(Page, Page.id == CrawlPageResult.page_id)
        .filter(
            CrawlPageResult.tenant_id == tenant_id,
            CrawlPageResult.campaign_id == campaign_id,
            CrawlPageResult.crawl_run_id == crawl_run.id,
        )
        .order_by(CrawlPageResult.crawled_at.desc(), CrawlPageResult.id.desc())
        .limit(bounded_limit)
        .all()
        if crawl_run is not None
        else []
    )
    source_page_evidence_count = len(wordpress_items) + len(crawl_rows)
    for result, page in crawl_rows:
        url = str(result.final_url or page.url or "").strip()
        normalized_url = _normalized_page_url(url)
        if normalized_url and normalized_url in seen_urls:
            continue
        if normalized_url:
            seen_urls.add(normalized_url)
        attention = []
        if not str(result.title or "").strip():
            attention.append("Add a clear page title")
        if not str(result.meta_description or "").strip():
            attention.append("Add a clear search description")
        if int(result.status_code or 0) >= 400:
            attention.append("Fix this page so it loads successfully")
        if not bool(result.is_indexable):
            attention.append("Review why this page is not available to search")
        if bool(result.is_indexable) and int(result.word_count or 0) < 150:
            attention.append("Review whether this page gives customers enough useful detail")
        pages.append(
            {
                "id": page.id,
                "title": str(result.title or "").strip() or "Untitled page",
                "url": url,
                "page_type": "website_page",
                "publication_state": (
                    "public" if int(result.status_code or 0) < 400 else "needs_attention"
                ),
                "source": "website_scan",
                "source_label": "Website scan",
                "last_checked_at": result.crawled_at.isoformat(),
                "word_count": int(result.word_count or 0),
                "attention": attention,
            }
        )
        if len(pages) >= bounded_limit:
            break

    briefs = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.campaign_id == campaign_id,
        )
        .order_by(ContentBrief.created_at.desc(), ContentBrief.id.desc())
        .limit(100)
        .all()
    )
    assets = (
        db.query(ContentAsset)
        .filter(
            ContentAsset.tenant_id == tenant_id,
            ContentAsset.campaign_id == campaign_id,
        )
        .order_by(ContentAsset.updated_at.desc(), ContentAsset.id.desc())
        .limit(100)
        .all()
    )
    pages.sort(
        key=lambda item: (
            -len(item["attention"]),
            str(item["title"]).casefold(),
            str(item["url"]),
        )
    )
    attention_count = sum(bool(item["attention"]) for item in pages)
    if briefs:
        next_action = {
            "code": "review_content_brief",
            "label": "Review the first content brief",
            "detail": (
                "Check the saved customer search, page choice, evidence, and outline. "
                "Nothing will be published from this screen."
            ),
            "href": "/content#briefs",
        }
    elif attention_count:
        next_action = {
            "code": "review_page_attention",
            "label": "Review the first page needing attention",
            "detail": "Start with the page that has the most clear, saved issues.",
            "href": "/content#pages",
        }
    elif not pages:
        next_action = {
            "code": "collect_website_pages",
            "label": "Run a website scan",
            "detail": "Save the website pages before planning content work.",
            "href": "/site-health",
        }
    else:
        next_action = {
            "code": "find_content_opportunity",
            "label": "Find a content opportunity",
            "detail": "Use confirmed customer searches and competitors to find the next useful page.",
            "href": "/competitors",
        }
    inventory_is_partial = bool(
        (wordpress_run is not None and wordpress_run.truncated)
        or (
            wordpress_run is not None
            and int(wordpress_run.source_total_count or 0) > len(wordpress_items)
        )
        or (crawl_run is not None and int(crawl_run.pages_discovered or 0) > len(crawl_rows))
        or source_page_evidence_count > bounded_limit
    )
    if pages:
        truth_state = "partial" if inventory_is_partial else "measured"
        truth_summary = (
            f"Showing the first {len(pages)} saved website page"
            f"{'s' if len(pages) != 1 else ''} for this location."
            if inventory_is_partial
            else (
                f"Showing {len(pages)} saved website page"
                f"{'s' if len(pages) != 1 else ''} for this location."
            )
        )
    else:
        truth_state = "not_measured"
        truth_summary = "No saved website pages are available for this location yet."

    return {
        "location": {
            "campaign_id": campaign.id,
            "business_location_id": campaign.business_location_id,
            "name": campaign.name,
            "domain": campaign.domain,
        },
        "truth": {
            "state": truth_state,
            "summary": truth_summary,
            "limitations": [
                "This workspace uses saved page and research evidence only.",
                "A draft or brief cannot publish or change the website.",
                *(
                    ["The saved inventory is larger than this view, so some pages are not shown."]
                    if inventory_is_partial
                    else []
                ),
            ],
        },
        "summary": {
            "pages": len(pages),
            "pages_needing_attention": attention_count,
            "draft_briefs": sum(item.status == "draft" for item in briefs),
            "planned_work": sum(item.status != "published" for item in assets),
            "published_work": sum(item.status == "published" for item in assets),
        },
        "sources": [
            {
                "code": "connected_website",
                "label": "Connected website",
                "state": "measured" if wordpress_run is not None else "not_connected",
                "last_checked_at": (
                    wordpress_run.completed_at.isoformat()
                    if wordpress_run is not None and wordpress_run.completed_at
                    else None
                ),
            },
            {
                "code": "website_scan",
                "label": "Website scan",
                "state": "measured" if crawl_run is not None else "not_measured",
                "last_checked_at": (
                    crawl_run.finished_at.isoformat()
                    if crawl_run is not None and crawl_run.finished_at
                    else None
                ),
            },
        ],
        "pages": pages,
        "briefs": [
            {
                "id": item.id,
                "status": item.status,
                "title": item.title,
                "primary_search": item.primary_keyword,
                "recommended_page_action": item.recommended_page_action,
                "target_url": item.target_url,
                "competitor_domain": item.competitor_domain,
                "competitor_url": item.competitor_url,
                "service_name": item.service_name,
                "service_area_name": item.service_area_name,
                "evidence": _customer_brief_evidence(item.evidence),
                "outline": list(item.outline or []),
                "created_at": item.created_at.isoformat(),
            }
            for item in briefs
        ],
        "work": [
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "target_url": item.target_url,
                "planned_month": item.planned_month,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in assets
        ],
        "next_action": next_action,
    }


def _normalized_page_url(value: str) -> str:
    return str(value or "").strip().casefold().rstrip("/")


def _customer_brief_evidence(value: dict | None) -> dict:
    evidence = value or {}
    allowed_fields = (
        "owner_position",
        "competitor_position",
        "search_volume",
        "source_updated_at",
        "evidence_note",
    )
    return {field: evidence[field] for field in allowed_fields if field in evidence}


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
