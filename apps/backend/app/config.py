from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Engram API"
    cors_origins: list[str] = ["http://localhost:5183"]
    capture_root: str = "/tmp/engram-captures"
    auth_mode: str = "dev"
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    database_url: str = "postgresql+psycopg://engram:engram@postgres:5432/engram"
    object_storage_endpoint: str = "http://minio:9000"
    object_storage_public_endpoint: str | None = None
    object_storage_bucket: str = "engram-captures"
    object_storage_access_key: str = "engram"
    object_storage_secret_key: str = "engram-password"
    object_storage_secure: bool = False
    object_storage_presigned_url_ttl_seconds: int = 300
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
    ai_job_max_retries: int = 3
    ai_job_retry_delay_seconds: int = 30
    ai_job_retry_max_delay_seconds: int = 900
    ai_job_dispatch_visibility_timeout_seconds: int = 300
    ai_job_running_stale_seconds: int = 900
    # Patient-memory (Pro) quiescence sweep, run on the Celery-beat recovery loop: a visit must be
    # idle this long before stale memory is refreshed in the background (so it is never rebuilt
    # mid-visit; read-triggered refresh handles immediacy). Capped per beat by the sweep limit.
    patient_memory_quiescence_seconds: int = 1800
    patient_memory_sweep_limit: int = 50
    ai_engine_internal_token: str = "dev-ai-engine-token"
    # Whether the Pro single-pass report synthesis (the revived `session_organize` job) is dispatched
    # at chain-drain. This is the backend-visible proxy for "the AI engine's synthesis gateway is
    # configured" (the gateway URL/key live in the worker env, which the backend can't see). Default
    # OFF so gateway-less / Basic environments dispatch ZERO synthesis and the deterministic baseline
    # stands untouched. Turn on (BACKEND_REPORT_SYNTHESIS_ENABLED=true) where a gateway is reachable.
    report_synthesis_enabled: bool = False
    # Error tracking (Sentry-SDK compatible; points at self-hosted GlitchTip). Empty DSN => no-op,
    # so dev / Basic / unconfigured environments are unaffected. Names match docs/monitoring.md:
    # the DSN is backend-specific (BACKEND_ prefix), while ENVIRONMENT / TRACES_SAMPLE_RATE are
    # shared across services (unprefixed) — explicit aliases opt those two out of the env prefix.
    sentry_dsn: str = ""
    sentry_environment: str = Field(default="development", validation_alias="SENTRY_ENVIRONMENT")
    sentry_traces_sample_rate: float = Field(default=0.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE")

    # --- Fair-use AI usage limits (see docs/business/ai-usage-limits.md) --------------------------
    # The monthly AI budget per SEAT (USD). When a clinic's real metered spend for the period exceeds
    # seats × this budget, background AI enrichment PAUSES (capture is never blocked; jobs queue and
    # resume next cycle). Set to $10/seat; that is ~67% of the $15 Pro price — deliberately generous for
    # now, to be tightened toward ~40% as synthesis cost drops (queue-collapse dispatch + prompt-cache
    # reuse). `ai_price_per_seat_usd` is kept only as a reference for that implied-share calculation.
    # Tunable per environment.
    ai_price_per_seat_usd: float = 15.0
    ai_budget_usd_per_seat: float = 10.0
    # Per-session SOFT cap on AI captures (a proxy that pauses further per-capture enrichment for a
    # single runaway session; the monthly budget is the real backstop). Zero = disabled.
    ai_session_soft_cap_captures: int = 30
    ai_session_soft_cap_captures_therapy: int = 25
    # Warn the clinic when metered spend reaches this fraction of the monthly budget.
    ai_usage_warn_threshold: float = 0.80
    # Dev/testing override: force a tiny per-seat AI budget (USD) so limit states are reachable without
    # hundreds of real captures. 0 / unset = use the computed budget. NEVER set in production.
    ai_usage_test_budget_per_seat_usd: float = 0.0

    model_config = SettingsConfigDict(env_prefix="BACKEND_")


settings = Settings()
