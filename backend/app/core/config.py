from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LSOS API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"

    jwt_secret: str = "local-dev-secret"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800
    jwt_algorithm: str = "HS256"

    postgres_dsn: str = "sqlite:///./lsos.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    crawl_min_request_interval_seconds: float = 0.2


@lru_cache
def get_settings() -> Settings:
    return Settings()
