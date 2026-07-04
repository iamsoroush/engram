"""Cross-visit safety-flag reconcile: a second, selection-only LLM pass inside session synthesis.

D7 deliberately isolates this from the main synthesis prompt: a narrow selection-only prompt (keys +
status out, never new text) can't hallucinate new safety text the way a free-writing prompt can. It
dedups-by-meaning / supersedes this visit's newly detected flags against the patient's existing ones;
a failure or sparse set leaves the deterministic union (the safety floor) intact.
"""
import json
import re
from typing import Any

from ai_engine.config import settings
from ai_engine.core.gateway import gateway_client, resolve_model, resolve_reasoning_effort


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


def safety_reconcile_prompt(payload: dict[str, Any]) -> str:
    """Build the cross-visit safety-reconcile prompt (selection-only; keys + status out, never text)."""
    existing = payload.get("existingFlags") if isinstance(payload.get("existingFlags"), list) else []
    new_flags = payload.get("newFlags") if isinstance(payload.get("newFlags"), list) else []
    return "\n\n".join(
        (
            "You are Engram, reconciling a patient's clinical SAFETY FLAGS across visits. You are given the "
            "patient's EXISTING flags and this visit's NEW flags. Each flag has a stable `key`, a `kind` "
            "(allergy / contraindication / consent), and `text` (clinical content — never translate or "
            "rewrite it).",
            (
                "Return ONE decision per flag (referenced by its `key`):\n"
                "- 'keep': a distinct, current safety fact — keep it.\n"
                "- 'duplicate': states the SAME clinical concept as another flag — set ofKey to that other "
                "flag's key (e.g. «آلرژی به پنی‌سیلین» and «حساسیت به پنی‌سیلین» are the same; keep one, mark "
                "the rest duplicate).\n"
                "- 'superseded': a later flag EXPLICITLY contradicts/updates this one — set ofKey to the "
                "superseding flag's key (e.g. «بیمار باردار است» then «دیگر باردار نیست»). A superseded flag "
                "is ANNOTATED, never deleted.\n"
                "RULES:\n"
                "- SELECTION ONLY: emit keys + status, never any new/edited text. Every `key` MUST be one of "
                "the given flags' keys; every `ofKey` MUST also be one of the given keys.\n"
                "- BIAS TO KEEP (safety errs to inclusion): mark 'duplicate'/'superseded' ONLY when you are "
                "confident it is the SAME concept or an EXPLICIT update. When unsure, 'keep'. NEVER drop a "
                "distinct allergy or contraindication.\n"
                "- NEVER merge across kinds (an allergy is never a duplicate of a consent).\n"
                "Return ONLY strict JSON: {\"decisions\": [{\"key\", \"status\", \"ofKey\"}]}."
            ),
            f"EXISTING flags: {json.dumps(existing, ensure_ascii=False)}",
            f"NEW flags (this visit): {json.dumps(new_flags, ensure_ascii=False)}",
        )
    )


def parse_safety_reconcile_output(raw_text: str, *, candidate_keys: list[str]) -> dict[str, dict[str, Any]] | None:
    """Validate the reconcile output into ``{key: {status, ofKey}}``, or None to fall back to the union.

    Safety-first: an unknown key is dropped; a duplicate/superseded whose ofKey isn't a real candidate is
    downgraded to 'keep' (never silently lose a distinct flag); any candidate with no decision defaults to
    'keep' upstream.
    """
    if not raw_text or not raw_text.strip():
        return None
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("decisions"), list):
        return None
    keys = set(candidate_keys)
    decisions: dict[str, dict[str, Any]] = {}
    for item in parsed["decisions"]:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        status = item.get("status")
        if key not in keys or status not in {"keep", "duplicate", "superseded"}:
            continue
        of_key = item.get("ofKey")
        # A collapse/supersede must point at a real OTHER candidate; otherwise keep (never drop).
        if status in {"duplicate", "superseded"} and (of_key not in keys or of_key == key):
            status, of_key = "keep", None
        decisions[key] = {"status": status, "ofKey": of_key if status != "keep" else None}
    return decisions


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
