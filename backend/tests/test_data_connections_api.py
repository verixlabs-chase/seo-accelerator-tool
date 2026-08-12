from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.models.analytics_daily_metric import AnalyticsDailyMetric
from app.models.data_connection import DataConnection
from app.models.search_console_daily_metric import SearchConsoleDailyMetric
from app.models.platform_job import PlatformJob
from app.services import data_connections_service, traffic_fact_service


def _login(client, email: str = "org-admin@example.com", password: str = "pass-org-admin") -> tuple[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["organization_id"]


def _create_location_campaign(client, token: str, organization_id: str, *, suffix: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={
            "name": f"Connection Location {suffix}",
            "domain": f"{suffix}.example.com",
            "city": "Austin",
            "region": "Texas",
            "country_code": "US",
        },
    )
    assert location_response.status_code == 200
    location_id = location_response.json()["data"]["business_location"]["id"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": f"Connection Campaign {suffix}",
            "domain": f"{suffix}.example.com",
            "business_location_id": location_id,
        },
    )
    assert campaign_response.status_code == 200
    campaign_id = campaign_response.json()["data"]["id"]
    return location_id, campaign_id


def _map_connection(client, token: str, organization_id: str, campaign_id: str, *, domain: str) -> dict:
    response = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/mappings/{campaign_id}"
        ),
        headers={"Authorization": f"Bearer {token}"},
        json={
            "external_resource_id": f"sc-domain:{domain}",
            "external_resource_name": domain,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["connection"]


def test_data_connections_list_is_tenant_scoped(client, db_session) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="tenant-scope",
    )
    mapped = _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="tenant-scope.example.com",
    )

    response = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["google_oauth"]["connected"] is False
    assert [item["id"] for item in payload["connections"]] == [mapped["id"]]
    assert payload["connections"][0]["business_location_name"] == "Connection Location tenant-scope"
    assert "shared website property" in payload["connections"][0]["source_truth"]
    assert db_session.query(DataConnection).filter(
        DataConnection.organization_id == organization_id
    ).count() == 1

    other_token, other_org = _login(client, "b@example.com", "pass-b")
    cross_scope = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert other_org != organization_id
    assert cross_scope.status_code == 403


def test_connection_health_uses_saved_freshness_and_plain_recovery_actions(
    client,
    db_session,
) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="health-center",
    )
    mapped = _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="health-center.example.com",
    )
    connection = db_session.get(DataConnection, mapped["id"])
    assert connection is not None
    connection.last_success_at = datetime.now(UTC)
    connection.status = data_connections_service.CONNECTION_STATUS_CONNECTED
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=organization_id,
            campaign_id=campaign_id,
            metric_date=date(2026, 8, 8),
            clicks=4,
            impressions=120,
            avg_position=8.5,
            deterministic_hash="9" * 64,
        )
    )
    db_session.commit()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    health = response.json()["data"]["health"]
    website_item = next(
        item
        for item in health["items"]
        if item["campaign_id"] == campaign_id
        and item["provider_name"] == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER
    )
    assert website_item["display_state"] == "healthy"
    assert website_item["newest_usable_data_date"] == "2026-08-08"
    assert website_item["recovery_action"]["label"] == "No action needed"
    assert website_item["affected_features"] == []

    listing_item = next(
        item
        for item in health["items"]
        if item["campaign_id"] == campaign_id
        and item["provider_name"] == "google_business_profile"
    )
    assert listing_item["display_state"] == "needs_setup"
    assert listing_item["recovery_action"]["label"] == "Reconnect Google"

    connection.status = data_connections_service.CONNECTION_STATUS_FAILED
    connection.last_error_message = "refresh_token=do-not-show-this"
    db_session.commit()
    failed_response = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    failed_item = next(
        item
        for item in failed_response.json()["data"]["health"]["items"]
        if item["campaign_id"] == campaign_id
        and item["provider_name"] == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER
    )
    assert failed_item["display_state"] == "needs_attention"
    assert failed_item["current_failure"] == "The last update did not finish."
    assert "do-not-show-this" not in str(failed_item)
    assert failed_item["recovery_action"] == {
        "kind": "reconnect",
        "label": "Reconnect Google",
        "href": "/settings",
    }

    connection.status = data_connections_service.CONNECTION_STATUS_DISCONNECTED
    db_session.commit()
    disconnected_response = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    disconnected_item = next(
        item
        for item in disconnected_response.json()["data"]["health"]["items"]
        if item["campaign_id"] == campaign_id
        and item["provider_name"] == data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER
    )
    assert disconnected_item["display_state"] == "needs_attention"
    assert disconnected_item["recovery_action"]["label"] == "Reconnect Google"


def test_search_console_resource_discovery_uses_owner_connection_flow(client, monkeypatch) -> None:
    token, organization_id = _login(client)
    monkeypatch.setattr(
        data_connections_service,
        "discover_search_console_resources",
        lambda _db, org_id: [
            {
                "id": "sc-domain:example.com",
                "name": "example.com",
                "permission_level": "siteOwner",
                "resource_scope": "domain_property",
            }
        ]
        if org_id == organization_id
        else [],
    )

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            "google-search-console/resources"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    resources = response.json()["data"]["resources"]
    assert resources[0]["id"] == "sc-domain:example.com"
    assert resources[0]["permission_level"] == "siteOwner"


def test_google_analytics_mapping_and_metrics_stay_location_scoped(client, db_session) -> None:
    token, organization_id = _login(client)
    location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="analytics-location",
    )
    mapping = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-analytics/mappings/{campaign_id}"
        ),
        headers={"Authorization": f"Bearer {token}"},
        json={"external_resource_id": "123456789", "external_resource_name": "Reno website"},
    )
    assert mapping.status_code == 200
    connection = mapping.json()["data"]["connection"]
    assert connection["provider_name"] == data_connections_service.GOOGLE_ANALYTICS_PROVIDER
    assert connection["business_location_id"] == location_id
    assert "read-only website visit" in connection["source_truth"].lower()

    for index in range(2):
        db_session.add(
            AnalyticsDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign_id,
                metric_date=date(2026, 8, 8 + index),
                sessions=10 + index,
                engaged_sessions=7 + index,
                conversions=1 + index,
                deterministic_hash=f"{index + 800:064d}",
            )
        )
    db_session.commit()

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-analytics/metrics/{campaign_id}?days=30"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["data_status"] == "ready"
    assert payload["summary"] == {
        "visits": 21,
        "engaged_visits": 15,
        "inquiries": 3,
        "engagement_rate_percent": 71.4,
    }
    assert [point["date"] for point in payload["points"]] == ["2026-08-08", "2026-08-09"]


def test_search_console_mapping_requires_business_location(client) -> None:
    token, organization_id = _login(client)
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Unassigned Connection", "domain": "unassigned.example.com"},
    )
    assert campaign_response.status_code == 200
    campaign_id = campaign_response.json()["data"]["id"]

    response = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/mappings/{campaign_id}"
        ),
        headers={"Authorization": f"Bearer {token}"},
        json={"external_resource_id": "sc-domain:unassigned.example.com"},
    )

    assert response.status_code == 409
    assert response.json()["errors"][0]["details"]["reason_code"] == "business_location_required"


def test_search_console_metrics_returns_location_scoped_stored_data(client, db_session) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="metrics-location",
    )
    _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="metrics-location.example.com",
    )
    start_date = date(2026, 6, 3)
    for index in range(56):
        metric_date = start_date + timedelta(days=index)
        db_session.add(
            SearchConsoleDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign_id,
                metric_date=metric_date,
                clicks=2 if index < 28 else 4,
                impressions=100 if index < 28 else 200,
                avg_position=12.0 if index < 28 else 9.0,
                deterministic_hash=f"{index:064d}",
            )
        )
    db_session.commit()

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}?days=28"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["data_status"] == "ready"
    assert payload["campaign_id"] == campaign_id
    assert payload["days_requested"] == 28
    assert payload["data_days"] == 28
    assert payload["coverage_percent"] == 100.0
    assert payload["date_from"] == "2026-07-01"
    assert payload["date_to"] == "2026-07-28"
    assert payload["summary"] == {
        "clicks": 112,
        "impressions": 5600,
        "ctr_percent": 2.0,
        "avg_position": 9.0,
    }
    assert payload["comparison"]["mode"] == "previous_period"
    assert payload["comparison"]["date_from"] == "2026-06-03"
    assert payload["comparison"]["date_to"] == "2026-06-30"
    assert payload["comparison"]["period_days"] == 28
    assert payload["comparison"]["data_days"] == 28
    assert payload["comparison"]["is_complete"] is True
    assert payload["comparison"]["clicks_change_percent"] == 100.0
    assert payload["comparison"]["impressions_change_percent"] == 100.0
    assert payload["comparison"]["position_improvement"] == 3.0
    assert len(payload["points"]) == 28
    assert len(payload["comparison_points"]) == 28
    assert payload["points"][0]["date"] == "2026-07-01"
    assert payload["points"][-1]["date"] == "2026-07-28"


def test_search_console_metrics_compares_custom_date_ranges(client, db_session) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="custom-metrics-range",
    )
    _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="custom-metrics-range.example.com",
    )
    start_date = date(2026, 6, 1)
    for index in range(40):
        metric_date = start_date + timedelta(days=index)
        is_july = metric_date.month == 7
        db_session.add(
            SearchConsoleDailyMetric(
                organization_id=organization_id,
                campaign_id=campaign_id,
                metric_date=metric_date,
                clicks=6 if is_july else 3,
                impressions=300 if is_july else 150,
                avg_position=8.0 if is_july else 11.0,
                deterministic_hash=f"custom-{index:056d}",
            )
        )
    db_session.commit()

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}"
            "?date_from=2026-07-01&date_to=2026-07-10"
            "&comparison_mode=custom"
            "&comparison_date_from=2026-06-01"
            "&comparison_date_to=2026-06-10"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["date_from"] == "2026-07-01"
    assert payload["date_to"] == "2026-07-10"
    assert payload["days_requested"] == 10
    assert payload["summary"]["clicks"] == 60
    assert payload["comparison"]["mode"] == "custom"
    assert payload["comparison"]["date_from"] == "2026-06-01"
    assert payload["comparison"]["date_to"] == "2026-06-10"
    assert payload["comparison"]["summary"]["clicks"] == 30
    assert payload["comparison"]["change_is_comparable"] is True
    assert payload["comparison"]["clicks_change_percent"] == 100.0
    assert payload["comparison"]["position_improvement"] == 3.0
    assert len(payload["points"]) == 10
    assert len(payload["comparison_points"]) == 10

    db_session.query(SearchConsoleDailyMetric).filter(
        SearchConsoleDailyMetric.organization_id == organization_id,
        SearchConsoleDailyMetric.campaign_id == campaign_id,
        SearchConsoleDailyMetric.metric_date == date(2026, 7, 5),
    ).delete()
    db_session.commit()
    incomplete_response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}"
            "?date_from=2026-07-01&date_to=2026-07-10"
            "&comparison_mode=custom"
            "&comparison_date_from=2026-06-01"
            "&comparison_date_to=2026-06-10"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    incomplete = incomplete_response.json()["data"]
    assert incomplete["data_days"] == 9
    assert incomplete["comparison"]["change_is_comparable"] is False
    assert incomplete["comparison"]["clicks_change_percent"] is None
    assert incomplete["comparison"]["position_improvement"] is None


def test_search_console_metrics_rejects_invalid_custom_date_ranges(
    client,
    db_session,
) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="invalid-metrics-range",
    )
    _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="invalid-metrics-range.example.com",
    )
    db_session.add(
        SearchConsoleDailyMetric(
            organization_id=organization_id,
            campaign_id=campaign_id,
            metric_date=date(2026, 7, 10),
            clicks=1,
            impressions=10,
            avg_position=10.0,
            deterministic_hash="invalid-range".ljust(64, "0"),
        )
    )
    db_session.commit()

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}"
            "?date_from=2026-07-10&date_to=2026-07-01"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["errors"][0]["details"]["reason_code"] == "invalid_date_range"

    unequal_response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}"
            "?date_from=2026-07-01&date_to=2026-07-10"
            "&comparison_mode=custom"
            "&comparison_date_from=2026-06-01"
            "&comparison_date_to=2026-06-05"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert unequal_response.status_code == 400
    assert (
        unequal_response.json()["errors"][0]["details"]["reason_code"]
        == "comparison_period_length_mismatch"
    )


def test_search_console_metrics_explains_when_location_is_not_connected(client) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="metrics-unmapped",
    )

    response = client.get(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-search-console/metrics/{campaign_id}"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["data_status"] == "not_connected"
    assert payload["connection"] is None
    assert payload["summary"] is None
    assert payload["points"] == []


def test_search_console_sync_is_durable_and_idempotent(client, db_session, monkeypatch) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="durable-sync",
    )
    mapped = _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="durable-sync.example.com",
    )
    calls: list[dict] = []

    def _sync(**kwargs):
        calls.append(kwargs)
        return traffic_fact_service.TrafficFactSyncResult(
            organization_id=organization_id,
            campaign_id=campaign_id,
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            requested_days=28,
            provider_calls=1,
            inserted_rows=28,
            updated_rows=0,
            skipped_rows=0,
        )

    monkeypatch.setattr(
        traffic_fact_service,
        "sync_search_console_daily_metrics_for_campaign",
        _sync,
    )
    endpoint = (
        f"/api/v1/organizations/{organization_id}/data-connections/{mapped['id']}/sync"
    )
    first = client.post(endpoint, headers={"Authorization": f"Bearer {token}"})
    second = client.post(endpoint, headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert first.json()["data"]["job"]["status"] == "completed"
    assert first.json()["data"]["connection"]["status"] == "current"
    assert second.status_code == 200
    assert second.json()["data"]["job"]["idempotent_replay"] is True
    assert len(calls) == 1
    assert calls[0]["site_url"] == "sc-domain:durable-sync.example.com"
    assert (calls[0]["end_date"] - calls[0]["start_date"]).days + 1 == 480
    assert db_session.query(PlatformJob).filter(
        PlatformJob.entity_id == mapped["id"]
    ).count() == 1

    connection = db_session.get(DataConnection, mapped["id"])
    db_session.refresh(connection)
    assert connection is not None
    assert connection.status == "current"
    assert connection.last_success_at is not None
    assert connection.next_sync_at is not None
    assert connection.sync_cursor.get("last_metric_date")
    assert connection.sync_cursor.get("history_start_date")
    assert connection.sync_cursor.get("history_days") == 480


def test_google_analytics_sync_is_durable_and_uses_saved_property(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="analytics-durable",
    )
    mapping = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-analytics/mappings/{campaign_id}"
        ),
        headers={"Authorization": f"Bearer {token}"},
        json={"external_resource_id": "987654321", "external_resource_name": "Main website"},
    )
    assert mapping.status_code == 200
    mapped = mapping.json()["data"]["connection"]
    calls: list[dict] = []

    def _sync(**kwargs):
        calls.append(kwargs)
        return traffic_fact_service.TrafficFactSyncResult(
            organization_id=organization_id,
            campaign_id=campaign_id,
            start_date=kwargs["start_date"],
            end_date=kwargs["end_date"],
            requested_days=480,
            provider_calls=1,
            inserted_rows=480,
            updated_rows=0,
            skipped_rows=0,
        )

    monkeypatch.setattr(
        traffic_fact_service,
        "sync_analytics_daily_metrics_for_campaign",
        _sync,
    )
    endpoint = f"/api/v1/organizations/{organization_id}/data-connections/{mapped['id']}/sync"
    first = client.post(endpoint, headers={"Authorization": f"Bearer {token}"})
    second = client.post(endpoint, headers={"Authorization": f"Bearer {token}"})

    assert first.status_code == 200
    assert first.json()["data"]["job"]["status"] == "completed"
    assert second.status_code == 200
    assert second.json()["data"]["job"]["idempotent_replay"] is True
    assert len(calls) == 1
    assert calls[0]["property_id"] == "987654321"
    assert (calls[0]["end_date"] - calls[0]["start_date"]).days + 1 == 480
    assert db_session.query(PlatformJob).filter(PlatformJob.entity_id == mapped["id"]).count() == 1


def test_search_console_sync_failure_is_visible_without_cross_tenant_leak(
    client,
    db_session,
    monkeypatch,
) -> None:
    token, organization_id = _login(client)
    _location_id, campaign_id = _create_location_campaign(
        client,
        token,
        organization_id,
        suffix="failed-sync",
    )
    mapped = _map_connection(
        client,
        token,
        organization_id,
        campaign_id,
        domain="failed-sync.example.com",
    )

    def _fail(**_kwargs):
        raise RuntimeError("Search Console dependency unavailable")

    monkeypatch.setattr(
        traffic_fact_service,
        "sync_search_console_daily_metrics_for_campaign",
        _fail,
    )
    response = client.post(
        f"/api/v1/organizations/{organization_id}/data-connections/{mapped['id']}/sync",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["job"]["status"] == "queued"
    connection = db_session.get(DataConnection, mapped["id"])
    db_session.refresh(connection)
    assert connection is not None
    assert connection.status == "failed"
    assert connection.last_error_code == "sync_failed"
    assert connection.last_error_message == "Search Console dependency unavailable"


def test_effective_connection_status_marks_old_success_stale(monkeypatch) -> None:
    connection = DataConnection(
        tenant_id="tenant",
        organization_id="organization",
        business_location_id="location",
        campaign_id="campaign",
        provider_name=data_connections_service.GOOGLE_SEARCH_CONSOLE_PROVIDER,
        external_resource_id="sc-domain:example.com",
        status="current",
        last_success_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    status = data_connections_service.effective_connection_status(
        connection,
        now=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert status == "stale"
