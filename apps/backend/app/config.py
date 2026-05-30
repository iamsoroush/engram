from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AesMem API"
    cors_origins: list[str] = ["http://localhost:5183"]
    capture_root: str = "/tmp/aesmem-captures"
    auth_mode: str = "dev"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    database_url: str = "postgresql+psycopg://aesmem:aesmem@postgres:5432/aesmem"
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_public_endpoint: str | None = None
    object_storage_bucket: str = "aesmem-captures"
    object_storage_access_key: str = "aesmem"
    object_storage_secret_key: str = "aesmem-password"
    object_storage_secure: bool = False
    object_storage_presigned_url_ttl_seconds: int = 300
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    ai_job_max_retries: int = 3
    ai_job_retry_delay_seconds: int = 30
    ai_engine_internal_token: str = "dev-ai-engine-token"

    model_config = SettingsConfigDict(env_prefix="BACKEND_")


settings = Settings()
