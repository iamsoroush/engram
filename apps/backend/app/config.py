from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Notari API"
    cors_origins: list[str] = ["http://localhost:5183"]
    capture_root: str = "/tmp/notari-captures"
    auth_mode: str = "dev"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    database_url: str = "postgresql+psycopg://notari:notari@postgres:5432/notari"
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_public_endpoint: str | None = None
    object_storage_bucket: str = "notari-captures"
    object_storage_access_key: str = "notari"
    object_storage_secret_key: str = "notari-password"
    object_storage_secure: bool = False
    object_storage_presigned_url_ttl_seconds: int = 300
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    ai_job_max_retries: int = 3
    ai_job_retry_delay_seconds: int = 30
    ai_job_retry_max_delay_seconds: int = 900
    ai_job_dispatch_visibility_timeout_seconds: int = 300
    ai_job_running_stale_seconds: int = 900
    ai_engine_internal_token: str = "dev-ai-engine-token"
    # Error tracking (Sentry-SDK compatible; points at self-hosted GlitchTip). Empty DSN => no-op,
    # so dev / Basic / unconfigured environments are unaffected. Names match docs/monitoring.md:
    # the DSN is backend-specific (BACKEND_ prefix), while ENVIRONMENT / TRACES_SAMPLE_RATE are
    # shared across services (unprefixed) — explicit aliases opt those two out of the env prefix.
    sentry_dsn: str = ""
    sentry_environment: str = Field(default="development", validation_alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(default=0.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE")

    model_config = SettingsConfigDict(env_prefix="BACKEND_")


settings = Settings()
