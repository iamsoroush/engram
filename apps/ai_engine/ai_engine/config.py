from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the AI engine worker."""

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    backend_internal_url: str = "http://backend:8000"
    internal_token: str = "dev-ai-engine-token"
    job_max_retries: int = 3
    job_retry_delay_seconds: int = 30
    recovery_interval_seconds: int = 60
    mock_stage_delay_seconds: float = 1.25
    http_timeout_seconds: float = 10.0
    transcription_base_url: str = ""
    transcription_api_key: str = "unused"
    transcription_model: str = "gemini-3.1-flash-lite"
    transcription_prompt: str = "Transcribe this audio."
    transcription_timeout_seconds: float = 120.0
    # Per-task model/gateway overrides. Each AI task (transcription, photo caption, note
    # decoration) can run on a different model — e.g. a fast multimodal model for transcription
    # and a different one for captioning. A blank value falls back to the transcription_* gateway,
    # so a single OpenAI-compatible gateway that routes by model name only needs the *_model vars;
    # a separate provider per task can also override its base_url/api_key.
    caption_model: str = ""
    caption_base_url: str = ""
    caption_api_key: str = ""
    note_decoration_model: str = ""
    note_decoration_base_url: str = ""
    note_decoration_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="AI_ENGINE_")


settings = Settings()
