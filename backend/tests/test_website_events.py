from __future__ import annotations

from datetime import UTC, datetime

from app.models.data_connection import DataConnection
from app.models.website_analytics import WebsiteFormEvent


def _login(client) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "org-admin@example.com", "password": "pass-org-admin"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data["access_token"], data["user"]["organization_id"]


def _mapped_analytics_connection(client) -> tuple[str, str, str, str]:
    token, organization_id = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    location_response = client.post(
        f"/api/v1/organizations/{organization_id}/business-locations",
        headers=headers,
        json={
            "name": "Secure Event Location",
            "domain": "secure-events.example.com",
            "city": "Reno",
            "region": "Nevada",
            "country_code": "US",
        },
    )
    assert location_response.status_code == 200
    location_id = location_response.json()["data"]["business_location"]["id"]
    campaign_response = client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "name": "Secure Event Campaign",
            "domain": "secure-events.example.com",
            "business_location_id": location_id,
        },
    )
    assert campaign_response.status_code == 200
    campaign_id = campaign_response.json()["data"]["id"]
    mapping = client.put(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"google-analytics/mappings/{campaign_id}"
        ),
        headers=headers,
        json={"external_resource_id": "123456789", "external_resource_name": "Main website"},
    )
    assert mapping.status_code == 200
    connection_id = mapping.json()["data"]["connection"]["id"]
    return token, organization_id, location_id, connection_id


def _create_key(client, token: str, organization_id: str, connection_id: str) -> dict:
    response = client.post(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"{connection_id}/website-events/key"
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()["data"]


def _event_payload(**overrides) -> dict:
    payload = {
        "event_id": "evt-secure-0001",
        "event_name": "inquiry_confirmed",
        "page_url": "https://secure-events.example.com/contact?email=private@example.com",
        "form_id": "contact-main",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


def test_form_event_key_is_returned_once_and_ingest_is_private_and_idempotent(
    client,
    db_session,
) -> None:
    token, organization_id, location_id, connection_id = _mapped_analytics_connection(client)
    key = _create_key(client, token, organization_id, connection_id)
    assert key["token"]
    assert key["event_path"].endswith(connection_id)

    listing = client.get(
        f"/api/v1/organizations/{organization_id}/data-connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200
    serialized = next(
        item
        for item in listing.json()["data"]["connections"]
        if item["id"] == connection_id
    )
    assert serialized["website_event_key_configured"] is True
    assert "website_event_token_hash" not in serialized
    assert "token" not in serialized

    endpoint = f"/api/v1/website-events/forms/{connection_id}"
    event_headers = {"Authorization": f"Bearer {key['token']}"}
    payload = _event_payload()
    first = client.post(endpoint, headers=event_headers, json=payload)
    replay = client.post(endpoint, headers=event_headers, json=payload)
    assert first.status_code == 200
    assert first.json()["data"]["duplicate"] is False
    assert replay.status_code == 200
    assert replay.json()["data"]["duplicate"] is True

    rows = db_session.query(WebsiteFormEvent).filter_by(data_connection_id=connection_id).all()
    assert len(rows) == 1
    assert rows[0].organization_id == organization_id
    assert rows[0].business_location_id == location_id
    assert rows[0].page_url == "https://secure-events.example.com/contact"
    assert "private@example.com" not in rows[0].page_url


def test_form_event_rejects_changed_replay_unknown_fields_wrong_domain_and_wrong_key(
    client,
    db_session,
) -> None:
    token, organization_id, _location_id, connection_id = _mapped_analytics_connection(client)
    key = _create_key(client, token, organization_id, connection_id)
    endpoint = f"/api/v1/website-events/forms/{connection_id}"
    headers = {"Authorization": f"Bearer {key['token']}"}

    assert client.post(endpoint, headers=headers, json=_event_payload()).status_code == 200
    conflict = client.post(
        endpoint,
        headers=headers,
        json=_event_payload(form_id="changed-form"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["errors"][0]["details"]["reason_code"] == "website_event_id_conflict"

    unknown_field = client.post(
        endpoint,
        headers=headers,
        json=_event_payload(event_id="evt-secure-0002", email="should-not-be-accepted@example.com"),
    )
    assert unknown_field.status_code == 422
    wrong_domain = client.post(
        endpoint,
        headers=headers,
        json=_event_payload(
            event_id="evt-secure-0003",
            page_url="https://unrelated.example.net/contact",
        ),
    )
    assert wrong_domain.status_code == 400
    wrong_key = client.post(
        endpoint,
        headers={"Authorization": "Bearer wrong-key"},
        json=_event_payload(event_id="evt-secure-0004"),
    )
    assert wrong_key.status_code == 401
    assert db_session.query(WebsiteFormEvent).filter_by(data_connection_id=connection_id).count() == 1


def test_rotating_form_event_key_invalidates_the_previous_key(client) -> None:
    token, organization_id, _location_id, connection_id = _mapped_analytics_connection(client)
    first_key = _create_key(client, token, organization_id, connection_id)
    second_key = _create_key(client, token, organization_id, connection_id)
    endpoint = f"/api/v1/website-events/forms/{connection_id}"

    rejected = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {first_key['token']}"},
        json=_event_payload(),
    )
    accepted = client.post(
        endpoint,
        headers={"Authorization": f"Bearer {second_key['token']}"},
        json=_event_payload(),
    )
    assert rejected.status_code == 401
    assert accepted.status_code == 200


def test_form_event_key_rotation_requires_an_organization_admin(client, db_session) -> None:
    token, organization_id, _location_id, connection_id = _mapped_analytics_connection(client)
    member_login = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": "pass-member"},
    )
    if member_login.status_code != 200:
        return
    member_token = member_login.json()["data"]["access_token"]
    response = client.post(
        (
            f"/api/v1/organizations/{organization_id}/data-connections/"
            f"{connection_id}/website-events/key"
        ),
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert response.status_code in {401, 403}
    connection = db_session.get(DataConnection, connection_id)
    assert not (connection.connection_metadata or {}).get("website_event_token_hash")
