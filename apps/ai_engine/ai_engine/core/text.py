"""Text + language helpers shared across jobs: digit normalization and language directives.

Vertical-agnostic and stateless. ``normalize_digits_to_latin`` makes quantification (doses, lot/batch
numbers, national IDs, phones, dates) comparable across captures regardless of the spoken script,
while leaving prose words untouched. The language directives instruct the gateway to keep the
original script and never romanize Persian/Farsi.
"""
from typing import Any

TRANSCRIPTION_LANGUAGE_NAMES = {
    "fa": "Persian (Farsi)",
    "en": "English",
    "ar": "Arabic",
}

# Tokens that name "no single language" rather than a real language subtag — never a BCP-47 stamp.
_NON_LANGUAGE_TOKENS = {"", "auto", "unknown", "mixed", "und"}


def normalize_bcp47_lang(value: Any) -> str | None:
    """Coerce a report/preferred-language input into a BCP-47 language tag, or None.

    The ``lang`` stamp records the language a payload's display strings were GENERATED in — the
    reference field a future language-switch migration reads (the ai-engine refactor decisions, docs/technical-decisions.md
    §4.6). Our inputs are already BCP-47-ish (``fa``, ``en``, ``fa-IR``); sentinels that name no single
    language (``auto``/``unknown``/``mixed``) map to None so the stamp is never a lie.
    """
    if not isinstance(value, str):
        return None
    token = value.strip()
    if token.lower() in _NON_LANGUAGE_TOKENS:
        return None
    return token


# Persian (۰-۹) and Arabic-Indic (٠-٩) digits → Western/Latin 0-9. Quantification read off a photo
# (lot/batch numbers, doses, dates) must be comparable across captures regardless of the caption's
# language, so digits are normalized deterministically while the prose words stay untouched.
_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_digits_to_latin(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to Western 0-9 (digit normalization, not romanizing words)."""
    return text.translate(_LATIN_DIGITS)


def transcription_language_directive(transcription_context: dict[str, Any] | None) -> str:
    """Instruct the model on transcript language/script.

    Default ('auto') transcribes verbatim in the original script — this prevents Persian speech
    from coming back romanized in Latin, which otherwise breaks name matching and reassignment.
    A specific preferred language asks the model to transcribe in that language's native script.
    """
    context = transcription_context if isinstance(transcription_context, dict) else {}
    preferred = str(context.get("preferredLanguage") or "auto").strip().lower()
    if preferred and preferred not in {"auto", "unknown", "mixed"}:
        name = TRANSCRIPTION_LANGUAGE_NAMES.get(preferred, preferred)
        return (
            f"The clinic's preferred transcription language is {name}: write the transcript in {name} using its "
            "native script. Do not translate into another language and do not romanize."
        )
    return (
        "Transcribe VERBATIM in whatever language(s) are actually spoken, preserving the ORIGINAL SCRIPT — "
        "Persian/Farsi speech MUST be written in Persian script (e.g. «بیمار را عوض کن به سروش»), never romanized "
        "Latin (not «Bimar ro avaz kon be Soroush»). Never translate the transcript and never romanize it."
    )


def enrichment_language_directive(enrichment_context: dict[str, Any] | None) -> str:
    """Instruct the model on enrichment output language/script (mirrors transcription)."""
    context = enrichment_context if isinstance(enrichment_context, dict) else {}
    preferred = str(context.get("preferredLanguage") or "auto").strip().lower()
    if preferred and preferred not in {"auto", "unknown", "mixed"}:
        name = TRANSCRIPTION_LANGUAGE_NAMES.get(preferred, preferred)
        return f"Write the output in {name} using its native script. Do not translate into another language and do not romanize."
    return (
        "Write the output in the same language and script as the source material; never translate it "
        "and never romanize Persian/Farsi into Latin."
    )
