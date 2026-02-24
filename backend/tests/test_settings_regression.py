import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from app.core.test_settings import TestSettings as AppTestSettings


def test_production_settings_requires_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('JWT_SECRET', raising=False)
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://example.com')
    monkeypatch.setenv('PLATFORM_MASTER_KEY', 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    assert 'jwt_secret' in str(exc_info.value)


def test_testsettings_uses_safe_default_without_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('JWT_SECRET', raising=False)
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'http://testserver')
    monkeypatch.setenv('PLATFORM_MASTER_KEY', 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')

    settings = AppTestSettings()

    assert settings.jwt_secret == 'test-jwt-secret-32-characters-minimum'
