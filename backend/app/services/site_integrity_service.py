from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.crawl import CrawlPageResult, CrawlRun, Page
from app.models.data_connection import DataConnection
from app.models.site_integrity import (
    SearchConsoleSitemapSnapshot,
    UrlInspectionSnapshot,
)
from app.providers.execution_types import ProviderExecutionRequest
from app.providers.google_search_console import SearchConsoleSiteIntegrityAdapter
from app.services import data_connections_service


MAX_URLS_PER_REFRESH = 25
DEFAULT_URLS_PER_REFRESH = 10
STALE_AFTER = timedelta(days=7)
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class SiteIntegrityError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def get_site_integrity(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    campaign = _campaign(db, tenant_id=tenant_id, campaign_id=campaign_id)
    connection = _connection(db, campaign=campaign)
    inspections = (
        db.query(UrlInspectionSnapshot)
        .filter(
            UrlInspectionSnapshot.tenant_id == tenant_id,
            UrlInspectionSnapshot.campaign_id == campaign_id,
        )
        .order_by(
            UrlInspectionSnapshot.inspected_at.desc(),
            UrlInspectionSnapshot.inspection_url.asc(),
        )
        .all()
    )
    sitemaps = (
        db.query(SearchConsoleSitemapSnapshot)
        .filter(
            SearchConsoleSitemapSnapshot.tenant_id == tenant_id,
            SearchConsoleSitemapSnapshot.campaign_id == campaign_id,
        )
        .order_by(SearchConsoleSitemapSnapshot.sitemap_url.asc())
        .all()
    )
    latest_crawl_results = _latest_crawl_results(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign_id,
    )
    findings = _build_findings(
        inspections=inspections,
        sitemaps=sitemaps,
        crawl_results=latest_crawl_results,
    )
    latest_observation = _latest_observation(inspections, sitemaps)
    is_stale = bool(
        latest_observation
        and resolved_now - _as_utc(latest_observation) > STALE_AFTER
    )

    indexed_urls = sum(1 for row in inspections if row.verdict == "PASS")
    attention_urls = sum(
        1
        for row in inspections
        if row.verdict in {"FAIL", "PARTIAL", "NEUTRAL", "VERDICT_UNSPECIFIED"}
    )
    canonical_conflicts = sum(
        1
        for row in inspections
        if row.google_canonical
        and row.user_canonical
        and _normalized_url(row.google_canonical) != _normalized_url(row.user_canonical)
    )
    sitemap_errors = sum(row.errors for row in sitemaps)
    sitemap_warnings = sum(row.warnings for row in sitemaps)
    if connection is None:
        status = "needs_connection"
        next_action = {
            "label": "Connect Google Search Console",
            "description": (
                "Connect this location in Settings so InsightOS can confirm whether "
                "Google has indexed its important pages."
            ),
            "href": "/settings",
        }
    elif not inspections and not sitemaps:
        status = "not_started"
        next_action = {
            "label": "Check important pages",
            "description": (
                "Run the first check to compare Google's saved page information with "
                "the latest website scan."
            ),
            "href": None,
        }
    elif is_stale:
        status = "stale"
        next_action = {
            "label": "Check again",
            "description": "The saved Google evidence is more than seven days old.",
            "href": None,
        }
    elif findings and findings[0]["severity"] == "high":
        status = "attention"
        next_action = {
            "label": "Review the first problem",
            "description": findings[0]["action"],
            "href": None,
        }
    else:
        status = "current"
        next_action = {
            "label": "Keep monitoring",
            "description": (
                "No urgent index problem was confirmed in the pages checked. Recheck "
                "after important website changes."
            ),
            "href": None,
        }

    return {
        "campaign_id": campaign.id,
        "status": status,
        "connection": {
            "connected": connection is not None,
            "site_url": connection.external_resource_id if connection else None,
            "last_error": connection.last_error_message if connection else None,
        },
        "summary": {
            "inspected_urls": len(inspections),
            "indexed_urls": indexed_urls,
            "attention_urls": attention_urls,
            "canonical_conflicts": canonical_conflicts,
            "sitemap_count": len(sitemaps),
            "sitemap_errors": sitemap_errors,
            "sitemap_warnings": sitemap_warnings,
        },
        "findings": findings[:10],
        "freshness": {
            "observed_at": latest_observation.isoformat() if latest_observation else None,
            "is_stale": is_stale,
            "stale_after_days": STALE_AFTER.days,
        },
        "next_action": next_action,
        "sources": [
            {
                "name": "Google Search Console URL inspection",
                "purpose": "Confirms Google's saved index information for each checked page.",
            },
            {
                "name": "Google Search Console sitemaps",
                "purpose": "Confirms sitemap processing errors, warnings, and submission totals.",
            },
            {
                "name": "InsightOS website scan",
                "purpose": "Checks the live website response and page setup.",
            },
        ],
        "coverage_note": (
            "This checks Google's saved index information, not a live indexing test. "
            "Sitemap submission totals are shown as submissions only; InsightOS does not "
            "treat Google's deprecated sitemap indexed field as proof of indexation."
        ),
    }


def refresh_site_integrity(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    max_urls: int = DEFAULT_URLS_PER_REFRESH,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    max_urls = max(1, min(int(max_urls), MAX_URLS_PER_REFRESH))
    campaign = _campaign(db, tenant_id=tenant_id, campaign_id=campaign_id)
    connection = _connection(db, campaign=campaign)
    if connection is None:
        raise SiteIntegrityError(
            "Connect Google Search Console for this location before checking index status.",
            reason_code="search_console_connection_required",
            status_code=409,
        )
    if connection.status in {
        data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        data_connections_service.CONNECTION_STATUS_PAUSED_CLOSURE,
    }:
        raise SiteIntegrityError(
            "This Search Console connection is paused. Reconnect it in Settings first.",
            reason_code="search_console_connection_paused",
            status_code=409,
        )
    if not campaign.organization_id:
        raise SiteIntegrityError(
            "This business must belong to an organization before Google pages can be checked.",
            reason_code="organization_required",
            status_code=409,
        )

    adapter = SearchConsoleSiteIntegrityAdapter(db=db)
    base_payload = {
        "organization_id": campaign.organization_id,
        "campaign_id": campaign.id,
        "site_url": connection.external_resource_id,
    }
    sitemap_result = adapter.execute(
        ProviderExecutionRequest(
            operation="sitemaps_list",
            payload=base_payload,
        )
    )
    if not sitemap_result.success:
        _record_connection_error(connection, sitemap_result.error, now=resolved_now)
        db.commit()
        raise _provider_error(sitemap_result.error, action="read this website's sitemaps")

    sitemap_rows = _payload_rows(sitemap_result.raw_payload)
    for row in sitemap_rows:
        _upsert_sitemap(
            db,
            campaign=campaign,
            connection=connection,
            row=row,
            observed_at=resolved_now,
        )

    pages = _priority_pages(
        db,
        tenant_id=tenant_id,
        campaign=campaign,
        limit=max_urls,
    )
    inspected = 0
    failures: list[dict[str, str]] = []
    for page_id, inspection_url in pages:
        result = adapter.execute(
            ProviderExecutionRequest(
                operation="url_inspection",
                payload={**base_payload, "inspection_url": inspection_url},
            )
        )
        if not result.success:
            failures.append(
                {
                    "url": inspection_url,
                    "reason_code": getattr(result.error, "reason_code", "provider_failed"),
                }
            )
            continue
        record = (result.raw_payload or {}).get("record")
        if not isinstance(record, dict):
            failures.append({"url": inspection_url, "reason_code": "response_invalid"})
            continue
        _upsert_inspection(
            db,
            campaign=campaign,
            connection=connection,
            page_id=page_id,
            row=record,
            inspected_at=resolved_now,
        )
        inspected += 1

    metadata = dict(connection.connection_metadata or {})
    metadata["site_integrity_last_refresh_at"] = resolved_now.isoformat()
    metadata["site_integrity_last_requested_urls"] = len(pages)
    metadata["site_integrity_last_inspected_urls"] = inspected
    metadata["site_integrity_last_failed_urls"] = len(failures)
    connection.connection_metadata = metadata
    connection.last_error_code = None if inspected or not pages else "site_integrity_refresh_failed"
    connection.last_error_message = None if inspected or not pages else "No page checks completed."
    connection.updated_at = resolved_now
    db.commit()

    return {
        "refresh": {
            "requested_urls": len(pages),
            "inspected_urls": inspected,
            "failed_urls": len(failures),
            "failures": failures,
            "sitemaps_read": len(sitemap_rows),
            "quota_guardrail": {
                "maximum_urls_per_request": MAX_URLS_PER_REFRESH,
                "requested_maximum": max_urls,
            },
        },
        "integrity": get_site_integrity(
            db,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            now=resolved_now,
        ),
    }


def _campaign(db: Session, *, tenant_id: str, campaign_id: str) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.tenant_id == tenant_id)
        .first()
    )
    if campaign is None:
        raise SiteIntegrityError(
            "Business website not found.",
            reason_code="campaign_not_found",
            status_code=404,
        )
    return campaign


def _connection(db: Session, *, campaign: Campaign) -> DataConnection | None:
    if not campaign.organization_id:
        return None
    return (
        db.query(DataConnection)
        .filter(
            DataConnection.tenant_id == campaign.tenant_id,
            DataConnection.organization_id == campaign.organization_id,
            DataConnection.campaign_id == campaign.id,
            DataConnection.provider_name
            == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
            DataConnection.status
            != data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        )
        .first()
    )


def _priority_pages(
    db: Session,
    *,
    tenant_id: str,
    campaign: Campaign,
    limit: int,
) -> list[tuple[str | None, str]]:
    latest_run = (
        db.query(CrawlRun)
        .filter(CrawlRun.tenant_id == tenant_id, CrawlRun.campaign_id == campaign.id)
        .order_by(CrawlRun.created_at.desc(), CrawlRun.id.desc())
        .first()
    )
    rows: list[tuple[str | None, str]] = []
    if latest_run is not None:
        results = (
            db.query(CrawlPageResult, Page)
            .join(Page, Page.id == CrawlPageResult.page_id)
            .filter(
                CrawlPageResult.tenant_id == tenant_id,
                CrawlPageResult.campaign_id == campaign.id,
                CrawlPageResult.crawl_run_id == latest_run.id,
            )
            .order_by(
                CrawlPageResult.is_indexable.desc(),
                CrawlPageResult.status_code.asc(),
                Page.url.asc(),
            )
            .all()
        )
        for result, page in results:
            if result.status_code and result.status_code >= 400:
                continue
            rows.append((page.id, page.url))
    fallback_url = _campaign_home_url(campaign.domain)
    if not rows:
        rows.append((None, fallback_url))
    else:
        rows.sort(key=lambda item: (0 if _normalized_url(item[1]) == fallback_url else 1, item[1]))

    deduped: list[tuple[str | None, str]] = []
    seen: set[str] = set()
    for page_id, url in rows:
        normalized = _normalized_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((page_id, url))
        if len(deduped) >= limit:
            break
    return deduped


def _latest_crawl_results(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
) -> dict[str, CrawlPageResult]:
    latest_run = (
        db.query(CrawlRun)
        .filter(CrawlRun.tenant_id == tenant_id, CrawlRun.campaign_id == campaign_id)
        .order_by(CrawlRun.created_at.desc(), CrawlRun.id.desc())
        .first()
    )
    if latest_run is None:
        return {}
    return {
        row.page_id: row
        for row in db.query(CrawlPageResult)
        .filter(
            CrawlPageResult.tenant_id == tenant_id,
            CrawlPageResult.campaign_id == campaign_id,
            CrawlPageResult.crawl_run_id == latest_run.id,
        )
        .all()
    }


def _build_findings(
    *,
    inspections: list[UrlInspectionSnapshot],
    sitemaps: list[SearchConsoleSitemapSnapshot],
    crawl_results: dict[str, CrawlPageResult],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        *,
        code: str,
        url: str,
        severity: str,
        title: str,
        evidence: str,
        action: str,
        source: str,
        observed_at: datetime,
        confidence: str = "confirmed",
    ) -> None:
        key = (code, _normalized_url(url))
        if key in seen:
            return
        seen.add(key)
        findings.append(
            {
                "code": code,
                "url": url,
                "severity": severity,
                "title": title,
                "evidence": evidence,
                "action": action,
                "source": source,
                "observed_at": observed_at.isoformat(),
                "confidence": confidence,
            }
        )

    for row in inspections:
        if row.verdict == "FAIL":
            if row.robots_txt_state == "DISALLOWED":
                add(
                    code="robots_blocked",
                    url=row.inspection_url,
                    severity="high",
                    title="The website is blocking Google from this page",
                    evidence=(
                        "Google reported that robots.txt does not allow this page to be crawled."
                    ),
                    action="Allow Google to crawl the page if it should appear in search.",
                    source="Google Search Console URL inspection",
                    observed_at=row.inspected_at,
                )
            elif row.indexing_state in {"BLOCKED_BY_META_TAG", "BLOCKED_BY_HTTP_HEADER"}:
                add(
                    code="noindex_blocked",
                    url=row.inspection_url,
                    severity="high",
                    title="This page tells Google not to index it",
                    evidence=(
                        f"Google reported {row.indexing_state.replace('_', ' ').lower()}."
                    ),
                    action=(
                        "Remove the noindex instruction if this page should appear in search."
                    ),
                    source="Google Search Console URL inspection",
                    observed_at=row.inspected_at,
                )
            elif row.page_fetch_state and row.page_fetch_state != "SUCCESSFUL":
                add(
                    code="google_fetch_failed",
                    url=row.inspection_url,
                    severity="high",
                    title="Google could not load this page successfully",
                    evidence=(
                        "Google's saved fetch result was "
                        f"{row.page_fetch_state.replace('_', ' ').lower()}."
                    ),
                    action=(
                        "Confirm the page loads without errors or access blocks, then check it again."
                    ),
                    source="Google Search Console URL inspection",
                    observed_at=row.inspected_at,
                )
            else:
                add(
                    code="not_indexed",
                    url=row.inspection_url,
                    severity="high",
                    title="Google is not showing this page in its index",
                    evidence=(
                        row.coverage_state or "Google reported that the page is not indexed."
                    ),
                    action=_index_action(row),
                    source="Google Search Console URL inspection",
                    observed_at=row.inspected_at,
                )
        elif row.verdict in {"PARTIAL", "NEUTRAL"}:
            add(
                code="index_status_unclear",
                url=row.inspection_url,
                severity="medium",
                title="Google needs a closer look at this page",
                evidence=row.coverage_state or "Google did not return a clear indexed result.",
                action=_index_action(row),
                source="Google Search Console URL inspection",
                observed_at=row.inspected_at,
            )
        if (
            row.google_canonical
            and row.user_canonical
            and _normalized_url(row.google_canonical) != _normalized_url(row.user_canonical)
        ):
            add(
                code="canonical_conflict",
                url=row.inspection_url,
                severity="medium",
                title="Google chose a different main version of this page",
                evidence=(
                    f"Your page points to {row.user_canonical}, but Google chose "
                    f"{row.google_canonical}."
                ),
                action="Check duplicate pages and internal links, then make the preferred page signal consistent.",
                source="Google Search Console URL inspection",
                observed_at=row.inspected_at,
            )
        crawl_result = crawl_results.get(row.page_id or "")
        if crawl_result and crawl_result.status_code and crawl_result.status_code >= 400:
            add(
                code="live_page_error",
                url=row.inspection_url,
                severity="high",
                title="The live page is returning an error",
                evidence=f"The latest website scan received HTTP {crawl_result.status_code}.",
                action="Restore or redirect this page, then run the website and Google checks again.",
                source="InsightOS website scan",
                observed_at=crawl_result.crawled_at,
            )
        elif crawl_result and not bool(crawl_result.is_indexable) and row.verdict == "PASS":
            add(
                code="crawl_index_conflict",
                url=row.inspection_url,
                severity="medium",
                title="The live page and Google's saved copy disagree",
                evidence="Google has the page indexed, but the latest website scan found an index block.",
                action="Confirm whether the page should stay visible, then remove the conflicting signal or request removal.",
                source="Google Search Console URL inspection + InsightOS website scan",
                observed_at=max(row.inspected_at, crawl_result.crawled_at),
            )

    for row in sitemaps:
        if row.errors > 0:
            add(
                code="sitemap_errors",
                url=row.sitemap_url,
                severity="high",
                title="Google found errors in this sitemap",
                evidence=f"Google reported {row.errors} sitemap error{'s' if row.errors != 1 else ''}.",
                action="Open the sitemap in Search Console, fix the listed errors, and submit it again.",
                source="Google Search Console sitemaps",
                observed_at=row.observed_at,
            )
        elif row.warnings > 0:
            add(
                code="sitemap_warnings",
                url=row.sitemap_url,
                severity="medium",
                title="This sitemap has warnings to review",
                evidence=f"Google reported {row.warnings} sitemap warning{'s' if row.warnings != 1 else ''}.",
                action="Review the warnings in Search Console and correct URLs that should be included.",
                source="Google Search Console sitemaps",
                observed_at=row.observed_at,
            )
        if row.is_pending:
            add(
                code="sitemap_pending",
                url=row.sitemap_url,
                severity="low",
                title="Google is still processing this sitemap",
                evidence="Google marked the sitemap as pending.",
                action="Wait for processing to finish, then check it again before making changes.",
                source="Google Search Console sitemaps",
                observed_at=row.observed_at,
            )

    findings.sort(
        key=lambda item: (
            _SEVERITY_ORDER.get(item["severity"], 9),
            item["title"],
            item["url"],
        )
    )
    return findings


def _index_action(row: UrlInspectionSnapshot) -> str:
    if row.robots_txt_state == "DISALLOWED":
        return "Allow Google to crawl the page if it should appear in search."
    if row.indexing_state in {"BLOCKED_BY_META_TAG", "BLOCKED_BY_HTTP_HEADER"}:
        return "Remove the noindex instruction if this page should appear in search."
    if row.page_fetch_state and row.page_fetch_state != "SUCCESSFUL":
        return "Fix the page loading problem, then check it again."
    return "Review Google's coverage reason, fix the page signal it names, then check the page again."


def _upsert_inspection(
    db: Session,
    *,
    campaign: Campaign,
    connection: DataConnection,
    page_id: str | None,
    row: dict[str, Any],
    inspected_at: datetime,
) -> UrlInspectionSnapshot:
    inspection_url = str(row.get("inspection_url") or "").strip()
    record = (
        db.query(UrlInspectionSnapshot)
        .filter(
            UrlInspectionSnapshot.campaign_id == campaign.id,
            UrlInspectionSnapshot.inspection_url == inspection_url,
        )
        .first()
    )
    if record is None:
        record = UrlInspectionSnapshot(
            tenant_id=campaign.tenant_id,
            organization_id=str(campaign.organization_id),
            campaign_id=campaign.id,
            connection_id=connection.id,
            site_url=connection.external_resource_id,
            inspection_url=inspection_url,
            created_at=inspected_at,
        )
        db.add(record)
    record.page_id = page_id
    record.verdict = str(row.get("verdict") or "VERDICT_UNSPECIFIED")
    record.coverage_state = _optional_text(row.get("coverage_state"))
    record.robots_txt_state = _optional_text(row.get("robots_txt_state"))
    record.indexing_state = _optional_text(row.get("indexing_state"))
    record.page_fetch_state = _optional_text(row.get("page_fetch_state"))
    record.google_canonical = _optional_text(row.get("google_canonical"))
    record.user_canonical = _optional_text(row.get("user_canonical"))
    record.crawled_as = _optional_text(row.get("crawled_as"))
    record.last_crawl_time = _parse_datetime(row.get("last_crawl_time"))
    record.sitemap_urls = _string_list(row.get("sitemap_urls"))
    record.referring_urls = _string_list(row.get("referring_urls"))
    record.inspected_at = inspected_at
    record.updated_at = inspected_at
    return record


def _upsert_sitemap(
    db: Session,
    *,
    campaign: Campaign,
    connection: DataConnection,
    row: dict[str, Any],
    observed_at: datetime,
) -> SearchConsoleSitemapSnapshot:
    sitemap_url = str(row.get("sitemap_url") or "").strip()
    record = (
        db.query(SearchConsoleSitemapSnapshot)
        .filter(
            SearchConsoleSitemapSnapshot.campaign_id == campaign.id,
            SearchConsoleSitemapSnapshot.sitemap_url == sitemap_url,
        )
        .first()
    )
    if record is None:
        record = SearchConsoleSitemapSnapshot(
            tenant_id=campaign.tenant_id,
            organization_id=str(campaign.organization_id),
            campaign_id=campaign.id,
            connection_id=connection.id,
            site_url=connection.external_resource_id,
            sitemap_url=sitemap_url,
            created_at=observed_at,
        )
        db.add(record)
    record.sitemap_type = _optional_text(row.get("sitemap_type"))
    record.is_pending = bool(row.get("is_pending"))
    record.is_sitemaps_index = bool(row.get("is_sitemaps_index"))
    record.warnings = _safe_int(row.get("warnings"))
    record.errors = _safe_int(row.get("errors"))
    record.submitted_url_count = _safe_int(row.get("submitted_url_count"))
    record.contents = row.get("contents") if isinstance(row.get("contents"), list) else []
    record.last_submitted_at = _parse_datetime(row.get("last_submitted_at"))
    record.last_downloaded_at = _parse_datetime(row.get("last_downloaded_at"))
    record.observed_at = observed_at
    record.updated_at = observed_at
    return record


def _record_connection_error(connection: DataConnection, error: Any, *, now: datetime) -> None:
    connection.last_error_code = getattr(error, "error_code", "site_integrity_refresh_failed")
    connection.last_error_message = str(error or "Google page checks could not be refreshed.")
    connection.updated_at = now


def _provider_error(error: Any, *, action: str) -> SiteIntegrityError:
    reason_code = getattr(error, "reason_code", "provider_failed")
    if reason_code == "auth_failed":
        message = "Google access needs to be reconnected in Settings before this check can run."
        status_code = 409
    elif reason_code in {"quota_exhausted", "rate_limited"}:
        message = "Google's check limit was reached. Wait a little while and try again."
        status_code = 429
    else:
        message = f"InsightOS could not {action} right now. Saved website results are still available."
        status_code = 502
    return SiteIntegrityError(message, reason_code=reason_code, status_code=status_code)


def _payload_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = (payload or {}).get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _latest_observation(
    inspections: list[UrlInspectionSnapshot],
    sitemaps: list[SearchConsoleSitemapSnapshot],
) -> datetime | None:
    values = [row.inspected_at for row in inspections] + [row.observed_at for row in sitemaps]
    return max(values) if values else None


def _campaign_home_url(domain: str) -> str:
    value = domain.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return _normalized_url(value)
    return _normalized_url(f"https://{value}")


def _normalized_url(url: str) -> str:
    value = url.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.rstrip("/").lower()
    if not parsed.scheme or not parsed.netloc:
        return value.rstrip("/").lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.query,
            "",
        )
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
