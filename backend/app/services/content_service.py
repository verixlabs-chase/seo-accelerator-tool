import hashlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse

from fastapi import HTTPException, status
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm import aliased

from app.models.campaign import Campaign
from app.models.content import (
    ContentAsset,
    ContentBrief,
    ContentDraft,
    ContentQcEvent,
    EditorialCalendar,
    InternalLinkMap,
)
from app.models.crawl import CrawlInternalLink, CrawlPageResult, CrawlRun, Page
from app.models.governed_ai import GovernedAIRun
from app.models.wordpress_content_inventory import (
    WordPressContentItem,
    WordPressContentSyncRun,
)
from app.services.audit_service import write_audit_log
from app.services.wordpress_managed_content_validation_service import (
    UNSAFE_TEXT_PATTERN,
    UNSUPPORTED_OUTCOME_PHRASES,
    UNVERIFIED_BUSINESS_PHRASES,
    UNVERIFIED_NUMBER_PATTERN,
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
    draft_storage_ready = _content_draft_storage_ready(db)
    bounded_limit = max(1, min(int(page_limit), 200))
    pages: list[dict] = []
    seen_urls: set[str] = set()
    page_metadata_by_url: dict[str, dict] = {}

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
            page_metadata_by_url[normalized_url] = {
                "url": item.url,
                "title": str(item.meta_title or item.title or "").strip() or None,
                "title_source": (
                    "Saved SEO title"
                    if str(item.meta_title or "").strip()
                    else "Saved page title"
                ),
                "description": str(item.meta_description or "").strip() or None,
                "structured_data_types": [
                    str(value).strip()
                    for value in list(item.schema_types or [])
                    if str(value).strip()
                ],
                "structured_data_present": bool(item.schema_present),
                "structured_data_valid": None,
                "outgoing_internal_links": [
                    str(value).strip()
                    for value in list(item.internal_links or [])
                    if str(value).strip()
                ],
                "eligible_for_internal_links": item.publication_status == "publish",
                "source_label": "Connected website",
                "observed_at": item.observed_at,
            }
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
    crawl_links_by_page_id: dict[str, list[str]] = {}
    crawl_source_page_ids = [page.id for _result, page in crawl_rows]
    if crawl_run is not None and crawl_source_page_ids:
        crawl_link_rows = (
            db.query(CrawlInternalLink)
            .filter(
                CrawlInternalLink.tenant_id == tenant_id,
                CrawlInternalLink.campaign_id == campaign_id,
                CrawlInternalLink.crawl_run_id == crawl_run.id,
                CrawlInternalLink.source_page_id.in_(crawl_source_page_ids),
            )
            .order_by(
                CrawlInternalLink.source_page_id.asc(),
                CrawlInternalLink.target_url.asc(),
            )
            .limit(bounded_limit * 100)
            .all()
        )
        for link in crawl_link_rows:
            crawl_links_by_page_id.setdefault(link.source_page_id, []).append(
                link.target_url
            )
    source_page_evidence_count = len(wordpress_items) + len(crawl_rows)
    for result, page in crawl_rows:
        url = str(result.final_url or page.url or "").strip()
        normalized_url = _normalized_page_url(url)
        if normalized_url and normalized_url in seen_urls:
            continue
        if normalized_url:
            seen_urls.add(normalized_url)
            page_metadata_by_url[normalized_url] = {
                "url": url,
                "title": str(result.title or "").strip() or None,
                "title_source": "Saved page title",
                "description": str(result.meta_description or "").strip() or None,
                "structured_data_types": [
                    str(value).strip()
                    for value in list(result.structured_data_types or [])
                    if str(value).strip()
                ],
                "structured_data_present": bool(result.structured_data_types),
                "structured_data_valid": bool(result.structured_data_valid),
                "outgoing_internal_links": list(
                    crawl_links_by_page_id.get(page.id, [])
                ),
                "eligible_for_internal_links": (
                    int(result.status_code or 0) < 400 and bool(result.is_indexable)
                ),
                "source_label": "Website scan",
                "observed_at": result.crawled_at,
            }
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
    briefs.sort(key=lambda item: (item.status != "draft", -item.created_at.timestamp()))
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.tenant_id == tenant_id,
            ContentDraft.campaign_id == campaign_id,
        )
        .order_by(ContentDraft.updated_at.desc(), ContentDraft.id.desc())
        .all()
        if draft_storage_ready
        else []
    )
    drafts_by_brief = {item.content_brief_id: item for item in drafts}
    suggestions_by_draft: dict[str, GovernedAIRun] = {}
    if drafts:
        draft_ids = {item.id for item in drafts}
        suggestion_rows = (
            db.query(GovernedAIRun)
            .filter(
                GovernedAIRun.tenant_id == tenant_id,
                GovernedAIRun.campaign_id == campaign_id,
                GovernedAIRun.feature == "content_draft_suggestion",
            )
            .order_by(GovernedAIRun.created_at.desc(), GovernedAIRun.id.desc())
            .limit(500)
            .all()
        )
        draft_revisions = {item.id: int(item.revision) for item in drafts}
        for row in suggestion_rows:
            action_id = str(row.selected_action_id or "")
            if not action_id.startswith("content_draft:"):
                continue
            draft_id = action_id.removeprefix("content_draft:")
            if draft_id not in draft_ids or draft_id in suggestions_by_draft:
                continue
            output = row.output_payload if isinstance(row.output_payload, dict) else {}
            if row.status != "validated" or int(output.get("draft_revision") or 0) != draft_revisions[draft_id]:
                continue
            suggestions_by_draft[draft_id] = row
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
    first_draft_brief = next((item for item in briefs if item.status == "draft"), None)
    first_accepted_without_draft = next(
        (
            item
            for item in briefs
            if item.status == "accepted" and item.id not in drafts_by_brief
        ),
        None,
    )
    if first_draft_brief is not None:
        next_action = {
            "code": "review_content_brief",
            "label": "Review the first content brief",
            "detail": (
                "Check the saved customer search, page choice, evidence, and outline. "
                "Nothing will be published from this screen."
            ),
            "href": "/content#briefs",
        }
    elif first_accepted_without_draft is not None and draft_storage_ready:
        next_action = {
            "code": "start_content_draft",
            "label": "Start the accepted working draft",
            "detail": (
                "Create an empty, editable draft from the accepted outline. "
                "Nothing will be generated or published automatically."
            ),
            "href": "/content#briefs",
        }
    elif drafts:
        next_action = {
            "code": "continue_content_draft",
            "label": "Continue the working draft",
            "detail": "Add or review the page wording. Saving cannot publish it.",
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
        "capabilities": {"working_drafts_available": draft_storage_ready},
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
                *(
                    ["Working drafts are temporarily unavailable while storage is updated."]
                    if not draft_storage_ready
                    else []
                ),
            ],
        },
        "summary": {
            "pages": len(pages),
            "pages_needing_attention": attention_count,
            "draft_briefs": sum(item.status == "draft" for item in briefs),
            "working_drafts": len(drafts),
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
            _serialize_workspace_brief(
                item,
                draft=drafts_by_brief.get(item.id),
                suggestion=(
                    suggestions_by_draft.get(drafts_by_brief[item.id].id)
                    if item.id in drafts_by_brief
                    else None
                ),
                page_metadata=(
                    page_metadata_by_url.get(_normalized_page_url(item.target_url or ""))
                    if item.target_url
                    else None
                ),
                page_inventory=list(page_metadata_by_url.values()),
            )
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


def review_content_brief(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    brief_id: str,
    decision: str,
    note: str | None,
    actor_user_id: str,
) -> dict:
    """Save one terminal owner decision without changing the frozen brief."""
    _campaign_or_404(db, tenant_id, campaign_id)
    brief = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.id == brief_id,
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.campaign_id == campaign_id,
        )
        .with_for_update()
        .first()
    )
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content brief not found")
    target_status = "accepted" if decision == "accept" else "declined"
    if brief.status == target_status:
        return {
            "changed": False,
            "message": "This brief decision was already saved.",
            "item": _serialize_workspace_brief(brief),
            "safety": _brief_review_safety(),
        }
    if brief.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This brief already has a different final decision.",
        )
    now = datetime.now(UTC)
    brief.status = target_status
    brief.updated_at = now
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="content.brief.reviewed",
        payload={
            "campaign_id": campaign_id,
            "content_brief_id": brief.id,
            "decision": target_status,
            "note": str(note or "").strip() or None,
            "brief_evidence_unchanged": True,
            "publishing_enabled": False,
        },
    )
    db.commit()
    db.refresh(brief)
    return {
        "changed": True,
        "message": (
            "Page target accepted for later drafting. Nothing was published."
            if target_status == "accepted"
            else "Brief declined. Nothing was changed on the website."
        ),
        "item": _serialize_workspace_brief(brief),
        "safety": _brief_review_safety(),
    }


def create_content_draft(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    brief_id: str,
    actor_user_id: str,
) -> dict:
    """Create one empty working draft from an owner-accepted frozen brief."""
    _campaign_or_404(db, tenant_id, campaign_id)
    if not _content_draft_storage_ready(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Working drafts are temporarily unavailable while storage is updated.",
        )
    brief = (
        db.query(ContentBrief)
        .filter(
            ContentBrief.id == brief_id,
            ContentBrief.tenant_id == tenant_id,
            ContentBrief.campaign_id == campaign_id,
        )
        .with_for_update()
        .first()
    )
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content brief not found")
    if brief.status != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accept the page target before starting a working draft.",
        )
    existing = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.tenant_id == tenant_id,
            ContentDraft.content_brief_id == brief.id,
        )
        .first()
    )
    if existing is not None:
        return {
            "created": False,
            "message": "This working draft is already saved.",
            "item": _serialize_content_draft(existing),
            "safety": _content_draft_safety(),
        }
    sections = [
        {
            "order": int(item.get("order") or index),
            "heading": str(item.get("heading") or "Page section").strip(),
            "guidance": str(item.get("guidance") or "").strip(),
            "body": "",
        }
        for index, item in enumerate(list(brief.outline or []), start=1)
        if isinstance(item, dict)
    ]
    if not sections:
        sections = [
            {
                "order": 1,
                "heading": "Explain the service clearly",
                "guidance": "Describe who this service helps and what customers receive.",
                "body": "",
            }
        ]
    now = datetime.now(UTC)
    draft = ContentDraft(
        tenant_id=brief.tenant_id,
        organization_id=brief.organization_id,
        campaign_id=brief.campaign_id,
        business_location_id=brief.business_location_id,
        content_brief_id=brief.id,
        status="working",
        title=brief.title,
        sections=sections,
        source_brief_hash=_content_brief_hash(brief),
        revision=1,
        automatic_publishing_allowed=False,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="content.draft.created",
        payload={
            "campaign_id": campaign_id,
            "content_brief_id": brief.id,
            "content_draft_id": draft.id,
            "source_brief_hash": draft.source_brief_hash,
            "draft_generated": False,
            "publishing_enabled": False,
        },
    )
    db.commit()
    db.refresh(draft)
    return {
        "created": True,
        "message": "Empty working draft created from the accepted outline.",
        "item": _serialize_content_draft(draft),
        "safety": _content_draft_safety(),
    }


def update_content_draft(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    draft_id: str,
    title: str,
    sections: list[dict],
    actor_user_id: str,
) -> dict:
    """Save owner-authored plain text without dispatching AI or website work."""
    _campaign_or_404(db, tenant_id, campaign_id)
    if not _content_draft_storage_ready(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Working drafts are temporarily unavailable while storage is updated.",
        )
    draft = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.id == draft_id,
            ContentDraft.tenant_id == tenant_id,
            ContentDraft.campaign_id == campaign_id,
        )
        .with_for_update()
        .first()
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content draft not found")
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise HTTPException(status_code=422, detail="Add a draft page title.")
    existing_guidance = {
        int(item.get("order") or 0): str(item.get("guidance") or "").strip()
        for item in list(draft.sections or [])
        if isinstance(item, dict)
    }
    seen_orders: set[int] = set()
    normalized_sections = []
    total_body_characters = 0
    for raw in sections:
        order = int(raw.get("order") or 0)
        heading = str(raw.get("heading") or "").strip()
        body = str(raw.get("body") or "").strip()
        if order < 1 or order in seen_orders or not heading:
            raise HTTPException(status_code=422, detail="Each draft section needs a unique order and heading.")
        seen_orders.add(order)
        total_body_characters += len(body)
        normalized_sections.append(
            {
                "order": order,
                "heading": heading,
                "guidance": existing_guidance.get(order, ""),
                "body": body,
            }
        )
    if total_body_characters > 12000:
        raise HTTPException(status_code=422, detail="The working draft is too long to save safely.")
    normalized_sections.sort(key=lambda item: item["order"])
    if draft.title == normalized_title and list(draft.sections or []) == normalized_sections:
        return {
            "changed": False,
            "message": "The working draft is already saved.",
            "item": _serialize_content_draft(draft),
            "safety": _content_draft_safety(),
        }
    draft.title = normalized_title
    draft.sections = normalized_sections
    draft.revision = int(draft.revision or 0) + 1
    draft.updated_by_user_id = actor_user_id
    draft.updated_at = datetime.now(UTC)
    write_audit_log(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        event_type="content.draft.saved",
        payload={
            "campaign_id": campaign_id,
            "content_brief_id": draft.content_brief_id,
            "content_draft_id": draft.id,
            "revision": draft.revision,
            "customer_copy_omitted": True,
            "publishing_enabled": False,
        },
    )
    db.commit()
    db.refresh(draft)
    return {
        "changed": True,
        "message": "Working draft saved. Nothing was published.",
        "item": _serialize_content_draft(draft),
        "safety": _content_draft_safety(),
    }


def _serialize_workspace_brief(
    item: ContentBrief,
    *,
    draft: ContentDraft | None = None,
    suggestion: GovernedAIRun | None = None,
    page_metadata: dict | None = None,
    page_inventory: list[dict] | None = None,
) -> dict:
    return {
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
        "updated_at": item.updated_at.isoformat(),
        "working_draft": (
            _serialize_content_draft(
                draft,
                suggestion=suggestion,
                brief=item,
                page_metadata=page_metadata,
                page_inventory=page_inventory,
            )
            if draft is not None
            else None
        ),
    }


def _serialize_content_draft(
    item: ContentDraft,
    *,
    suggestion: GovernedAIRun | None = None,
    brief: ContentBrief | None = None,
    page_metadata: dict | None = None,
    page_inventory: list[dict] | None = None,
) -> dict:
    ai_suggestion = None
    if suggestion is not None and isinstance(suggestion.output_payload, dict):
        saved = {
            key: value
            for key, value in suggestion.output_payload.items()
            if key != "draft_revision"
        }
        ai_suggestion = {
            "state": "available",
            "suggestion": saved,
            "updated_at": (
                suggestion.completed_at or suggestion.created_at
            ).isoformat(),
            "safety": {
                "owner_draft_changed": False,
                "approval_recorded": False,
                "automatic_publishing_allowed": False,
                "website_changed": False,
            },
        }
    return {
        "id": item.id,
        "status": item.status,
        "title": item.title,
        "sections": list(item.sections or []),
        "revision": int(item.revision),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "ai_suggestion": ai_suggestion,
        "metadata_recommendations": (
            _metadata_recommendations(brief, page_metadata=page_metadata)
            if brief is not None
            else []
        ),
        "structured_data_recommendation": (
            _structured_data_recommendation(brief, page_metadata=page_metadata)
            if brief is not None
            else None
        ),
        "internal_link_recommendations": (
            _internal_link_recommendations(
                brief,
                page_metadata=page_metadata,
                page_inventory=page_inventory or [],
            )
            if brief is not None
            else None
        ),
        "content_readiness": (
            _content_readiness(item, brief) if brief is not None else None
        ),
        "safety": _content_draft_safety(),
    }


def _content_readiness(draft: ContentDraft, brief: ContentBrief) -> dict:
    sections = [item for item in list(draft.sections or []) if isinstance(item, dict)]
    expected_outline = [
        item for item in list(brief.outline or []) if isinstance(item, dict)
    ]
    expected_orders = {
        int(item.get("order") or index)
        for index, item in enumerate(expected_outline, start=1)
    }
    actual_orders = {int(item.get("order") or 0) for item in sections}
    missing_orders = sorted(expected_orders - actual_orders)
    completed_sections = sum(bool(str(item.get("body") or "").strip()) for item in sections)
    combined_copy = " ".join(
        [
            str(draft.title or "").strip(),
            *[
                str(value or "").strip()
                for item in sections
                for value in (item.get("heading"), item.get("body"))
            ],
        ]
    ).strip()
    normalized_copy = " ".join(combined_copy.casefold().split())
    word_count = len(re.findall(r"\b[\w'-]+\b", combined_copy))
    checks: list[dict] = []

    lineage_matches = draft.source_brief_hash == _content_brief_hash(brief)
    checks.append(
        {
            "code": "accepted_brief",
            "label": "Accepted brief",
            "state": "passed" if lineage_matches else "blocked",
            "detail": (
                "This draft still matches the accepted brief used to create it."
                if lineage_matches
                else "The accepted brief changed after this draft was created. Start a fresh review before using it."
            ),
        }
    )
    sections_present = bool(sections) and not missing_orders
    checks.append(
        {
            "code": "required_sections",
            "label": "Required sections",
            "state": "passed" if sections_present else "blocked",
            "detail": (
                f"All {len(expected_orders) or len(sections)} planned sections are present."
                if sections_present
                else "One or more sections from the accepted outline are missing."
            ),
        }
    )
    all_sections_complete = bool(sections) and completed_sections == len(sections)
    checks.append(
        {
            "code": "section_copy",
            "label": "Section wording",
            "state": "passed" if all_sections_complete else "action_needed",
            "detail": (
                f"All {completed_sections} saved sections include owner wording."
                if all_sections_complete
                else f"{completed_sections} of {len(sections)} saved sections include owner wording."
            ),
        }
    )
    for code, label, value in (
        ("service_fact", "Confirmed service", brief.service_name),
        ("service_area_fact", "Confirmed service area", brief.service_area_name),
    ):
        fact = " ".join(str(value or "").casefold().split())
        found = not fact or fact in normalized_copy
        checks.append(
            {
                "code": code,
                "label": label,
                "state": "passed" if found else "action_needed",
                "detail": (
                    "The confirmed fact appears in the saved title or page wording."
                    if found and fact
                    else (
                        "No confirmed fact was required for this check."
                        if not fact
                        else "Add the confirmed fact naturally to the page before owner review."
                    )
                ),
            }
        )
    unsafe_markup = bool(UNSAFE_TEXT_PATTERN.search(combined_copy))
    checks.append(
        {
            "code": "safe_plain_text",
            "label": "Safe plain text",
            "state": "blocked" if unsafe_markup else "passed",
            "detail": (
                "Remove script-like markup or unsafe link code from the working draft."
                if unsafe_markup
                else "No script-like markup or unsafe link code was found."
            ),
        }
    )
    lowered_copy = combined_copy.casefold()
    unverified_phrase_found = any(
        phrase in lowered_copy
        for phrase in (*UNVERIFIED_BUSINESS_PHRASES, *UNSUPPORTED_OUTCOME_PHRASES)
    )
    unverified_number_found = bool(UNVERIFIED_NUMBER_PATTERN.search(combined_copy))
    claims_need_confirmation = unverified_phrase_found or unverified_number_found
    checks.append(
        {
            "code": "business_claims",
            "label": "Business claims",
            "state": "owner_confirmation" if claims_need_confirmation else "passed",
            "detail": (
                "One or more business, performance, price, percentage, or experience claims need owner proof."
                if claims_need_confirmation
                else "No unsupported business or performance claim pattern was found."
            ),
        }
    )
    blocked_count = sum(item["state"] == "blocked" for item in checks)
    action_needed_count = sum(
        item["state"] in {"action_needed", "owner_confirmation"} for item in checks
    )
    if blocked_count:
        readiness_state = "blocked"
        summary = "Fix the blocked draft checks before owner review."
    elif action_needed_count:
        readiness_state = "needs_work"
        summary = "The working draft still needs edits or owner confirmation."
    else:
        readiness_state = "ready_for_owner_review"
        summary = "The saved draft is ready for an owner to review."
    return {
        "state": readiness_state,
        "summary": summary,
        "facts": {
            "planned_sections": len(expected_orders) or len(sections),
            "saved_sections": len(sections),
            "completed_sections": completed_sections,
            "word_count": word_count,
            "blocked_checks": blocked_count,
            "checks_needing_attention": action_needed_count,
        },
        "checks": checks,
        "limitations": [
            "Ready for owner review is not approval and does not mean the page is ready to publish.",
            "These checks confirm saved structure and supported facts; they do not grade writing quality.",
            "Passing these checks does not guarantee rankings, traffic, leads, or revenue.",
        ],
        "safety": {
            "owner_approval_recorded": False,
            "publishing_allowed": False,
            "automatic_publishing_allowed": False,
            "website_changed": False,
        },
    }


def _structured_data_recommendation(
    brief: ContentBrief,
    *,
    page_metadata: dict | None,
) -> dict:
    service = _clean_metadata_fact(brief.service_name)
    area = _clean_metadata_fact(brief.service_area_name)
    page_url = _clean_metadata_fact(
        brief.target_url or ((page_metadata or {}).get("url") if page_metadata else None)
    )
    current_types = list(
        dict.fromkeys(
            _clean_metadata_fact(item)
            for item in list((page_metadata or {}).get("structured_data_types") or [])
            if _clean_metadata_fact(item)
        )
    )
    current_type_keys = {item.casefold() for item in current_types}
    structured_data_valid = (
        (page_metadata or {}).get("structured_data_valid")
        if page_metadata is not None
        else None
    )
    if service is None:
        recommendation_state = "not_enough_information"
        recommended_type = None
    elif structured_data_valid is False:
        recommendation_state = "fix_saved_code"
        recommended_type = "Service"
    elif "service" in current_type_keys:
        recommendation_state = "matches"
        recommended_type = "Service"
    elif page_metadata is None:
        recommendation_state = "prepare"
        recommended_type = "Service"
    else:
        recommendation_state = "add"
        recommended_type = "Service"
    fields = [
        {
            "code": "service_name",
            "label": "Service name",
            "value": service,
            "state": "confirmed" if service else "missing",
            "required": True,
        },
        {
            "code": "service_area",
            "label": "Area served",
            "value": area,
            "state": "confirmed" if area else "optional_not_saved",
            "required": False,
        },
        {
            "code": "page_url",
            "label": "Final page address",
            "value": page_url,
            "state": "confirmed" if page_url else "missing",
            "required": True,
        },
        {
            "code": "business_identity",
            "label": "Public business identity",
            "value": None,
            "state": "owner_confirmation_required",
            "required": True,
        },
    ]
    source_label = (
        str((page_metadata or {}).get("source_label") or "").strip()
        if page_metadata
        else ""
    )
    observed_at = (page_metadata or {}).get("observed_at") if page_metadata else None
    return {
        "state": recommendation_state,
        "recommended_type": recommended_type,
        "recommended_type_label": "Service details" if recommended_type else None,
        "current_types": current_types,
        "current_state": (
            "not_saved"
            if page_metadata is None
            else (
                "invalid"
                if structured_data_valid is False
                else ("present" if current_types else "not_found")
            )
        ),
        "fields": fields,
        "reason": (
            "Describe the confirmed service on this page without adding unsupported business claims."
            if service
            else "Confirm the service before preparing structured page details."
        ),
        "evidence": [
            "Accepted content brief",
            *([f"Confirmed service: {service}"] if service else []),
            *([f"Confirmed service area: {area}"] if area else []),
            *([f"Current page evidence: {source_label}"] if source_label else []),
        ],
        "source_label": source_label or None,
        "observed_at": observed_at.isoformat() if observed_at is not None else None,
        "limitations": [
            "This recommends behind-the-scenes page details; it does not generate or publish website code.",
            "Structured details do not guarantee a special search result or higher rankings.",
            "Confirm the public business identity and final page address before creating a change preview.",
        ],
        "safety": {
            "owner_approval_required": True,
            "publishable_code_created": False,
            "automatic_publishing_allowed": False,
            "website_changed": False,
        },
    }


_INTERNAL_LINK_STOP_WORDS = frozenset(
    {
        "and",
        "business",
        "company",
        "emergency",
        "for",
        "from",
        "help",
        "home",
        "local",
        "near",
        "our",
        "page",
        "service",
        "services",
        "the",
        "this",
        "with",
        "your",
    }
)


def _internal_link_terms(value: str | None) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(token) >= 3 and token not in _INTERNAL_LINK_STOP_WORDS
    }


def _normalized_internal_link_url(value: str, *, base_url: str | None = None) -> str:
    raw = urljoin(str(base_url or ""), str(value or "").strip())
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _normalized_page_url(raw)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            path,
            parsed.params,
            parsed.query,
            "",
        )
    )


def _internal_link_recommendations(
    brief: ContentBrief,
    *,
    page_metadata: dict | None,
    page_inventory: list[dict],
) -> dict:
    target_url = _clean_metadata_fact(
        brief.target_url or ((page_metadata or {}).get("url") if page_metadata else None)
    )
    service = _clean_metadata_fact(brief.service_name)
    primary_search = _clean_metadata_fact(brief.primary_keyword)
    target_title = _clean_metadata_fact(
        (page_metadata or {}).get("title") if page_metadata else None
    ) or service or _clean_metadata_fact(brief.title)
    area_terms = _internal_link_terms(brief.service_area_name)
    accepted_terms = _internal_link_terms(
        " ".join(value for value in [service, primary_search] if value)
    ) - area_terms
    suggested_anchor = service or primary_search
    if target_url is None:
        state = "target_not_saved"
        items: list[dict] = []
        reason = "Save the final page address before planning links to this page."
    elif not accepted_terms or suggested_anchor is None:
        state = "not_enough_information"
        items = []
        reason = "Confirm the service or customer search before comparing related pages."
    else:
        normalized_target = _normalized_internal_link_url(target_url)
        candidates: list[dict] = []
        for page in page_inventory:
            source_url = _clean_metadata_fact(page.get("url"))
            source_title = _clean_metadata_fact(page.get("title"))
            if (
                source_url is None
                or source_title is None
                or _normalized_internal_link_url(source_url) == normalized_target
                or page.get("eligible_for_internal_links") is not True
            ):
                continue
            shared_terms = sorted(_internal_link_terms(source_title) & accepted_terms)
            if not shared_terms:
                continue
            outgoing_targets = {
                _normalized_internal_link_url(value, base_url=source_url)
                for value in list(page.get("outgoing_internal_links") or [])
                if _clean_metadata_fact(value)
            }
            already_links = normalized_target in outgoing_targets
            observed_at = page.get("observed_at")
            candidates.append(
                {
                    "state": "already_exists" if already_links else "recommended",
                    "source_title": source_title,
                    "source_url": source_url,
                    "target_title": target_title,
                    "target_url": target_url,
                    "suggested_anchor": suggested_anchor[:100],
                    "relationship_evidence": [
                        f"Saved source page: {source_title}",
                        f"Shared accepted wording: {', '.join(shared_terms)}",
                    ],
                    "source_label": _clean_metadata_fact(page.get("source_label")),
                    "observed_at": (
                        observed_at.isoformat()
                        if observed_at is not None and hasattr(observed_at, "isoformat")
                        else _clean_metadata_fact(observed_at)
                    ),
                    "existing_link_found": already_links,
                    "_shared_term_count": len(shared_terms),
                }
            )
        items = sorted(
            candidates,
            key=lambda item: (
                item["state"] == "already_exists",
                -item["_shared_term_count"],
                item["source_title"].casefold(),
                item["source_url"].casefold(),
            ),
        )[:5]
        for item in items:
            item.pop("_shared_term_count", None)
        if any(item["state"] == "recommended" for item in items):
            state = "recommendations_ready"
            reason = "These saved pages share exact accepted service wording and do not already show this link."
        elif items:
            state = "already_supported"
            reason = "The related saved pages already link to this target in the latest check."
        else:
            state = "no_related_pages"
            reason = "No other saved public page shared enough exact service wording for a safe link suggestion."
    return {
        "state": state,
        "target": {
            "title": target_title,
            "url": target_url,
        },
        "items": items,
        "reason": reason,
        "limitations": [
            "Only public pages with exact shared accepted wording are included.",
            "Review the sentence around a link so it is useful to a person reading the page.",
            "This does not insert links, create website code, or publish anything.",
            "Internal links do not guarantee higher rankings or more traffic.",
        ],
        "safety": {
            "owner_approval_required": True,
            "link_insertion_allowed": False,
            "automatic_publishing_allowed": False,
            "website_changed": False,
        },
    }


def _metadata_recommendations(
    brief: ContentBrief,
    *,
    page_metadata: dict | None,
) -> list[dict]:
    service = _clean_metadata_fact(brief.service_name or brief.primary_keyword)
    area = _clean_metadata_fact(brief.service_area_name)
    evidence = [
        "Accepted content brief",
        *([f"Confirmed service: {service}"] if service else []),
        *([f"Confirmed service area: {area}"] if area else []),
        *(
            [f"Customer search: {_clean_metadata_fact(brief.primary_keyword)}"]
            if _clean_metadata_fact(brief.primary_keyword)
            else []
        ),
    ]
    proposed_title = _proposed_metadata_title(service=service, area=area)
    proposed_description = _proposed_metadata_description(service=service, area=area)
    current_title = _clean_metadata_fact(
        (page_metadata or {}).get("title") if page_metadata else None
    )
    current_description = _clean_metadata_fact(
        (page_metadata or {}).get("description") if page_metadata else None
    )
    observed_at = (page_metadata or {}).get("observed_at") if page_metadata else None
    source_label = (
        str((page_metadata or {}).get("source_label") or "").strip()
        if page_metadata
        else ""
    )
    source_evidence = [f"Current value: {source_label}"] if source_label else []
    return [
        _metadata_recommendation_item(
            code="seo_title",
            label="Search result title",
            current_value=current_title,
            current_label=(
                str((page_metadata or {}).get("title_source") or "Saved page title")
                if page_metadata
                else "Current title not saved"
            ),
            proposed_value=proposed_title,
            review_after_characters=65,
            reason=(
                "Keep the confirmed service and service area clear so a customer can understand the page before opening it."
            ),
            evidence=[*evidence, *source_evidence],
            source_label=source_label or None,
            observed_at=observed_at,
        ),
        _metadata_recommendation_item(
            code="meta_description",
            label="Search description",
            current_value=current_description,
            current_label=(
                "Saved search description"
                if page_metadata
                else "Current description not saved"
            ),
            proposed_value=proposed_description,
            review_after_characters=160,
            reason=(
                "Describe the confirmed service and area without adding prices, guarantees, or other unsupported claims."
            ),
            evidence=[*evidence, *source_evidence],
            source_label=source_label or None,
            observed_at=observed_at,
        ),
    ]


def _metadata_recommendation_item(
    *,
    code: str,
    label: str,
    current_value: str | None,
    current_label: str,
    proposed_value: str | None,
    review_after_characters: int,
    reason: str,
    evidence: list[str],
    source_label: str | None,
    observed_at: datetime | None,
) -> dict:
    if proposed_value is None:
        recommendation_state = "not_enough_information"
    elif current_value is None:
        recommendation_state = "add"
    elif current_value.casefold() == proposed_value.casefold():
        recommendation_state = "matches"
    else:
        recommendation_state = "review"
    return {
        "code": code,
        "label": label,
        "state": recommendation_state,
        "current_value": current_value,
        "current_label": current_label,
        "proposed_value": proposed_value,
        "proposed_character_count": len(proposed_value) if proposed_value else None,
        "review_after_characters": review_after_characters,
        "reason": reason,
        "evidence": list(dict.fromkeys(item for item in evidence if item)),
        "source_label": source_label,
        "observed_at": observed_at.isoformat() if observed_at is not None else None,
        "limitations": [
            "The character check is a writing guide, not a Google ranking rule.",
            "Google may show different wording in a search result.",
            "Review this recommendation before using it. Nothing has changed on the website.",
        ],
        "safety": {
            "owner_approval_required": True,
            "automatic_publishing_allowed": False,
            "website_changed": False,
        },
    }


def _proposed_metadata_title(*, service: str | None, area: str | None) -> str | None:
    if not service:
        return None
    candidate = service
    if area and area.casefold() not in service.casefold():
        candidate = f"{service} in {area}"
    if len(candidate) <= 65:
        return _sentence_case(candidate)
    if len(service) <= 65:
        return _sentence_case(service)
    return None


def _proposed_metadata_description(
    *,
    service: str | None,
    area: str | None,
) -> str | None:
    if not service:
        return None
    scope = f" for customers in {area}" if area else ""
    candidate = (
        f"{_sentence_case(service)}{scope}. Review the service details, who it helps, "
        "and what to consider before choosing it."
    )
    if len(candidate) <= 160:
        return candidate
    shorter = f"{_sentence_case(service)}{scope}. Review the service details and who it helps."
    if len(shorter) <= 160:
        return shorter
    service_only = f"{_sentence_case(service)}. Review the service details and who it helps."
    return service_only if len(service_only) <= 160 else None


def _clean_metadata_fact(value: object) -> str | None:
    cleaned = " ".join(str(value or "").split()).strip()
    return cleaned or None


def _sentence_case(value: str) -> str:
    return f"{value[:1].upper()}{value[1:]}" if value else value


def _content_brief_hash(item: ContentBrief) -> str:
    payload = {
        "id": item.id,
        "title": item.title,
        "primary_keyword": item.primary_keyword,
        "recommended_page_action": item.recommended_page_action,
        "target_url": item.target_url,
        "competitor_domain": item.competitor_domain,
        "competitor_url": item.competitor_url,
        "evidence": item.evidence or {},
        "outline": item.outline or [],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _content_draft_safety() -> dict:
    return {
        "ai_generated": False,
        "automatic_publishing_allowed": False,
        "website_changed": False,
        "approval_to_publish_recorded": False,
    }


def _content_draft_storage_ready(db: Session) -> bool:
    return bool(inspect(db.get_bind()).has_table("content_drafts"))


def _brief_review_safety() -> dict:
    return {
        "brief_evidence_changed": False,
        "draft_generated": False,
        "publishing_enabled": False,
        "website_changed": False,
    }


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
