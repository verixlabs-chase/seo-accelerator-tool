import base64

from app.models.organization import Organization
from app.models.wordpress_site_connection import WordPressSiteConnection
from app.services.wordpress_connection_service import get_site_credentials
from tests.conftest import create_test_campaign


MASTER_KEY_B64 = base64.b64encode(
    b"0123456789abcdef0123456789abcdef"
).decode("ascii")


def _login(client) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    return payload["access_token"], payload["user"]["tenant_id"]


def _growth_campaign(client, db_session, monkeypatch, *, domain: str = "paired.example"):
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    token, tenant_id = _login(client)
    organization = db_session.get(Organization, tenant_id)
    assert organization is not None
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant_id,
        name="WordPress Pairing Campaign",
        domain=domain,
    )
    db_session.commit()
    return token, campaign


def test_wordpress_pairing_is_one_time_site_scoped_and_encrypted(
    client, db_session, monkeypatch
) -> None:
    token, campaign = _growth_campaign(client, db_session, monkeypatch)

    start = client.post(
        "/api/v1/provider-health/wordpress-pairing/start",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200
    pairing = start.json()["data"]
    assert len(pairing["pairing_code"].replace("-", "")) == 24
    assert pairing["site_url"] == "https://paired.example"
    assert "plugin_token" not in str(start.json())

    wrong_site = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": pairing["pairing_code"],
            "site_url": "https://other.example",
            "plugin_version": "1.4.0",
        },
    )
    assert wrong_site.status_code == 403
    assert (
        wrong_site.json()["errors"][0]["details"]["reason_code"]
        == "wordpress_pairing_site_mismatch"
    )

    exchange = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": pairing["pairing_code"],
            "site_url": "https://www.paired.example",
            "plugin_version": "1.4.0",
        },
    )
    assert exchange.status_code == 200
    exchanged = exchange.json()["data"]
    assert exchanged["connected"] is True
    assert exchanged["plugin_token"]
    assert exchanged["shared_secret"]

    row = db_session.query(WordPressSiteConnection).filter_by(campaign_id=campaign.id).one()
    db_session.refresh(row)
    assert row.status == "connected"
    assert row.pairing_code_hash is None
    assert exchanged["plugin_token"] not in str(row.encrypted_secret_blob)
    assert exchanged["shared_secret"] not in str(row.encrypted_secret_blob)
    saved = get_site_credentials(db_session, campaign_id=campaign.id)
    assert saved["plugin_token"] == exchanged["plugin_token"]

    replay = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": pairing["pairing_code"],
            "site_url": "https://paired.example",
            "plugin_version": "1.4.0",
        },
    )
    assert replay.status_code == 404


def test_wordpress_repairing_rotates_one_site_and_disconnect_wipes_keys(
    client, db_session, monkeypatch
) -> None:
    token, campaign = _growth_campaign(
        client, db_session, monkeypatch, domain="rotate.example"
    )

    def pair_once() -> dict:
        start_response = client.post(
            "/api/v1/provider-health/wordpress-pairing/start",
            params={"campaign_id": campaign.id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert start_response.status_code == 200
        pairing = start_response.json()["data"]
        exchange_response = client.post(
            "/api/v1/provider-health/wordpress-pairing/exchange",
            json={
                "pairing_code": pairing["pairing_code"],
                "site_url": "https://rotate.example",
                "plugin_version": "1.4.0",
            },
        )
        assert exchange_response.status_code == 200
        return exchange_response.json()["data"]

    first = pair_once()
    second_start = client.post(
        "/api/v1/provider-health/wordpress-pairing/start",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_start.status_code == 200
    assert second_start.json()["data"]["replaces_existing_connection"] is True
    second = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": second_start.json()["data"]["pairing_code"],
            "site_url": "https://rotate.example",
            "plugin_version": "1.4.0",
        },
    ).json()["data"]
    assert second["plugin_token"] != first["plugin_token"]
    assert second["shared_secret"] != first["shared_secret"]

    disconnected = client.delete(
        "/api/v1/provider-health/wordpress-connection",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["data"]["disconnected"] is True
    db_session.expire_all()
    row = db_session.query(WordPressSiteConnection).filter_by(campaign_id=campaign.id).one()
    assert row.status == "disconnected"
    assert row.encrypted_secret_blob is None
    assert get_site_credentials(db_session, campaign_id=campaign.id) == {}
