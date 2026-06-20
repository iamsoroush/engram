from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the AI engine worker."""

    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    # Error tracking (Sentry-SDK compatible; self-hosted GlitchTip). Empty DSN => no-op. Reuses the
    # backend's DSN by default (BACKEND_SENTRY_DSN); ENVIRONMENT / TRACES_SAMPLE_RATE are the shared,
    # unprefixed vars (see docs/monitoring.md), so they are aliased to opt out of the AI_ENGINE_ prefix.
    sentry_dsn: str = Field(default="", validation_alias="BACKEND_SENTRY_DSN")
    sentry_environment: str = Field(default="development", validation_alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(default=0.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE")
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
    # Combined patient summary + history (Pro). Falls back to the transcription gateway/model.
    patient_memory_model: str = ""
    patient_memory_base_url: str = ""
    patient_memory_api_key: str = ""
    # Session report synthesis + treatment extraction (Pro). One single-pass structured call.
    # Falls back to the transcription gateway/model when blank. Reasoning effort is low by default
    # (stability comes from structured output + low effort; NO temperature for GPT-5-class models).
    report_synthesis_model: str = ""
    report_synthesis_base_url: str = ""
    report_synthesis_api_key: str = ""
    report_synthesis_reasoning_effort: str = "low"

    model_config = SettingsConfigDict(env_prefix="AI_ENGINE_")


settings = Settings()
