from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from app.core.test_settings import TestSettings as AppTestSettings


def test_production_settings_requires_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            jwt_secret="",
            platform_master_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            object_storage_endpoint="https://storage.example.com",
            object_storage_bucket="bucket",
            object_storage_access_key="key",
            object_storage_secret_key="secret",
            smtp_host="smtp.example.com",
            smtp_username="user",
            smtp_password="pass",
            smtp_from_email="noreply@example.com",
            otel_exporter_endpoint="https://otel.example.com",
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
        )


def test_testsettings_uses_safe_default_without_jwt_secret() -> None:
    settings = AppTestSettings(jwt_secret="")
    assert settings.jwt_secret == "test-jwt-secret-32-characters-minimum"
