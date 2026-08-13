import base64

import pytest

from app.intelligence.executors import wordpress_plugin
from app.models.organization import Organization
from app.models.wordpress_content_inventory import (
    WordPressContentItem,
    WordPressContentSyncRun,
)
from tests.conftest import create_test_campaign


MASTER_KEY_B64 = base64.b64encode(
    b"0123456789abcdef0123456789abcdef"
).decode("ascii")


def _inventory_item(post_id: int, *, url: str, description: str = "") -> dict:
    return {
        "wp_post_id": post_id,
        "post_type": "page",
        "publication_status": "publish",
        "slug": f"page-{post_id}",
        "url": url,
        "title": f"Page {post_id}",
        "meta_title": f"Page {post_id} | Example",
        "meta_description": description,
        "canonical_url": url,
        "headings": [{"level": 1, "text": f"Page {post_id}"}],
        "internal_links": ["https://example.com/contact"],
        "schema_types": ["Service"] if post_id == 1 else [],
        "schema_present": post_id == 1,
        "word_count": 250 + post_id,
        "revision_id": f"revision:{100 + post_id}",
        "content_hash": f"{post_id}" * 64,
        "modified_at": "2026-08-12T12:00:00+00:00",
    }


def test_wordpress_inventory_reads_bounded_pages_and_checks_site(monkeypatch) -> None:
    calls: list[int] = []
    health: list[dict] = []
    monkeypatch.setattr(
        wordpress_plugin,
        "_resolve_site_config",
        lambda db, campaign_id: {
            "mode": "live",
            "base_url": "https://example.com",
            "token": "token",
            "shared_secret": "secret",
            "timeout_seconds": 5,
            "tenant_id": "tenant-1",
            "site_id": "example.com",
        },
    )

    def fake_post(config, path, payload):  # noqa: ANN001
        calls.append(payload["page"])
        post_id = payload["page"]
        return {
            "plugin_version": "1.4.0",
            "wordpress_version": "6.8.2",
            "php_version": "8.3",
            "site_url": "https://www.example.com",
            "page": payload["page"],
            "total_items": 2,
            "total_pages": 2,
            "seo_plugins": [{"name": "Yoast SEO", "version": "25.0"}],
            "items": [
                _inventory_item(post_id, url=f"https://example.com/page-{post_id}")
            ],
        }

    monkeypatch.setattr(wordpress_plugin, "_post_json", fake_post)
    monkeypatch.setattr(
        wordpress_plugin,
        "track_plugin_health",
        lambda db, **kwargs: health.append(kwargs),
    )

    result = wordpress_plugin.fetch_content_inventory(object(), campaign_id="campaign-1")
    assert calls == [1, 2]
    assert result["total_items"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["revision_id"] == "revision:101"
    assert health[0]["healthy"] is True

    with pytest.raises(wordpress_plugin.WordPressExecutionError) as exc_info:
        wordpress_plugin._normalize_inventory_item(
            _inventory_item(3, url="https://another.example/page"),
            "https://example.com",
        )
    assert exc_info.value.reason_code == "wordpress_inventory_invalid"


def test_wordpress_inventory_api_persists_current_metadata_without_page_body(
    client, db_session, monkeypatch
) -> None:
    monkeypatch.setenv("PLATFORM_MASTER_KEY", MASTER_KEY_B64)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert login.status_code == 200
    payload = login.json()["data"]
    token = payload["access_token"]
    tenant_id = payload["user"]["tenant_id"]
    organization = db_session.get(Organization, tenant_id)
    assert organization is not None
    organization.plan_type = "multi_location"
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant_id,
        name="Inventory Campaign",
        domain="example.com",
    )
    db_session.commit()

    start = client.post(
        "/api/v1/provider-health/wordpress-pairing/start",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert start.status_code == 200
    exchange = client.post(
        "/api/v1/provider-health/wordpress-pairing/exchange",
        json={
            "pairing_code": start.json()["data"]["pairing_code"],
            "site_url": "https://example.com",
            "plugin_version": "1.4.0",
        },
    )
    assert exchange.status_code == 200

    monkeypatch.setattr(
        "app.services.wordpress_content_inventory_service.wordpress_plugin.fetch_content_inventory",
        lambda db, campaign_id: {
            "mode": "live",
            "plugin_version": "1.4.0",
            "wordpress_version": "6.8.2",
            "php_version": "8.3",
            "site_url": "https://example.com",
            "seo_plugins": [{"name": "Yoast SEO", "version": "25.0"}],
            "total_items": 2,
            "truncated": False,
            "items": [
                _inventory_item(1, url="https://example.com/services", description="Service description"),
                _inventory_item(2, url="https://example.com/about"),
            ],
        },
    )
    sync = client.post(
        "/api/v1/provider-health/wordpress-content-sync",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sync.status_code == 200
    result = sync.json()["data"]
    assert result["summary"]["pages_found"] == 2
    assert result["summary"]["missing_description"] == 1
    assert result["summary"]["with_schema"] == 1
    assert "post_content" not in str(result)
    assert "Nothing on the website was changed" in result["message"]

    saved_run = db_session.query(WordPressContentSyncRun).filter_by(campaign_id=campaign.id).one()
    assert saved_run.status == "complete"
    assert saved_run.item_count == 2
    saved_items = db_session.query(WordPressContentItem).filter_by(sync_run_id=saved_run.id).all()
    assert len(saved_items) == 2
    assert all(item.content_hash for item in saved_items)
    assert all(item.revision_id for item in saved_items)

    listed = client.get(
        "/api/v1/provider-health/wordpress-content-inventory",
        params={"campaign_id": campaign.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["url"].startswith("https://example.com/")
