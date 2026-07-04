"""Gateway-enforced structured outputs + one validation-failure retry (§3.2).

Every JSON-emitting task sends ``response_format={"type":"json_schema", ...}`` (the gateway enforces it
OpenAI-style for both OpenAI and Gemini models) and, on an invalid output, does ONE in-job re-request
appending the validation error before falling back to the task's existing path (transcription re-raises
InvalidOutput → retryable; caption/memory/qa fall back to their deterministic default). The typed
contracts (§2.2) stay the validation layer — schema enforcement is defense in depth, so the fence-strip
tolerance is retained. The retry tier hook (``retry_tier``) is the seam §3.1 fills with escalation.
"""
from __future__ import annotations

from typing import Any, Callable

from ai_engine.config import settings
from ai_engine.core.errors import InvalidOutput

# invoke(model, effort, correction) -> raw_text. correction is None on the first attempt, else the
# validation error to append so the model can self-correct on the retry.
Invoke = Callable[[str, "str | None", "str | None"], str]
Parse = Callable[[str], Any]


def structured_outputs_enabled() -> bool:
    """Whether gateway-enforced structured outputs + the validation retry are active (kill-switch)."""
    return settings.structured_outputs_enabled


def response_format(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    """The OpenAI-compatible ``response_format`` block for a json_schema-enforced call."""
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}


def correction_message(error: str) -> dict[str, Any]:
    """A user message appended on the retry telling the model exactly how its last output was invalid."""
    return {
        "role": "user",
        "content": (
            "Your previous response was invalid and could not be used: "
            f"{error} Return a corrected response as STRICT JSON matching the required schema, with no "
            "markdown and no code fences."
        ),
    }


def retry_tier(task: str, ai_models: dict[str, Any] | None, *, model: str, effort: str | None) -> tuple[str, str | None]:
    """The (model, effort) for the validation-failure retry.

    §3.2 retries on the SAME tier; §3.1 overrides this to fire the configured escalation tier — spend
    more exactly where the cheap tier just demonstrably failed. Kept as one seam so that swap is local.
    """
    return model, effort


def call_with_validation_retry(
    *,
    task: str,
    ai_models: dict[str, Any] | None,
    model: str,
    effort: str | None,
    invoke: Invoke,
    parse: Parse,
) -> Any:
    """Run a structured-output gateway call, retrying once on invalid output (appending the error).

    The caller resolves ``model``/``effort`` (as it does today) and passes ``ai_models`` so the retry can
    escalate (§3.1). ``invoke`` owns the messages + response_format for ONE call; ``parse`` returns the
    validated result or ``None``/raises ``InvalidOutput`` on invalid output. When structured outputs are
    disabled this is a single call with the parser's natural behavior (byte-identical to the pre-§3.2
    path). Returns the parsed result, or the final parse's natural failure (``None`` / raised
    ``InvalidOutput``) so the caller keeps its existing fallback.
    """
    raw = invoke(model, effort, None)
    if not structured_outputs_enabled():
        return parse(raw)
    result, error = _safe_parse(parse, raw)
    if result is not None:
        return result
    retry_model, retry_effort = retry_tier(task, ai_models, model=model, effort=effort)
    raw_retry = invoke(retry_model, retry_effort, error)
    return parse(raw_retry)


def _safe_parse(parse: Parse, raw: str) -> tuple[Any, str | None]:
    """Parse, folding both ``None`` and a raised ``InvalidOutput`` into ``(None, error_message)``."""
    try:
        result = parse(raw)
    except InvalidOutput as exc:
        return None, str(exc)
    if result is None:
        return None, "The response did not match the required JSON schema."
    return result, None
