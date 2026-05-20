from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the AI engine worker."""

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    backend_internal_url: str = "http://backend:8000"
    internal_token: str = "dev-ai-engine-token"
    job_max_retries: int = 3
    job_retry_delay_seconds: int = 30
    mock_stage_delay_seconds: float = 1.25
    http_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(env_prefix="AI_ENGINE_")


settings = Settings()
