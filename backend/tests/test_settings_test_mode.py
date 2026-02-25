from app.core import settings as settings_module


def test_get_settings_in_test_mode_without_jwt_secret(monkeypatch) -> None:
    settings_module.get_settings.cache_clear()
    try:
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("PLATFORM_MASTER_KEY", raising=False)
        monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

        settings = settings_module.get_settings()

        assert settings.app_env == "test"
        assert settings.jwt_secret == "test-secret-key"
    finally:
        settings_module.get_settings.cache_clear()
