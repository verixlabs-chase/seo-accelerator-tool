from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta

from app.models.provider_metric_contract import ProviderMetricContractVersion
from app.services import action_plan_measurement_service, metric_contract_service


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_default_metric_contract_registry_is_versioned_and_truthful(db_session) -> None:
    rows = metric_contract_service.ensure_default_contracts(db_session)

    assert len(rows) == len(metric_contract_service.DEFAULT_METRIC_CONTRACTS)
    assert db_session.query(ProviderMetricContractVersion).count() == len(rows)
    assert all(row.version == "1.0" for row in rows)
    assert all(row.automatic_activation_allowed is False for row in rows)
    indexing = next(row for row in rows if row.contract_id == "search.indexing_state")
    response_time = next(row for row in rows if row.contract_id == "reputation.response_time")
    assert indexing.collection_status == "not_collected"
    assert response_time.collection_status == "not_collected"


def test_scope_keys_change_only_when_comparison_scope_changes() -> None:
    base = {
        "organization_id": "org-1",
        "campaign_id": "campaign-1",
        "property_uri": "sc-domain:example.com",
        "search_type": "web",
        "dimensions": ["date"],
        "filters": {},
        "window_start": "2026-07-01",
        "window_end": "2026-07-31",
    }
    later = {
        **base,
        "window_start": "2026-08-01",
        "window_end": "2026-08-31",
    }
    different_property = {**later, "property_uri": "sc-domain:other.example"}

    first = metric_contract_service.scope_evidence("search_console.clicks", base)
    second = metric_contract_service.scope_evidence("search_console.clicks", later)
    third = metric_contract_service.scope_evidence(
        "search_console.clicks", different_property
    )

    assert first["scope_key"] == second["scope_key"]
    assert first["scope_key"] != third["scope_key"]


def test_incomplete_objective_scope_fails_closed() -> None:
    with pytest.raises(metric_contract_service.MetricContractScopeError) as error:
        metric_contract_service.scope_evidence(
            "web.crux.lcp",
            {
                "organization_id": "org-1",
                "campaign_id": "campaign-1",
                "measured_url": "https://example.com/",
            },
        )

    assert "form_factor" in error.value.missing_fields
    assert "collection_start" in error.value.missing_fields


def test_metric_contract_registry_endpoint_is_platform_only(client) -> None:
    tenant_token = _login(client, "a@example.com", "pass-a")
    forbidden = client.get(
        "/api/v1/reference-library/standards/contracts",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert forbidden.status_code == 403

    platform_token = _login(
        client,
        "platform-admin@example.com",
        "pass-platform-admin",
    )
    response = client.get(
        "/api/v1/reference-library/standards/contracts?provider_name=google_search_console",
        headers={"Authorization": f"Bearer {platform_token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["items"]
    assert all(
        item["provider_name"] == "google_search_console" for item in payload["items"]
    )
    assert payload["automatic_activation_allowed"] is False


def test_action_result_rejects_a_metric_contract_version_boundary() -> None:
    completed_at = datetime(2026, 8, 1, tzinfo=UTC)
    baseline = {
        "value": 100.0,
        "direction": "higher_is_better",
        "metric_contract_id": "search_console.clicks",
        "metric_contract_version": "1.0",
        "scope_key": "same-scope",
        "source_provider": "google_search_console",
        "aggregation": "sum",
        "scope": "campaign",
        "measurement_window_days": 28,
        "entity_scope": {"campaign_id": "campaign-1"},
        "source_record_id": "before",
    }
    observed = {
        **baseline,
        "value": 125.0,
        "metric_contract_version": "2.0",
        "source_record_id": "after",
        "measured_at": (completed_at + timedelta(days=28)).isoformat(),
    }

    result = action_plan_measurement_service._comparison(
        baseline,
        observed,
        work_completed_at=completed_at,
    )

    assert result["comparison"] == "insufficient_data"
    assert result["comparison_requirements_met"] is False
    assert result["change"] is None
