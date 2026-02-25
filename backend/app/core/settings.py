import os
import base64
import binascii
import sys
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LSOS API"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    public_base_url: str

    jwt_secret: str
    platform_master_key: str
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800
    jwt_algorithm: str = "HS256"

    postgres_dsn: str = "sqlite:///./lsos.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False
    celery_task_eager_propagates: bool = False
    celery_worker_prefetch_multiplier: int = 1
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
    competitor_provider_backend: str = "dataset"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_scope: str = "https://www.googleapis.com/auth/business.manage"
    google_oauth_scope_gbp: str = "https://www.googleapis.com/auth/business.manage"
    google_oauth_scope_gsc: str = "https://www.googleapis.com/auth/webmasters.readonly"
    google_oauth_auth_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_endpoint: str = "https://oauth2.googleapis.com/token"
    google_oauth_state_ttl_seconds: int = 600
    google_oauth_http_timeout_seconds: float = 15.0
    google_oauth_access_token_skew_seconds: int = 60
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
    metrics_require_auth: bool = False
    metrics_allowed_ips: str = ""
    max_request_body_bytes: int = 2_000_000
    rate_limit_requests_per_minute: int = 60
    rate_limit_enabled: bool = False
    queue_backpressure_threshold: int = 100
    queue_backpressure_enabled: bool = False
    shadow_replay_enabled: bool = True
    shadow_replay_backpressure_disable: bool = True
    shadow_replay_max_concurrency: int = 4
    otel_exporter_endpoint: str = ""
    reference_library_loader_enabled: bool = True
    reference_library_hot_reload_enabled: bool = False
    reference_library_enforce_validation: bool = True
    reference_library_seed_path: str = ""

    @model_validator(mode="after")
    def validate_production_guardrails(self) -> "Settings":
        if not self.jwt_secret.strip():
            raise ValueError("JWT_SECRET is required and must not be empty.")
        if not self.platform_master_key.strip():
            raise ValueError("PLATFORM_MASTER_KEY is required and must not be empty.")
        if not self.public_base_url.strip():
            raise ValueError("PUBLIC_BASE_URL is required and must not be empty.")

        if self.app_env.lower() != "production":
            return self

        if self.jwt_secret in {"", "local-dev-secret", "replace-me"} or len(self.jwt_secret) < 32:
            raise ValueError("Production requires JWT_SECRET with at least 32 characters.")
        if self.google_oauth_client_secret.strip() in {"replace-me", "local-dev-secret"}:
            raise ValueError("Production forbids weak GOOGLE_OAUTH_CLIENT_SECRET default values.")
        if self.google_oauth_client_id.strip() in {"replace-me", "local-dev-client-id"}:
            raise ValueError("Production forbids weak GOOGLE_OAUTH_CLIENT_ID default values.")
        if self.platform_master_key in {"", "replace-me", "local-dev-master-key"}:
            raise ValueError("Production requires PLATFORM_MASTER_KEY and forbids weak default values.")
        try:
            decoded_master_key = base64.b64decode(self.platform_master_key)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Production requires PLATFORM_MASTER_KEY to be valid base64.") from exc
        if len(decoded_master_key) != 32:
            raise ValueError("Production requires PLATFORM_MASTER_KEY to decode to exactly 32 bytes.")

        parsed_public_base = urlparse(self.public_base_url)
        host = (parsed_public_base.hostname or "").lower()
        if not parsed_public_base.scheme or not host:
            raise ValueError("Production requires PUBLIC_BASE_URL to be an absolute URL.")
        if host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Production forbids localhost PUBLIC_BASE_URL for OAuth redirects.")

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
    app_env = os.getenv("APP_ENV", "").lower()
    is_pytest_runtime = "pytest" in sys.modules
    if app_env == "test" or (not app_env and is_pytest_runtime):
        def _env_or_default(name: str, default: str) -> str:
            value = os.getenv(name)
            if value is None:
                return default
            stripped = value.strip()
            return stripped if stripped else default

        return Settings(
            app_env="test",
            public_base_url=_env_or_default("PUBLIC_BASE_URL", "http://testserver"),
            jwt_secret=_env_or_default("JWT_SECRET", "test-secret-key"),
            platform_master_key=_env_or_default("PLATFORM_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),
            celery_task_always_eager=True,
            celery_task_eager_propagates=True,
            celery_broker_url="memory://",
            celery_result_backend="cache+memory://",
            competitor_provider_backend="fixture",
        )
    return Settings()
