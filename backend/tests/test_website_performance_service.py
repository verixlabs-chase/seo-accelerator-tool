from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace

import httpx

from app.services import website_performance_service
from app.services.website_performance_service import (
    collect_campaign_performance,
    get_campaign_performance_summary,
)
from tests.conftest import create_test_campaign


def _provider_response(request: httpx.Request) -> httpx.Response:
    if request.url.host == "chromeuxreport.googleapis.com":
        body = json.loads(request.content.decode("utf-8"))
        if "url" in body:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(
            200,
            json={
                "record": {
                    "metrics": {
                        "largest_contentful_paint": {
                            "percentiles": {"p75": 2200},
                            "histogram": [{"start": 0, "end": 2500, "density": 0.8}],
                        },
                        "interaction_to_next_paint": {
                            "percentiles": {"p75": 180},
                            "histogram": [{"start": 0, "end": 200, "density": 0.76}],
                        },
                        "cumulative_layout_shift": {
                            "percentiles": {"p75": "0.08"},
                            "histogram": [{"start": "0.00", "end": "0.10", "density": 0.9}],
                        },
                        "experimental_time_to_first_byte": {
                            "percentiles": {"p75": 650},
                            "histogram": [{"start": 0, "end": 800, "density": 0.82}],
                        },
                    },
                    "collectionPeriod": {
                        "firstDate": {"year": 2026, "month": 7, "day": 1},
                        "lastDate": {"year": 2026, "month": 7, "day": 28},
                    },
                }
            },
        )
    if request.url.host == "www.googleapis.com":
        return httpx.Response(
            200,
            json={
                "lighthouseResult": {
                    "finalDisplayedUrl": "https://example.test/",
                    "lighthouseVersion": "13.0.0",
                    "fetchTime": "2026-07-30T18:00:00Z",
                    "userAgent": "test-agent",
                    "categories": {"performance": {"score": 0.91}},
                    "audits": {
                        "largest-contentful-paint": {"numericValue": 2100},
                        "cumulative-layout-shift": {"numericValue": 0.07},
                        "first-contentful-paint": {"numericValue": 1200},
                        "total-blocking-time": {"numericValue": 90},
                        "server-response-time": {"numericValue": 310},
                        "render-blocking-resources": {
                            "score": 0.4,
                            "title": "Eliminate render-blocking resources",
                            "description": "Load critical styles first.",
                            "details": {"overallSavingsMs": 450},
                        },
                    },
                }
            },
        )
    raise AssertionError(f"Unexpected provider request: {request.url}")


def test_collects_field_and_lab_measurements_with_origin_fallback(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        website_performance_service,
        "get_settings",
        lambda: SimpleNamespace(
            crux_api_key="test-google-key",
            pagespeed_api_key="",
            website_performance_http_timeout_seconds=45.0,
            website_performance_collection_interval_hours=168,
        ),
    )
    organization = create_test_org(name="Performance org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        name="Performance campaign",
        domain="example.test",
    )
    campaign.setup_state = "Active"
    captured_at = datetime(2026, 7, 30, 18, 0, tzinfo=UTC)
    client = httpx.Client(transport=httpx.MockTransport(_provider_response))

    rows = collect_campaign_performance(
        db_session,
        campaign=campaign,
        form_factor="mobile",
        captured_at=captured_at,
        client=client,
    )
    db_session.commit()

    assert [row.source for row in rows] == ["crux_field", "pagespeed_lab"]
    field, lab = rows
    assert field.status == "ready"
    assert field.scope == "origin"
    assert field.fallback_to_origin is True
    assert field.lcp_ms == 2200
    assert field.inp_ms == 180
    assert field.cls_value == 0.08
    assert field.diagnostics["assessment"]["assessment"]["status"] == "good"
    assert lab.performance_score == 91
    assert lab.source_version == "13.0.0"
    assert lab.diagnostics["opportunities"][0]["estimated_savings_ms"] == 450

    replay = collect_campaign_performance(
        db_session,
        campaign=campaign,
        form_factor="mobile",
        captured_at=captured_at,
        client=client,
    )
    assert [row.id for row in replay] == [row.id for row in rows]

    manual_retry = collect_campaign_performance(
        db_session,
        campaign=campaign,
        form_factor="mobile",
        captured_at=captured_at,
        idempotency_scope="manual:retry:1",
        client=client,
    )
    assert [row.id for row in manual_retry] != [row.id for row in rows]

    summary = get_campaign_performance_summary(
        db_session,
        tenant_id=organization.id,
        campaign_id=campaign.id,
        form_factor="mobile",
        days=90,
    )
    assert summary["latest"]["crux_field"]["metrics"]["lcp_ms"] == 2200
    assert summary["latest"]["pagespeed_lab"]["metrics"]["performance_score"] == 91
    assert len(summary["history"]) == 2
    assert summary["sync"]["state"] == "current"


def test_missing_crux_data_stays_insufficient_instead_of_passing(
    db_session,
    create_test_org,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        website_performance_service,
        "get_settings",
        lambda: SimpleNamespace(
            crux_api_key="test-google-key",
            pagespeed_api_key="",
            website_performance_http_timeout_seconds=45.0,
            website_performance_collection_interval_hours=168,
        ),
    )
    organization = create_test_org(name="Sparse performance org")
    campaign = create_test_campaign(
        db_session,
        organization.id,
        domain="sparse.example",
    )
    campaign.setup_state = "Active"

    def _sparse_provider(request: httpx.Request) -> httpx.Response:
        if request.url.host == "chromeuxreport.googleapis.com":
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return _provider_response(request)

    rows = collect_campaign_performance(
        db_session,
        campaign=campaign,
        form_factor="desktop",
        captured_at=datetime(2026, 7, 30, 19, 0, tzinfo=UTC),
        client=httpx.Client(transport=httpx.MockTransport(_sparse_provider)),
    )

    field = rows[0]
    assert field.status == "insufficient_data"
    assert field.diagnostics["assessment"]["assessment"]["status"] == "insufficient_data"
    assert field.diagnostics["assessment"]["assessment"]["passes_core_web_vitals"] is None
    missing_lcp = field.diagnostics["assessment"]["metrics"][0]
    assert missing_lcp["thresholds"]["good_boundary"] == 2500
