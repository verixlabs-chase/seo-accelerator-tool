import os
from functools import lru_cache

from pydantic import model_validator
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
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = False
    crawl_min_request_interval_seconds: float = 0.2
    crawl_timeout_seconds: float = 10.0
    crawl_use_playwright: bool = False
    crawl_max_pages_per_run: int = 200
    crawl_max_discovered_links_per_page: int = 50
    crawl_frontier_batch_size: int = 25
    crawl_max_active_runs_per_tenant: int = 5
    crawl_max_active_runs_per_campaign: int = 2
    rank_provider_backend: str = "synthetic"
    local_provider_backend: str = "synthetic"
    authority_provider_backend: str = "synthetic"
    rank_provider_http_endpoint: str = ""
    rank_provider_http_timeout_seconds: float = 15.0
    rank_provider_http_auth_header: str = ""
    rank_provider_http_auth_token: str = ""
    rank_provider_http_keyword_field: str = "keyword"
    rank_provider_http_location_field: str = "location_code"
    rank_provider_serpapi_api_key: str = ""
    rank_provider_serpapi_endpoint: str = "https://serpapi.com/search.json"
    rank_provider_serpapi_timeout_seconds: float = 15.0
    rank_provider_serpapi_engine: str = "google"
    rank_provider_serpapi_default_gl: str = "us"
    rank_provider_serpapi_default_hl: str = "en"

    object_storage_endpoint: str = ""
    object_storage_bucket: str = ""
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    proxy_provider_config_json: str = ""
    log_level: str = "INFO"
    metrics_enabled: bool = False
    otel_exporter_endpoint: str = ""
    reference_library_loader_enabled: bool = True
    reference_library_hot_reload_enabled: bool = False
    reference_library_enforce_validation: bool = True
    reference_library_seed_path: str = ""

    @model_validator(mode="after")
    def validate_production_guardrails(self) -> "Settings":
        if self.app_env.lower() != "production":
            return self

        if self.jwt_secret in {"", "local-dev-secret", "replace-me"} or len(self.jwt_secret) < 32:
            raise ValueError("Production requires JWT_SECRET with at least 32 characters.")

        if self.postgres_dsn.startswith("sqlite"):
            raise ValueError("Production requires POSTGRES_DSN backed by PostgreSQL.")

        required = {
            "OBJECT_STORAGE_ENDPOINT": self.object_storage_endpoint,
            "OBJECT_STORAGE_BUCKET": self.object_storage_bucket,
            "OBJECT_STORAGE_ACCESS_KEY": self.object_storage_access_key,
            "OBJECT_STORAGE_SECRET_KEY": self.object_storage_secret_key,
            "SMTP_HOST": self.smtp_host,
            "SMTP_USERNAME": self.smtp_username,
            "SMTP_PASSWORD": self.smtp_password,
            "SMTP_FROM_EMAIL": self.smtp_from_email,
            "OTEL_EXPORTER_ENDPOINT": self.otel_exporter_endpoint,
        }
        missing = [key for key, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Production is missing required settings: {', '.join(missing)}")

        return self


@lru_cache
def get_settings() -> Settings:
    if os.getenv("APP_ENV", "").lower() == "test":
        from app.core.test_settings import TestSettings

        return TestSettings()
    return Settings()
