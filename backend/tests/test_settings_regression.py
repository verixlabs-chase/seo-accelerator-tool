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
            cron_secret="hosted-cron-secret-with-at-least-32-characters",
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
    assert settings.intelligence_activation_mode == "recommendation_only"


def test_autonomous_intelligence_is_forbidden_outside_test_runtime() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="local",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="local-dev-jwt-secret-change-before-shared-use",
            platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            public_base_url="http://localhost",
            intelligence_activation_mode="autonomous",
        )


def test_rotation_key_lists_reject_duplicates_and_weak_values() -> None:
    active_jwt = "active-jwt-secret-with-at-least-32-characters"
    active_master_key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    with pytest.raises(ValidationError, match="must not include JWT_SECRET"):
        Settings(
            _env_file=None,
            app_env="production",
            hosted_serverless=True,
            cron_secret="hosted-cron-secret-with-at-least-32-characters",
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret=active_jwt,
            jwt_previous_secrets_json=f'["{active_jwt}"]',
            platform_master_key=active_master_key,
        )
    with pytest.raises(ValidationError, match="Previous JWT secrets"):
        Settings(
            _env_file=None,
            app_env="production",
            hosted_serverless=True,
            cron_secret="hosted-cron-secret-with-at-least-32-characters",
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret=active_jwt,
            jwt_previous_secrets_json='["weak"]',
            platform_master_key=active_master_key,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"rate_limit_backend": "memory"}, "RATE_LIMIT_BACKEND"),
        ({"rate_limit_identity_source": "forwarded"}, "RATE_LIMIT_IDENTITY_SOURCE"),
        ({"rate_limit_requests_per_minute": 0}, "RATE_LIMIT_REQUESTS_PER_MINUTE"),
        ({"rate_limit_requests_per_minute": 1_000_001}, "RATE_LIMIT_REQUESTS_PER_MINUTE"),
    ],
)
def test_rate_limit_settings_reject_unsupported_or_nonpositive_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            app_env="test",
            public_base_url="http://testserver",
            postgres_dsn="sqlite:///:memory:",
            jwt_secret="test-secret-key",
            platform_master_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            **overrides,
        )


def test_enabled_non_test_rate_limit_requires_dedicated_strong_hmac_secret() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_HMAC_SECRET"):
        Settings(
            _env_file=None,
            app_env="local",
            public_base_url="http://localhost",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="local-jwt-secret-with-at-least-32-characters",
            platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            rate_limit_hmac_secret="",
        )


def test_hosted_production_rejects_redis_rate_limit_backend() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_BACKEND=postgres"):
        Settings(
            _env_file=None,
            app_env="production",
            hosted_serverless=True,
            vercel=True,
            cron_secret="hosted-cron-secret-with-at-least-32-characters",
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="production-jwt-secret-with-at-least-32-characters",
            platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            rate_limit_enabled=True,
            rate_limit_backend="redis",
            rate_limit_identity_source="vercel",
            rate_limit_hmac_secret="rate-limit-hmac-secret-with-at-least-32-characters",
        )


def test_hosted_vercel_rate_limit_rejects_peer_identity_source() -> None:
    with pytest.raises(ValidationError, match="RATE_LIMIT_IDENTITY_SOURCE=vercel"):
        Settings(
            _env_file=None,
            app_env="production",
            hosted_serverless=True,
            vercel=True,
            cron_secret="hosted-cron-secret-with-at-least-32-characters",
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="production-jwt-secret-with-at-least-32-characters",
            platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            rate_limit_identity_source="peer",
            rate_limit_hmac_secret="rate-limit-hmac-secret-with-at-least-32-characters",
        )


@pytest.mark.parametrize("cron_secret", ["", "short", "replace-me"])
def test_hosted_production_requires_strong_cron_secret(cron_secret: str) -> None:
    with pytest.raises(ValidationError, match="CRON_SECRET"):
        Settings(
            _env_file=None,
            app_env="production",
            hosted_serverless=True,
            vercel=True,
            public_base_url="https://example.com",
            postgres_dsn="postgresql://user:pass@db:5432/app",
            jwt_secret="production-jwt-secret-with-at-least-32-characters",
            platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
            cron_secret=cron_secret,
            rate_limit_enabled=True,
            rate_limit_backend="postgres",
            rate_limit_identity_source="vercel",
            rate_limit_hmac_secret="rate-limit-hmac-secret-with-at-least-32-characters",
        )


def test_hosted_production_accepts_database_rate_limit_and_strong_cron_secret_without_redis() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        hosted_serverless=True,
        vercel=True,
        cron_secret="hosted-cron-secret-with-at-least-32-characters",
        public_base_url="https://example.com",
        postgres_dsn="postgresql://user:pass@db:5432/app",
        jwt_secret="production-jwt-secret-with-at-least-32-characters",
        platform_master_key="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        rate_limit_enabled=True,
        rate_limit_backend="postgres",
        rate_limit_identity_source="vercel",
        rate_limit_hmac_secret="rate-limit-hmac-secret-with-at-least-32-characters",
        redis_url="",
    )

    assert settings.rate_limit_enabled is True
    assert settings.rate_limit_backend == "postgres"
    assert settings.rate_limit_identity_source == "vercel"
    assert settings.cron_secret == "hosted-cron-secret-with-at-least-32-characters"
