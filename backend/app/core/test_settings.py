from app.core.settings import Settings
from pydantic import model_validator


class TestSettings(Settings):
    app_env: str = "test"
    public_base_url: str = "http://testserver"
    jwt_secret: str = "test-jwt-secret-32-characters-minimum"
    platform_master_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    celery_task_always_eager: bool = True
    celery_task_eager_propagates: bool = True
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"

    @model_validator(mode="before")
    @classmethod
    def _apply_test_defaults_for_blank_env(cls, values):
        if not isinstance(values, dict):
            return values
        values = dict(values)
        if not str(values.get("jwt_secret", "")).strip():
            values["jwt_secret"] = "test-jwt-secret-32-characters-minimum"
        if not str(values.get("platform_master_key", "")).strip():
            values["platform_master_key"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        if not str(values.get("public_base_url", "")).strip():
            values["public_base_url"] = "http://testserver"
        return values
