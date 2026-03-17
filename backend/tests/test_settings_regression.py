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


def test_non_test_settings_require_explicit_sensitive_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="local",
            public_base_url="http://localhost",
            postgres_dsn="postgresql://user:pass@db:5432/app",
        )


def test_non_test_settings_reject_weak_local_style_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="local",
            public_base_url="http://localhost",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="dev-secret",
            platform_master_key="dev-master-key",
        )


def test_local_admin_bootstrap_is_forbidden_outside_local_runtime() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="test",
            public_base_url="http://testserver",
            postgres_dsn="sqlite:///:memory:",
            jwt_secret="test-secret-key",
            platform_master_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            local_admin_bootstrap_enabled=True,
        )


def test_testsettings_uses_safe_default_without_jwt_secret() -> None:
    settings = AppTestSettings(jwt_secret="")
    assert settings.jwt_secret == "test-jwt-secret-32-characters-minimum"


def test_local_admin_bootstrap_is_disabled_by_default() -> None:
    settings = Settings(
        _env_file=None,
        postgres_dsn="postgresql://user:pass@db:5432/app",
        jwt_secret="local-dev-jwt-secret-change-before-shared-use",
        platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        public_base_url="http://localhost",
    )
    assert settings.local_admin_bootstrap_enabled is False
