import json
import time
from collections import deque
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.campaign import Campaign
from app.models.crawl import CrawlFrontierUrl, CrawlPageResult, CrawlRun, Page, TechnicalIssue
from app.services import crawl_parser


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


def _fetch_url(url: str, client: httpx.Client, use_playwright: bool, timeout_seconds: float) -> tuple[int | None, str]:
    if use_playwright:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                response = page.goto(url, wait_until="networkidle", timeout=int(timeout_seconds * 1000))
                html = page.content()
                status_code = response.status if response is not None else None
                browser.close()
                return status_code, html
        except Exception:
            pass

    try:
        response = client.get(url, timeout=timeout_seconds)
        status_code = response.status_code
        html = response.text if "text/html" in response.headers.get("content-type", "") else ""
        return status_code, html
    except httpx.HTTPError:
        return None, ""


def build_batch_urls(seed_url: str, crawl_type: str) -> list[str]:
    seed = seed_url.rstrip("/")
    if crawl_type == "delta":
        return [seed]
    return [seed, urljoin(f"{seed}/", "about"), urljoin(f"{seed}/", "contact")]


def _normalize_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    normalized = parsed._replace(fragment="")
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
    created = 0
    for raw_url in urls:
        normalized = _normalize_url(raw_url)
        if normalized is None:
            continue
        try:
            with db.begin_nested():
                row = CrawlFrontierUrl(
                    tenant_id=run.tenant_id,
                    campaign_id=run.campaign_id,
                    crawl_run_id=run.id,
                    url=normalized,
                    normalized_url=normalized,
                    status="pending",
                    depth=depth,
                    discovered_from_url=discovered_from_url,
                    updated_at=datetime.now(UTC),
                )
                db.add(row)
                db.flush()
                created += 1
        except IntegrityError:
            continue
    return created


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
) -> tuple[CrawlPageResult, dict]:
    page = _ensure_page(db, run.tenant_id, run.campaign_id, url)
    page.last_crawled_at = datetime.now(UTC)
    signals = crawl_parser.parse_signals(url, html)
    result = CrawlPageResult(
        tenant_id=run.tenant_id,
        campaign_id=run.campaign_id,
        crawl_run_id=run.id,
        page_id=page.id,
        status_code=status_code,
        is_indexable=1 if signals["is_indexable"] else 0,
        title=signals["title"],
    )
    db.add(result)
    db.flush()
    return result, signals


def extract_issues_for_result(db: Session, run: CrawlRun, result: CrawlPageResult, signals: dict | None = None) -> list[TechnicalIssue]:
    issues: list[TechnicalIssue] = []
    if signals is None:
        signals = {
            "title": result.title,
            "canonical": None,
            "meta_description": None,
            "h1_count": 0,
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


def get_run_or_404(db: Session, crawl_run_id: str) -> CrawlRun:
    run = db.get(CrawlRun, crawl_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl run not found")
    return run


def execute_run(
    db: Session,
    crawl_run_id: str,
    provided_urls: list[str] | None = None,
    batch_size: int | None = None,
) -> dict:
    settings = get_settings()
    run = get_run_or_404(db, crawl_run_id)
    run.status = "running"
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    db.flush()

    raw_urls = provided_urls or []
    max_pages = max(1, int(getattr(settings, "crawl_max_pages_per_run", 200)))
    max_links_per_page = max(1, int(getattr(settings, "crawl_max_discovered_links_per_page", 50)))
    frontier_batch_size = max(1, int(batch_size or getattr(settings, "crawl_frontier_batch_size", 25)))
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
    else:
        seed_frontier_for_run(db, run)
        frontier_rows = _dequeue_frontier_batch(db, run, frontier_batch_size)
        for row in frontier_rows:
            if row.normalized_url in queued:
                continue
            frontier.append((row.normalized_url, row.depth, row))
            queued.add(row.normalized_url)

    domain_last_hit: dict[str, float] = {}
    robots_cache: dict[str, str] = {}
    min_interval = max(0.0, getattr(settings, "crawl_min_request_interval_seconds", 0.2))
    use_playwright = bool(getattr(settings, "crawl_use_playwright", False))
    timeout_seconds = float(getattr(settings, "crawl_timeout_seconds", 10.0))

    processed = 0
    seen: set[str] = set()
    with httpx.Client(follow_redirects=True) as client:
        while frontier and run.pages_discovered < max_pages:
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

            status_code, html = _fetch_url(url, client=client, use_playwright=use_playwright, timeout_seconds=timeout_seconds)
            domain_last_hit[domain_key] = time.time()

            result, signals = record_page_result(db, run, url, status_code, html)
            extract_issues_for_result(db, run, result, signals)
            processed += 1
            run.pages_discovered += 1
            if frontier_row is not None:
                _mark_frontier_entry(db, frontier_row, "complete")
            if should_expand_frontier and html:
                links = crawl_parser.extract_internal_links(url, html, max_links=max_links_per_page)
                remaining_budget = max(0, max_pages - run.pages_discovered)
                if remaining_budget > 0:
                    enqueue_frontier_urls(
                        db,
                        run,
                        links[:remaining_budget],
                        depth=depth + 1,
                        discovered_from_url=url,
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
