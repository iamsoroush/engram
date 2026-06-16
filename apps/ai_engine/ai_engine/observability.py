"""Sentry/GlitchTip error tracking for the AI engine worker (Sentry-SDK compatible).

Initialized once when the Celery app is imported. **No-op when the DSN is empty**, so dev /
unconfigured environments are unaffected.

PHI safety: ``send_default_pii=False`` plus a ``before_send`` hook that redacts any
patient/clinical-looking fields the worker might attach to event context (extra/tags/contexts) and
drops user PII. The worker handles audio transcripts, captions, and patient identity, so clinical
content must never leave the box in an error event.
"""
from typing import Any

from ai_engine.config import settings

_SENSITIVE_KEY_HINTS = (
    "patient",
    "name",
    "national",
    "phone",
    "email",
    "dob",
    "birth",
    "address",
    "detail",
    "metadata",
    "transcript",
    "transcription",
    "caption",
    "note",
    "report",
    "summary",
    "content",
    "audio",
    "prompt",
    "token",
    "api_key",
    "authorization",
    "secret",
)

_REDACTED = "[redacted]"


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(hint in lowered for hint in _SENSITIVE_KEY_HINTS)


def _scrub(value: Any) -> Any:
    """Recursively redact values under keys that may carry PHI / secrets."""
    if isinstance(value, dict):
        return {
            key: (_REDACTED if _is_sensitive_key(key) else _scrub(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(item) for item in value]
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Strip clinical fields / user PII from an outgoing event."""
    for section in ("extra", "tags", "contexts"):
        if isinstance(event.get(section), dict):
            event[section] = _scrub(event[section])
    event.pop("user", None)
    return event


def init_sentry() -> None:
    """Initialize Sentry with the Celery integration. No-op when the DSN is empty."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[CeleryIntegration()],
        send_default_pii=False,
        before_send=_before_send,
    )
