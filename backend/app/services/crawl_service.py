import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, Page, TechnicalIssue


def schedule_crawl(db: Session, tenant_id: str, campaign_id: str, crawl_type: str, seed_url: str) -> CrawlRun:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if crawl_type not in {"deep", "delta"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid crawl_type")

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


def _parse_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    return value or None


def _is_indexable(html: str) -> bool:
    return "noindex" not in html.lower()


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


def build_batch_urls(seed_url: str, crawl_type: str) -> list[str]:
    seed = seed_url.rstrip("/")
    if crawl_type == "delta":
        return [seed]
    return [seed, urljoin(f"{seed}/", "about"), urljoin(f"{seed}/", "contact")]


def record_page_result(
    db: Session,
    run: CrawlRun,
    url: str,
    status_code: int | None,
    html: str,
) -> CrawlPageResult:
    page = _ensure_page(db, run.tenant_id, run.campaign_id, url)
    page.last_crawled_at = datetime.now(UTC)
    result = CrawlPageResult(
        tenant_id=run.tenant_id,
        campaign_id=run.campaign_id,
        crawl_run_id=run.id,
        page_id=page.id,
        status_code=status_code,
        is_indexable=1 if _is_indexable(html) else 0,
        title=_parse_title(html),
    )
    db.add(result)
    db.flush()
    return result


def extract_issues_for_result(db: Session, run: CrawlRun, result: CrawlPageResult) -> list[TechnicalIssue]:
    issues: list[TechnicalIssue] = []
    if result.status_code is None or result.status_code >= 400:
        issues.append(
            TechnicalIssue(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                page_id=result.page_id,
                issue_code="http_error",
                severity="high",
                details_json=json.dumps({"status_code": result.status_code}),
            )
        )
    if not result.title:
        issues.append(
            TechnicalIssue(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                page_id=result.page_id,
                issue_code="missing_title",
                severity="medium",
                details_json="{}",
            )
        )
    if result.is_indexable == 0:
        issues.append(
            TechnicalIssue(
                tenant_id=run.tenant_id,
                campaign_id=run.campaign_id,
                crawl_run_id=run.id,
                page_id=result.page_id,
                issue_code="non_indexable",
                severity="high",
                details_json="{}",
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


def execute_run(db: Session, crawl_run_id: str, provided_urls: list[str] | None = None) -> dict:
    settings = get_settings()
    run = get_run_or_404(db, crawl_run_id)
    run.status = "running"
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    db.flush()

    urls = provided_urls or build_batch_urls(run.seed_url, run.crawl_type)
    domain_last_hit: dict[str, float] = {}
    robots_cache: dict[str, str] = {}
    min_interval = max(0.0, getattr(settings, "crawl_min_request_interval_seconds", 0.2))

    processed = 0
    with httpx.Client(follow_redirects=True) as client:
        for url in urls:
            parsed = urlparse(url)
            robots = _fetch_robots(client, url, robots_cache)
            if robots and not _robots_txt_allows(robots, parsed.path or "/"):
                continue

            domain_key = parsed.netloc
            now = time.time()
            last_hit = domain_last_hit.get(domain_key)
            if last_hit is not None:
                sleep_for = min_interval - (now - last_hit)
                if sleep_for > 0:
                    time.sleep(sleep_for)

            status_code: int | None = None
            html = ""
            try:
                response = client.get(url, timeout=10.0)
                status_code = response.status_code
                html = response.text if "text/html" in response.headers.get("content-type", "") else ""
            except httpx.HTTPError:
                status_code = None
                html = ""
            finally:
                domain_last_hit[domain_key] = time.time()

            result = record_page_result(db, run, url, status_code, html)
            extract_issues_for_result(db, run, result)
            processed += 1

    run.pages_discovered = processed
    run.status = "complete"
    run.finished_at = datetime.now(UTC)
    db.commit()
    return {"crawl_run_id": run.id, "status": run.status, "processed_urls": processed}


def mark_run_failed(db: Session, crawl_run_id: str, error_message: str) -> None:
    run = db.get(CrawlRun, crawl_run_id)
    if run is None:
        return
    run.status = "failed"
    run.finished_at = datetime.now(UTC)
    db.commit()
