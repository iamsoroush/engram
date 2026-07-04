"""Audio capture job: transcription + patient-information extraction + intent classification.

Transcribes through the configured OpenAI-compatible gateway into strict structured JSON (transcript
+ patient_information + intents), normalizing spoken digits to Latin so quantification stays
comparable across captures. Fixture audio maps to deterministic text; a gateway-less non-fixture
capture raises so the backend can retry. Vertical-agnostic via the domain descriptor.
"""
import json
import re
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
from ai_engine.core.text import normalize_digits_to_latin, transcription_language_directive
from ai_engine.core.util import clamp_confidence, utc_now
from ai_engine.jobs.captures_common import CaptureProcessingOutput, DetectedPatientOutput

TRANSCRIPTION_LANGUAGES = {"fa", "en", "mixed", "unknown"}

ASSIGNMENT_INTENT_BASES = {"explicit", "implicit"}

PATIENT_INFORMATION_FIELDS = (
    "raw_mentioned_name",
    "standardized_display_name",
    "alternate_transliterations",
    "national_id",
    "phone",
    "date_of_birth",
    "evidence",
    "confidence",
)


def empty_patient_information(*, source_text: str | None = None) -> dict[str, Any]:
    """Return the generated patient-information schema for no detected identity."""
    return {
        "raw_mentioned_name": None,
        "standardized_display_name": None,
        "alternate_transliterations": [],
        "national_id": None,
        "phone": None,
        "date_of_birth": None,
        "evidence": None,
        "confidence": 0.0,
        "source_text": source_text,
    }


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


def structured_transcription_from_text(text: str, *, language: str = "en") -> dict[str, Any]:
    """Return deterministic structured transcription for fixtures and fallback output."""
    return {
        "transcript": text,
        "language": language,
        "patient_information": empty_patient_information(source_text=text),
        "clinical_summary": None,
        "uncertainties": [],
        "intents": None,
    }


def normalize_intents(raw: Any) -> dict[str, Any] | None:
    """Normalize best-effort intent classification, dropping absent or malformed intents.

    The transcript is the required, high-trust field; intents are optional so a malformed
    intent payload never invalidates an otherwise usable transcript.
    """
    if not isinstance(raw, dict):
        return None
    intents: dict[str, Any] = {}
    assignment = raw.get("assignment")
    if isinstance(assignment, dict) and assignment.get("present") is True:
        basis = assignment.get("basis")
        evidence = assignment.get("evidence")
        intents["assignment"] = {
            "present": True,
            "basis": basis if basis in ASSIGNMENT_INTENT_BASES else "implicit",
            "confidence": clamp_confidence(assignment.get("confidence")),
            "evidence": str(evidence).strip() if isinstance(evidence, str) and evidence.strip() else None,
        }
    append = raw.get("append")
    if isinstance(append, dict) and append.get("present") is True:
        intents["append"] = {"present": True, "confidence": clamp_confidence(append.get("confidence"))}
    out_of_context = raw.get("out_of_context")
    if isinstance(out_of_context, dict) and out_of_context.get("present") is True:
        reason = out_of_context.get("reason")
        intents["out_of_context"] = {
            "present": True,
            "confidence": clamp_confidence(out_of_context.get("confidence")),
            "reason": str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        }
    return intents or None


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


def parse_structured_transcription_output(raw_text: str) -> dict[str, Any]:
    """Parse and validate strict structured transcription JSON."""
    text = raw_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Audio transcription returned malformed structured JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Audio transcription returned non-object structured JSON")

    transcript = parsed.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise RuntimeError("Audio transcription structured JSON is missing transcript")
    # Normalize spoken numbers (doses, national IDs, phones, dates) to Western/Latin digits so all
    # extracted quantification is comparable regardless of the spoken language — a national ID or dose
    # dictated in Persian digits must match a stored Latin one. The prose words stay original script.
    transcript = normalize_digits_to_latin(transcript.strip())
    language = parsed.get("language")
    if language not in TRANSCRIPTION_LANGUAGES:
        language = "unknown"
    patient_information = parsed.get("patient_information")
    if not isinstance(patient_information, dict):
        raise RuntimeError("Audio transcription structured JSON is missing patient_information")

    normalized_patient = empty_patient_information(source_text=transcript)
    for field in PATIENT_INFORMATION_FIELDS:
        if field in patient_information:
            normalized_patient[field] = patient_information[field]
    alternates = normalized_patient.get("alternate_transliterations")
    normalized_patient["alternate_transliterations"] = [str(value) for value in alternates if isinstance(value, str)] if isinstance(alternates, list) else []
    confidence = normalized_patient.get("confidence")
    normalized_patient["confidence"] = max(0.0, min(float(confidence), 1.0)) if isinstance(confidence, int | float) else 0.0
    for field in ("raw_mentioned_name", "standardized_display_name", "national_id", "phone", "date_of_birth", "evidence"):
        value = normalized_patient.get(field)
        normalized_patient[field] = str(value).strip() if value is not None and str(value).strip() else None
    # Identifiers/dates are comparison-critical (patient matching reads national_id/phone) → Latin digits.
    for field in ("national_id", "phone", "date_of_birth"):
        if normalized_patient.get(field):
            normalized_patient[field] = normalize_digits_to_latin(normalized_patient[field])

    uncertainties = parsed.get("uncertainties")
    clinical_summary = parsed.get("clinical_summary")
    return {
        "transcript": transcript,
        "language": language,
        "patient_information": normalized_patient,
        "clinical_summary": normalize_digits_to_latin(clinical_summary.strip()) if isinstance(clinical_summary, str) and clinical_summary.strip() else None,
        "uncertainties": [str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        "intents": normalize_intents(parsed.get("intents")),
    }


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
