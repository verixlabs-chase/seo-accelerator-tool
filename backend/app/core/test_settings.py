from app.core.settings import Settings


class TestSettings(Settings):
    app_env: str = "test"
    public_base_url: str = "http://testserver"
    jwt_secret: str = "test-jwt-secret-32-characters-minimum"
    platform_master_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    celery_task_always_eager: bool = True
    celery_task_eager_propagates: bool = True
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"
