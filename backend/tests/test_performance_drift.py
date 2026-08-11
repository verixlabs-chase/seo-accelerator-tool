from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import json
import uuid

from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.standards_governance import PerformanceDriftEvent
from app.services import performance_drift_service
from app.services.performance_drift_service import MinimizedDriftObservation
from tests.conftest import create_test_campaign


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_minimum_sample_detector_requires_broad_direction_agreement() -> None:
    insufficient = performance_drift_service.analyze_minimized_cohort(
        [
            MinimizedDriftObservation(
                organization_key=f"org-{index}",
                sample_key=f"sample-{index}",
                baseline_value=100,
                comparison_value=70,
            )
            for index in range(4)
        ],
        metric_name="impressions",
    )
    assert insufficient["status"] == "insufficient_sample"

    signal = performance_drift_service.analyze_minimized_cohort(
        [
            MinimizedDriftObservation(
                organization_key=f"org-{index}",
                sample_key=f"sample-{index}",
                baseline_value=100,
                comparison_value=70 + index,
            )
            for index in range(5)
        ],
        metric_name="impressions",
    )
    assert signal["status"] == "signal_detected"
    assert signal["direction"] == "down"
    assert signal["organization_count"] == 5
    assert signal["agreement_ratio"] == 1.0


def test_drift_check_persists_minimized_idempotent_event_and_owner_review(
    client, db_session
) -> None:
    comparison_end = date(2026, 8, 9)
    baseline_start = comparison_end - timedelta(days=27)
    organization_ids: list[str] = []
    metric_versions = {
        "search_console.clicks": "1.0",
        "search_console.impressions": "1.0",
        "search_console.ctr": "1.0",
        "search_console.position": "1.0",
    }
    for index in range(5):
        organization_id = str(uuid.uuid4())
        organization_ids.append(organization_id)
        campaign = create_test_campaign(
            db_session,
            organization_id,
            tenant_id=organization_id,
            name=f"Drift sample {index}",
        )
        campaign.created_at = datetime(2026, 6, 1, tzinfo=UTC)
        for offset in range(28):
            metric_date = baseline_start + timedelta(days=offset)
            in_comparison = offset >= 14
            impressions = 70 + index if in_comparison else 100
            clicks = 7 + index if in_comparison else 10
            db_session.add(
                SearchConsoleDailyMetric(
                    organization_id=organization_id,
                    campaign_id=campaign.id,
                    metric_date=metric_date,
                    clicks=clicks,
                    impressions=impressions,
                    ctr=float(clicks) / float(impressions),
                    avg_position=4.5 if in_comparison else 3.0,
                    property_uri=f"sc-domain:sample-{index}.test",
                    search_type="web",
                    dimensions=["date"],
                    filters={},
                    metric_contract_versions=metric_versions,
                    scope_key=f"scope-{index}",
                    deterministic_hash=(f"{index:x}{offset:x}" * 64)[:64],
                    captured_at=datetime(2026, 8, 10, tzinfo=UTC),
                    created_at=datetime(2026, 8, 10, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 10, tzinfo=UTC),
                )
            )
    db_session.commit()

    tenant_token = _login(client, "a@example.com", "pass-a")
    blocked = client.post(
        "/api/v1/reference-library/standards/drift/check",
        headers={"Authorization": f"Bearer {tenant_token}"},
        json={"metrics": ["impressions"], "period_days": 14, "as_of": "2026-08-09"},
    )
    assert blocked.status_code == 403

    admin_token = _login(client, "platform-admin@example.com", "pass-platform-admin")
    body = {
        "metrics": ["impressions"],
        "period_days": 14,
        "as_of": "2026-08-09",
        "minimum_organizations": 5,
    }
    first = client.post(
        "/api/v1/reference-library/standards/drift/check",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=body,
    )
    assert first.status_code == 200, first.text
    payload = first.json()["data"]
    assert payload["status"] == "completed"
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    assert event["label"] == "possible_ecosystem_change"
    assert event["status"] == "needs_review"
    assert event["organization_count"] == 5
    assert event["automatic_activation_allowed"] is False
    serialized = json.dumps(event)
    assert all(organization_id not in serialized for organization_id in organization_ids)

    second = client.post(
        "/api/v1/reference-library/standards/drift/check",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=body,
    )
    assert second.status_code == 200
    assert db_session.query(PerformanceDriftEvent).count() == 1

    admin_review = client.post(
        f"/api/v1/reference-library/standards/drift/events/{event['id']}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "investigating", "note": "Check provider health."},
    )
    assert admin_review.status_code == 403

    owner_token = _login(client, "platform-owner@example.com", "pass-platform-owner")
    reviewed = client.post(
        f"/api/v1/reference-library/standards/drift/events/{event['id']}/review",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "status": "investigating",
            "note": "Provider health is normal; compare affected markets before any response.",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["status"] == "investigating"
    assert reviewed.json()["data"]["automatic_activation_allowed"] is False
