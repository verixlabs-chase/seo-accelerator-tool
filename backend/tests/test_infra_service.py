from app.services import infra_service


class _FakeRedis:
    def __init__(self, *, exists_value: int = 1, ttl_value: int = 60, ping_value: bool = True, raises: bool = False):
        self._exists_value = exists_value
        self._ttl_value = ttl_value
        self._ping_value = ping_value
        self._raises = raises

    def ping(self) -> bool:
        if self._raises:
            raise RuntimeError("redis down")
        return self._ping_value

    def exists(self, _key: str) -> int:
        if self._raises:
            raise RuntimeError("redis down")
        return self._exists_value

    def ttl(self, _key: str) -> int:
        if self._raises:
            raise RuntimeError("redis down")
        return self._ttl_value


def test_worker_active_true_when_heartbeat_exists_and_ttl_positive(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=1, ttl_value=60),
    )
    assert infra_service.worker_active() is True


def test_worker_active_false_when_heartbeat_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=0, ttl_value=60),
    )
    assert infra_service.worker_active() is False


def test_worker_active_false_when_ttl_non_positive(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(exists_value=1, ttl_value=0),
    )
    assert infra_service.worker_active() is False


def test_redis_connected_false_on_redis_exception(monkeypatch):
    monkeypatch.setattr(
        "app.services.infra_service._healthcheck_redis_client",
        lambda: _FakeRedis(raises=True),
    )
    assert infra_service.redis_connected() is False
