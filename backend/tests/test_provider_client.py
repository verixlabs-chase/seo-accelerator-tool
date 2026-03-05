import time

import pytest

from app.services.provider_client import ProviderCallError, call_provider


def test_call_provider_success() -> None:
    result = call_provider('google', 'ping', lambda: {'ok': True}, timeout=2, retries=1)
    assert result == {'ok': True}


def test_call_provider_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {'count': 0}

    def _flaky() -> dict:
        attempts['count'] += 1
        if attempts['count'] < 3:
            raise RuntimeError('transient')
        return {'ok': True}

    monkeypatch.setattr(time, 'sleep', lambda _: None)
    result = call_provider('google', 'retryable', _flaky, timeout=2, retries=3)

    assert result == {'ok': True}
    assert attempts['count'] == 3


def test_call_provider_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, 'sleep', lambda _: None)

    with pytest.raises(ProviderCallError):
        call_provider('google', 'always_fail', lambda: (_ for _ in ()).throw(RuntimeError('fail')), timeout=1, retries=2)
