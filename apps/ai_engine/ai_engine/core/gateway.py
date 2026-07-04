"""OpenAI-compatible gateway client + real per-job usage metering + model/effort resolution.

Every gateway call returns an OpenAI-style ``usage`` block; a ContextVar sink armed for the duration
of one job (see ``tasks.run_task_with_retries``) captures it so the backend meters REAL spend rather
than estimates. ``gateway_client`` wraps the OpenAI client in a metering proxy; ``resolve_model`` /
``resolve_reasoning_effort`` pick the per-task model + quality knob from the live ``aiModels`` payload
with an env-default fallback. See ``docs/business/ai-usage-limits.md``.
"""
import contextvars
import logging
from typing import Any

from openai import OpenAI

from ai_engine.config import settings

logger = logging.getLogger(__name__)


def transcription_is_configured() -> bool:
    """Return whether a real audio transcription gateway is configured.

    Doubles as the "is any gateway configured" gate every AI job checks before spending — a blank
    ``transcription_base_url`` means gateway-less (deterministic fallbacks / skip sentinels).
    """
    return bool(settings.transcription_base_url.strip())


def gateway_settings_for(task: str) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for an AI task, falling back to the transcription gateway.

    `task` is one of `transcription`, `caption`, `patient_memory`, `report_synthesis`. A blank
    per-task override falls back to the shared `transcription_*` setting, so a single
    OpenAI-compatible gateway only needs the per-task `*_model` set, while a separate provider per
    task can also override base_url/api_key.
    """
    base_url = (getattr(settings, f"{task}_base_url", "") or settings.transcription_base_url).strip()
    api_key = getattr(settings, f"{task}_api_key", "") or settings.transcription_api_key
    model = getattr(settings, f"{task}_model", "") or settings.transcription_model
    return base_url, api_key, model


# --- Real AI-usage metering ---------------------------------------------------
#
# Every gateway call returns an OpenAI-style `usage` block; the worker used to discard it. We now
# capture it per job so the backend can meter REAL spend (never lose money on a plan). A ContextVar
# sink is armed for the duration of one job (see tasks.run_task_with_retries); the metered client
# below appends one record per gateway call, and BackendClient.complete_job ships the records with
# the completion callback. `report_synthesis`/`transcription` etc. are the task labels the backend's
# pricing table keys on. Audio is priced per-minute, so transcription records also carry audioSeconds.
_usage_sink: "contextvars.ContextVar[list[dict[str, Any]] | None]" = contextvars.ContextVar(
    "engram_ai_usage_sink", default=None
)
_pending_audio_seconds: "contextvars.ContextVar[float | None]" = contextvars.ContextVar(
    "engram_ai_audio_seconds", default=None
)


def arm_usage_sink() -> "contextvars.Token":
    """Start collecting per-call gateway usage for the current job. Returns a reset token."""
    return _usage_sink.set([])


def drain_usage_sink() -> list[dict[str, Any]]:
    """Return the usage records collected since the sink was armed (empty if none)."""
    sink = _usage_sink.get()
    return list(sink) if sink else []


def set_pending_audio_seconds(seconds: float | None) -> None:
    """Record the audio duration for the NEXT transcription call (priced per-minute)."""
    _pending_audio_seconds.set(seconds)


def _record_gateway_usage(task: str, model: str | None, response: Any) -> None:
    sink = _usage_sink.get()
    if sink is None:
        return
    usage = getattr(response, "usage", None)
    record: dict[str, Any] = {
        "task": task,
        "model": model,
        "promptTokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completionTokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }
    audio_seconds = _pending_audio_seconds.get()
    if audio_seconds is not None:
        record["audioSeconds"] = float(audio_seconds)
        _pending_audio_seconds.set(None)
    sink.append(record)


class _MeteredCompletions:
    def __init__(self, inner: Any, task: str) -> None:
        self._inner = inner
        self._task = task

    def create(self, *args: Any, **kwargs: Any) -> Any:
        response = self._inner.create(*args, **kwargs)
        try:
            _record_gateway_usage(self._task, kwargs.get("model"), response)
        except Exception:  # metering must never break a job
            logger.debug("Failed to record gateway usage", exc_info=True)
        return response


class _MeteredChat:
    def __init__(self, inner: Any, task: str) -> None:
        self._inner = inner
        self._task = task

    @property
    def completions(self) -> _MeteredCompletions:
        return _MeteredCompletions(self._inner.completions, self._task)


class _MeteredClient:
    """Thin proxy over the OpenAI client that records `usage` for every chat completion."""

    def __init__(self, inner: OpenAI, task: str) -> None:
        self._inner = inner
        self._task = task

    @property
    def chat(self) -> _MeteredChat:
        return _MeteredChat(self._inner.chat, self._task)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def gateway_client(task: str) -> Any:
    """Return a usage-metering OpenAI-compatible client for an AI task's resolved gateway."""
    base_url, api_key, _ = gateway_settings_for(task)
    inner = OpenAI(base_url=base_url, api_key=api_key, timeout=settings.transcription_timeout_seconds)
    return _MeteredClient(inner, task)


def resolve_model(task: str, ai_models: dict[str, Any] | None, *, override: str | None = None) -> str:
    """Resolve the model id for a task: explicit override → live `aiModels` payload → env default.

    The backend resolves the live per-task selection and passes it in the job payload's `aiModels`,
    so a model change applies to the next request; a blank/absent value falls back to the worker env.
    A task entry may be a bare model string (legacy) or a `{model, reasoningEffort}` object — the
    richer shape carries the per-task quality knobs (see `resolve_reasoning_effort`).
    """
    if isinstance(override, str) and override.strip():
        return override.strip()
    if isinstance(ai_models, dict):
        selected = ai_models.get(task)
        if isinstance(selected, dict):
            selected = selected.get("model")
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
    return gateway_settings_for(task)[2]


def resolve_reasoning_effort(task: str, ai_models: dict[str, Any] | None, *, default: str | None = None) -> str | None:
    """Resolve a task's reasoning effort from the live `aiModels` payload, else `default`.

    Only the `{model, reasoningEffort}` task shape carries an effort; a bare model string has none.
    GPT-5-class models take `reasoning_effort` instead of `temperature` (which they reject), so this
    is the stability/quality knob for structured synthesis. Returns None to send no effort at all.
    """
    if isinstance(ai_models, dict):
        selected = ai_models.get(task)
        if isinstance(selected, dict):
            effort = selected.get("reasoningEffort")
            if isinstance(effort, str) and effort.strip():
                return effort.strip()
    return default
