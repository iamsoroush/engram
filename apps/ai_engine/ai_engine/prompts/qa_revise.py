"""Q&A voice-edit prompt (AES-402): classify revise-vs-replace and produce the final reply."""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-05.qa_revise.v2"


def build(payload: dict[str, Any]) -> str:
    """Prompt for a Q&A reply voice edit: classify revise-vs-replace and produce the reply (AES-402)."""
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    return "\n\n".join(
        (
            "You are Engram, helping an aesthetics-clinic doctor edit a reply to a patient's question "
            "using a voice note they just recorded. The doctor reviews and approves before sending.",
            (
                "Decide from the VOICE NOTE whether the doctor is REVISING the current draft (e.g. "
                "'make it warmer', 'remove the part about ice', 'add that she should avoid sun') or "
                "dictating an ENTIRELY NEW reply. Then produce the final reply text in the patient's "
                "language. Keep the doctor's sign-off. Do NOT invent clinical facts, doses, or products "
                "not present in the current draft, the spoken note, or the context. "
                "Return STRICT JSON only: {\"mode\":\"revise\"|\"replace\",\"reply\":\"<final reply text>\"}."
            ),
            # Cross-patient guard (Q-3): the PRIOR ANSWERS below are OTHER patients' conversations, kept
            # only to match the doctor's voice. Never copy a dose, product, brand, lot, date, or a NAME
            # from them (or anywhere outside the current draft + spoken note) into this reply.
            (
                "CRITICAL cross-patient rule: the PRIOR ANSWERS are OTHER patients' conversations — use "
                "them ONLY for the doctor's tone. NEVER copy a specific dose, product, brand, lot/batch "
                "number, date, or a person's NAME from them into this reply; those belong to someone else."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"Current draft reply:\n{qa.get('currentDraft', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )
