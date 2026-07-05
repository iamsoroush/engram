"""Audio transcription + patient-information + intent-classification prompt (vertical-agnostic)."""
from __future__ import annotations

import json
from typing import Any

from ai_engine.config import settings
from ai_engine.prompts._shared import domain_framing, transcription_language_directive, vocabulary_line

PROMPT_VERSION = "2026-07-05.transcription.v2"


def build(transcription_context: dict[str, Any] | None) -> str:
    """Build the rich instruction prompt for the OpenAI-compatible gateway."""
    context = transcription_context if isinstance(transcription_context, dict) else {}
    configured_prompt = settings.transcription_prompt.strip()
    language_directive = transcription_language_directive(context)
    # Vertical-aware framing supplied by the backend; neutral "clinic" + no vocabulary when absent.
    label, vocabulary, _ = domain_framing(context)
    vocab_line = vocabulary_line(label, vocabulary)
    return "\n\n".join(
        part
        for part in (
            configured_prompt if configured_prompt and configured_prompt != "Transcribe this audio." else None,
            (
                f"You are transcribing and extracting clinical identity details for Engram, a clinical memory system. The clinical setting is a {label}. "
                "The audio may be Persian/Farsi, English, or mixed. Preserve the transcript faithfully, including clinically relevant filler words when useful. "
                f"{language_directive} "
                "Keep names inside the transcript exactly as spoken (original script); provide a readable English transliteration ONLY in standardized_display_name (with alternates in alternate_transliterations) — do not let that transliteration change the transcript text. "
                "Iranian national IDs and phone numbers may be spoken digit by digit in Persian, Arabic, or English numerals; normalize them to digit strings when explicitly present. "
                f"{vocab_line}"
                "Use the provided context ONLY to spell/transliterate a name that is actually spoken in THIS audio clip — never to introduce or confirm an identity. Set raw_mentioned_name and standardized_display_name ONLY to a patient name spoken in this clip; if no name or identifier is spoken here, both MUST be null with confidence 0, even when the assigned-patient/session context names someone. Never copy the patient's name from context, history, or a previous capture. "
                "Also classify intent in `intents`: set assignment.present=true only when THIS audio clip itself states or mentions which patient the visit is about (a spoken name or identifier) — not based on the provided context. Set basis='explicit' for a clear instruction to change, set, or CORRECT which patient this visit is about — including correction directives such as 'correct it', 'fix it to X', 'it should be X', 'اسم بیمار X است، درستش', 'اصلاح بشه', 'اصلاحش کن به X', as well as 'change the patient to X', 'this is actually X not Y', or 'wrong patient, it's X'. A directive to correct/fix the patient's name is ALWAYS basis='explicit', even when phrased as a plain statement of the name followed by 'correct it'. Treat any bare statement of who the patient is (no correction directive) as basis='implicit' — a name simply stated or fronted, or identity declarations such as 'Ms. Ghasemi, follow-up', 'the patient is X', 'this is X', or 'I am X'. When unsure, prefer 'implicit'. "
                "If the clip mentions TWO different candidate names in a self-correction ('for Sara… no, Maryam' / 'برای سارا… نه، مریم'), the corrected (last) name is the intended patient — put it in patient_information with basis='explicit'; if it names two DIFFERENT patients with no correction between them, you are not sure which the visit is about, so lower patient_information.confidence and add an entry to uncertainties rather than guessing one. "
                "Set intents.detach.present=true (with basis 'explicit') when the clip says this visit is NOT the currently-assigned patient or asks to remove/unassign the patient WITHOUT naming a replacement (for example 'this isn't her', 'wrong patient, remove her', 'این پرونده مال ایشون نیست'); leave patient_information null in that case. "
                "Set out_of_context.present=true ONLY when the audio has no clinical AND no visit-administration content. Assignment, reassignment, or name-correction instructions ARE visit content — a clip whose only content is 'wrong patient, it's Sara' is NOT out of context. Set append.present=true when it only adds incremental detail to an ongoing note; use null for any intent you cannot determine. "
                "Return only strict JSON with no markdown."
            ),
            (
                "Required JSON shape: "
                '{"transcript":"string","language":"fa|en|mixed|unknown","patient_information":{"raw_mentioned_name":null,'
                '"standardized_display_name":null,"alternate_transliterations":[],"national_id":null,"phone":null,'
                '"date_of_birth":null,"evidence":null,"confidence":0.0},"clinical_summary":null,"uncertainties":[],'
                '"intents":{"assignment":{"present":false,"basis":"implicit","confidence":0.0,"evidence":null},'
                '"detach":{"present":false,"basis":"explicit","confidence":0.0},'
                '"append":{"present":false,"confidence":0.0},"out_of_context":{"present":false,"confidence":0.0,"reason":null}}}'
            ),
            f"Tenant-scoped transcription context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
        if part
    )
