"""Q&A voice-edit prompt (AES-402): classify revise-vs-replace and produce the final reply."""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-09.qa_revise.v3"


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
            # (G4) Cross-patient guard: never introduce a specific fact from outside the draft + spoken
            # note + this patient's context. `priorAnswers` (doctor-wide, other patients) is no longer in
            # the payload — the tone comes from the current draft, so it was noise and a leak surface.
            (
                "CRITICAL: NEVER introduce a specific dose, product, brand, lot/batch number, date, or a "
                "person's NAME that is not already in the current draft, the spoken note, or THIS patient's "
                "context — those would belong to someone else."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"Current draft reply:\n{qa.get('currentDraft', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
        )
    )
