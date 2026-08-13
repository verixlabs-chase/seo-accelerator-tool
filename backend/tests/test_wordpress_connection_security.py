import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.intelligence.executors import wordpress_plugin


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_wordpress_request_signature_binds_one_time_nonce(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout):  # noqa: ANN001
        captured["request"] = req
        captured["timeout"] = timeout
        return _FakeHttpResponse({"plugin_version": "1.4.0"})

    monkeypatch.setattr(wordpress_plugin.request, "urlopen", fake_urlopen)
    response = wordpress_plugin._post_json(
        {
            "base_url": "https://example.com",
            "token": "site-token",
            "shared_secret": "shared-secret",
            "timeout_seconds": 5,
        },
        "/wp-json/lsos/v1/health",
        {"check": "connection_health"},
    )
    assert response["plugin_version"] == "1.4.0"
    request = captured["request"]
    timestamp = request.headers["X-lsos-timestamp"]
    nonce = request.headers["X-lsos-nonce"]
    signature = request.headers["X-lsos-signature"]
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-agent"] == wordpress_plugin.WORDPRESS_CONNECTOR_USER_AGENT
    assert len(nonce) == 32
    expected = hmac.new(
        b"shared-secret",
        timestamp.encode("utf-8") + b"." + nonce.encode("ascii") + b"." + request.data,
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(signature, expected)


def test_wordpress_connection_handshake_requires_matching_site_and_permissions(monkeypatch) -> None:
    health_calls: list[dict] = []
    monkeypatch.setattr(
        wordpress_plugin,
        "_resolve_site_config",
        lambda db, campaign_id: {
            "mode": "live",
            "base_url": "https://www.example.com",
            "token": "token",
            "shared_secret": "secret",
            "timeout_seconds": 5,
            "tenant_id": "tenant-1",
            "site_id": "example.com",
        },
    )
    monkeypatch.setattr(
        wordpress_plugin,
        "_post_json",
        lambda config, path, payload: {
            "plugin_version": "1.4.0",
            "wordpress_version": "6.8.2",
            "php_version": "8.3",
            "site_url": "https://example.com",
            "permissions": {
                "mutations": True,
                "rollback": True,
                "health_check": True,
                "content_inventory": True,
                "change_preview": True,
            },
            "supported_actions": ["update_meta_title"],
        },
    )
    monkeypatch.setattr(
        wordpress_plugin,
        "track_plugin_health",
        lambda db, **kwargs: health_calls.append(kwargs),
    )

    result = wordpress_plugin.check_connection(object(), campaign_id="campaign-1")
    assert result["connected"] is True
    assert result["site_url"] == "https://example.com"
    assert result["supported_actions"] == ["update_meta_title"]
    assert health_calls[0]["healthy"] is True
    assert health_calls[0]["plugin_version"] == "1.4.0"


def test_wordpress_connection_handshake_fails_closed_on_site_mismatch(monkeypatch) -> None:
    failures: list[dict] = []
    monkeypatch.setattr(
        wordpress_plugin,
        "_resolve_site_config",
        lambda db, campaign_id: {
            "mode": "live",
            "base_url": "https://expected.example",
            "token": "token",
            "shared_secret": "secret",
            "timeout_seconds": 5,
            "tenant_id": "tenant-1",
            "site_id": "expected.example",
        },
    )
    monkeypatch.setattr(
        wordpress_plugin,
        "_post_json",
        lambda config, path, payload: {
            "plugin_version": "1.4.0",
            "site_url": "https://different.example",
            "permissions": {
                "mutations": True,
                "rollback": True,
                "health_check": True,
                "content_inventory": True,
                "change_preview": True,
            },
        },
    )
    monkeypatch.setattr(
        wordpress_plugin,
        "detect_plugin_failure",
        lambda db, **kwargs: failures.append(kwargs),
    )

    with pytest.raises(wordpress_plugin.WordPressExecutionError) as exc_info:
        wordpress_plugin.check_connection(object(), campaign_id="campaign-1")
    assert exc_info.value.reason_code == "wordpress_site_mismatch"
    assert failures[0]["reason_code"] == "wordpress_site_mismatch"


def test_wordpress_plugin_contract_contains_health_and_replay_protection() -> None:
    plugin_root = (
        Path(__file__).resolve().parents[1]
        / "wordpress_execution_plugin"
        / "lsos-execution-plugin"
    )
    main = (plugin_root / "lsos-execution-plugin.php").read_text(encoding="utf-8")
    auth = (plugin_root / "includes" / "class-lsos-auth.php").read_text(encoding="utf-8")
    rest = (plugin_root / "includes" / "class-lsos-rest-controller.php").read_text(
        encoding="utf-8"
    )
    mutation_engine = (
        plugin_root / "includes" / "class-lsos-dom-mutation-engine.php"
    ).read_text(encoding="utf-8")
    store = (plugin_root / "includes" / "class-lsos-audit-store.php").read_text(
        encoding="utf-8"
    )
    settings = (plugin_root / "includes" / "class-lsos-settings-page.php").read_text(
        encoding="utf-8"
    )
    assert "Version: 1.5.1" in main
    assert "x-lsos-nonce" in auth
    assert "lsos_replayed_request" in auth
    assert "claim_request_nonce" in auth
    assert "'/health'" in rest
    assert "lsos_request_nonces" in store
    assert "lsos_pair_site" in settings
    assert "manage_options" in settings
    assert "pairing_code" in settings
    assert "WordPress administrator password" in settings
    assert "lsos_execution_plugin_disconnected" in settings
    assert "lsos_execution_plugin_disconnected" in auth
    assert "'/connection/disconnect'" in rest
    assert "'/content/inventory'" in rest
    assert "'/mutations/preview'" in rest
    assert "assert_preview_is_current" in rest
    assert "expected_version" in mutation_engine
    assert "post_version" in mutation_engine
    assert "content_from_payload" in mutation_engine
    assert "wordpress_preview_stale" in rest
    assert rest.index("get_mutation($mutation_id)") < rest.index(
        "assert_preview_is_current($mutation)"
    )
    assert "content_hash" in rest
    assert "revision_id" in rest
    assert "meta_description" in rest
    assert "pre_get_document_title" in (
        plugin_root / "includes" / "class-lsos-execution-plugin.php"
    ).read_text(encoding="utf-8")
    assert "render_meta_description" in (
        plugin_root / "includes" / "class-lsos-execution-plugin.php"
    ).read_text(encoding="utf-8")
