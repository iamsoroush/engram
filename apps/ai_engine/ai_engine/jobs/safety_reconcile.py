"""Cross-visit safety-flag reconcile: a second, selection-only LLM pass inside session synthesis.

D7 deliberately isolates this from the main synthesis prompt: a narrow selection-only prompt (keys +
status out, never new text) can't hallucinate new safety text the way a free-writing prompt can. It
dedups-by-meaning / supersedes this visit's newly detected flags against the patient's existing ones;
a failure or sparse set leaves the deterministic union (the safety floor) intact.
"""
from typing import Any

from ai_engine.config import settings
from ai_engine.contracts.safety_reconcile import (  # noqa: F401 — re-exported for the shim + tests
    SAFETY_RECONCILE_OUTPUT_VERSION,
    parse_safety_reconcile_output,
)
from ai_engine.core.gateway import gateway_client, resolve_model, resolve_reasoning_effort
# The prompt lives in its own versioned module (§3.3); ``safety_reconcile_prompt`` is re-exported for
# the shim + tests (this pass folds into synthesis, so its version rides the synthesis provenance).
from ai_engine.prompts.safety_reconcile import PROMPT_VERSION as SAFETY_RECONCILE_PROMPT_VERSION  # noqa: F401
from ai_engine.prompts.safety_reconcile import build as safety_reconcile_prompt  # noqa: F401


def safety_reconcile_json_schema() -> dict[str, Any]:
    """JSON schema for the cross-visit safety-reconcile output — one keys-only decision per flag."""
    decision = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "status": {"type": "string", "enum": ["keep", "duplicate", "superseded"]},
            "ofKey": {"type": ["string", "null"]},
        },
        "required": ["key", "status"],
    }
    return {
        "type": "object",
        "properties": {"decisions": {"type": "array", "items": decision}},
        "required": ["decisions"],
    }


def _safety_flag_key(kind: Any, text: Any) -> str:
    """Stable key for a safety flag — MUST match backend `patient_safety.safety_flag_key`."""
    return f"{kind}|{' '.join(str(text).strip().lower().split())}"


def reconcile_safety_flags(payload: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Run the cross-visit safety reconcile through the gateway; None to fall back to the raw union.

    Selection-only: returns ``{key: {status, ofKey}}``. Network errors propagate (retryable); empty/
    malformed content returns None so the deterministic union (the safety floor) stands.
    """
    existing = payload.get("existingFlags") if isinstance(payload.get("existingFlags"), list) else []
    new_flags = payload.get("newFlags") if isinstance(payload.get("newFlags"), list) else []
    candidate_keys = [str(f.get("key")) for f in [*existing, *new_flags] if isinstance(f, dict) and f.get("key")]
    if not candidate_keys:
        return {}
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    effort = resolve_reasoning_effort(
        "report_synthesis", ai_models, default=(settings.report_synthesis_reasoning_effort or None)
    )
    client = gateway_client("report_synthesis")
    request: dict[str, Any] = {
        "model": resolve_model("report_synthesis", ai_models),
        "messages": [{"role": "user", "content": safety_reconcile_prompt(payload)}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "safety_reconcile_output", "schema": safety_reconcile_json_schema()},
        },
    }
    if effort:
        request["extra_body"] = {"reasoning_effort": effort}
    response = client.chat.completions.create(**request)
    return parse_safety_reconcile_output(response.choices[0].message.content or "", candidate_keys=candidate_keys)
