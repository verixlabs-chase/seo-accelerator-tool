from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from app.core.settings import Settings


class TestSettings(Settings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore', env_ignore_empty=True)

    app_env: str = 'test'
    public_base_url: str = 'http://testserver'
    jwt_secret: str = 'test-jwt-secret-32-characters-minimum'
    platform_master_key: str = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
    celery_task_always_eager: bool = True
    celery_task_eager_propagates: bool = True
    celery_broker_url: str = 'memory://'
    celery_result_backend: str = 'cache+memory://'

    @model_validator(mode='before')
    @classmethod
    def apply_required_test_defaults(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        defaults = {
            'jwt_secret': 'test-jwt-secret-32-characters-minimum',
            'public_base_url': 'http://testserver',
            'platform_master_key': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
        }
        for key, value in defaults.items():
            raw = data.get(key)
            if raw is None or not str(raw).strip():
                data[key] = value
        return data
