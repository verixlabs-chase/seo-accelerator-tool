import os
import base64
import binascii
import json
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
    public_base_url: str = 'http://localhost'
    local_admin_bootstrap_enabled: bool = False
    hosted_serverless: bool = False
    startup_invariants_enabled: bool = True
    cron_secret: str = ""
    durable_job_batch_size: int = 5
    durable_job_lease_seconds: int = 120
    durable_job_retry_base_seconds: int = 30
    intelligence_activation_mode: str = "recommendation_only"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    jwt_secret: str
    jwt_previous_secrets_json: str = "[]"
    platform_master_key: str
    platform_previous_master_keys_json: str = "[]"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 604800
    jwt_algorithm: str = "HS256"

    postgres_dsn: str
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 30
    database_rls_enabled: bool = False
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
    local_rank_grid_provider_backend: str = ""
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
    traffic_fact_sync_lookback_days: int = 7
    traffic_fact_sync_hour_utc: int = 2
    traffic_fact_sync_minute_utc: int = 0
    traffic_fact_max_staleness_days: int = 2
    data_connection_initial_backfill_days: int = 480
    data_connection_sync_delay_days: int = 2
    data_connection_sync_interval_hours: int = 24
    customer_app_base_url: str = ""
    google_oauth_access_token_skew_seconds: int = 60
    rank_provider_http_endpoint: str = ""
    rank_provider_http_timeout_seconds: float = 15.0
    rank_provider_http_auth_header: str = ""
    rank_provider_http_auth_token: str = ""
    rank_provider_http_keyword_field: str = "keyword"
    rank_provider_http_location_field: str = "location_code"
    rank_provider_dataforseo_endpoint: str = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    rank_provider_dataforseo_timeout_seconds: float = 30.0
    rank_provider_dataforseo_language_code: str = "en"
    rank_provider_dataforseo_depth: int = 100
    local_rank_grid_task_post_endpoint: str = "https://api.dataforseo.com/v3/serp/google/maps/task_post"
    local_rank_grid_task_get_endpoint: str = "https://api.dataforseo.com/v3/serp/google/maps/task_get/advanced"
    local_rank_grid_timeout_seconds: float = 30.0
    local_rank_grid_language_code: str = "en"
    local_rank_grid_depth: int = 100
    local_rank_grid_zoom: int = 15
    dataforseo_locations_endpoint: str = "https://api.dataforseo.com/v3/serp/google/locations"
    location_geocoder_endpoint: str = "https://nominatim.openstreetmap.org/search"
    location_resolver_timeout_seconds: float = 20.0
    service_area_places_endpoint: str = "https://overpass-api.de/api/interpreter"
    service_area_places_timeout_seconds: float = 20.0
    service_area_drive_time_api_key: str = ""
    service_area_drive_time_endpoint: str = (
        "https://api.openrouteservice.org/v2/isochrones/driving-car"
    )
    service_area_drive_time_timeout_seconds: float = 30.0
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
    max_concurrent_requests: int = 2000
    max_requests_per_tenant: int = 200
    max_queue_depth: int = 10000
    max_worker_inflight: int = 2000
    knowledge_graph_batch_size: int = 100
    knowledge_graph_flush_interval_ms: int = 500
    event_stream_batch_size: int = 100
    campaign_execution_lock_timeout_seconds: int = 30
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
    intelligence_lexicon_enabled: bool = True
    action_measurement_readiness_enabled: bool = True
    action_plan_forecasting_enabled: bool = True
    crux_api_key: str = ""
    cwv_standards_probe_origin: str = "https://web.dev"
    cwv_standards_review_interval_days: int = 30
    standards_source_monitoring_enabled: bool = True
    standards_source_http_timeout_seconds: float = 15.0
    standards_source_max_content_bytes: int = 1_000_000
    pagespeed_api_key: str = ""
    website_performance_collection_interval_hours: int = 168
    website_performance_http_timeout_seconds: float = 45.0
    ai_provider_backend: str = "mistral"
    mistral_api_key: str = ""
    mistral_api_endpoint: str = "https://api.mistral.ai/v1/chat/completions"
    mistral_model: str = "mistral-small-2603"
    ai_provider_timeout_seconds: float = 30.0
    ai_provider_max_attempts: int = 2
    ai_max_input_tokens: int = 12_000
    ai_max_output_tokens: int = 800

    _WEAK_JWT_SECRET_VALUES = {
        "",
        "test-secret",
        "test-secret-key",
        "dev-secret",
        "local-dev-secret",
        "replace-me",
    }
    _WEAK_PLATFORM_MASTER_KEY_VALUES = {
        "",
        "test-master-key",
        "dev-master-key",
        "local-dev-master-key",
        "replace-me",
    }

    @staticmethod
    def _rotation_secret_list(raw_value: str, *, setting_name: str) -> list[str]:
        try:
            parsed = json.loads(raw_value or "[]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{setting_name} must be a JSON array of strings.") from exc
        if not isinstance(parsed, list) or any(
            not isinstance(value, str) or not value.strip()
            for value in parsed
        ):
            raise ValueError(f"{setting_name} must be a JSON array of non-empty strings.")
        normalized = [value.strip() for value in parsed]
        if len(normalized) != len(set(normalized)):
            raise ValueError(f"{setting_name} must not contain duplicate values.")
        if len(normalized) > 2:
            raise ValueError(f"{setting_name} supports at most two previous keys.")
        return normalized

    def jwt_verification_secrets(self) -> tuple[str, ...]:
        previous = self._rotation_secret_list(
            self.jwt_previous_secrets_json,
            setting_name="JWT_PREVIOUS_SECRETS_JSON",
        )
        return (self.jwt_secret, *previous)

    def credential_master_keys(self) -> tuple[bytes, ...]:
        encoded_keys = [
            self.platform_master_key,
            *self._rotation_secret_list(
                self.platform_previous_master_keys_json,
                setting_name="PLATFORM_PREVIOUS_MASTER_KEYS_JSON",
            ),
        ]
        decoded_keys: list[bytes] = []
        for encoded_key in encoded_keys:
            try:
                decoded = base64.b64decode(encoded_key, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError(
                    "Credential master keys must be valid base64."
                ) from exc
            if len(decoded) != 32:
                raise ValueError(
                    "Credential master keys must decode to exactly 32 bytes."
                )
            decoded_keys.append(decoded)
        return tuple(decoded_keys)

    @model_validator(mode="after")
    def validate_production_guardrails(self) -> "Settings":
        intelligence_mode = self.intelligence_activation_mode.strip().lower()
        if intelligence_mode not in {"recommendation_only", "autonomous"}:
            raise ValueError(
                "INTELLIGENCE_ACTIVATION_MODE must be recommendation_only or autonomous."
            )
        if intelligence_mode == "autonomous" and self.app_env.lower() != "test":
            raise ValueError(
                "Autonomous intelligence execution is disabled outside the test runtime."
            )
        self.intelligence_activation_mode = intelligence_mode
        ai_backend = self.ai_provider_backend.strip().lower()
        if ai_backend not in {"disabled", "mistral"}:
            raise ValueError(
                "AI_PROVIDER_BACKEND must be disabled or mistral."
            )
        if self.ai_provider_max_attempts < 1 or self.ai_provider_max_attempts > 3:
            raise ValueError("AI_PROVIDER_MAX_ATTEMPTS must be between 1 and 3.")
        if self.ai_max_input_tokens < 1 or self.ai_max_output_tokens < 1:
            raise ValueError("AI token ceilings must be positive.")
        self.ai_provider_backend = ai_backend

        if not self.jwt_secret.strip():
            raise ValueError("JWT_SECRET is required and must not be empty.")
        if not self.platform_master_key.strip():
            raise ValueError("PLATFORM_MASTER_KEY is required and must not be empty.")
        if not self.public_base_url.strip():
            raise ValueError("PUBLIC_BASE_URL is required and must not be empty.")
        previous_jwt_secrets = self._rotation_secret_list(
            self.jwt_previous_secrets_json,
            setting_name="JWT_PREVIOUS_SECRETS_JSON",
        )
        previous_master_keys = self._rotation_secret_list(
            self.platform_previous_master_keys_json,
            setting_name="PLATFORM_PREVIOUS_MASTER_KEYS_JSON",
        )
        if self.jwt_secret in previous_jwt_secrets:
            raise ValueError("JWT_PREVIOUS_SECRETS_JSON must not include JWT_SECRET.")
        if self.platform_master_key in previous_master_keys:
            raise ValueError(
                "PLATFORM_PREVIOUS_MASTER_KEYS_JSON must not include PLATFORM_MASTER_KEY."
            )
        if self.local_admin_bootstrap_enabled and self.app_env.lower() != "local":
            raise ValueError("LOCAL_ADMIN_BOOTSTRAP_ENABLED is only allowed when APP_ENV=local.")

        if self.app_env.lower() != "test":
            if self.jwt_secret in self._WEAK_JWT_SECRET_VALUES or len(self.jwt_secret) < 32:
                raise ValueError("Non-test runtime requires JWT_SECRET with at least 32 characters and forbids weak default values.")
            if any(
                secret in self._WEAK_JWT_SECRET_VALUES or len(secret) < 32
                for secret in previous_jwt_secrets
            ):
                raise ValueError(
                    "Previous JWT secrets must contain at least 32 characters and cannot use weak defaults."
                )
            if self.platform_master_key in self._WEAK_PLATFORM_MASTER_KEY_VALUES:
                raise ValueError("Non-test runtime requires PLATFORM_MASTER_KEY and forbids weak default values.")
            if any(
                key in self._WEAK_PLATFORM_MASTER_KEY_VALUES
                for key in previous_master_keys
            ):
                raise ValueError("Previous credential master keys cannot use weak defaults.")
            self.credential_master_keys()

        if self.app_env.lower() != "production":
            return self

        if self.google_oauth_client_secret.strip() in {"replace-me", "local-dev-secret"}:
            raise ValueError("Production forbids weak GOOGLE_OAUTH_CLIENT_SECRET default values.")
        if self.google_oauth_client_id.strip() in {"replace-me", "local-dev-client-id"}:
            raise ValueError("Production forbids weak GOOGLE_OAUTH_CLIENT_ID default values.")

        parsed_public_base = urlparse(self.public_base_url)
        host = (parsed_public_base.hostname or "").lower()
        if not parsed_public_base.scheme or not host:
            raise ValueError("Production requires PUBLIC_BASE_URL to be an absolute URL.")
        if host in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Production forbids localhost PUBLIC_BASE_URL for OAuth redirects.")

        if self.postgres_dsn.startswith("sqlite"):
            raise ValueError("Production requires POSTGRES_DSN backed by PostgreSQL.")

        # A serverless deployment can launch its database-backed core without
        # optional report storage, email, and telemetry integrations. Individual
        # features still validate those settings when used.
        if not self.hosted_serverless:
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

        test_dsn = _env_or_default("DATABASE_URL", _env_or_default("POSTGRES_DSN", "sqlite:///:memory:"))
        return Settings(
            app_env="test",
            public_base_url=_env_or_default("PUBLIC_BASE_URL", "http://testserver"),
            jwt_secret=_env_or_default("JWT_SECRET", "test-secret-key"),
            platform_master_key=_env_or_default("PLATFORM_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),
            postgres_dsn=test_dsn,
            celery_task_always_eager=True,
            celery_task_eager_propagates=True,
            celery_broker_url="memory://",
            celery_result_backend="cache+memory://",
            competitor_provider_backend="fixture",
            intelligence_activation_mode="autonomous",
        )
    return Settings()

