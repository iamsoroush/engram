"""Audio capture job: transcription + patient-information extraction + intent classification.

Transcribes through the configured OpenAI-compatible gateway into strict structured JSON (transcript
+ patient_information + intents), normalizing spoken digits to Latin so quantification stays
comparable across captures. Fixture audio maps to deterministic text; a gateway-less non-fixture
capture raises so the backend can retry. Vertical-agnostic via the domain descriptor.
"""
import json
from typing import Any

from ai_engine.config import settings
from ai_engine.core.domain import domain_framing
from ai_engine.core.fixtures import TEST_CAPTURE_TEXT_BY_FILENAME
from ai_engine.core.gateway import (
    gateway_client,
    gateway_settings_for,
    set_pending_audio_seconds,
    transcription_is_configured,
)
from ai_engine.core.media import audio_duration_seconds, audio_to_flac_mono_16khz_base64
from ai_engine.core.text import transcription_language_directive
from ai_engine.core.util import utc_now
# The capture-intelligence contract (transcript + patient information + intents) — the tolerant
# shaping now lives in ``contracts.capture``; re-exported here so the ``processing`` shim and tests
# keep importing these names from the job module.
from ai_engine.contracts.capture import (  # noqa: F401
    ASSIGNMENT_INTENT_BASES,
    CAPTURE_INTELLIGENCE_OUTPUT_VERSION,
    PATIENT_INFORMATION_FIELDS,
    TRANSCRIPTION_LANGUAGES,
    empty_patient_information,
    normalize_intents,
    parse_structured_transcription_output,
    structured_transcription_from_text,
)
from ai_engine.jobs.captures_common import CaptureProcessingOutput, DetectedPatientOutput


def detected_patient_from_patient_information(patient_information: dict[str, Any], transcript: str) -> DetectedPatientOutput:
    """Return the legacy detected-patient shape from structured patient information."""
    name = patient_information.get("standardized_display_name") or patient_information.get("raw_mentioned_name")
    confidence = patient_information.get("confidence")
    return {
        "status": "detected" if name or patient_information.get("national_id") else "not_detected",
        "full_name": str(name) if name else None,
        "national_id": str(patient_information.get("national_id")) if patient_information.get("national_id") else None,
        "confidence": float(confidence) if isinstance(confidence, int | float) else None,
        "evidence": str(patient_information.get("evidence")) if patient_information.get("evidence") else None,
        "source_text": transcript,
    }


def transcription_prompt(transcription_context: dict[str, Any] | None) -> str:
    """Build the rich instruction prompt for the OpenAI-compatible gateway."""
    context = transcription_context if isinstance(transcription_context, dict) else {}
    configured_prompt = settings.transcription_prompt.strip()
    language_directive = transcription_language_directive(context)
    # Vertical-aware framing supplied by the backend; neutral "clinic" + no vocabulary when absent.
    label, vocabulary, _ = domain_framing(context)
    vocab_line = f"Common {label} vocabulary may include {', '.join(vocabulary)}. " if vocabulary else ""
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
                "Also classify intent in `intents`: set assignment.present=true only when THIS audio clip itself states or mentions which patient the visit is about (a spoken name or identifier) — not based on the provided context. Set basis='explicit' ONLY for a clear instruction to change or correct an existing assignment (for example 'change the patient to X', 'this is actually X not Y', or 'wrong patient, it's X'). Treat any statement of who the patient is as basis='implicit' — this includes a name simply stated or fronted and identity declarations (for example 'Ms. Ghasemi, follow-up', 'the patient is X', 'this is X', or 'I am X'). When unsure, prefer 'implicit'. Set out_of_context.present=true when the audio has no clinical or visit content; set append.present=true when it only adds incremental detail to an ongoing note; use null for any intent you cannot determine. "
                "Return only strict JSON with no markdown."
            ),
            (
                "Required JSON shape: "
                '{"transcript":"string","language":"fa|en|mixed|unknown","patient_information":{"raw_mentioned_name":null,'
                '"standardized_display_name":null,"alternate_transliterations":[],"national_id":null,"phone":null,'
                '"date_of_birth":null,"evidence":null,"confidence":0.0},"clinical_summary":null,"uncertainties":[],'
                '"intents":{"assignment":{"present":false,"basis":"implicit","confidence":0.0,"evidence":null},'
                '"append":{"present":false,"confidence":0.0},"out_of_context":{"present":false,"confidence":0.0,"reason":null}}}'
            ),
            f"Tenant-scoped transcription context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
        if part
    )


def transcribe_audio_content(
    content: bytes,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Transcribe audio through the configured OpenAI-compatible gateway."""
    base64_flac = audio_to_flac_mono_16khz_base64(content)
    # Duration drives per-minute transcription cost in the backend meter (set before the call so the
    # metered client attaches it to this transcription's usage record).
    set_pending_audio_seconds(audio_duration_seconds(content))
    client = gateway_client("transcription")
    response = client.chat.completions.create(
        model=model or gateway_settings_for("transcription")[2],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": transcription_prompt(transcription_context)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ],
    )
    text = response.choices[0].message.content
    if not text or not text.strip():
        raise RuntimeError("Audio transcription returned empty text")
    return parse_structured_transcription_output(text)


def completed_audio_metadata(
    job: dict[str, Any],
    capture: dict[str, Any],
    content: bytes | None,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> CaptureProcessingOutput:
    """Return completed audio metadata using real transcription."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        structured = structured_transcription_from_text(TEST_CAPTURE_TEXT_BY_FILENAME[filename])
    elif transcription_is_configured():
        if content is None:
            raise RuntimeError("Audio capture source file is missing")
        structured = transcribe_audio_content(content, transcription_context, model=model)
    else:
        raise RuntimeError("Audio transcription gateway is not configured")
    text = structured["transcript"]
    patient_information = structured["patient_information"]

    return {
        "status": "completed",
        "schemaVersion": CAPTURE_INTELLIGENCE_OUTPUT_VERSION,
        "text": text,
        "language": structured["language"],
        "patient_information": patient_information,
        "clinical_summary": structured["clinical_summary"],
        "uncertainties": structured["uncertainties"],
        "intents": structured.get("intents"),
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
        "detected_patient": detected_patient_from_patient_information(patient_information, text),
    }
