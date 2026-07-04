"""Q&A reply-draft prompt (AES-402): a grounded, clinically-cautious reply the doctor approves."""
from __future__ import annotations

import json
from typing import Any

PROMPT_VERSION = "2026-07-04.qa_draft.v1"


def build(payload: dict[str, Any]) -> str:
    """Build the prompt for a post-session patient Q&A reply draft (AES-402)."""
    qa = payload.get("qaDraft") if isinstance(payload.get("qaDraft"), dict) else {}
    return "\n\n".join(
        (
            "You are Engram, drafting a reply on behalf of an aesthetics clinic doctor to a patient's "
            "between-visits question. The doctor will review and edit before sending.",
            (
                "Write a warm, concise reply (2-4 sentences) in the patient's voice-appropriate register. "
                "Ground it in the doctor's PRIOR ANSWERS and THIS PATIENT'S CONTEXT below; match the "
                "doctor's tone. Do NOT invent clinical facts, doses, products, or diagnoses not present "
                "in the context. Reassure when appropriate, reference the aftercare already given, and "
                "tell the patient to contact the clinic if symptoms worsen or they are worried. Sign off "
                f"as {qa.get('doctorName') or 'the clinic'}. Return ONLY the plain-text reply."
            ),
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )
