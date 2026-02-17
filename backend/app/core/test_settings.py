from app.core.settings import Settings


class TestSettings(Settings):
    app_env: str = "test"
    celery_task_always_eager: bool = True
    celery_task_eager_propagates: bool = True
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"
