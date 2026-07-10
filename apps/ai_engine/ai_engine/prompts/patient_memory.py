"""Combined patient-memory prompt (Pro): grounded longitudinal summary + history card."""
from __future__ import annotations

import json
from typing import Any

from ai_engine.prompts._shared import domain_framing

PROMPT_VERSION = "2026-07-10.patient_memory.v3"


def build(payload: dict[str, Any]) -> str:
    """Build the prompt for the combined patient summary + history (incremental, grounded)."""
    patient = payload.get("patient") if isinstance(payload.get("patient"), dict) else {}
    language = payload.get("language")
    label, _, _ = domain_framing(payload)  # vertical-aware; neutral "clinic" when absent
    language_directive = (
        f"Write EVERY field in {language} and ONLY {language} — one language throughout, native script."
        if isinstance(language, str) and language.strip()
        else (
            "Write EVERY field in the SAME language the visit notes use (if the notes are Persian/Farsi, "
            "write Persian — do NOT default to English) — one language throughout, native script."
        )
    )
    return "\n\n".join(
        (
            "You are Engram, a calm clinical assistant that maintains a patient's longitudinal memory. "
            f"The clinical setting is a {label}.",
            (
                "Update this patient's memory from the prior memory and the new visit briefs below. "
                "Each visit brief may include the treatments performed that visit (product, dose, area, "
                "lot) — use them to ground recall in specifics (e.g. in a Persian brief: «ویزیت قبل: "
                "ولوما ۰.۳ سی‌سی، گونه چپ»), quoting doses verbatim. Write UNITS in the brief's language "
                "and script (Persian: «سی‌سی», «واحد» — never mL/cc/u inside a Persian brief); brand "
                "names and lot numbers keep their original form. Produce a warm, assistant-voiced brief — natural "
                "sentences, never a form or bullet dump. Synthesize across visits, but do NOT invent "
                "clinical facts, names, products, or doses that are not present in the briefs. Do NOT "
                "include the patient's name in any field — it is already shown beside this text in the "
                "UI; use pronouns or omit the subject (if the patient is «نگار محمدی», write «بیمار» or "
                "drop the subject — the name itself never appears in any field, first or last). Keep "
                "the card summary to 1-2 sentences. "
                "Also produce a compact 'card' for the line-up worklist: 'storySoFar' and 'rightNow' are "
                "EACH at most 2 short sentences; 'flags' surfaces only genuinely important "
                "allergy/consent/preference/caution items actually found in the briefs — return an empty "
                "list when there are none, and never invent one. "
                f"{language_directive} "
                "The whole brief MUST be in that one language — NEVER mix (e.g. an English sentence "
                "containing «گونه چپ»). Brand names and lot numbers may keep their original form. When "
                "the language is Persian/Farsi, embedding common English clinical terms is fine "
                "(Finglish, e.g. «فیلر گونه چپ»), but do not switch into English sentences and never "
                "romanize Persian into Latin."
            ),
            (
                "META-SPEECH EXCLUSION: a visit brief can contain administrative / non-clinical talk aimed "
                "at staff or the app (e.g. «این رو برای منشی بفرست», «نوبت بعدی رو ثبت کن», \"send to "
                "reception\", \"remind me to call\", \"stop the recording\"). NEVER carry such "
                "scheduling/app-command/meta content into the memory — not the summary, not any history "
                "section, not a flag. Remember ONLY the patient's clinical story (what was done, "
                "preferences, cautions, genuine allergy/consent). An app command is never a flag."
            ),
            (
                "Return ONLY strict JSON (no markdown, no code fences) with EXACTLY this shape:\n"
                '{"summary": "<1-2 sentence card summary>", '
                '"history": {"snapshot": "<one line: the current clinical focus — never the patient\'s name>", '
                '"sections": [{"label": "Story so far", "body": "<2-4 sentences>"}, '
                '{"label": "Worth remembering", "body": "<preferences, cautions, recurring themes>"}, '
                '{"label": "Right now", "body": "<open threads / next visit>"}], "visits": []}, '
                '"card": {"storySoFar": "<at most 2 short sentences>", '
                '"rightNow": "<at most 2 short sentences: what is open / next visit>", '
                '"flags": [{"kind": "allergy|consent|preference|caution", "label": "<short>"}]}}'
            ),
            f"Patient context:\n{json.dumps(patient, ensure_ascii=False, sort_keys=True)}",
        )
    )
