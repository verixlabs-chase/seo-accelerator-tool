from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.events import emit_event
from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.campaign import Campaign
from app.models.crawl import CrawlRun, TechnicalIssue
from app.models.data_connection import DataConnection
from app.models.onboarding_baseline import OnboardingBaseline
from app.models.rank import CampaignKeyword, RankingSnapshot
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.website_performance import WebsitePerformanceMeasurement
from app.models.website_analytics import (
    AnalyticsLandingPageDailyMetric,
    AnalyticsTrafficSourceDailyMetric,
    WebsiteFormEvent,
)
from app.services import (
    data_connections_service,
    onboarding_baseline_ai_service,
    premium_report_service,
    reporting_service,
)


ANALYSIS_VERSION = "cx1.1-baseline-v1"
EVIDENCE_WINDOW_DAYS = 28
logger = logging.getLogger(__name__)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


def _campaign(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    lock: bool = False,
) -> Campaign:
    query = db.query(Campaign).filter(
        Campaign.id == campaign_id,
        Campaign.tenant_id == tenant_id,
        Campaign.organization_id == organization_id,
    )
    if lock:
        query = query.populate_existing().with_for_update()
    row = query.one_or_none()
    if row is None or not row.business_location_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )
    return row


def _existing(
    db: Session, *, tenant_id: str, organization_id: str, campaign_id: str
) -> OnboardingBaseline | None:
    return (
        db.query(OnboardingBaseline)
        .filter(
            OnboardingBaseline.tenant_id == tenant_id,
            OnboardingBaseline.organization_id == organization_id,
            OnboardingBaseline.campaign_id == campaign_id,
            OnboardingBaseline.baseline_number == 1,
        )
        .one_or_none()
    )


def _latest_crawl(db: Session, *, tenant_id: str, campaign_id: str) -> CrawlRun | None:
    return (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign_id,
        )
        .order_by(CrawlRun.created_at.desc(), CrawlRun.id.desc())
        .first()
    )


def _source(
    key: str,
    label: str,
    state: str,
    detail: str,
    *,
    observed: int = 0,
    optional: bool = True,
    last_updated: date | datetime | None = None,
) -> dict[str, Any]:
    if isinstance(last_updated, (date, datetime)):
        last_updated_value = last_updated.isoformat()
    else:
        last_updated_value = None
    return {
        "key": key,
        "label": label,
        "state": state,
        "detail": detail,
        "observed": max(int(observed), 0),
        "optional": optional,
        "last_updated": last_updated_value,
    }


def _readiness(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign: Campaign,
    checked_at: datetime,
) -> dict[str, Any]:
    window_start_date = checked_at.date() - timedelta(days=EVIDENCE_WINDOW_DAYS - 1)
    window_start_at = datetime.combine(window_start_date, datetime.min.time(), tzinfo=UTC)
    latest_crawl = _latest_crawl(
        db, tenant_id=tenant_id, campaign_id=campaign.id
    )
    completed_crawl = (
        latest_crawl
        if latest_crawl is not None and latest_crawl.status == "completed"
        else None
    )
    if completed_crawl is not None:
        crawl_state = "measured"
        crawl_detail = "The first completed website scan is ready to freeze."
    elif latest_crawl is not None and latest_crawl.status in {
        "scheduled",
        "queued",
        "running",
        "in_progress",
    }:
        crawl_state = "collecting"
        crawl_detail = "The first website scan is still collecting results."
    elif latest_crawl is not None:
        crawl_state = "blocked"
        crawl_detail = "The first website scan needs to be retried before the baseline can be frozen."
    else:
        crawl_state = "needs_setup"
        crawl_detail = "Start a website scan before creating the baseline."

    search_days, search_latest = (
        db.query(
            func.count(SearchConsoleDailyMetric.id),
            func.max(SearchConsoleDailyMetric.metric_date),
        )
        .filter(
            SearchConsoleDailyMetric.organization_id == organization_id,
            SearchConsoleDailyMetric.campaign_id == campaign.id,
            SearchConsoleDailyMetric.metric_date >= window_start_date,
            SearchConsoleDailyMetric.metric_date <= checked_at.date(),
        )
        .one()
    )
    search_connection = (
        db.query(DataConnection)
        .filter(
            DataConnection.tenant_id == tenant_id,
            DataConnection.organization_id == organization_id,
            DataConnection.campaign_id == campaign.id,
            DataConnection.business_location_id == campaign.business_location_id,
            DataConnection.provider_name
            == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
        )
        .one_or_none()
    )
    search_connection_status = (
        data_connections_service.effective_connection_status(
            search_connection,
            now=checked_at,
        )
        if search_connection is not None
        else "not_connected"
    )
    search_sync_complete = bool(
        search_connection is not None and search_connection.last_success_at is not None
    )
    if search_connection is None:
        search_state = "needs_connection"
        search_detail = (
            "Connect this website's Google Search data before the official baseline is created."
        )
    elif search_connection_status in {
        data_connections_service.CONNECTION_STATUS_FAILED,
        data_connections_service.CONNECTION_STATUS_RECONNECT_REQUIRED,
        data_connections_service.CONNECTION_STATUS_DISCONNECTED,
        data_connections_service.CONNECTION_STATUS_PAUSED_CLOSURE,
    }:
        search_state = "blocked"
        search_detail = (
            "The saved Google Search connection needs attention before the official baseline can be created."
        )
    elif not search_sync_complete or search_connection_status in {
        data_connections_service.CONNECTION_STATUS_CONNECTED,
        data_connections_service.CONNECTION_STATUS_SYNCING,
    }:
        search_state = "collecting"
        search_detail = (
            "Google Search is connected. InsightOS is waiting for the first saved search update."
        )
    else:
        search_state = "measured"
        search_detail = (
            "Saved clicks, appearances, CTR, and average Google position are included."
            if search_days
            else "Google Search is connected and synchronized, but it returned no dated records for this baseline window."
        )
    analytics_days, analytics_latest = (
        db.query(
            func.count(AnalyticsDailyMetric.id),
            func.max(AnalyticsDailyMetric.metric_date),
        )
        .filter(
            AnalyticsDailyMetric.organization_id == organization_id,
            AnalyticsDailyMetric.campaign_id == campaign.id,
            AnalyticsDailyMetric.metric_date >= window_start_date,
            AnalyticsDailyMetric.metric_date <= checked_at.date(),
        )
        .one()
    )
    tracked_keywords = int(
        db.query(func.count(CampaignKeyword.id))
        .filter(
            CampaignKeyword.tenant_id == tenant_id,
            CampaignKeyword.campaign_id == campaign.id,
        )
        .scalar()
        or 0
    )
    rank_count, rank_latest = (
        db.query(func.count(RankingSnapshot.id), func.max(RankingSnapshot.captured_at))
        .filter(
            RankingSnapshot.tenant_id == tenant_id,
            RankingSnapshot.campaign_id == campaign.id,
            RankingSnapshot.source_type != "imported",
            RankingSnapshot.captured_at >= window_start_at,
            RankingSnapshot.captured_at <= checked_at,
        )
        .one()
    )
    performance_count, performance_latest = (
        db.query(
            func.count(WebsitePerformanceMeasurement.id),
            func.max(WebsitePerformanceMeasurement.captured_at),
        )
        .filter(
            WebsitePerformanceMeasurement.tenant_id == tenant_id,
            WebsitePerformanceMeasurement.organization_id == organization_id,
            WebsitePerformanceMeasurement.campaign_id == campaign.id,
            WebsitePerformanceMeasurement.status.in_(("ready", "insufficient_data")),
            WebsitePerformanceMeasurement.captured_at >= window_start_at,
            WebsitePerformanceMeasurement.captured_at <= checked_at,
        )
        .one()
    )

    sources = [
        _source(
            "website_crawl",
            "Website scan",
            crawl_state,
            crawl_detail,
            observed=1 if completed_crawl else 0,
            optional=False,
            last_updated=completed_crawl.finished_at if completed_crawl else None,
        ),
        _source(
            "website_performance",
            "Website performance",
            "measured" if performance_count else "not_measured",
            "Saved Core Web Vitals and lab measurements are included."
            if performance_count
            else "Website performance has not been measured yet; it is not scored as zero.",
            observed=int(performance_count or 0),
            last_updated=performance_latest,
        ),
        _source(
            "search_console",
            "Google Search data",
            "not_enough_history"
            if search_state == "measured" and not search_days
            else search_state,
            search_detail,
            observed=int(search_days or 0),
            optional=False,
            last_updated=search_latest,
        ),
        _source(
            "analytics",
            "Website traffic and engagement",
            "measured" if analytics_days else "not_connected",
            "Saved sessions, engaged sessions, and conversions are included."
            if analytics_days
            else "Website analytics is not connected yet; traffic is not scored as zero.",
            observed=int(analytics_days or 0),
            last_updated=analytics_latest,
        ),
        _source(
            "rank_tracking",
            "Tracked search positions",
            "measured"
            if rank_count
            else "collecting"
            if tracked_keywords
            else "not_configured",
            f"Saved positions are available for {tracked_keywords} tracked search{'es' if tracked_keywords != 1 else ''}."
            if rank_count
            else "The first tracked search is waiting for a saved position."
            if tracked_keywords
            else "No tracked searches have been selected yet.",
            observed=int(rank_count or 0),
            last_updated=rank_latest,
        ),
    ]
    state = "ready_to_generate"
    if search_state == "needs_connection":
        state = "needs_search_connection"
    elif search_state == "blocked" or crawl_state in {"blocked", "needs_setup"}:
        state = "blocked"
    elif search_state == "collecting" or crawl_state == "collecting":
        state = "collecting"
    return {
        "state": state,
        "completion_required": True,
        "basic_access_blocked": False,
        "checked_at": checked_at.isoformat(),
        "message": (
            "The official website and organic-search baseline can now be frozen."
            if state == "ready_to_generate"
            else search_detail
            if search_state != "measured"
            else crawl_detail
        ),
        "sources": sources,
        "actions": (
            [
                {
                    "code": "connect_google_search",
                    "label": "Connect Google Search data",
                    "href": (
                        "/settings?setup=connections&campaign_id="
                        f"{campaign.id}#website-mappings"
                    ),
                }
            ]
            if state == "needs_search_connection"
            else [
                {
                    "code": "repair_google_search",
                    "label": "Check Google Search connection",
                    "href": (
                        "/settings?setup=connections&campaign_id="
                        f"{campaign.id}#website-mappings"
                    ),
                }
            ]
            if search_state == "blocked"
            else [
                {
                    "code": "retry_website_scan",
                    "label": "Retry website scan",
                    "href": "/site-health",
                }
            ]
            if state == "blocked"
            else []
        ),
    }


def _window_rows(rows: list[Any], start: date, end: date) -> list[Any]:
    return [row for row in rows if start <= row.metric_date <= end]


def _score_metric(value: float | None, good: float, poor: float) -> float | None:
    if value is None:
        return None
    if value <= good:
        return 100.0
    if value >= poor:
        return 0.0
    return round(100.0 * (poor - value) / (poor - good), 1)


def _build_evidence(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign: Campaign,
    cutoff_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    window_end = cutoff_at.date()
    window_start = window_end - timedelta(days=EVIDENCE_WINDOW_DAYS - 1)
    latest_crawl = (
        db.query(CrawlRun)
        .filter(
            CrawlRun.tenant_id == tenant_id,
            CrawlRun.campaign_id == campaign.id,
            CrawlRun.status == "completed",
            CrawlRun.finished_at.isnot(None),
            CrawlRun.finished_at <= cutoff_at,
        )
        .order_by(CrawlRun.finished_at.desc(), CrawlRun.id.desc())
        .first()
    )
    if latest_crawl is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "The first website scan is not complete yet.",
                "reason_code": "baseline_website_scan_not_ready",
            },
        )
    issues = (
        db.query(TechnicalIssue)
        .filter(
            TechnicalIssue.tenant_id == tenant_id,
            TechnicalIssue.campaign_id == campaign.id,
            TechnicalIssue.crawl_run_id == latest_crawl.id,
        )
        .order_by(TechnicalIssue.detected_at.asc(), TechnicalIssue.id.asc())
        .all()
    )
    severity_counts = Counter(str(item.severity or "medium").lower() for item in issues)
    issue_codes = Counter(str(item.issue_code or "website_issue") for item in issues)
    issue_groups = [
        {
            "issue_code": code,
            "label": code.replace("_", " ").replace("-", " ").title(),
            "count": count,
            "severity": max(
                (
                    str(item.severity or "medium").lower()
                    for item in issues
                    if item.issue_code == code
                ),
                key=lambda value: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(value, 2),
            ),
        }
        for code, count in issue_codes.most_common(25)
    ]

    search_rows = (
        db.query(SearchConsoleDailyMetric)
        .filter(
            SearchConsoleDailyMetric.organization_id == organization_id,
            SearchConsoleDailyMetric.campaign_id == campaign.id,
            SearchConsoleDailyMetric.metric_date >= window_start,
            SearchConsoleDailyMetric.metric_date <= window_end,
        )
        .order_by(SearchConsoleDailyMetric.metric_date.asc())
        .all()
    )
    analytics_rows = (
        db.query(AnalyticsDailyMetric)
        .filter(
            AnalyticsDailyMetric.organization_id == organization_id,
            AnalyticsDailyMetric.campaign_id == campaign.id,
            AnalyticsDailyMetric.metric_date >= window_start,
            AnalyticsDailyMetric.metric_date <= window_end,
        )
        .order_by(AnalyticsDailyMetric.metric_date.asc())
        .all()
    )
    landing_rows = (
        db.query(AnalyticsLandingPageDailyMetric)
        .filter(
            AnalyticsLandingPageDailyMetric.tenant_id == tenant_id,
            AnalyticsLandingPageDailyMetric.organization_id == organization_id,
            AnalyticsLandingPageDailyMetric.campaign_id == campaign.id,
            AnalyticsLandingPageDailyMetric.metric_date >= window_start,
            AnalyticsLandingPageDailyMetric.metric_date <= window_end,
        )
        .all()
    )
    source_rows = (
        db.query(AnalyticsTrafficSourceDailyMetric)
        .filter(
            AnalyticsTrafficSourceDailyMetric.tenant_id == tenant_id,
            AnalyticsTrafficSourceDailyMetric.organization_id == organization_id,
            AnalyticsTrafficSourceDailyMetric.campaign_id == campaign.id,
            AnalyticsTrafficSourceDailyMetric.metric_date >= window_start,
            AnalyticsTrafficSourceDailyMetric.metric_date <= window_end,
        )
        .all()
    )
    window_start_at = datetime.combine(window_start, datetime.min.time(), tzinfo=UTC)
    window_end_at = datetime.combine(
        window_end + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )
    form_events = (
        db.query(WebsiteFormEvent)
        .filter(
            WebsiteFormEvent.tenant_id == tenant_id,
            WebsiteFormEvent.organization_id == organization_id,
            WebsiteFormEvent.campaign_id == campaign.id,
            WebsiteFormEvent.occurred_at >= window_start_at,
            WebsiteFormEvent.occurred_at < window_end_at,
        )
        .all()
    )
    rank_rows = (
        db.query(RankingSnapshot)
        .filter(
            RankingSnapshot.tenant_id == tenant_id,
            RankingSnapshot.campaign_id == campaign.id,
            RankingSnapshot.source_type != "imported",
            RankingSnapshot.captured_at >= window_start_at,
            RankingSnapshot.captured_at <= cutoff_at,
        )
        .order_by(RankingSnapshot.captured_at.asc(), RankingSnapshot.id.asc())
        .all()
    )
    latest_rank_by_keyword: dict[str, RankingSnapshot] = {}
    for row in rank_rows:
        latest_rank_by_keyword[row.keyword_id] = row
    rank_positions = [row.position for row in latest_rank_by_keyword.values()]

    performance_rows = (
        db.query(WebsitePerformanceMeasurement)
        .filter(
            WebsitePerformanceMeasurement.tenant_id == tenant_id,
            WebsitePerformanceMeasurement.organization_id == organization_id,
            WebsitePerformanceMeasurement.campaign_id == campaign.id,
            WebsitePerformanceMeasurement.status.in_(("ready", "insufficient_data")),
            WebsitePerformanceMeasurement.captured_at >= window_start_at,
            WebsitePerformanceMeasurement.captured_at <= cutoff_at,
        )
        .order_by(WebsitePerformanceMeasurement.captured_at.asc(), WebsitePerformanceMeasurement.id.asc())
        .all()
    )
    latest_performance: dict[tuple[str, str], WebsitePerformanceMeasurement] = {}
    for row in performance_rows:
        latest_performance[(row.form_factor, row.source)] = row
    performance = [
        {
            "form_factor": row.form_factor,
            "source": row.source,
            "status": row.status,
            "lcp_ms": row.lcp_ms,
            "inp_ms": row.inp_ms,
            "cls": row.cls_value,
            "ttfb_ms": row.ttfb_ms,
            "fcp_ms": row.fcp_ms,
            "tbt_ms": row.tbt_ms,
            "performance_score": row.performance_score,
            "captured_at": row.captured_at.isoformat(),
        }
        for row in latest_performance.values()
    ]

    impressions = sum(row.impressions for row in search_rows)
    clicks = sum(row.clicks for row in search_rows)
    weighted_position = (
        round(
            sum((row.avg_position or 0) * row.impressions for row in search_rows)
            / impressions,
            2,
        )
        if impressions
        else None
    )
    sessions = sum(row.sessions for row in analytics_rows)
    engaged_sessions = sum(row.engaged_sessions for row in analytics_rows)
    conversions = sum(row.conversions for row in analytics_rows)
    landing_totals: dict[str, dict[str, int]] = {}
    for row in landing_rows:
        total = landing_totals.setdefault(
            row.landing_page,
            {"sessions": 0, "engaged_sessions": 0, "key_events": 0},
        )
        total["sessions"] += int(row.sessions or 0)
        total["engaged_sessions"] += int(row.engaged_sessions or 0)
        total["key_events"] += int(row.key_events or 0)
    source_totals: dict[str, dict[str, int]] = {}
    for row in source_rows:
        total = source_totals.setdefault(
            row.source_medium,
            {"sessions": 0, "engaged_sessions": 0, "key_events": 0},
        )
        total["sessions"] += int(row.sessions or 0)
        total["engaged_sessions"] += int(row.engaged_sessions or 0)
        total["key_events"] += int(row.key_events or 0)
    form_event_counts = Counter(str(row.event_name) for row in form_events)

    evidence = {
        "window": {
            "days": EVIDENCE_WINDOW_DAYS,
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "cutoff_at": cutoff_at.isoformat(),
        },
        "website": {
            "crawl_run_id": latest_crawl.id,
            "finished_at": latest_crawl.finished_at.isoformat(),
            "pages_discovered": int(latest_crawl.pages_discovered or 0),
            "issue_count": len(issues),
            "severity_counts": dict(sorted(severity_counts.items())),
            "issue_groups": issue_groups,
            "performance": performance,
        },
        "organic_search": {
            "observed_days": len(search_rows),
            "clicks": clicks if search_rows else None,
            "impressions": impressions if search_rows else None,
            "ctr": round(clicks / impressions, 4) if impressions else None,
            "average_position": weighted_position,
        },
        "traffic": {
            "observed_days": len(analytics_rows),
            "sessions": sessions if analytics_rows else None,
            "engaged_sessions": engaged_sessions if analytics_rows else None,
            "engagement_rate": round(engaged_sessions / sessions, 4) if sessions else None,
            "conversions": conversions if analytics_rows else None,
            "conversion_rate": round(conversions / sessions, 4) if sessions else None,
            "top_landing_pages": [
                {"landing_page": key, **values}
                for key, values in sorted(
                    landing_totals.items(),
                    key=lambda item: (-item[1]["sessions"], item[0]),
                )[:10]
            ],
            "top_sources": [
                {"source_medium": key, **values}
                for key, values in sorted(
                    source_totals.items(),
                    key=lambda item: (-item[1]["sessions"], item[0]),
                )[:10]
            ],
            "privacy_safe_form_outcomes": {
                "count": len(form_events),
                "event_counts": dict(sorted(form_event_counts.items())),
                "contains_contact_details": False,
            },
        },
        "rank_tracking": {
            "tracked_keywords_measured": len(rank_positions),
            "average_position": round(sum(rank_positions) / len(rank_positions), 2)
            if rank_positions
            else None,
            "top_10": sum(1 for value in rank_positions if value <= 10),
            "top_3": sum(1 for value in rank_positions if value <= 3),
        },
    }

    pages = max(int(latest_crawl.pages_discovered or 0), 1)
    technical_penalty = (
        severity_counts.get("critical", 0) * 18
        + severity_counts.get("high", 0) * 12
        + severity_counts.get("medium", 0) * 5
        + severity_counts.get("low", 0) * 2
    ) / pages
    technical_score = round(max(0.0, 100.0 - min(100.0, technical_penalty * 8)), 1)
    performance_scores: list[float] = []
    for item in performance:
        if item["performance_score"] is not None:
            raw = float(item["performance_score"])
            performance_scores.append(raw * 100 if raw <= 1 else raw)
        for key, good, poor in (("lcp_ms", 2500, 4000), ("inp_ms", 200, 500), ("cls", 0.1, 0.25)):
            rated = _score_metric(item[key], good, poor)
            if rated is not None:
                performance_scores.append(rated)
    performance_score = (
        round(sum(performance_scores) / len(performance_scores), 1)
        if performance_scores
        else None
    )
    visibility_inputs = []
    if weighted_position is not None:
        visibility_inputs.append(max(0.0, min(100.0, 104.0 - weighted_position * 4)))
    if rank_positions:
        avg_rank = sum(rank_positions) / len(rank_positions)
        visibility_inputs.append(max(0.0, min(100.0, 104.0 - avg_rank * 4)))
    visibility_score = (
        round(sum(visibility_inputs) / len(visibility_inputs), 1)
        if visibility_inputs
        else None
    )
    engagement_rate = evidence["traffic"]["engagement_rate"]
    engagement_score = (
        round(max(0.0, min(100.0, float(engagement_rate) * 125)), 1)
        if engagement_rate is not None
        else None
    )
    weighted = [
        (technical_score, 0.4),
        (performance_score, 0.25),
        (visibility_score, 0.25),
        (engagement_score, 0.1),
    ]
    available = [(value, weight) for value, weight in weighted if value is not None]
    overall = round(
        sum(float(value) * weight for value, weight in available)
        / sum(weight for _, weight in available),
        1,
    )
    scores = {
        "overall": overall,
        "coverage_weight": round(sum(weight for _, weight in available), 2),
        "components": {
            "website_health": technical_score,
            "website_performance": performance_score,
            "organic_visibility": visibility_score,
            "traffic_engagement": engagement_score,
        },
        "missing_is_not_zero": True,
        "method": "deterministic_explainable_v1",
    }

    fixes: list[dict[str, Any]] = []
    for group in issue_groups:
        fixes.append(
            {
                "key": f"crawl:{group['issue_code']}",
                "priority": "urgent"
                if group["severity"] in {"critical", "high"}
                else "important",
                "title": f"Fix {group['label'].lower()}",
                "why": f"The baseline found {group['count']} affected page{'s' if group['count'] != 1 else ''}.",
                "why_it_matters": f"The baseline found {group['count']} affected page{'s' if group['count'] != 1 else ''}.",
                "detail": f"The baseline found {group['count']} affected page{'s' if group['count'] != 1 else ''}.",
                "what_to_do": "Open Website Health, review the affected pages, fix the shared cause first, then rerun the scan.",
                "steps": [
                    "Open Website Health and review the affected pages.",
                    "Fix the shared cause before editing one page at a time.",
                    "Rerun the website scan and compare the same issue count.",
                ],
                "evidence": [f"crawl:{latest_crawl.id}:{group['issue_code']}"],
                "measurement": {
                    "metric_id": f"technical_issue_count:{group['issue_code']}",
                    "label": f"{group['label']} issue count",
                    "baseline": group["count"],
                    "unit": "pages",
                    "check_after_days": 1,
                    "explanation": "Rerun the website scan and compare the count from the same issue rule.",
                    "verification_method": "completed_website_scan",
                },
            }
        )
    poor_performance = any(
        (item["lcp_ms"] is not None and item["lcp_ms"] > 2500)
        or (item["inp_ms"] is not None and item["inp_ms"] > 200)
        or (item["cls"] is not None and item["cls"] > 0.1)
        for item in performance
    )
    if poor_performance:
        fixes.append(
            {
                "key": "website:core_web_vitals",
                "priority": "important",
                "title": "Improve the slowest Core Web Vital",
                "why": "At least one saved website experience metric is outside Google's good threshold.",
                "why_it_matters": "At least one saved website experience metric is outside Google's good threshold.",
                "detail": "At least one saved website experience metric is outside Google's good threshold.",
                "what_to_do": "Start with the worst mobile metric, change one cause at a time, and measure the same URL again.",
                "steps": [
                    "Start with the worst mobile metric.",
                    "Change one measurable cause at a time.",
                    "Measure the same URL and device class again.",
                ],
                "evidence": ["website_performance:latest"],
                "measurement": {
                    "metric_id": "core_web_vitals:worst_mobile_metric",
                    "label": "worst mobile website experience metric",
                    "baseline": performance_score,
                    "unit": "score",
                    "check_after_days": 28,
                    "explanation": "Compare the same URL, form factor, source, and metric contract after a complete field-data window when available.",
                    "verification_method": "matching_website_performance_measurement",
                },
            }
        )
    avg_rank = evidence["rank_tracking"]["average_position"]
    if avg_rank is not None and avg_rank > 10:
        fixes.append(
            {
                "key": "visibility:tracked_searches",
                "priority": "important",
                "title": "Improve the first tracked service search",
                "why": f"The measured tracked searches average position {avg_rank} in this baseline.",
                "why_it_matters": f"The measured tracked searches average position {avg_rank} in this baseline.",
                "detail": f"The measured tracked searches average position {avg_rank} in this baseline.",
                "what_to_do": "Review the matching service page and local relevance before adding more search terms.",
                "steps": [
                    "Open Search Rankings and choose the first tracked service search.",
                    "Review the matching service page and local relevance evidence.",
                    "Recheck the same search and location after the observation window.",
                ],
                "evidence": ["rank_tracking:latest"],
                "measurement": {
                    "metric_id": "tracked_keyword_position",
                    "label": "average tracked search position",
                    "baseline": avg_rank,
                    "unit": "position",
                    "check_after_days": 28,
                    "explanation": "Compare the same tracked searches, location, and source after 28 days.",
                    "verification_method": "comparable_ranking_snapshot",
                },
            }
        )
    if not search_rows:
        fixes.append(
            {
                "key": "connection:search_console",
                "priority": "data_needed",
                "title": "Review Google Search data coverage",
                "why": "The required Google Search connection synchronized, but returned no dated records for the 28-day window. Missing facts were not scored as zero.",
                "why_it_matters": "The required Google Search connection synchronized, but returned no dated records for the 28-day window. Missing facts were not scored as zero.",
                "detail": "The official baseline records the successful connection separately from the absence of dated search activity.",
                "what_to_do": "Confirm that the selected website belongs to this business, then check again after Google has dated search activity to return.",
                "steps": [
                    "Open Settings and confirm the selected Google Search website.",
                    "Confirm that the website belongs to this location.",
                    "Check again after Google has dated search activity to return.",
                ],
                "evidence": [],
                "measurement": {
                    "metric_id": "search_console_coverage_days",
                    "label": "saved Google search days",
                    "baseline": None,
                    "unit": "days",
                    "check_after_days": 28,
                    "explanation": "Confirm 28 complete saved days before drawing a period comparison.",
                    "verification_method": "search_console_daily_metrics",
                },
            }
        )
    if not analytics_rows:
        fixes.append(
            {
                "key": "connection:analytics",
                "priority": "data_needed",
                "title": "Connect website analytics",
                "why": "Sessions, engagement, and conversions are not available yet and were not scored as zero.",
                "why_it_matters": "Sessions, engagement, and conversions are not available yet and were not scored as zero.",
                "detail": "This connection adds dated traffic and engagement facts without changing the frozen baseline.",
                "what_to_do": "Connect the correct website analytics property and confirm the reporting time zone.",
                "steps": ["Connect the matching website analytics property in Settings.", "Confirm the website and reporting time zone."],
                "evidence": [],
                "measurement": {
                    "metric_id": "analytics_coverage_days",
                    "label": "saved website analytics days",
                    "baseline": None,
                    "unit": "days",
                    "check_after_days": 28,
                    "explanation": "Confirm 28 complete saved days before drawing a period comparison.",
                    "verification_method": "analytics_daily_metrics",
                },
            }
        )
    fixes = fixes[:10]
    diagnosis = {
        "headline": (
            "Strong starting foundation"
            if overall >= 80
            else "A workable foundation with clear priorities"
            if overall >= 60
            else "The baseline found foundational work to address first"
        ),
        "summary": (
            f"The first baseline measured {len(issues)} website issue{'s' if len(issues) != 1 else ''} "
            f"across {int(latest_crawl.pages_discovered or 0)} discovered page{'s' if int(latest_crawl.pages_discovered or 0) != 1 else ''}. "
            "Scores use only measured evidence; missing connections do not become zeroes."
        ),
        "fixes": fixes,
        "analysis": {
            "mode": "governed_evidence_synthesis",
            "narrative_source": "deterministic",
            "ai_enrichment": "optional_non_blocking",
            "causal_proof": False,
            "limitations": [
                "This baseline describes the saved evidence at the cutoff time; it does not guarantee ranking changes.",
                "AI wording, when enabled later, may summarize only these frozen facts and may not invent measurements or fixes.",
            ],
        },
    }
    return evidence, scores, diagnosis


def _merge_validated_ai_narrative(
    diagnosis: dict[str, Any],
    narrative: dict[str, Any],
) -> dict[str, Any]:
    """Merge validated wording without allowing AI to change the fix plan."""
    return {
        **diagnosis,
        "headline": str(narrative["headline"]),
        "summary": str(narrative["summary"]),
        "themes": list(narrative.get("themes") or []),
        "evidence_used": list(narrative.get("evidence_used") or []),
        "uncertainties": list(narrative.get("uncertainties") or []),
        "analysis": {
            **dict(diagnosis.get("analysis") or {}),
            "narrative_source": "governed_ai",
            "ai_enrichment": "validated",
            "causal_proof": False,
        },
    }


def _report_metric(
    *, key: str, label: str, value: float | int | None, unit: str, explanation: str, source: str
) -> dict[str, Any]:
    observed = 1 if value is not None else 0
    return {
        "key": key,
        "label": label,
        "current": value,
        "previous": None,
        "change_percent": None,
        "direction": "not_enough_information",
        "result": "not_enough_information",
        "unit": unit,
        "explanation": explanation,
        "source": {"label": source, "system": key, "last_updated": None},
        "coverage": {
            "current": {
                "state": "complete" if observed else "unavailable",
                "observed": observed,
                "expected": 1,
            },
            "comparison": {"state": "unavailable", "observed": 0, "expected": 1},
        },
    }


def _enrich_report_snapshot(
    snapshot: dict[str, Any],
    *,
    evidence: dict[str, Any],
    scores: dict[str, Any],
    diagnosis: dict[str, Any],
    source_states: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = dict(snapshot)
    traffic = evidence["traffic"]
    website = evidence["website"]
    performance = website["performance"]
    latest_mobile = next(
        (item for item in performance if item["form_factor"] == "mobile"),
        performance[0] if performance else {},
    )
    extra_metrics = [
        _report_metric(
            key="website_health_baseline",
            label="Website health baseline",
            value=scores["components"]["website_health"],
            unit="score",
            explanation="An explainable score based on the severity and density of issues in the first completed scan.",
            source="InsightOS website scan",
        ),
        _report_metric(
            key="website_sessions",
            label="Website sessions",
            value=traffic["sessions"],
            unit="sessions",
            explanation="Saved website sessions during the frozen 28-day baseline window.",
            source="Connected website analytics",
        ),
        _report_metric(
            key="engagement_rate",
            label="Engagement rate",
            value=round(traffic["engagement_rate"] * 100, 1)
            if traffic["engagement_rate"] is not None
            else None,
            unit="percent",
            explanation="The share of saved sessions that were engaged during the baseline window.",
            source="Connected website analytics",
        ),
        _report_metric(
            key="conversions",
            label="Recorded conversions",
            value=traffic["conversions"],
            unit="conversions",
            explanation="Conversions saved by the connected website analytics property.",
            source="Connected website analytics",
        ),
        _report_metric(
            key="mobile_lcp",
            label="Mobile largest contentful paint",
            value=latest_mobile.get("lcp_ms"),
            unit="milliseconds",
            explanation="How quickly the main content appeared in the latest saved mobile measurement.",
            source="Website performance measurement",
        ),
        _report_metric(
            key="mobile_inp",
            label="Mobile interaction responsiveness",
            value=latest_mobile.get("inp_ms"),
            unit="milliseconds",
            explanation="How quickly the page responded to interaction in the latest saved mobile measurement.",
            source="Website performance measurement",
        ),
        _report_metric(
            key="mobile_cls",
            label="Mobile layout stability",
            value=latest_mobile.get("cls"),
            unit="score",
            explanation="How stable the layout was in the latest saved mobile measurement.",
            source="Website performance measurement",
        ),
    ]
    existing_keys = {item.get("key") for item in list(enriched.get("metrics") or [])}
    enriched["metrics"] = list(enriched.get("metrics") or []) + [
        item for item in extra_metrics if item["key"] not in existing_keys
    ]
    enriched["executive_summary"] = {
        "headline": diagnosis["headline"],
        "summary": diagnosis["summary"],
    }
    enriched["next_priorities"] = diagnosis["fixes"][:5]
    enriched["baseline"] = {
        "analysis_version": ANALYSIS_VERSION,
        "immutable": True,
        "window": evidence["window"],
        "scores": scores,
        "sources": source_states,
        "diagnosis": diagnosis,
    }
    enriched["snapshot_hash"] = premium_report_service._snapshot_hash(enriched)
    return enriched


def _serialize(row: OnboardingBaseline) -> dict[str, Any]:
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "report_id": row.report_id,
        "baseline_number": row.baseline_number,
        "status": row.status,
        "analysis_version": row.analysis_version,
        "window": {
            "days": row.evidence_window_days,
            "start": row.window_start.isoformat(),
            "end": row.window_end.isoformat(),
            "cutoff_at": row.cutoff_at.isoformat(),
        },
        "sources": row.source_states,
        "evidence": row.evidence_snapshot,
        "scores": row.score_snapshot,
        "diagnosis": row.diagnosis_snapshot,
        "baseline_hash": row.baseline_hash,
        "report_snapshot_hash": row.report_snapshot_hash,
        "immutable": True,
        "generated_at": row.generated_at.isoformat(),
    }


def get_status(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    campaign = _campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    row = _existing(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if row is not None:
        return {
            "state": row.status,
            "completion_required": True,
            "completion_satisfied": True,
            "basic_access_blocked": False,
            "message": "Your immutable first baseline and diagnosis are ready.",
            "baseline": _serialize(row),
        }
    checked_at = _aware(now) or datetime.now(UTC)
    readiness = _readiness(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign=campaign,
        checked_at=checked_at,
    )
    return {**readiness, "completion_satisfied": False, "baseline": None}


def ensure_baseline(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    generated_by_user_id: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    cutoff_at = _aware(now) or datetime.now(UTC)
    campaign = _campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    existing = _existing(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if existing is not None:
        return {
            "created": False,
            "state": existing.status,
            "completion_required": True,
            "completion_satisfied": True,
            "basic_access_blocked": False,
            "message": "Your immutable first baseline and diagnosis are ready.",
            "baseline": _serialize(existing),
        }
    readiness = _readiness(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign=campaign,
        checked_at=cutoff_at,
    )
    if readiness["state"] != "ready_to_generate":
        return {
            **readiness,
            "created": False,
            "completion_satisfied": False,
            "baseline": None,
        }

    evidence, scores, diagnosis = _build_evidence(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign=campaign,
        cutoff_at=cutoff_at,
    )
    source_states = readiness["sources"]
    try:
        ai_result = onboarding_baseline_ai_service.generate_baseline_narrative(
            db,
            campaign=campaign,
            evidence=evidence,
            scores=scores,
            diagnosis=diagnosis,
            source_states=source_states,
            requested_by_user_id=generated_by_user_id,
            now=cutoff_at,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Optional onboarding baseline explanation failed",
            extra={
                "organization_id": organization_id,
                "campaign_id": campaign_id,
            },
        )
        ai_result = {
            "state": "unavailable",
            "narrative": None,
            "context_hash": None,
        }

    # Provider and cost work happens before the immutable baseline lock. Re-read
    # the same cutoff under the lock so a concurrent request cannot freeze AI
    # wording against evidence that differs from the saved report.
    campaign = _campaign(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
        lock=True,
    )
    existing = _existing(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign_id,
    )
    if existing is not None:
        return {
            "created": False,
            "state": existing.status,
            "completion_required": True,
            "completion_satisfied": True,
            "basic_access_blocked": False,
            "message": "Your immutable first baseline and diagnosis are ready.",
            "baseline": _serialize(existing),
        }
    readiness = _readiness(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign=campaign,
        checked_at=cutoff_at,
    )
    if readiness["state"] != "ready_to_generate":
        return {
            **readiness,
            "created": False,
            "completion_satisfied": False,
            "baseline": None,
        }
    evidence, scores, diagnosis = _build_evidence(
        db,
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign=campaign,
        cutoff_at=cutoff_at,
    )
    source_states = readiness["sources"]
    current_context_hash = onboarding_baseline_ai_service.baseline_context_hash(
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
    )
    narrative = ai_result.get("narrative")
    if (
        isinstance(narrative, dict)
        and ai_result.get("state") == "validated"
        and ai_result.get("context_hash") == current_context_hash
    ):
        diagnosis = _merge_validated_ai_narrative(diagnosis, narrative)
    else:
        diagnosis["analysis"] = {
            **dict(diagnosis.get("analysis") or {}),
            "narrative_source": "deterministic",
            "ai_enrichment": "unavailable_non_blocking",
        }
    limited = any(item["state"] != "measured" for item in source_states)
    baseline_status = "limited" if limited else "ready"
    report_snapshot = premium_report_service.build_report_snapshot(
        db,
        tenant_id=tenant_id,
        campaign=campaign,
        month_number=0,
        generated_at=cutoff_at,
    )
    report_snapshot = _enrich_report_snapshot(
        report_snapshot,
        evidence=evidence,
        scores=scores,
        diagnosis=diagnosis,
        source_states=source_states,
    )
    report = reporting_service.create_report_from_snapshot(
        db,
        tenant_id=tenant_id,
        campaign_id=campaign.id,
        month_number=0,
        snapshot=report_snapshot,
        event_type="onboarding.baseline_report_generated",
    )
    baseline_payload = {
        "analysis_version": ANALYSIS_VERSION,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "campaign_id": campaign.id,
        "business_location_id": campaign.business_location_id,
        "report_id": report.id,
        "baseline_number": 1,
        "status": baseline_status,
        "window": evidence["window"],
        "sources": source_states,
        "evidence": evidence,
        "scores": scores,
        "diagnosis": diagnosis,
        "report_snapshot_hash": report_snapshot["snapshot_hash"],
    }
    row = OnboardingBaseline(
        tenant_id=tenant_id,
        organization_id=organization_id,
        campaign_id=campaign.id,
        business_location_id=str(campaign.business_location_id),
        report_id=report.id,
        generated_by_user_id=generated_by_user_id,
        baseline_number=1,
        status=baseline_status,
        analysis_version=ANALYSIS_VERSION,
        evidence_window_days=EVIDENCE_WINDOW_DAYS,
        window_start=date.fromisoformat(evidence["window"]["start"]),
        window_end=date.fromisoformat(evidence["window"]["end"]),
        cutoff_at=cutoff_at,
        source_states=source_states,
        evidence_snapshot=evidence,
        score_snapshot=scores,
        diagnosis_snapshot=diagnosis,
        report_snapshot_hash=report_snapshot["snapshot_hash"],
        baseline_hash=_hash(baseline_payload),
        generated_at=cutoff_at,
    )
    db.add(row)
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="onboarding.baseline_generated",
        payload={
            "organization_id": organization_id,
            "campaign_id": campaign.id,
            "business_location_id": campaign.business_location_id,
            "baseline_id": row.id,
            "report_id": report.id,
            "status": baseline_status,
            "analysis_version": ANALYSIS_VERSION,
            "baseline_hash": row.baseline_hash,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "created": True,
        "state": row.status,
        "completion_required": True,
        "completion_satisfied": True,
        "basic_access_blocked": False,
        "message": (
            "Your first baseline is ready. Optional data connections can make later comparisons more complete."
            if row.status == "limited"
            else "Your first baseline and diagnosis are ready."
        ),
        "baseline": _serialize(row),
    }
