"""Cross-visit safety-reconcile prompt (selection-only; emits keys + status, never new text)."""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-10.safety_reconcile.v2"


def build(payload: dict[str, Any]) -> str:
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
                "the rest duplicate). Compare the clinical FACT, not the wording: the same "
                "substance/procedure + the same concern + the same timeframe is the SAME concept even when "
                "the sentences share almost no words (different word order, verb form, or «مصرف …»/«بیمار … "
                "مصرف کرده» restructuring). WORKED EXAMPLE: existing «مصرف کورتون در ماه گذشته» + new "
                "«بیمار ماه پیش کورتون مصرف کرده» → the new one is 'duplicate' ofKey the existing one. When "
                "an EXISTING flag and a NEW flag are the same fact, keep the existing and mark the NEW one "
                "duplicate.\n"
                "- 'superseded': a later flag EXPLICITLY contradicts/updates this one — set ofKey to the "
                "superseding flag's key (e.g. «بیمار باردار است» then «دیگر باردار نیست»). A superseded flag "
                "is ANNOTATED, never deleted.\n"
                "RULES:\n"
                "- COMPLETE: return exactly ONE decision for EVERY flag given — every EXISTING flag AND "
                "every NEW flag. Never omit a flag; deciding only the new arrivals is an error.\n"
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
