from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.intelligence.lexicon.evaluator import evaluate_core_web_vitals
from app.intelligence.lexicon.loader import get_active_lexicon
from app.models.campaign import Campaign
from app.models.website_performance import WebsitePerformanceMeasurement


CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_METRICS = (
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
    "experimental_time_to_first_byte",
)
METRIC_COLUMNS = {
    "largest_contentful_paint": "lcp_ms",
    "interaction_to_next_paint": "inp_ms",
    "cumulative_layout_shift": "cls_value",
    "experimental_time_to_first_byte": "ttfb_ms",
}


class WebsitePerformanceProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def normalize_site_url(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise ValueError("Campaign website is missing.")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        raise ValueError("Campaign website is not a valid URL.")
    path = parsed.path or "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()


def origin_for_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _date_from_crux(payload: dict[str, Any] | None) -> date | None:
    if not isinstance(payload, dict):
        return None
    try:
        return date(
            int(payload["year"]),
            int(payload["month"]),
            int(payload["day"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _metric_p75(metrics: dict[str, Any], metric_id: str) -> float | None:
    raw_value = (
        metrics.get(metric_id, {}).get("percentiles", {}).get("p75")
        if isinstance(metrics.get(metric_id), dict)
        else None
    )
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def query_crux_field_data(
    client: httpx.Client,
    *,
    requested_url: str,
    form_factor: str,
    api_key: str,
) -> dict[str, Any]:
    if not api_key.strip():
        raise WebsitePerformanceProviderError(
            "Chrome UX Report is not configured.",
            code="crux_not_configured",
        )

    request_base = {
        "formFactor": "PHONE" if form_factor == "mobile" else "DESKTOP",
        "metrics": list(CRUX_METRICS),
    }
    attempts = (
        ("url", requested_url),
        ("origin", origin_for_url(requested_url)),
    )
    response: httpx.Response | None = None
    resolved_scope = "url"
    measured_url = requested_url
    fallback_to_origin = False
    for index, (scope, target) in enumerate(attempts):
        response = client.post(
            CRUX_ENDPOINT,
            params={"key": api_key},
            json={**request_base, scope: target},
        )
        if response.status_code == 200:
            resolved_scope = scope
            measured_url = target
            fallback_to_origin = index > 0
            break
        if response.status_code not in {404, 400}:
            raise WebsitePerformanceProviderError(
                f"Chrome UX Report returned HTTP {response.status_code}.",
                code="crux_request_failed",
            )

    if response is None or response.status_code != 200:
        return {
            "status": "insufficient_data",
            "scope": "origin",
            "measured_url": origin_for_url(requested_url),
            "fallback_to_origin": True,
            "metrics": {},
            "collection_start": None,
            "collection_end": None,
            "distribution": {},
        }

    payload = response.json()
    record = payload.get("record") if isinstance(payload, dict) else None
    record = record if isinstance(record, dict) else {}
    metrics = record.get("metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    collection_period = record.get("collectionPeriod")
    collection_period = collection_period if isinstance(collection_period, dict) else {}
    values = {
        column: _metric_p75(metrics, metric_id)
        for metric_id, column in METRIC_COLUMNS.items()
    }
    return {
        "status": "ready" if any(value is not None for value in values.values()) else "insufficient_data",
        "scope": resolved_scope,
        "measured_url": measured_url,
        "fallback_to_origin": fallback_to_origin,
        "metrics": values,
        "collection_start": _date_from_crux(collection_period.get("firstDate")),
        "collection_end": _date_from_crux(collection_period.get("lastDate")),
        "distribution": {
            metric_id: metric_payload.get("histogram", [])
            for metric_id, metric_payload in metrics.items()
            if isinstance(metric_payload, dict)
        },
    }


def _audit_numeric(audits: dict[str, Any], audit_id: str) -> float | None:
    audit = audits.get(audit_id)
    raw_value = audit.get("numericValue") if isinstance(audit, dict) else None
    try:
        return float(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        return None


def _lab_opportunities(audits: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for audit_id, raw_audit in audits.items():
        if not isinstance(raw_audit, dict):
            continue
        details = raw_audit.get("details")
        savings = (
            details.get("overallSavingsMs")
            if isinstance(details, dict)
            else None
        )
        try:
            savings_ms = float(savings or 0)
        except (TypeError, ValueError):
            savings_ms = 0
        score = raw_audit.get("score")
        if savings_ms <= 0 or score in {1, 1.0}:
            continue
        candidates.append(
            {
                "audit_id": audit_id,
                "title": str(raw_audit.get("title") or audit_id),
                "description": str(raw_audit.get("description") or ""),
                "estimated_savings_ms": round(savings_ms, 1),
            }
        )
    return sorted(
        candidates,
        key=lambda item: item["estimated_savings_ms"],
        reverse=True,
    )[:5]


def query_pagespeed_lab_data(
    client: httpx.Client,
    *,
    requested_url: str,
    form_factor: str,
    api_key: str,
) -> dict[str, Any]:
    params: list[tuple[str, str]] = [
        ("url", requested_url),
        ("strategy", form_factor),
        ("category", "PERFORMANCE"),
    ]
    if api_key.strip():
        params.append(("key", api_key))
    response = client.get(PAGESPEED_ENDPOINT, params=params)
    if response.status_code != 200:
        raise WebsitePerformanceProviderError(
            f"PageSpeed Insights returned HTTP {response.status_code}.",
            code="pagespeed_request_failed",
        )
    payload = response.json()
    lighthouse = payload.get("lighthouseResult")
    lighthouse = lighthouse if isinstance(lighthouse, dict) else {}
    audits = lighthouse.get("audits")
    audits = audits if isinstance(audits, dict) else {}
    categories = lighthouse.get("categories")
    categories = categories if isinstance(categories, dict) else {}
    performance = categories.get("performance")
    performance = performance if isinstance(performance, dict) else {}
    raw_score = performance.get("score")
    try:
        performance_score = round(float(raw_score) * 100, 1)
    except (TypeError, ValueError):
        performance_score = None
    return {
        "status": "ready" if audits else "insufficient_data",
        "scope": "url",
        "measured_url": str(lighthouse.get("finalDisplayedUrl") or requested_url),
        "source_version": str(lighthouse.get("lighthouseVersion") or "") or None,
        "metrics": {
            "lcp_ms": _audit_numeric(audits, "largest-contentful-paint"),
            "cls_value": _audit_numeric(audits, "cumulative-layout-shift"),
            "fcp_ms": _audit_numeric(audits, "first-contentful-paint"),
            "tbt_ms": _audit_numeric(audits, "total-blocking-time"),
            "ttfb_ms": _audit_numeric(audits, "server-response-time"),
            "performance_score": performance_score,
        },
        "diagnostics": {
            "opportunities": _lab_opportunities(audits),
            "test_environment": {
                "strategy": form_factor,
                "fetch_time": lighthouse.get("fetchTime"),
                "user_agent": lighthouse.get("userAgent"),
            },
        },
    }


def _assessment_for_measurement(
    db: Session,
    *,
    tenant_id: str,
    form_factor: str,
    source: str,
    metrics: dict[str, Any],
    measured_at: datetime,
) -> dict[str, Any]:
    return evaluate_core_web_vitals(
        get_active_lexicon(db, tenant_id=tenant_id),
        {
            "lcp": metrics.get("lcp_ms"),
            "inp": metrics.get("inp_ms"),
            "cls": metrics.get("cls_value"),
            "ttfb": metrics.get("ttfb_ms"),
        },
        form_factor=form_factor,
        measured_at=measured_at,
        source=source,
    )


def collect_campaign_performance(
    db: Session,
    *,
    campaign: Campaign,
    form_factor: str,
    captured_at: datetime | None = None,
    idempotency_scope: str | None = None,
    client: httpx.Client | None = None,
) -> list[WebsitePerformanceMeasurement]:
    if form_factor not in {"mobile", "desktop"}:
        raise ValueError("form_factor must be mobile or desktop.")
    if not campaign.organization_id:
        raise ValueError("Campaign is missing organization scope.")
    measured_at = captured_at or datetime.now(UTC)
    requested_url = normalize_site_url(campaign.domain)
    lexicon = get_active_lexicon(db, tenant_id=campaign.tenant_id)
    settings = get_settings()
    api_key = settings.pagespeed_api_key.strip() or settings.crux_api_key.strip()
    owns_client = client is None
    resolved_client = client or httpx.Client(
        timeout=settings.website_performance_http_timeout_seconds,
        follow_redirects=True,
    )
    collectors = (
        (
            "crux_field",
            lambda: query_crux_field_data(
                resolved_client,
                requested_url=requested_url,
                form_factor=form_factor,
                api_key=settings.crux_api_key,
            ),
        ),
        (
            "pagespeed_lab",
            lambda: query_pagespeed_lab_data(
                resolved_client,
                requested_url=requested_url,
                form_factor=form_factor,
                api_key=api_key,
            ),
        ),
    )
    rows: list[WebsitePerformanceMeasurement] = []
    try:
        for source, collector in collectors:
            resolved_scope = (
                str(idempotency_scope).strip()
                if idempotency_scope
                else measured_at.date().isoformat()
            )
            idempotency_key = (
                f"website-performance:{campaign.id}:{form_factor}:"
                f"{source}:{resolved_scope}"
            )
            existing = (
                db.query(WebsitePerformanceMeasurement)
                .filter(
                    WebsitePerformanceMeasurement.idempotency_key == idempotency_key
                )
                .first()
            )
            if existing is not None:
                rows.append(existing)
                continue

            result: dict[str, Any]
            error_code: str | None = None
            error_message: str | None = None
            try:
                result = collector()
            except WebsitePerformanceProviderError as exc:
                result = {
                    "status": "failed",
                    "scope": "url",
                    "measured_url": requested_url,
                    "metrics": {},
                }
                error_code = exc.code
                error_message = str(exc)
            except (httpx.HTTPError, ValueError) as exc:
                result = {
                    "status": "failed",
                    "scope": "url",
                    "measured_url": requested_url,
                    "metrics": {},
                }
                error_code = "provider_request_failed"
                error_message = str(exc)

            metrics = dict(result.get("metrics") or {})
            assessment = _assessment_for_measurement(
                db,
                tenant_id=campaign.tenant_id,
                form_factor=form_factor,
                source=source,
                metrics=metrics,
                measured_at=measured_at,
            )
            diagnostics = dict(result.get("diagnostics") or {})
            diagnostics["assessment"] = assessment
            row = WebsitePerformanceMeasurement(
                tenant_id=campaign.tenant_id,
                organization_id=campaign.organization_id,
                business_location_id=campaign.business_location_id,
                campaign_id=campaign.id,
                requested_url=requested_url,
                measured_url=str(result.get("measured_url") or requested_url),
                source=source,
                scope=str(result.get("scope") or "url"),
                form_factor=form_factor,
                status=str(result.get("status") or "failed"),
                lcp_ms=metrics.get("lcp_ms"),
                inp_ms=metrics.get("inp_ms"),
                cls_value=metrics.get("cls_value"),
                ttfb_ms=metrics.get("ttfb_ms"),
                fcp_ms=metrics.get("fcp_ms"),
                tbt_ms=metrics.get("tbt_ms"),
                performance_score=metrics.get("performance_score"),
                collection_start=result.get("collection_start"),
                collection_end=result.get("collection_end"),
                source_version=result.get("source_version"),
                lexicon_id=lexicon.meta.lexicon_id,
                lexicon_version=lexicon.meta.version,
                fallback_to_origin=bool(result.get("fallback_to_origin")),
                distribution=dict(result.get("distribution") or {}),
                diagnostics=diagnostics,
                error_code=error_code,
                error_message=error_message,
                idempotency_key=idempotency_key,
                captured_at=measured_at,
            )
            db.add(row)
            db.flush()
            rows.append(row)
        return rows
    finally:
        if owns_client:
            resolved_client.close()


def serialize_measurement(row: WebsitePerformanceMeasurement) -> dict[str, Any]:
    assessment = dict(row.diagnostics or {}).get("assessment")
    return {
        "id": row.id,
        "campaign_id": row.campaign_id,
        "business_location_id": row.business_location_id,
        "requested_url": row.requested_url,
        "measured_url": row.measured_url,
        "source": row.source,
        "scope": row.scope,
        "form_factor": row.form_factor,
        "status": row.status,
        "metrics": {
            "lcp_ms": row.lcp_ms,
            "inp_ms": row.inp_ms,
            "cls": row.cls_value,
            "ttfb_ms": row.ttfb_ms,
            "fcp_ms": row.fcp_ms,
            "tbt_ms": row.tbt_ms,
            "performance_score": row.performance_score,
        },
        "assessment": assessment if isinstance(assessment, dict) else None,
        "collection_period": {
            "start": row.collection_start.isoformat() if row.collection_start else None,
            "end": row.collection_end.isoformat() if row.collection_end else None,
        },
        "source_version": row.source_version,
        "lexicon": {
            "id": row.lexicon_id,
            "version": row.lexicon_version,
        },
        "fallback_to_origin": row.fallback_to_origin,
        "diagnostics": {
            key: value
            for key, value in dict(row.diagnostics or {}).items()
            if key != "assessment"
        },
        "error": (
            {"code": row.error_code, "message": row.error_message}
            if row.error_code
            else None
        ),
        "captured_at": row.captured_at.isoformat(),
    }


def get_campaign_performance_summary(
    db: Session,
    *,
    tenant_id: str,
    campaign_id: str,
    form_factor: str,
    days: int = 90,
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=max(1, min(int(days), 730)))
    rows = (
        db.query(WebsitePerformanceMeasurement)
        .filter(
            WebsitePerformanceMeasurement.tenant_id == tenant_id,
            WebsitePerformanceMeasurement.campaign_id == campaign_id,
            WebsitePerformanceMeasurement.form_factor == form_factor,
            WebsitePerformanceMeasurement.captured_at >= since,
        )
        .order_by(WebsitePerformanceMeasurement.captured_at.asc())
        .all()
    )
    latest: dict[str, WebsitePerformanceMeasurement] = {}
    for row in rows:
        latest[row.source] = row
    successful_capture_times = []
    for row in rows:
        if row.status not in {"ready", "insufficient_data"}:
            continue
        captured_at = row.captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        successful_capture_times.append(captured_at)
    latest_success_at = max(successful_capture_times, default=None)
    next_refresh_at = (
        latest_success_at
        + timedelta(hours=max(1, get_settings().website_performance_collection_interval_hours))
        if latest_success_at
        else None
    )
    return {
        "campaign_id": campaign_id,
        "form_factor": form_factor,
        "days": days,
        "latest": {
            source: serialize_measurement(row)
            for source, row in latest.items()
        },
        "history": [
            serialize_measurement(row)
            for row in rows
            if row.source == "crux_field"
        ],
        "sync": {
            "last_success_at": latest_success_at.isoformat() if latest_success_at else None,
            "next_refresh_at": next_refresh_at.isoformat() if next_refresh_at else None,
            "state": (
                "not_started"
                if not rows
                else "failed"
                if all(row.status == "failed" for row in latest.values())
                else "current"
            ),
        },
    }
