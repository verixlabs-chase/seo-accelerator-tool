import html as html_lib
import json
import re
import time
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain import entitlement_codes
from app.events import emit_event
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.crawl import (
    CrawlFrontierUrl,
    CrawlInternalLink,
    CrawlPageResult,
    CrawlRun,
    Page,
    TechnicalIssue,
)
from app.providers import get_crawl_adapter
from app.providers.crawl import CrawlFetchResult
from app.services import crawl_parser, observability_service
from app.services.entitlement_service import EntitlementNotFoundError, check_and_consume


def schedule_crawl(db: Session, tenant_id: str, campaign_id: str, crawl_type: str, seed_url: str) -> CrawlRun:
    settings = get_settings()
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if crawl_type not in {"deep", "delta"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid crawl_type")
    active_statuses = {"scheduled", "running"}
    tenant_active_limit = max(1, int(getattr(settings, "crawl_max_active_runs_per_tenant", 5)))
    campaign_active_limit = max(1, int(getattr(settings, "crawl_max_active_runs_per_campaign", 2)))
    active_for_tenant = (
        db.query(CrawlRun)
        .filter(CrawlRun.tenant_id == tenant_id, CrawlRun.status.in_(active_statuses))
        .count()
    )
    if active_for_tenant >= tenant_active_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active crawl run limit reached for tenant ({tenant_active_limit}).",
        )
    active_for_campaign = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign_id,
            CrawlRun.status.in_(active_statuses),
        )
        .count()
    )
    if active_for_campaign >= campaign_active_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active crawl run limit reached for campaign ({campaign_active_limit}).",
        )

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


def get_run_progress(db: Session, tenant_id: str, crawl_run_id: str) -> dict:
    run = get_run_or_404(db, crawl_run_id)
    if run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl run not found")
    rows = (
        db.query(CrawlFrontierUrl.status, func.count(CrawlFrontierUrl.id))
        .filter(CrawlFrontierUrl.crawl_run_id == crawl_run_id, CrawlFrontierUrl.tenant_id == tenant_id)
        .group_by(CrawlFrontierUrl.status)
        .all()
    )
    status_counts = {status_name: count for status_name, count in rows}
    total_frontier = sum(status_counts.values())
    return {
        "crawl_run_id": run.id,
        "campaign_id": run.campaign_id,
        "run_status": run.status,
        "pages_discovered": run.pages_discovered,
        "frontier_total": total_frontier,
        "frontier_counts": status_counts,
    }


def _ensure_page(db: Session, tenant_id: str, campaign_id: str, url: str) -> Page:
    page = (
        db.query(Page)
        .filter(Page.tenant_id == tenant_id, Page.campaign_id == campaign_id, Page.url == url)
        .first()
    )
    if page:
        return page
    page = Page(tenant_id=tenant_id, campaign_id=campaign_id, url=url)
    db.add(page)
    db.flush()
    return page


def _robots_txt_allows(robots_txt: str, path: str) -> bool:
    lines = [line.strip() for line in robots_txt.splitlines()]
    disallowed_prefixes: list[str] = []
    in_global_agent = False
    for line in lines:
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower.startswith("user-agent:"):
            agent = lower.split(":", 1)[1].strip()
            in_global_agent = agent in {"*", '"*"'}
            continue
        if in_global_agent and lower.startswith("disallow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                disallowed_prefixes.append(value)
    return not any(path.startswith(prefix) for prefix in disallowed_prefixes)


def _fetch_robots(client: httpx.Client, url: str, cache: dict[str, str]) -> str:
    parsed = urlparse(url)
    key = f"{parsed.scheme}://{parsed.netloc}"
    if key in cache:
        return cache[key]
    robots_url = f"{key}/robots.txt"
    try:
        response = client.get(robots_url, timeout=5.0)
        cache[key] = response.text if response.status_code == 200 else ""
    except httpx.HTTPError:
        cache[key] = ""
    return cache[key]


def _discover_sitemap_inventory(
    client: httpx.Client,
    seed_url: str,
    robots_txt: str,
    *,
    max_urls: int,
) -> tuple[list[str], bool]:
    origin = urlparse(seed_url)
    origin_host = origin.netloc.lower()
    declared = [
        line.split(":", 1)[1].strip()
        for line in robots_txt.splitlines()
        if line.lower().startswith("sitemap:") and line.split(":", 1)[1].strip()
    ]
    queue = deque(declared or [f"{origin.scheme}://{origin.netloc}/sitemap.xml"])
    seen_sitemaps: set[str] = set()
    inventory: list[str] = []
    inventory_seen: set[str] = set()
    loaded_urlset = False

    while queue and len(seen_sitemaps) < 10 and len(inventory) < max_urls:
        sitemap_url = _normalize_url(queue.popleft())
        if sitemap_url is None or sitemap_url in seen_sitemaps:
            continue
        if urlparse(sitemap_url).netloc.lower() != origin_host:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            response = client.get(sitemap_url, timeout=8.0)
        except httpx.HTTPError:
            continue
        if response.status_code != 200 or len(response.text) > 5_000_000:
            continue
        root_match = re.search(
            r"<(?:[\w.-]+:)?(sitemapindex|urlset)\b",
            response.text,
            re.IGNORECASE,
        )
        if root_match is None:
            continue
        root_name = root_match.group(1).lower()
        locations = [
            html_lib.unescape(value).strip()
            for value in re.findall(
                r"<(?:[\w.-]+:)?loc\b[^>]*>(.*?)</(?:[\w.-]+:)?loc>",
                response.text,
                re.IGNORECASE | re.DOTALL,
            )
            if value.strip()
        ]
        if root_name == "sitemapindex":
            queue.extend(locations)
            continue
        if root_name != "urlset":
            continue
        loaded_urlset = True
        for location in locations:
            normalized = _normalize_url(location)
            if (
                normalized is None
                or urlparse(normalized).netloc.lower() != origin_host
                or normalized in inventory_seen
            ):
                continue
            inventory_seen.add(normalized)
            inventory.append(normalized)
            if len(inventory) >= max_urls:
                break

    return inventory, loaded_urlset


def _fetch_url(url: str, use_playwright: bool, timeout_seconds: float) -> CrawlFetchResult:
    adapter = get_crawl_adapter()
    result = adapter.fetch_url(
        url=url,
        timeout_seconds=timeout_seconds,
        use_playwright=use_playwright,
    )
    if isinstance(result, CrawlFetchResult):
        return result
    # Keep older custom adapters compatible while they move to the evidence-rich contract.
    status_code, html = result
    return CrawlFetchResult(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        html=html,
        redirect_chain=[],
    )


def build_batch_urls(seed_url: str, crawl_type: str) -> list[str]:
    del crawl_type
    return [seed_url.rstrip("/")]


def _normalize_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
    )
    path = normalized.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((normalized.scheme, normalized.netloc, path, normalized.params, normalized.query, ""))


def enqueue_frontier_urls(
    db: Session,
    run: CrawlRun,
    urls: list[str],
    *,
    depth: int = 0,
    discovered_from_url: str | None = None,
) -> int:
    payload_rows: list[dict[str, object]] = []
    seen_normalized: set[str] = set()
    now = datetime.now(UTC)
    for raw_url in urls:
        normalized = _normalize_url(raw_url)
        if normalized is None or normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        payload_rows.append(
            {
                "tenant_id": run.tenant_id,
                "campaign_id": run.campaign_id,
                "crawl_run_id": run.id,
                "url": normalized,
                "normalized_url": normalized,
                "status": "pending",
                "depth": depth,
                "discovered_from_url": discovered_from_url,
                "updated_at": now,
            }
        )
    if not payload_rows:
        return 0
    stmt = pg_insert(CrawlFrontierUrl.__table__).values(payload_rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["crawl_run_id", "normalized_url"])
    result = db.execute(stmt)
    db.flush()
    return int(result.rowcount or 0)


def seed_frontier_for_run(db: Session, run: CrawlRun) -> int:
    existing = db.query(CrawlFrontierUrl).filter(CrawlFrontierUrl.crawl_run_id == run.id).count()
    if existing > 0:
        return 0
    initial_urls = build_batch_urls(run.seed_url, run.crawl_type)
    return enqueue_frontier_urls(db, run, initial_urls, depth=0)


def _dequeue_frontier_batch(db: Session, run: CrawlRun, batch_size: int) -> list[CrawlFrontierUrl]:
    rows = (
        db.query(CrawlFrontierUrl)
        .filter(CrawlFrontierUrl.crawl_run_id == run.id, CrawlFrontierUrl.status == "pending")
        .order_by(CrawlFrontierUrl.created_at.asc())
        .limit(batch_size)
        .all()
    )
    now = datetime.now(UTC)
    for row in rows:
        row.status = "processing"
        row.attempt_count += 1
        row.updated_at = now
    db.flush()
    return rows


def _mark_frontier_entry(db: Session, row: CrawlFrontierUrl, status_value: str, error: str | None = None) -> None:
    row.status = status_value
    row.last_error = error
    row.updated_at = datetime.now(UTC)
    db.flush()


def record_page_result(
    db: Session,
    run: CrawlRun,
    url: str,
    status_code: int | None,
    html: str,
    *,
    final_url: str | None = None,
    redirect_chain: list[dict[str, object]] | None = None,
) -> tuple[CrawlPageResult, dict]:
    page = _ensure_page(db, run.tenant_id, run.campaign_id, url)
    page.last_crawled_at = datetime.now(UTC)
    resolved_final_url = _normalize_url(final_url or url) or url
    signals = crawl_parser.parse_signals(resolved_final_url, html)
    signals["page_url"] = url
    resolved_redirect_chain = list(redirect_chain or [])
    signals["final_url"] = resolved_final_url
    signals["redirect_chain"] = resolved_redirect_chain
    result = CrawlPageResult(
        tenant_id=run.tenant_id,
        campaign_id=run.campaign_id,
        crawl_run_id=run.id,
        page_id=page.id,
        status_code=status_code,
        is_indexable=1 if signals["is_indexable"] else 0,
        title=signals["title"],
        meta_description=signals["meta_description"],
        heading_text=signals["heading_text"],
        body_text_excerpt=signals["body_text_excerpt"],
        final_url=resolved_final_url,
        redirect_chain=resolved_redirect_chain,
        redirect_count=len(resolved_redirect_chain),
        canonical_url=signals["canonical"],
        content_hash=signals["content_hash"],
        word_count=signals["word_count"],
        internal_link_count=signals["internal_links"],
        structured_data_types=signals["structured_data_types"],
        structured_data_valid=signals["structured_data_errors"] == 0,
    )
    db.add(result)
    db.flush()
    return result, signals


def record_internal_links(
    db: Session,
    run: CrawlRun,
    *,
    source_page_id: str,
    links: list[str],
) -> int:
    inserted = 0
    seen: set[str] = set()
    for target_url in links:
        normalized = _normalize_url(target_url)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        existing = (
            db.query(CrawlInternalLink)
            .filter(
                CrawlInternalLink.crawl_run_id == run.id,
                CrawlInternalLink.source_page_id == source_page_id,
                CrawlInternalLink.normalized_target_url == normalized,
            )
            .first()
        )
        if existing is not None:
            continue
        db.add(
            CrawlInternalLink(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                source_page_id=source_page_id,
                target_url=target_url,
                normalized_target_url=normalized,
            )
        )
        inserted += 1
    db.flush()
    return inserted


def extract_issues_for_result(db: Session, run: CrawlRun, result: CrawlPageResult, signals: dict | None = None) -> list[TechnicalIssue]:
    issues: list[TechnicalIssue] = []
    if signals is None:
        signals = {
            "title": result.title,
            "canonical": None,
            "meta_description": result.meta_description,
            "heading_text": result.heading_text,
            "body_text_excerpt": result.body_text_excerpt,
            "h1_count": 1 if result.heading_text else 0,
            "internal_links": 0,
            "is_indexable": bool(result.is_indexable),
        }
    taxonomy = crawl_parser.build_issue_taxonomy(result.status_code, signals)
    for item in taxonomy:
        issues.append(
            TechnicalIssue(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                page_id=result.page_id,
                issue_code=item["issue_code"],
                severity=item["severity"],
                details_json=json.dumps(item["details"]),
            )
        )
    for issue in issues:
        db.add(issue)
    db.flush()
    return issues


_RUN_DERIVED_ISSUES = {
    "broken_internal_link",
    "duplicate_content",
    "orphan_page",
    "canonical_target_missing",
}


def finalize_run_integrity(
    db: Session,
    run: CrawlRun,
    *,
    coverage_complete: bool,
) -> list[TechnicalIssue]:
    (
        db.query(TechnicalIssue)
        .filter(
            TechnicalIssue.crawl_run_id == run.id,
            TechnicalIssue.issue_code.in_(_RUN_DERIVED_ISSUES),
        )
        .delete(synchronize_session=False)
    )
    joined_rows = (
        db.query(CrawlPageResult, Page)
        .join(Page, Page.id == CrawlPageResult.page_id)
        .filter(CrawlPageResult.crawl_run_id == run.id)
        .all()
    )
    result_by_url: dict[str, tuple[CrawlPageResult, Page]] = {}
    for result, page in joined_rows:
        for candidate in (page.url, result.final_url):
            normalized = _normalize_url(candidate or "")
            if normalized is not None:
                result_by_url.setdefault(normalized, (result, page))
    result_by_page_id = {page.id: (result, page) for result, page in joined_rows}
    links = (
        db.query(CrawlInternalLink)
        .filter(CrawlInternalLink.crawl_run_id == run.id)
        .all()
    )
    sitemap_inventory_urls = {
        row.normalized_url
        for row in (
            db.query(CrawlFrontierUrl)
            .filter(
                CrawlFrontierUrl.crawl_run_id == run.id,
                CrawlFrontierUrl.discovered_from_url == "sitemap",
            )
            .all()
        )
    }
    issues: list[TechnicalIssue] = []
    incoming: dict[str, int] = {}
    for link in links:
        target = result_by_url.get(link.normalized_target_url)
        if target is None:
            continue
        target_result, target_page = target
        link.target_page_id = target_page.id
        incoming[target_page.id] = incoming.get(target_page.id, 0) + 1
        if target_result.status_code is None or target_result.status_code >= 400:
            source = result_by_page_id.get(link.source_page_id)
            source_url = source[1].url if source else None
            issues.append(
                _derived_issue(
                    run,
                    page_id=link.source_page_id,
                    code="broken_internal_link",
                    severity="high",
                    details={
                        "source_url": source_url,
                        "target_url": target_page.url,
                        "status_code": target_result.status_code,
                        "confidence": "confirmed",
                        "source": "InsightOS website scan",
                        "action": "Update or remove this link so it leads to a working page.",
                    },
                )
            )

    duplicate_groups: dict[str, list[tuple[CrawlPageResult, Page]]] = {}
    for result, page in joined_rows:
        if (
            result.status_code == 200
            and bool(result.is_indexable)
            and result.redirect_count == 0
            and result.content_hash
            and result.word_count >= 20
        ):
            duplicate_groups.setdefault(result.content_hash, []).append((result, page))
    for group in duplicate_groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: (len(item[1].url), item[1].url))
        preferred_url = ordered[0][1].url
        for _result, duplicate_page in ordered[1:]:
            issues.append(
                _derived_issue(
                    run,
                    page_id=duplicate_page.id,
                    code="duplicate_content",
                    severity="medium",
                    details={
                        "page_url": duplicate_page.url,
                        "duplicate_with": preferred_url,
                        "match_type": "exact_visible_text",
                        "confidence": "confirmed",
                        "source": "InsightOS website scan",
                        "action": (
                            "Keep one useful version, then merge, redirect, or clearly "
                            "differentiate the other page."
                        ),
                    },
                )
            )

    for result, page in joined_rows:
        canonical = _normalize_url(result.canonical_url or "")
        if not canonical or result.redirect_count > 0:
            continue
        if urlparse(canonical).netloc.lower() != urlparse(page.url).netloc.lower():
            continue
        canonical_target = result_by_url.get(canonical)
        if canonical_target is None:
            continue
        target_result, target_page = canonical_target
        if target_result.status_code is not None and target_result.status_code < 400:
            continue
        issues.append(
            _derived_issue(
                run,
                page_id=page.id,
                code="canonical_target_missing",
                severity="high",
                details={
                    "page_url": page.url,
                    "canonical_url": result.canonical_url,
                    "status_code": target_result.status_code,
                    "target_page_id": target_page.id,
                    "confidence": "confirmed",
                    "source": "InsightOS website scan",
                    "action": (
                        "Point the preferred page setting to a working page on this website."
                    ),
                },
            )
        )

    if coverage_complete:
        seed_url = _normalize_url(run.seed_url)
        for result, page in joined_rows:
            page_url = _normalize_url(page.url)
            if (
                page_url
                and page_url != seed_url
                and page_url in sitemap_inventory_urls
                and result.status_code == 200
                and result.redirect_count == 0
                and incoming.get(page.id, 0) == 0
            ):
                issues.append(
                    _derived_issue(
                        run,
                        page_id=page.id,
                        code="orphan_page",
                        severity="medium",
                        details={
                            "page_url": page.url,
                            "incoming_internal_links": 0,
                            "confidence": "strong",
                            "source": "Complete sitemap-backed InsightOS website scan",
                            "action": (
                                "Link to this page from a relevant website page, or remove it "
                                "from the site if it is no longer useful."
                            ),
                        },
                    )
                )
    for issue in issues:
        db.add(issue)
    db.flush()
    return issues


def _derived_issue(
    run: CrawlRun,
    *,
    page_id: str | None,
    code: str,
    severity: str,
    details: dict,
) -> TechnicalIssue:
    return TechnicalIssue(
        tenant_id=run.tenant_id,
        campaign_id=run.campaign_id,
        crawl_run_id=run.id,
        page_id=page_id,
        issue_code=code,
        severity=severity,
        details_json=json.dumps(details, sort_keys=True),
    )


def get_run_or_404(db: Session, crawl_run_id: str) -> CrawlRun:
    run = db.get(CrawlRun, crawl_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl run not found")
    return run


def get_planned_page_count(
    db: Session,
    crawl_run_id: str,
    provided_urls: list[str] | None = None,
) -> int:
    run = get_run_or_404(db, crawl_run_id)
    settings = get_settings()
    max_pages = max(1, int(getattr(settings, "crawl_max_pages_per_run", 200)))

    if provided_urls is not None:
        return min(max_pages, len(_normalize_urls_for_admission(provided_urls)))

    if run.started_at is not None:
        return 0

    return max_pages



def _normalize_urls_for_admission(urls: list[str]) -> list[str]:
    normalized_urls: list[str] = []
    seen: set[str] = set()
    for raw_url in urls:
        normalized = _normalize_url(raw_url)
        if normalized is None or normalized in seen:
            continue
        normalized_urls.append(normalized)
        seen.add(normalized)
    return normalized_urls



def execute_run(
    db: Session,
    crawl_run_id: str,
    provided_urls: list[str] | None = None,
    batch_size: int | None = None,
) -> dict:
    settings = get_settings()
    run = get_run_or_404(db, crawl_run_id)
    campaign = db.get(Campaign, run.campaign_id)
    if campaign is None or campaign.organization_id is None:
        raise EntitlementNotFoundError(
            f"Campaign missing organization_id for crawl entitlement enforcement: {run.campaign_id}"
        )
    organization = db.get(Organization, campaign.organization_id)
    if organization is None:
        raise ValueError(f"Organization not found for crawl run: {crawl_run_id}")
    if organization.status.strip().lower() != "active":
        return {
            "crawl_run_id": run.id,
            "status": "failed",
            "processed_urls": 0,
            "total_processed_urls": run.pages_discovered,
            "pending_urls": 0,
            "reason_code": "ORG_INACTIVE",
        }

    admitted_page_count = get_planned_page_count(db, crawl_run_id, provided_urls=provided_urls)

    if run.started_at is None and admitted_page_count > 0:
        allowed = check_and_consume(
            db,
            str(campaign.organization_id),
            entitlement_codes.LIMIT_CRAWL_PAGES_MONTHLY,
            amount=admitted_page_count,
        )
        if not allowed:
            return {
                "crawl_run_id": run.id,
                "status": "failed",
                "processed_urls": 0,
                "total_processed_urls": run.pages_discovered,
                "pending_urls": 0,
                "reason_code": "ENTITLEMENT_EXCEEDED",
            }

    run.status = "running"
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    db.flush()

    raw_urls = provided_urls or []
    max_pages = max(1, int(getattr(settings, "crawl_max_pages_per_run", 200)))
    max_links_per_page = max(1, int(getattr(settings, "crawl_max_discovered_links_per_page", 50)))
    configured_batch_size = batch_size if batch_size is not None else getattr(settings, "crawl_frontier_batch_size", 25)
    frontier_batch_size = max(1, int(configured_batch_size))
    should_expand_frontier = run.crawl_type == "deep" and provided_urls is None

    frontier: deque[tuple[str, int, CrawlFrontierUrl | None]] = deque()
    queued: set[str] = set()
    if provided_urls:
        for raw in raw_urls:
            normalized = _normalize_url(raw)
            if normalized is None or normalized in queued:
                continue
            frontier.append((normalized, 0, None))
            queued.add(normalized)

    domain_last_hit: dict[str, float] = {}
    robots_cache: dict[str, str] = {}
    min_interval = max(0.0, getattr(settings, "crawl_min_request_interval_seconds", 0.2))
    use_playwright = bool(getattr(settings, "crawl_use_playwright", False))
    timeout_seconds = float(getattr(settings, "crawl_timeout_seconds", 10.0))

    processed = 0
    seen: set[str] = set()
    sitemap_inventory_loaded = False
    with httpx.Client(follow_redirects=True) as client:
        if provided_urls is None:
            seed_frontier_for_run(db, run)
            seed_robots = _fetch_robots(client, run.seed_url, robots_cache)
            sitemap_inventory, sitemap_inventory_loaded = _discover_sitemap_inventory(
                client,
                run.seed_url,
                seed_robots,
                max_urls=max_pages + 1,
            )
            enqueue_frontier_urls(
                db,
                run,
                sitemap_inventory,
                depth=0,
                discovered_from_url="sitemap",
            )
            frontier_rows = _dequeue_frontier_batch(db, run, frontier_batch_size)
            for row in frontier_rows:
                if row.normalized_url in queued:
                    continue
                frontier.append((row.normalized_url, row.depth, row))
                queued.add(row.normalized_url)

        while (
            run.pages_discovered < max_pages
            and processed < frontier_batch_size
        ):
            if not frontier:
                if provided_urls is not None:
                    break
                remaining_batch = frontier_batch_size - processed
                refill_rows = _dequeue_frontier_batch(db, run, remaining_batch)
                if not refill_rows:
                    break
                for row in refill_rows:
                    if row.normalized_url in queued:
                        continue
                    frontier.append((row.normalized_url, row.depth, row))
                    queued.add(row.normalized_url)
                if not frontier:
                    break
            url, depth, frontier_row = frontier.popleft()
            if url in seen:
                if frontier_row is not None:
                    _mark_frontier_entry(db, frontier_row, "duplicate")
                continue
            seen.add(url)
            parsed = urlparse(url)
            robots = _fetch_robots(client, url, robots_cache)
            if robots and not _robots_txt_allows(robots, parsed.path or "/"):
                if frontier_row is not None:
                    _mark_frontier_entry(db, frontier_row, "blocked_robots")
                continue

            domain_key = parsed.netloc
            now = time.time()
            last_hit = domain_last_hit.get(domain_key)
            if last_hit is not None:
                sleep_for = min_interval - (now - last_hit)
                if sleep_for > 0:
                    time.sleep(sleep_for)

            fetch_result = _fetch_url(
                url,
                use_playwright=use_playwright,
                timeout_seconds=timeout_seconds,
            )
            domain_last_hit[domain_key] = time.time()

            result, signals = record_page_result(
                db,
                run,
                url,
                fetch_result.status_code,
                fetch_result.html,
                final_url=fetch_result.final_url,
                redirect_chain=fetch_result.redirect_chain,
            )
            extract_issues_for_result(db, run, result, signals)
            internal_links = (
                crawl_parser.extract_internal_links(
                    fetch_result.final_url or url,
                    fetch_result.html,
                    max_links=max_links_per_page,
                )
                if fetch_result.html
                else []
            )
            record_internal_links(
                db,
                run,
                source_page_id=result.page_id,
                links=internal_links,
            )
            processed += 1
            run.pages_discovered += 1
            if frontier_row is not None:
                _mark_frontier_entry(db, frontier_row, "complete")
            if should_expand_frontier and internal_links:
                remaining_budget = max(0, max_pages - run.pages_discovered)
                if remaining_budget > 0:
                    enqueue_frontier_urls(
                        db,
                        run,
                        internal_links[:remaining_budget],
                        depth=depth + 1,
                        discovered_from_url=url,
                    )
            canonical_target = _normalize_url(result.canonical_url or "")
            if (
                should_expand_frontier
                and canonical_target
                and urlparse(canonical_target).netloc.lower()
                == urlparse(url).netloc.lower()
                and canonical_target != _normalize_url(url)
                and run.pages_discovered < max_pages
            ):
                enqueue_frontier_urls(
                    db,
                    run,
                    [canonical_target],
                    depth=depth + 1,
                    discovered_from_url=f"canonical:{url}",
                )

    if provided_urls is None and frontier:
        remaining_status = "skipped_limit" if run.pages_discovered >= max_pages else "pending"
        for _, _, remaining_row in frontier:
            if remaining_row is None:
                continue
            _mark_frontier_entry(db, remaining_row, remaining_status)

    pending_count = (
        db.query(CrawlFrontierUrl)
        .filter(CrawlFrontierUrl.crawl_run_id == run.id, CrawlFrontierUrl.status == "pending")
        .count()
        if provided_urls is None
        else 0
    )
    if run.pages_discovered >= max_pages and provided_urls is None:
        (
            db.query(CrawlFrontierUrl)
            .filter(CrawlFrontierUrl.crawl_run_id == run.id, CrawlFrontierUrl.status == "pending")
            .update(
                {
                    CrawlFrontierUrl.status: "skipped_limit",
                    CrawlFrontierUrl.updated_at: datetime.now(UTC),
                },
                synchronize_session=False,
            )
        )
        pending_count = 0
    if provided_urls is not None or pending_count == 0:
        run.status = "complete"
        run.finished_at = datetime.now(UTC)
        skipped_count = (
            db.query(CrawlFrontierUrl)
            .filter(
                CrawlFrontierUrl.crawl_run_id == run.id,
                CrawlFrontierUrl.status == "skipped_limit",
            )
            .count()
            if provided_urls is None
            else 0
        )
        finalize_run_integrity(
            db,
            run,
            coverage_complete=(
                run.crawl_type == "deep"
                and provided_urls is None
                and skipped_count == 0
                and sitemap_inventory_loaded
            ),
        )
        observability_service.record_crawl_result(failed=False)
        emit_event(
            db,
            tenant_id=run.tenant_id,
            event_type="crawl.completed",
            payload={
                "campaign_id": run.campaign_id,
                "crawl_run_id": run.id,
                "processed_urls": processed,
            },
        )
    else:
        run.status = "running"
        run.finished_at = None
    db.commit()
    return {
        "crawl_run_id": run.id,
        "status": run.status,
        "processed_urls": processed,
        "total_processed_urls": run.pages_discovered,
        "pending_urls": pending_count,
    }


def mark_run_failed(db: Session, crawl_run_id: str, error_message: str) -> None:
    run = db.get(CrawlRun, crawl_run_id)
    if run is None:
        return
    run.status = "failed"
    run.finished_at = datetime.now(UTC)
    observability_service.record_crawl_result(failed=True)
    if error_message:
        db.add(
            TechnicalIssue(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                page_id=None,
                issue_code="crawl_run_failed",
                severity="high",
                details_json=json.dumps({"error": error_message}),
            )
        )
    db.commit()




