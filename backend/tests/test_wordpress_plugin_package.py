from __future__ import annotations

import hashlib
import io
from zipfile import ZipFile

from app.models.organization import Organization
from app.services.wordpress_plugin_package_service import build_wordpress_plugin_package
from tests.conftest import create_test_campaign


def test_wordpress_plugin_package_is_deterministic_and_installable() -> None:
    first = build_wordpress_plugin_package()
    second = build_wordpress_plugin_package()

    assert first.content == second.content
    assert first.version == "1.5.1"
    assert first.filename == "insightos-wordpress-1.5.1.zip"
    assert first.sha256 == hashlib.sha256(first.content).hexdigest()
    assert first.file_count == 7

    with ZipFile(io.BytesIO(first.content)) as archive:
        names = archive.namelist()
        assert names == sorted(names, key=str.lower)
        assert "lsos-execution-plugin/lsos-execution-plugin.php" in names
        assert "lsos-execution-plugin/includes/class-lsos-settings-page.php" in names
        assert all(name.startswith("lsos-execution-plugin/") for name in names)
        assert all(".env" not in name for name in names)
        assert all("wp-config.php" not in name for name in names)
        entrypoint = archive.read("lsos-execution-plugin/lsos-execution-plugin.php")
        assert b"Plugin Name: LSOS WordPress Execution Plugin" in entrypoint
        assert b"Version: 1.5.1" in entrypoint
        assert b"test-secret-never-package" not in first.content


def test_wordpress_plugin_download_requires_plan_and_returns_verified_zip(
    client,
    db_session,
) -> None:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": "pass-a"},
    )
    assert login.status_code == 200
    login_data = login.json()["data"]
    token = login_data["access_token"]
    tenant_id = login_data["user"]["tenant_id"]
    organization = db_session.get(Organization, tenant_id)
    assert organization is not None
    campaign = create_test_campaign(
        db_session,
        organization.id,
        tenant_id=tenant_id,
        name="WordPress Package Campaign",
        domain="wordpress-package.example",
    )
    headers = {"Authorization": f"Bearer {token}"}

    denied = client.get(
        "/api/v1/provider-health/wordpress-plugin-download",
        params={"campaign_id": campaign.id},
        headers=headers,
    )
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["details"]["reason_code"] == (
        "wordpress_execution_upgrade_required"
    )

    organization.plan_type = "multi_location"
    db_session.commit()
    response = client.get(
        "/api/v1/provider-health/wordpress-plugin-download",
        params={"campaign_id": campaign.id},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-insightos-plugin-version"] == "1.5.1"
    assert "insightos-wordpress-1.5.1.zip" in response.headers["content-disposition"]
    assert response.headers["x-insightos-package-sha256"] == hashlib.sha256(
        response.content
    ).hexdigest()
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert "lsos-execution-plugin/lsos-execution-plugin.php" in archive.namelist()
