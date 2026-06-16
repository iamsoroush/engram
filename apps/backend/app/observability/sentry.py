"""Sentry/GlitchTip error tracking for the backend (Sentry-SDK compatible).

Initialized once at app startup from config. **No-op when the DSN is empty**, so dev / Basic /
unconfigured environments are unaffected.

PHI safety: ``send_default_pii=False`` plus a ``before_send`` hook that strips request bodies, form
data, cookies, and any patient/clinical fields before an event leaves the process. This is a
defense-in-depth scrubber — we keep stack traces + URLs (route templates), never request payloads or
clinical content.
"""
from typing import Any

from app.config import settings

# Substrings (case-insensitive) that mark a key as potentially carrying PHI / sensitive data. Any
# matching key in request data / extra / tags has its value redacted.
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
    "caption",
    "note",
    "report",
    "summary",
    "content",
    "password",
    "token",
    "authorization",
    "secret",
)

_REDACTED = "[redacted]"


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


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    return any(hint in lowered for hint in _SENSITIVE_KEY_HINTS)


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Strip request bodies / form data / clinical fields from an outgoing event."""
    request = event.get("request")
    if isinstance(request, dict):
        # Never ship request payloads: bodies, form data, cookies, or raw query strings.
        for field in ("data", "cookies", "query_string"):
            request.pop(field, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                key: (_REDACTED if _is_sensitive_key(key) else value)
                for key, value in headers.items()
            }

    # Belt-and-suspenders: scrub any patient/clinical-looking keys anywhere we attach context.
    for section in ("extra", "tags", "contexts"):
        if isinstance(event.get(section), dict):
            event[section] = _scrub(event[section])

    # Drop the username/email/ip the SDK may attach to user context (PII).
    event.pop("user", None)
    return event


def init_sentry() -> None:
    """Initialize Sentry once at startup. No-op when ``BACKEND_SENTRY_DSN`` is empty."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        before_send=_before_send,
    )
