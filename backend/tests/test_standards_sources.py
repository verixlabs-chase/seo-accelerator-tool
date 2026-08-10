from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.models.platform_job import PlatformJob
from app.models.reference_library import (
    StandardsChangeCandidate,
    StandardsImpactLink,
    StandardsSourceRegistry,
    StandardsSourceSnapshot,
)
from app.services import durable_job_service, standards_source_service


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_default_registry_contains_only_allowlisted_official_sources(db_session) -> None:
    rows = standards_source_service.ensure_default_sources(db_session)

    assert len(rows) == len(standards_source_service.DEFAULT_STANDARDS_SOURCES)
    assert {row.source_owner for row in rows} == {"Google"}
    assert all(row.source_uri.startswith("https://") for row in rows)
    assert all(row.is_active for row in rows)
    assert {
        "google.search.docs_updates",
        "google.search.status_incidents",
        "google.business.api_change_log",
    }.issubset({row.source_id for row in rows})


def test_source_check_saves_one_immutable_snapshot_and_uses_conditional_get(
    db_session,
) -> None:
    standards_source_service.ensure_default_sources(db_session)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "developers.google.com"
        if calls == 1:
            assert "if-none-match" not in request.headers
            return httpx.Response(
                200,
                text="<html><body><h1>Official update</h1><script>ignore me</script></body></html>",
                headers={
                    "content-type": "text/html; charset=utf-8",
                    "etag": '"standards-v1"',
                    "last-modified": "Wed, 05 Aug 2026 12:00:00 GMT",
                },
            )
        assert request.headers["if-none-match"] == '"standards-v1"'
        assert request.headers["if-modified-since"] == "Wed, 05 Aug 2026 12:00:00 GMT"
        return httpx.Response(304)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = standards_source_service.check_source(
            db_session,
            source_id="google.search.ranking_systems",
            client=client,
        )
        second = standards_source_service.check_source(
            db_session,
            source_id="google.search.ranking_systems",
            client=client,
        )

    assert first["change_status"] == "initial_snapshot"
    assert first["snapshot_created"] is True
    assert second["change_status"] == "not_modified"
    assert second["snapshot_created"] is False
    snapshots = (
        db_session.query(StandardsSourceSnapshot)
        .filter(StandardsSourceSnapshot.source_id == "google.search.ranking_systems")
        .all()
    )
    assert len(snapshots) == 1
    assert "Official update" in snapshots[0].content_text
    assert snapshots[0].source_digest == first["source_digest"]
    assert snapshots[0].normalized_digest == first["normalized_digest"]


def test_source_check_records_changed_raw_evidence_without_false_normalized_drift(
    db_session,
) -> None:
    standards_source_service.ensure_default_sources(db_session)
    payloads = iter(
        (
            "<html><body><p>Same guidance</p><script>build-1</script></body></html>",
            "<html><body><p>Same guidance</p><script>build-2</script></body></html>",
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text=next(payloads), headers={"content-type": "text/html"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = standards_source_service.check_source(
            db_session,
            source_id="google.search.core_web_vitals",
            client=client,
        )
        second = standards_source_service.check_source(
            db_session,
            source_id="google.search.core_web_vitals",
            client=client,
        )

    assert second["change_status"] == "changed"
    assert second["source_digest"] != first["source_digest"]
    assert second["normalized_digest"] == first["normalized_digest"]
    assert (
        db_session.query(StandardsSourceSnapshot)
        .filter(StandardsSourceSnapshot.source_id == "google.search.core_web_vitals")
        .count()
        == 2
    )
    assert db_session.query(StandardsChangeCandidate).count() == 0


def test_source_failure_is_visible_and_preserves_last_success(db_session) -> None:
    standards_source_service.ensure_default_sources(db_session)
    responses = iter((200, 503))

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        status = next(responses)
        if status == 200:
            return httpx.Response(200, json={"incidents": []})
        return httpx.Response(503, text="temporarily unavailable")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = standards_source_service.check_source(
            db_session,
            source_id="google.search.status_incidents",
            client=client,
        )
        successful_at = first["last_success_at"]
        failed = standards_source_service.check_source(
            db_session,
            source_id="google.search.status_incidents",
            client=client,
        )

    assert failed["status"] == "check_failed"
    assert failed["error_code"] == "source_http_error"
    source = db_session.get(StandardsSourceRegistry, "google.search.status_incidents")
    assert source is not None
    assert source.last_success_at == successful_at
    assert source.last_http_status == 503
    status = standards_source_service.list_source_status(db_session)
    assert status["status"] == "attention_required"


def test_due_source_scheduler_queues_only_due_platform_owned_checks(
    db_session,
    monkeypatch,
) -> None:
    now = datetime(2026, 8, 5, 18, tzinfo=UTC)
    monkeypatch.setattr(
        durable_job_service,
        "get_settings",
        lambda: SimpleNamespace(
            intelligence_lexicon_enabled=True,
            standards_source_monitoring_enabled=True,
        ),
    )

    first = durable_job_service.enqueue_due_standards_source_checks(
        db_session,
        now=now,
        limit=25,
    )
    db_session.commit()

    assert first == len(standards_source_service.DEFAULT_STANDARDS_SOURCES)
    jobs = (
        db_session.query(PlatformJob)
        .filter(
            PlatformJob.job_type == durable_job_service.STANDARDS_SOURCE_CHECK_JOB_TYPE
        )
        .all()
    )
    assert len(jobs) == first
    assert all(job.tenant_id is None for job in jobs)
    assert all(job.payload["automatic_activation_allowed"] is False for job in jobs)

    source = db_session.get(StandardsSourceRegistry, "google.search.status_incidents")
    assert source is not None
    source.last_checked_at = now
    other = db_session.get(StandardsSourceRegistry, "google.search.docs_updates")
    assert other is not None
    other.last_checked_at = now - timedelta(days=2)
    db_session.commit()

    later = durable_job_service.enqueue_due_standards_source_checks(
        db_session,
        now=now + timedelta(hours=1),
        limit=25,
    )
    assert later >= 1


def test_source_status_is_platform_only_and_does_not_expose_snapshot_content(
    client,
) -> None:
    tenant_token = _login(client, "a@example.com", "pass-a")
    forbidden = client.get(
        "/api/v1/reference-library/standards/sources/status",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert forbidden.status_code == 403

    platform_token = _login(
        client,
        "platform-admin@example.com",
        "pass-platform-admin",
    )
    response = client.get(
        "/api/v1/reference-library/standards/sources/status",
        headers={"Authorization": f"Bearer {platform_token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["registered_sources"] == len(
        standards_source_service.DEFAULT_STANDARDS_SOURCES
    )
    assert payload["automatic_activation_allowed"] is False
    assert all("content_text" not in item for item in payload["items"])


def test_meaningful_source_change_creates_typed_candidate_and_impacts(db_session) -> None:
    standards_source_service.ensure_default_sources(db_session)
    payloads = iter(
        (
            "<html><body><p>LCP is good at 2.5 seconds or less.</p></body></html>",
            "<html><body><p>LCP is good at 2.0 seconds or less.</p></body></html>",
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text=next(payloads), headers={"content-type": "text/html"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = standards_source_service.check_source(
            db_session,
            source_id="google.search.core_web_vitals",
            client=client,
        )
        second = standards_source_service.check_source(
            db_session,
            source_id="google.search.core_web_vitals",
            client=client,
        )

    assert first["change_candidate_id"] is None
    assert second["change_type"] == "threshold_change"
    candidate = db_session.get(StandardsChangeCandidate, second["change_candidate_id"])
    assert candidate is not None
    assert candidate.status == "needs_review"
    assert candidate.automatic_activation_allowed is False
    impacts = (
        db_session.query(StandardsImpactLink)
        .filter(StandardsImpactLink.candidate_id == candidate.id)
        .all()
    )
    assert any(
        impact.impact_type == "metric_contract"
        and impact.impact_key == "core_web_vitals"
        and impact.is_blocking
        for impact in impacts
    )


def test_api_contract_change_blocks_provider_until_reviewed(db_session) -> None:
    standards_source_service.ensure_default_sources(db_session)
    payloads = iter(
        (
            "<html><body><p>The location field is supported.</p></body></html>",
            "<html><body><p>The location field is deprecated and will be removed.</p></body></html>",
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, text=next(payloads), headers={"content-type": "text/html"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        standards_source_service.check_source(
            db_session,
            source_id="google.business.api_change_log",
            client=client,
        )
        changed = standards_source_service.check_source(
            db_session,
            source_id="google.business.api_change_log",
            client=client,
        )

    assert changed["change_type"] == "api_field_or_deprecation_change"
    with pytest.raises(standards_source_service.StandardsContractBlockedError):
        standards_source_service.assert_provider_contract_ready(
            db_session,
            "google_business_profile",
        )

    reviewed = standards_source_service.review_change_candidate(
        db_session,
        candidate_id=changed["change_candidate_id"],
        disposition="no_product_impact",
        actor_user_id="platform-reviewer",
        note="Reviewed against the fields InsightOS requests.",
    )
    assert reviewed["status"] == "no_product_impact"
    assert reviewed["automatic_activation_allowed"] is False
    standards_source_service.assert_provider_contract_ready(
        db_session,
        "google_business_profile",
    )


def test_change_review_endpoints_are_platform_only(client, db_session) -> None:
    standards_source_service.ensure_default_sources(db_session)
    source = db_session.get(StandardsSourceRegistry, "google.search_console.metrics")
    assert source is not None
    previous = StandardsSourceSnapshot(
        source_id=source.source_id,
        source_uri=source.source_uri,
        source_format="html",
        parser_version=source.parser_version,
        http_status=200,
        source_digest="a" * 64,
        normalized_digest="b" * 64,
        content_bytes=40,
        content_text="<p>Clicks are counted when a user visits.</p>",
        observed_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
    )
    current = StandardsSourceSnapshot(
        source_id=source.source_id,
        source_uri=source.source_uri,
        source_format="html",
        parser_version=source.parser_version,
        http_status=200,
        source_digest="c" * 64,
        normalized_digest="d" * 64,
        content_bytes=52,
        content_text="<p>Clicks use a new metric definition and aggregation.</p>",
        observed_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
    )
    db_session.add_all([previous, current])
    db_session.flush()
    candidate = standards_source_service.create_change_candidate(
        db_session,
        source=source,
        previous_snapshot=previous,
        current_snapshot=current,
    )

    tenant_token = _login(client, "a@example.com", "pass-a")
    forbidden = client.get(
        "/api/v1/reference-library/standards/changes",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert forbidden.status_code == 403

    platform_token = _login(
        client,
        "platform-admin@example.com",
        "pass-platform-admin",
    )
    listed = client.get(
        "/api/v1/reference-library/standards/changes",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["id"] == candidate.id
    assert "diff" not in listed.json()["data"]["items"][0]

    detail = client.get(
        f"/api/v1/reference-library/standards/changes/{candidate.id}",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["diff"]["added"]

    reviewed = client.post(
        f"/api/v1/reference-library/standards/changes/{candidate.id}/review",
        headers={"Authorization": f"Bearer {platform_token}"},
        json={
            "disposition": "requires_contract_update",
            "note": "Replay and a new metric contract are required.",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["data"]["status"] == "requires_contract_update"
    assert reviewed.json()["data"]["automatic_activation_allowed"] is False
