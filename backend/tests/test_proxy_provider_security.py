import json

from app.providers import proxy


def test_proxy_config_logging_redacts_secrets(monkeypatch) -> None:
    secret = "super-secret-proxy-token"
    calls: list[tuple[str, dict]] = []

    def _capture_info(message: str, **kwargs) -> None:
        calls.append((message, kwargs))

    monkeypatch.setattr(
        proxy,
        "get_settings",
        lambda: type(
            "S",
            (),
            {
                "proxy_provider_config_json": json.dumps(
                    {
                        "provider": "example-proxy",
                        "auth": {"username": "svc-user", "password": secret, "token": secret},
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(proxy.logger, "info", _capture_info)
    proxy.get_proxy_rotation_adapter.cache_clear()
    _adapter = proxy.get_proxy_rotation_adapter()

    assert calls
    message, kwargs = calls[0]
    assert "configured" in message.lower()
    assert secret not in message
    redacted_config = kwargs["extra"]["config"]
    assert redacted_config["auth"]["password"] == "***redacted***"
    assert redacted_config["auth"]["token"] == "***redacted***"
    assert redacted_config["auth"]["username"] == "***redacted***"


def test_proxy_invalid_json_does_not_log_raw_secret(monkeypatch) -> None:
    secret = "bad-json-secret"
    warning_calls: list[str] = []

    def _capture_warning(message: str, **_kwargs) -> None:
        warning_calls.append(message)

    monkeypatch.setattr(
        proxy,
        "get_settings",
        lambda: type("S", (), {"proxy_provider_config_json": f"{{not-json-{secret}"})(),
    )
    monkeypatch.setattr(proxy.logger, "warning", _capture_warning)
    proxy.get_proxy_rotation_adapter.cache_clear()
    _adapter = proxy.get_proxy_rotation_adapter()
    assert warning_calls
    assert all(secret not in message for message in warning_calls)
