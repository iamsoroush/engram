import json
import logging
import re
from time import sleep
from typing import Any

from ai_engine.config import settings

# ``processing`` is a transitional re-export shim (Axis-1 increments 1–2): the shared worker
# infrastructure now lives under ``ai_engine.core`` and the job runners under ``ai_engine.jobs``, but
# evals (``eval/*``) and unit tests still import these names from ``ai_engine.processing`` and patch
# them here. The imports below rebind the moved names into this module so
# ``from ai_engine.processing import X`` keeps working until the shim is deleted (increment 5). Any
# job body still defined below resolves its dependencies in this namespace, so
# ``patch("ai_engine.processing.X")`` still intercepts those calls.
from ai_engine.core.backend_client import BackendClient  # noqa: F401
from ai_engine.core.domain import domain_framing
from ai_engine.core.fixtures import (  # noqa: F401
    TEST_CAPTURE_TEXT_BY_FILENAME,
    TEST_FINAL_SUMMARY,
    is_fixture_capture,
)
from ai_engine.core.gateway import (  # noqa: F401
    _MeteredChat,
    _MeteredClient,
    _MeteredCompletions,
    _pending_audio_seconds,
    _record_gateway_usage,
    _usage_sink,
    arm_usage_sink,
    drain_usage_sink,
    gateway_client,
    gateway_settings_for,
    resolve_model,
    resolve_reasoning_effort,
    set_pending_audio_seconds,
    transcription_is_configured,
)
from ai_engine.core.media import (  # noqa: F401
    CAPTION_JPEG_QUALITY,
    CAPTION_MAX_EDGE,
    CAPTION_PRODUCT_LABEL_MAX_EDGE,
    audio_duration_seconds,
    audio_to_flac_mono_16khz_base64,
    downscale_image_for_caption,
    image_to_data_url,
)
from ai_engine.core.text import (  # noqa: F401
    _LATIN_DIGITS,
    TRANSCRIPTION_LANGUAGE_NAMES,
    enrichment_language_directive,
    normalize_digits_to_latin,
    transcription_language_directive,
)
from ai_engine.core.util import clamp_confidence, utc_now  # noqa: F401
from ai_engine.jobs.capture_note import raw_note_text  # noqa: F401
from ai_engine.jobs.capture_photo import (  # noqa: F401
    CAPTION_LOW_CONFIDENCE_THRESHOLD,
    PAIRING_LATERALITIES,
    PAIRING_PHASES,
    caption_image_content,
    caption_output_metadata,
    caption_prompt,
    normalize_caption_pairing,
    parse_caption_output,
)
from ai_engine.jobs.captures_common import (  # noqa: F401
    NOT_DETECTED_PATIENT,
    CaptureProcessingOutput,
    DetectedPatientOutput,
    capture_detected_patient,
    capture_processing_output,
    completed_metadata,
    output_key_for_capture,
    partial_metadata,
    placeholder_text_for_capture,
)

logger = logging.getLogger(__name__)


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


def capture_text(capture: dict[str, Any]) -> str:
    """Extract the best available mock/generated text for a capture."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    for key in ("transcript", "caption", "note_text", "ocr"):
        generated = metadata.get(key)
        if isinstance(generated, dict) and generated.get("text"):
            return str(generated["text"])
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return TEST_CAPTURE_TEXT_BY_FILENAME[filename]
    return str(metadata.get("detail") or capture.get("type") or "capture")


def extracted_patient_information(captures: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic patient metadata until real extraction exists."""
    combined = "\n".join(capture_text(capture) for capture in captures)
    full_name = "Demo Patient" if "demo patient" in combined.lower() else None
    national_id = "1234567890" if "1234567890" in combined else None
    missing_fields = [
        field
        for field, value in (("full_name", full_name), ("national_id", national_id))
        if not value
    ]
    return {
        "full_name": full_name,
        "national_id": national_id,
        "expected": ["full_name", "national_id"],
        "missing_fields": missing_fields,
        "status": "complete" if not missing_fields else "missing_required",
        "source": "mock-session-job",
    }


def flattened_processing_captures(processing_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return captures from the stable session-processing input context."""
    captures = processing_context.get("captures") if isinstance(processing_context.get("captures"), dict) else {}
    flattened: list[dict[str, Any]] = []
    for group in ("audio", "photos", "text"):
        values = captures.get(group)
        if isinstance(values, list):
            flattened.extend(capture for capture in values if isinstance(capture, dict))
    return flattened


def capture_id(capture: dict[str, Any]) -> str | None:
    """Read capture IDs from either the new context or legacy worker payload."""
    value = capture.get("captureId") or capture.get("id")
    return str(value) if value else None


def session_capture_text(capture: dict[str, Any]) -> str:
    """Extract text from the session-processing context or legacy capture metadata."""
    for key in ("transcript", "caption", "rawText"):
        value = capture.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return capture_text(capture)


def extracted_patient_information_from_context(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return deterministic patient extraction without owning assignment."""
    assigned_patient = processing_context.get("assignedPatient")
    if isinstance(assigned_patient, dict):
        return {
            "status": "assigned_context_available",
            "patient_id": assigned_patient.get("patientId"),
            "display_name": assigned_patient.get("displayName"),
            "source": "db-session-assignment",
        }
    for capture in captures:
        patient_information = capture.get("patientInformation")
        if isinstance(patient_information, dict):
            meaningful_values = [
                patient_information.get("raw_mentioned_name"),
                patient_information.get("standardized_display_name"),
                patient_information.get("national_id"),
                patient_information.get("phone"),
            ]
            if any(isinstance(value, str) and value.strip() for value in meaningful_values):
                return {
                    **patient_information,
                    "source": "capture-transcription-patient-information",
                }
    return extracted_patient_information(captures)


def structured_session_report_body(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
    summary: str,
) -> dict[str, Any]:
    """Build deterministic body-level structured output for session processing."""
    if is_expected_test_fixture(captures):
        return expected_test_structured_report(captures, summary)

    paragraphs: list[str] = []
    history = processing_context.get("patientSummarizedHistory")
    if isinstance(history, str) and history.strip():
        paragraphs.append(f"Known patient history summary: {history.strip()}")

    audio: list[str] = []
    notes: list[str] = []
    photos: list[str] = []
    for capture in captures:
        text = session_capture_text(capture)
        if not text:
            continue
        if capture.get("type") == "audio":
            audio.append(text)
        elif capture.get("type") == "note":
            notes.append(text)
        elif capture.get("type") == "photo":
            photos.append(text)
    if audio:
        paragraphs.append("Audio notes: " + " ".join(audio))
    if notes:
        paragraphs.append("Written notes: " + " ".join(notes))
    if photos:
        paragraphs.append("Photo observations: " + " ".join(photos))
    if not paragraphs:
        paragraphs.append("Mock clinical body generated from the available session context.")

    blocks: list[dict[str, Any]] = [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs]
    for capture in captures:
        if capture.get("type") == "photo" and capture.get("artifactId"):
            blocks.append(
                {
                    "type": "image",
                    "artifactId": str(capture["artifactId"]),
                    "captureId": capture_id(capture),
                    "caption": capture.get("caption") or "Source image",
                }
            )

    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [{"id": "clinical-report", "title": "Clinical report", "blocks": blocks}],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def is_expected_test_fixture(captures: list[dict[str, Any]]) -> bool:
    """Return true when uploads match the deterministic QA fixture."""
    combined = "\n".join(session_capture_text(capture) for capture in captures)
    markers = (
        "follow-up after cheek filler",
        "mild asymmetry on the left cheek",
        "0.3 mL hyaluronic acid filler",
        "avoid heavy exercise for 24 hours",
    )
    return all(marker.lower() in combined.lower() for marker in markers)


def first_capture_by_text(captures: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    """Find a fixture capture by deterministic mock text."""
    for capture in captures:
        if needle.lower() in session_capture_text(capture).lower():
            return capture
    return None


def expected_test_structured_report(captures: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    """Return the final structured report for the provided QA fixture."""
    pre_photo = first_capture_by_text(captures, "Pre-correction image")
    post_photo = first_capture_by_text(captures, "Post-correction image")
    photo_blocks: list[dict[str, Any]] = []
    for capture in (pre_photo, post_photo):
        if capture is None:
            continue
        photo_blocks.append(
            {
                "type": "image",
                "artifactId": str(capture.get("artifactId") or capture.get("sourceArtifactId") or ""),
                "captureId": capture_id(capture),
                "caption": session_capture_text(capture),
            }
        )
    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId") or capture.get("sourceArtifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId") or capture.get("sourceArtifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [
            {
                "id": "visit-reason",
                "title": "Visit Reason",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Follow-up visit after cheek filler. Patient reported mild left cheek asymmetry and requested a conservative correction.",
                    }
                ],
            },
            {
                "id": "relevant-history",
                "title": "Relevant History",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "No pain, fever, or allergy was reported during the visit. Patient prefers subtle correction and wants to avoid visible overfilling.",
                    }
                ],
            },
            {
                "id": "procedure",
                "title": "Procedure",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek using cannula technique. Patient tolerated the procedure well.",
                    }
                ],
            },
            {"id": "photos", "title": "Photos", "blocks": photo_blocks},
            {
                "id": "aftercare",
                "title": "Aftercare",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Aftercare instructions were given. Patient was advised not to massage the area and to avoid heavy exercise for 24 hours. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
                    }
                ],
            },
        ],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def completed_session_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Return mock session summary, metadata, and report output."""
    job = payload["job"]
    session = payload["session"]
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    report_template = payload.get("reportTemplate") or {}
    captured_text = [session_capture_text(capture) for capture in captures]
    summary = (
        TEST_FINAL_SUMMARY
        if is_expected_test_fixture(captures)
        else "Mock session summary: " + (
            " ".join(text[:140] for text in captured_text[:3]) if captured_text else "No capture content was available."
        )
    )
    patient_information = extracted_patient_information_from_context(processing_context, captures)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    structured_report = structured_session_report_body(processing_context, captures, summary)
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "patient_information": patient_information,
        "clinical_metadata": {
            "visit_type": "mock aesthetics consultation",
            "body_area": "mock treatment area",
            "concerns": ["mock concern"],
        },
        "source_capture_ids": source_capture_ids,
    }
    body = "\n\n".join(captured_text) if captured_text else "Mock clinical body generated from session captures."
    # The backend owns report templating and patient-information injection.
    # The AI engine returns structured clinical body content only.
    report = body
    return {
        "status": "completed",
        "summary": summary,
        "extracted_metadata": {
            **extracted_metadata,
            "progressive_report": {
                "status": "processed",
                "format": "markdown",
                "body": report,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "summaries": {
                "status": "processed",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": mock_findings(captures),
            "processing_status": {
                "state": "complete",
                "label": "Complete",
                "stage": "complete",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
        "structured_report": structured_report,
        "report": report,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def mock_findings(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic extracted finding rows for progressive session UX."""
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    if is_expected_test_fixture(captures):
        return [
            {
                "id": "procedure",
                "label": "Procedure",
                "value": "Cheek filler touch-up",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "anatomical_area",
                "label": "Anatomical area",
                "value": "Left mid cheek",
                "category": "clinical",
                "confidence": 0.94,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "product",
                "label": "Product",
                "value": "Hyaluronic acid filler",
                "category": "clinical",
                "confidence": 0.91,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "volume",
                "label": "Volume",
                "value": "0.3 mL",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "technique",
                "label": "Technique",
                "value": "Cannula technique",
                "category": "clinical",
                "confidence": 0.9,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "aftercare",
                "label": "Aftercare",
                "value": "No massage; avoid heavy exercise for 24 hours",
                "category": "clinical",
                "confidence": 0.93,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
        ]
    capture_types = [str(capture.get("type")) for capture in captures if capture.get("type")]
    findings = [
        {
            "id": "visit_type",
            "label": "Visit type",
            "value": "Mock aesthetics consultation",
            "category": "clinical",
            "confidence": 0.82,
            "sourceCaptureIds": source_capture_ids,
            "status": "extracted",
        },
        {
            "id": "source_mix",
            "label": "Source mix",
            "value": ", ".join(sorted(set(capture_types))) or "capture",
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]
    if any("botox" in session_capture_text(capture).lower() for capture in captures):
        findings.append(
            {
                "id": "product",
                "label": "Product",
                "value": "Botox",
                "category": "clinical",
                "confidence": 0.76,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            }
        )
    return findings


def session_progress_output(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    """Return deterministic partial session output for one mock processing stage."""
    session = payload["session"]
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    captured_text = [session_capture_text(capture) for capture in captures]
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    body_source = "\n\n".join(captured_text[:2]) if captured_text else "Mock clinical body is waiting for source capture text."
    stage_copy = {
        "transcripts": "Reading source captures and preparing the report surface.",
        "report": "Drafting the clinical report from available source material.",
        "findings": "Extracting structured findings from the draft.",
        "summary": "Condensing the session into a short clinical summary.",
    }
    summary = stage_copy.get(stage, "Processing session.")
    findings = mock_findings(captures) if stage in {"findings", "summary"} else []
    return {
        "status": "processing",
        "summary": summary,
        "report_template_key": session.get("reportTemplateKey") or "default",
        "extracted_metadata": {
            "status": "processing",
            "generated_by": "ai-engine",
            "job_id": payload["job"]["id"],
            "job_type": payload["job"]["jobType"],
            "generated_at": utc_now().isoformat(),
            "source_capture_ids": source_capture_ids,
            "summaries": {
                "status": "partial",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": findings,
            "processing_status": {
                "state": "processing",
                "label": summary,
                "stage": stage,
                "detail": f"Mock AI stage: {stage}",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
    }


def run_capture_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a capture processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    capture = payload["capture"]
    if job.get("status") == "succeeded":
        return

    output_key = output_key_for_capture(capture["type"])
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    # Audio transcription and Pro photo/note enrichment are real (gateway-backed); Basic, gateway-less,
    # and QA-fixture captures fall back to the deterministic placeholder below.
    client.progress_job(job_id, output_key=output_key, output=partial_metadata(job, capture), stage="transcript")
    if capture.get("type") == "audio":
        source_content = None
        if transcription_is_configured() and capture.get("sourceArtifactId"):
            source_content = client.get_bytes(f"/internal/captures/{capture['id']}/file-content")
        if not transcription_is_configured():
            sleep(settings.mock_stage_delay_seconds)
        client.complete_job(
            job_id,
            output_key=output_key,
            output=completed_audio_metadata(
                job,
                capture,
                source_content,
                payload.get("transcriptionContext"),
                model=resolve_model("transcription", ai_models),
            ),
        )
        return

    # Notes are a pure passthrough (note decoration removed): no gateway call ever. The job marks the
    # note processed with its RAW text — preserving chain ordering + report_contribution wiring — and
    # the report reads the raw `detail`. Fixtures keep their deterministic text for QA.
    if capture.get("type") == "note" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, raw_note_text(capture) or ""))
        return

    # Pro photo captioning. The backend attaches an `enrichmentContext` only for Pro tenants; Basic and
    # gateway-less/fixture captures keep the deterministic/blank fallback. A gateway failure propagates
    # as a retryable worker error; an empty gateway response leaves the caption blank (manual add).
    enrichment_context = payload.get("enrichmentContext") if isinstance(payload.get("enrichmentContext"), dict) else None
    if (
        capture.get("type") == "photo"
        and enrichment_context is not None
        and transcription_is_configured()
        and not is_fixture_capture(capture)
        and capture.get("sourceArtifactId")
    ):
        content, media_type = client.get_file(f"/internal/captures/{capture['id']}/file-content")
        caption_result = caption_image_content(
            content, media_type, enrichment_context, model=resolve_model("caption", ai_models)
        )
        output = caption_output_metadata(job, caption_result) if caption_result else capture_processing_output(job, "")
        client.complete_job(job_id, output_key=output_key, output=output)
        return

    # Un-enriched photos (Basic tenants, or no gateway) get NO AI caption — leave it blank so the UI
    # offers a manual "Add caption" instead of a meaningless placeholder. Fixtures keep their
    # deterministic caption for QA.
    if capture.get("type") == "photo" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, ""))
        return

    sleep(settings.mock_stage_delay_seconds)
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))


# --- Session report synthesis + treatment extraction (Pro, single-pass) ------------------------
#
# The keystone of the Pro capture-intelligence wave. ONE structured call emits the per-visit report
# sections AND the performed treatments[] together (the A↔B contract). It is dispatched by the
# backend (the revived `session_organize` job) only for Pro tenants with a gateway, AFTER the
# deterministic baseline already wrote a report — so synthesis is a refinement that never blocks the
# capture. Gateway-less / malformed → a SKIP sentinel; the backend keeps the deterministic baseline
# and treatments stay empty (Basic + gateway-less run zero AI and must never break).

SESSION_SYNTHESIS_OUTPUT_VERSION = "2026-06-15.session-synthesis-output.v1"

# Fixed section ids + order (rendered by the backend). `treatment-performed` is a PROSE MIRROR of
# treatments[] — the backend re-renders it FROM treatments[] so prose + store can never diverge.
SYNTHESIS_SECTIONS: tuple[tuple[str, str], ...] = (
    ("visit-summary", "Visit summary"),
    ("concern-goals", "Concern & goals"),
    ("assessment", "Assessment"),
    ("treatment-performed", "Treatment performed"),
    ("media", "Media"),
    ("plan-followup", "Plan & follow-up"),
    ("aftercare", "Aftercare"),
)
SYNTHESIS_SECTION_IDS: tuple[str, ...] = tuple(section_id for section_id, _ in SYNTHESIS_SECTIONS)
SYNTHESIS_LANGUAGES = {"fa", "en", "mixed"}

# Persian section titles (report_language="fa"). The body prose already follows reportLanguage; the
# fixed section TITLES must too, or a Persian report shows English headings.
SYNTHESIS_SECTION_TITLES_FA: dict[str, str] = {
    "visit-summary": "خلاصه ویزیت",
    "concern-goals": "نگرانی‌ها و اهداف",
    "assessment": "ارزیابی",
    "treatment-performed": "درمان انجام‌شده",
    "media": "تصاویر",
    "plan-followup": "برنامه و پیگیری",
    "aftercare": "مراقبت‌های بعد از درمان",
}


def synthesis_section_title(section_id: str, default_title: str, report_language: str | None) -> str:
    """Return the section title localized to the report language (English title by default)."""
    if isinstance(report_language, str) and report_language.strip().lower().startswith("fa"):
        return SYNTHESIS_SECTION_TITLES_FA.get(section_id, default_title)
    return default_title


def report_synthesis_json_schema() -> dict[str, Any]:
    """JSON schema for the single-pass synthesis structured output (the A↔B contract)."""
    block = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["paragraph", "image"]},
            "text": {"type": ["string", "null"]},
            "captureId": {"type": ["string", "null"]},
            "caption": {"type": ["string", "null"]},
        },
        "required": ["type"],
    }
    section = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "blocks": {"type": "array", "items": block},
        },
        "required": ["id", "title", "blocks"],
    }
    treatment = {
        "type": "object",
        "properties": {
            "area": {"type": "string"},
            "product": {"type": "string"},
            "brand": {"type": ["string", "null"]},
            "quantity": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]},
            "quantityText": {"type": ["string", "null"]},
            "lot": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "sourceCaptureIds": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": ["string", "null"]},
            "carriedForward": {"type": "boolean"},
            "supersedesCaptureId": {"type": ["string", "null"]},
            "attributes": {"type": "object"},
        },
        "required": ["area", "product", "confidence", "sourceCaptureIds", "carriedForward"],
    }
    aftercare_selection = {
        "type": "object",
        "properties": {
            "templateId": {"type": "string"},
            "status": {"type": "string", "enum": ["applies", "conflicts", "superseded"]},
            "note": {"type": ["string", "null"]},
        },
        "required": ["templateId", "status"],
    }
    safety_flag = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["allergy", "contraindication", "consent"]},
            "text": {"type": "string"},
            "sourceCaptureIds": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "text"],
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "language": {"type": "string", "enum": ["fa", "en", "mixed"]},
            "sections": {"type": "array", "items": section},
            "treatments": {"type": "array", "items": treatment},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
            "aftercareSelections": {"type": "array", "items": aftercare_selection},
            "safetyFlags": {"type": "array", "items": safety_flag},
        },
        "required": [
            "summary",
            "language",
            "sections",
            "treatments",
            "uncertainties",
            "aftercareSelections",
            "safetyFlags",
        ],
    }


def report_synthesis_prompt(processing_context: dict[str, Any]) -> str:
    """Build the single-pass report-synthesis + treatment-extraction prompt.

    Vertical-AGNOSTIC: the clinical setting comes from the domain descriptor (neutral "clinic" when
    absent). The prompt encodes the design's discipline: ground every statement in captures, native
    script prose, verbatim quantities/brands, stable targeted update from the prior draft + changeset,
    corrections-vs-additions with `supersedesCaptureId`, carry-forward only on an explicit cue, and
    "leave null rather than guess".
    """
    context = processing_context if isinstance(processing_context, dict) else {}
    label, vocabulary, _ = domain_framing(context)
    report_language = context.get("reportLanguage")
    language_directive = (
        f"Write all report prose in {report_language} using its native script."
        if isinstance(report_language, str) and report_language.strip()
        else "Write all report prose in the language the captures use (the report template's default)."
    )
    vocab_line = f"Common {label} vocabulary may include {', '.join(vocabulary)}. " if vocabulary else ""
    section_lines = "; ".join(f"{section_id} ({title})" for section_id, title in SYNTHESIS_SECTIONS)
    return "\n\n".join(
        (
            f"You are Engram, synthesizing ONE per-visit clinical report and extracting the performed "
            f"treatments for a {label}. Work only from the provided captures (audio transcripts, photo "
            f"captions, and raw text notes) and the prior visit context. Invent nothing.",
            (
                "Produce a strict JSON object with EXACTLY these keys: summary, language, sections, "
                "treatments, uncertainties, aftercareSelections, safetyFlags.\n"
                f"- sections: populate these fixed section ids, in this order: {section_lines}. Each "
                "section has id, title, and blocks. A block is either {\"type\":\"paragraph\",\"text\":...} "
                "or {\"type\":\"image\",\"captureId\":<a photo captureId from the context>,\"caption\":...}. "
                "Leave a section's blocks empty ([]) when the captures do not support it — never pad it.\n"
                f"- {language_directive} Write the DESCRIPTIVE treatment fields — area, product (the "
                "generic/category, e.g. فیلر/ژل, بوتاکس), and unit (e.g. واحد, سی‌سی) — in the REPORT "
                "LANGUAGE using its native script; prefer the clinician's own word when they gave one. "
                "Do NOT emit an English category (\"filler\", \"botox\", \"unit\") in a Persian report. "
                "Keep VERBATIM in their original script: brand names, lot numbers, patient/clinician "
                "quotes, and quantityText (e.g. «۲ سی‌سی») — never translate or romanize these, and never "
                "normalize «۲» to \"2\" in quantityText.\n"
                f"{vocab_line}"
                "- treatments: one TreatmentItem per distinct performed treatment, with core fields "
                "area, product, brand, quantity (number or null), unit, quantityText (VERBATIM original "
                "script), lot (dictated or read off a product-label photo), confidence (0..1), "
                "sourceCaptureIds, evidence, carriedForward, supersedesCaptureId, and an open attributes "
                "map (needleGauge, depth, device, sessions, …). The treatment-performed section is a prose "
                "MIRROR of treatments — keep them consistent.\n"
                "- product vs brand: `product` is the GENERIC category ONLY (e.g. ژل/فیلر, بوتاکس) — never "
                "put a commercial brand in it. `brand` is the commercial name verbatim (e.g. ژوویدرم/"
                "Juvederm, رستیلین/Restylane, ولوما/Voluma), null if none was said. When the clinician "
                "names a brand (e.g. «ژل ژوویدرم»), set product=«ژل» and brand=«ژوویدرم» — split them, "
                "never merge the brand into product.\n"
                "- Leave any field null rather than guessing. Set confidence to reflect genuine certainty."
            ),
            (
                "UPDATE DISCIPLINE — the captures are authoritative. If a prior report draft and a "
                "changeset are provided, update the prior draft to match the current captures: keep "
                "unchanged prose byte-stable, recompute only the sections/treatments affected by the "
                "changed captures, and REMOVE anything no longer supported by a capture."
            ),
            (
                "CORRECTIONS vs ADDITIONS (e.g. «ژل ۲ سی‌سی» then «ژل ۳ سی‌سی» for the same area):\n"
                "- CORRECTION (supersede): on an explicit correction cue (اشتباه گفتم، منظورم…بود، "
                "\"actually\", \"make that\") OR the same area+product+unit simply restated with a new "
                "quantity. Emit ONE corrected TreatmentItem and set supersedesCaptureId to the captureId "
                "of the superseded statement (auditable/undoable).\n"
                "- ADDITION: on an additive cue (هم…هم، اضافه، \"another\") OR a different area/product. "
                "Emit a separate TreatmentItem for each.\n"
                "- AMBIGUOUS (cannot tell correction from addition): DO NOT silently overwrite. Emit BOTH "
                "treatments AND add a clear sentence to uncertainties describing the ambiguity."
            ),
            (
                "CARRY-FORWARD: only when a capture explicitly says \"same as last time\" (همون قبلی، "
                "مثل دفعه قبل). Then set carriedForward=true, LOWER the confidence, cite the prior visit "
                "in sourceCaptureIds/evidence, and copy the referenced prior-visit treatment. NEVER "
                "silently materialize a prior dose without an explicit cue."
            ),
            (
                "AFTERCARE SELECTION (intelligent, not keyword): the clinic's reusable aftercare protocols "
                "are in the context as `aftercareTemplates` [{id, name, procedureType, body}]. Decide by "
                "CLINICAL RELEVANCE — judge the procedure, not a word match — and return one entry per "
                "applicable protocol in `aftercareSelections` [{templateId, status, note}].\n"
                "- COMPLETENESS: emit a selection for EVERY protocol whose procedure was actually performed "
                "this visit (one per treatment area/product, e.g. a botox+filler visit → BOTH the botox and "
                "filler protocols). Do not omit an applicable protocol just because another one conflicts. "
                "Omit only protocols whose procedure was NOT performed; return [] if none were performed or "
                "there are no templates.\n"
                "- PER-PROCEDURE: compare a protocol ONLY against what the clinician dictated about that "
                "SAME procedure/area — never judge the botox protocol against a filler instruction.\n"
                "- status='applies': that procedure's protocol fits and the clinician dictated nothing that "
                "contradicts it. note=null.\n"
                "- status='conflicts': the clinician DICTATED aftercare for that procedure that DIFFERS from "
                "its protocol (e.g. botox protocol says avoid sun 3 days, clinician said 1 week). The "
                "clinician's words win — set note to ONE sentence in the report language naming the specific "
                "difference and quoting both values.\n"
                "- status='superseded': the clinician dictated their OWN full aftercare that REPLACES that "
                "protocol entirely. note = one short sentence in the report language saying so.\n"
                "Prefer the clinician's dictated aftercare over a fixed protocol whenever they differ; never "
                "silently include a protocol that contradicts what the clinician said."
            ),
            (
                "SAFETY FLAGS (highest priority — surface, never gate): scan EVERY capture for any ALLERGY, "
                "CONTRAINDICATION, or CONSENT statement actually made this visit, and return one entry per "
                "distinct mention in `safetyFlags` [{kind, text, sourceCaptureIds}].\n"
                "- kind='allergy': a stated allergy or prior adverse reaction (e.g. «به لیدوکائین حساسیت "
                "داره», «آلرژی به پنی‌سیلین»).\n"
                "- kind='contraindication': a stated reason to avoid or use caution with a treatment — "
                "pregnancy/breastfeeding, anticoagulants, active infection at the site, recent isotretinoin, "
                "autoimmune or keloid history, a drug interaction the clinician flags.\n"
                "- kind='consent': a statement about informed consent for a procedure — given, declined, "
                "withdrawn, or still pending/required (e.g. «رضایت‌نامه امضا شد», «هنوز رضایت نگرفتیم»).\n"
                "- text: ONE short clinical sentence, in the REPORT LANGUAGE using its native script, stating "
                "exactly what the capture says (quote the clinician's own words where possible). NEVER "
                "translate, soften, or generalize the clinical content.\n"
                "- GROUNDING: flag ONLY what a capture EXPLICITLY states. Invent nothing; never infer an "
                "allergy or contraindication from the treatment itself, and NEVER emit a negative/absence "
                "statement (no «no known allergies», no «مشکلی نداشت»). Set sourceCaptureIds to the "
                "captureId(s) that state it.\n"
                "- Safety errs toward INCLUSION: when a statement plausibly reads as an allergy / "
                "contraindication / consent concern, include it — the clinician removes a wrong one. Return "
                "[] only when no capture states any such thing."
            ),
            (
                "uncertainties: a list of short human-readable sentences for anything a clinician should "
                "confirm (ambiguous correction, a missing-but-expected lot number, a low-confidence "
                "product, a carried-forward dose). Return ONLY strict JSON, no markdown, no code fences."
            ),
            f"Session context (captures, prior report draft, changeset, prior-visit treatments):\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )


def _clean_synthesis_blocks(raw_blocks: Any) -> list[dict[str, Any]]:
    """Coerce model block output into validated paragraph/image blocks."""
    blocks: list[dict[str, Any]] = []
    if not isinstance(raw_blocks, list):
        return blocks
    for block in raw_blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "paragraph":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                blocks.append({"type": "paragraph", "text": text.strip()})
        elif block_type == "image":
            capture_id = block.get("captureId")
            if isinstance(capture_id, str) and capture_id.strip():
                image: dict[str, Any] = {"type": "image", "captureId": capture_id.strip()}
                caption = block.get("caption")
                if isinstance(caption, str) and caption.strip():
                    image["caption"] = caption.strip()
                blocks.append(image)
    return blocks


def _clean_synthesis_treatment(raw: Any) -> dict[str, Any] | None:
    """Coerce one TreatmentItem into the stable core+attributes shape, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    area = raw.get("area")
    product = raw.get("product")
    if not (isinstance(area, str) and area.strip()) and not (isinstance(product, str) and product.strip()):
        return None

    def _text(value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    def _number(value: Any) -> float | int | None:
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    source_ids = raw.get("sourceCaptureIds")
    attributes = raw.get("attributes")
    return {
        "area": _text(area) or "",
        "product": _text(product) or "",
        "brand": _text(raw.get("brand")),
        "quantity": _number(raw.get("quantity")),
        "unit": _text(raw.get("unit")),
        "quantityText": _text(raw.get("quantityText")),
        "lot": _text(raw.get("lot")),
        "confidence": clamp_confidence(raw.get("confidence")),
        "sourceCaptureIds": [str(value) for value in source_ids if isinstance(value, str)] if isinstance(source_ids, list) else [],
        "evidence": _text(raw.get("evidence")),
        "carriedForward": raw.get("carriedForward") is True,
        "supersedesCaptureId": _text(raw.get("supersedesCaptureId")),
        "attributes": attributes if isinstance(attributes, dict) else {},
    }


def parse_session_synthesis_output(
    raw_text: str, *, source_capture_ids: list[str] | None = None, report_language: str | None = None
) -> dict[str, Any] | None:
    """Parse + validate the synthesis JSON into the A↔B contract, or None to fall back.

    Returns the full output with ALL fixed section ids present (in order), cleaned treatments, and
    `sourceReferences` covering every reportable capture so the backend can mark contributions.
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
    if not isinstance(parsed, dict):
        return None
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None

    raw_sections = parsed.get("sections")
    blocks_by_id: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw_sections, list):
        for section in raw_sections:
            if isinstance(section, dict) and isinstance(section.get("id"), str):
                blocks_by_id[section["id"]] = _clean_synthesis_blocks(section.get("blocks"))
    sections = [
        {
            "id": section_id,
            "title": synthesis_section_title(section_id, title, report_language),
            "blocks": blocks_by_id.get(section_id, []),
        }
        for section_id, title in SYNTHESIS_SECTIONS
    ]

    treatments = [cleaned for cleaned in (_clean_synthesis_treatment(item) for item in (parsed.get("treatments") or [])) if cleaned]
    language = parsed.get("language") if parsed.get("language") in SYNTHESIS_LANGUAGES else "mixed"
    uncertainties = parsed.get("uncertainties")
    source_references = [{"type": "capture", "captureId": capture_id} for capture_id in (source_capture_ids or [])]
    return {
        "schemaVersion": SESSION_SYNTHESIS_OUTPUT_VERSION,
        "summary": summary.strip(),
        "language": language,
        "sections": sections,
        "treatments": treatments,
        "sourceReferences": source_references,
        "uncertainties": [str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        "aftercareSelections": _clean_aftercare_selections(parsed.get("aftercareSelections")),
        "safetyFlags": _clean_safety_flags(parsed.get("safetyFlags")),
        "generatedBy": "ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def _clean_aftercare_selections(raw: Any) -> list[dict[str, Any]]:
    """Coerce the model's aftercare matches into validated {templateId, status, note} items."""
    selections: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return selections
    for item in raw:
        if not isinstance(item, dict):
            continue
        template_id = item.get("templateId")
        status = item.get("status")
        if not isinstance(template_id, str) or not template_id.strip():
            continue
        if status not in {"applies", "conflicts", "superseded"}:
            continue
        note = item.get("note")
        selections.append(
            {"templateId": template_id, "status": status, "note": note if isinstance(note, str) and note.strip() else None}
        )
    return selections


def _clean_safety_flags(raw: Any) -> list[dict[str, Any]]:
    """Coerce the model's safety flags into validated {kind, text, sourceCaptureIds} items.

    Safety errs toward inclusion (opt-out): a flag the model surfaced is kept — the clinician removes a
    wrong one downstream. We only drop items that are structurally unusable (unknown kind, empty text).
    ``text`` is clinical content in the report language and is never translated.
    """
    flags: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return flags
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if kind not in {"allergy", "contraindication", "consent"}:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        source_ids = item.get("sourceCaptureIds")
        flags.append(
            {
                "kind": kind,
                "text": text.strip(),
                "sourceCaptureIds": [str(value) for value in source_ids if isinstance(value, str)]
                if isinstance(source_ids, list)
                else [],
            }
        )
    return flags


def synthesize_session_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run the single-pass report synthesis through the gateway; None to fall back to baseline.

    Network/gateway EXCEPTIONS propagate (retryable). Empty/malformed CONTENT returns None so the
    caller emits the skip sentinel and the deterministic baseline stands (never breaks).
    """
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("report_synthesis", ai_models)
    effort = resolve_reasoning_effort(
        "report_synthesis", ai_models, default=(settings.report_synthesis_reasoning_effort or None)
    )
    client = gateway_client("report_synthesis")
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": report_synthesis_prompt(processing_context)}],
        # Schema-enforced JSON; NO temperature (GPT-5-class rejects it — stability from low effort).
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "session_synthesis_output", "schema": report_synthesis_json_schema()},
        },
    }
    if effort:
        request["extra_body"] = {"reasoning_effort": effort}
    response = client.chat.completions.create(**request)
    return parse_session_synthesis_output(
        response.choices[0].message.content or "",
        source_capture_ids=source_capture_ids,
        report_language=processing_context.get("reportLanguage") if isinstance(processing_context, dict) else None,
    )


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


def session_synthesis_skip_output(reason: str) -> dict[str, Any]:
    """Sentinel telling the backend synthesis did not run — keep the deterministic baseline."""
    return {
        "status": "skipped",
        "synthesis_skipped": True,
        "reason": reason,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def completed_session_synthesis_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the worker completion envelope for a Pro session synthesis job.

    Wraps the A↔B synthesis output as `structured_report` plus the top-level summary +
    extracted_metadata the backend's `complete_session_worker_job` expects. Gateway-less or
    malformed → a skip sentinel so the deterministic baseline is preserved (treatments empty).
    """
    job = payload["job"]
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    report_template = payload.get("reportTemplate") if isinstance(payload.get("reportTemplate"), dict) else {}
    if not transcription_is_configured():
        return session_synthesis_skip_output("gateway_not_configured")
    synthesis = synthesize_session_report(payload)
    if synthesis is None:
        return session_synthesis_skip_output("empty_or_malformed_synthesis")

    source_capture_ids = [reference["captureId"] for reference in synthesis["sourceReferences"] if reference.get("captureId")]
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_capture_ids": source_capture_ids,
        # The backend post-processes treatments (validate/supersede/carry-forward) before storing.
        "treatments": synthesis["treatments"],
        "uncertainties": synthesis["uncertainties"],
        # The model's intelligent aftercare matches (which clinic protocols apply + dictation conflicts).
        "aftercare_selections": synthesis.get("aftercareSelections", []),
        # Session-level safety flags (allergy/contraindication/consent) detected from the captures.
        # Auto-kept (opt-out): the clinician rejects a wrong one; the backend persists the rest to the
        # patient so they surface cross-visit. Clinical text stays in the report language (never translated).
        "safety_flags": synthesis.get("safetyFlags", []),
        "processing_status": {
            "state": "complete",
            "label": "Complete",
            "stage": "complete",
            "source": "ai-engine",
            "updated_at": utc_now().isoformat(),
        },
    }
    # Cross-visit SAFETY RECONCILE (selection-only): dedup-by-meaning / supersede this visit's newly
    # detected flags against the patient's existing ones. Best-effort + gated — a failure or sparse set
    # leaves the deterministic union (the safety floor) intact; never breaks the synthesis.
    context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    existing_flags = context.get("patientSafetyFlags") if isinstance(context.get("patientSafetyFlags"), list) else []
    new_flags = [
        {"key": _safety_flag_key(flag.get("kind"), flag.get("text")), "kind": flag.get("kind"), "text": flag.get("text")}
        for flag in extracted_metadata["safety_flags"]
        if isinstance(flag, dict) and flag.get("kind") and flag.get("text")
    ]
    if len(existing_flags) + len(new_flags) >= 2:
        try:
            decisions = reconcile_safety_flags(
                {"existingFlags": existing_flags, "newFlags": new_flags, "aiModels": payload.get("aiModels")}
            )
            if decisions:
                extracted_metadata["safety_reconciliation"] = decisions
        except Exception:  # noqa: BLE001 — reconcile is additive; never fail the synthesis on it
            pass
    return {
        "status": "completed",
        "summary": synthesis["summary"],
        "structured_report": synthesis,
        "extracted_metadata": extracted_metadata,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    # Pro single-pass report synthesis + treatment extraction (the revived `session_organize`). The
    # backend sets `reportSynthesis` only for Pro tenants with a gateway, AFTER the deterministic
    # baseline already wrote a report. Gateway-less / malformed yields a skip sentinel that the
    # backend treats as "keep the deterministic baseline" (treatments empty) — never breaks.
    if payload.get("reportSynthesis"):
        client.complete_job(job_id, output_key="session_outputs", output=completed_session_synthesis_output(payload))
        return

    # Legacy deterministic progressive stages (placeholder pipeline + recovery of pre-synthesis jobs).
    for stage in ("transcripts", "report", "findings", "summary"):
        client.progress_job(job_id, output_key="session_progress", output=session_progress_output(payload, stage), stage=stage)
        sleep(settings.mock_stage_delay_seconds)

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))


# --- Combined patient memory (Pro): summary + history in one call ------------------------------


def patient_memory_prompt(payload: dict[str, Any]) -> str:
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
                "lot) — use them to ground recall in specifics (e.g. 'last visit: Voluma 0.3 mL, left "
                "cheek'), quoting doses verbatim. Produce a warm, assistant-voiced brief — natural "
                "sentences, never a form or bullet dump. Synthesize across visits, but do NOT invent "
                "clinical facts, names, products, or doses that are not present in the briefs. Do NOT "
                "include the patient's name in any field — it is already shown beside this text in the "
                "UI; use pronouns or omit the subject. Keep the card summary to 1-2 sentences. "
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
                "Return ONLY strict JSON (no markdown, no code fences) with EXACTLY this shape:\n"
                '{"summary": "<1-2 sentence card summary>", '
                '"history": {"snapshot": "<one line: patient + current focus>", '
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


def parse_patient_memory_output(text: str) -> dict[str, Any] | None:
    """Parse the model's patient-memory JSON; return None if unusable so the caller can fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) >= 2 else cleaned.strip("`")
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    history = data.get("history")
    if not isinstance(summary, str) or not summary.strip() or not isinstance(history, dict):
        return None
    if not isinstance(history.get("snapshot"), str):
        return None
    sections = history.get("sections")
    if not isinstance(sections, list) or not sections:
        return None
    # The compact line-up card is optional (backend layers in a deterministic fallback if absent).
    card = data.get("card")
    return {"summary": summary.strip(), "history": history, "card": card if isinstance(card, dict) else None}


def completed_patient_memory_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the combined patient summary+history output, via the gateway when configured.

    Falls back to the backend-provided deterministic content when no gateway is configured or when
    the model returns something unusable, so the job always completes with valid memory.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "summary": fallback.get("summary"),
            "history": fallback.get("history"),
            "card": fallback.get("card"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("patient_memory", ai_models)
    client = gateway_client("patient_memory")
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": patient_memory_prompt(payload)}],
    )
    parsed = parse_patient_memory_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    history = parsed["history"]
    history["source"] = f"ai:{model}"
    return {
        "summary": parsed["summary"],
        "history": history,
        # Carry the model's compact card through; backend coerces it + falls back deterministically.
        "card": parsed.get("card") or fallback.get("card"),
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_patient_memory_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a combined patient summary+history job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="patient_memory", output=completed_patient_memory_output(payload))


def qa_draft_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for a post-session patient Q&A reply draft (AES-402).

    The doctor reviews and approves the result before anything is sent, so the draft must be a warm,
    clinically-cautious *suggestion* grounded in the doctor's prior answers + this patient's context,
    inventing no clinical facts and escalating to the clinic when warranted.
    """
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


def parse_qa_draft_output(text: str) -> str | None:
    """Return a usable plain-text reply draft from the model output, else None to fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) >= 2 else cleaned.strip("`")
        cleaned = cleaned.strip()
    return cleaned or None


def completed_qa_draft_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the Q&A reply-draft output, via the gateway when configured.

    Falls back to the backend-provided deterministic draft when no gateway is configured or the
    model returns nothing usable, so the job always completes and the inbox always has a suggestion.
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "draft": fallback.get("draft"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured():
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    client = gateway_client("qa_draft")
    # A gateway/network error propagates and is retried by the task wrapper (gateway_unavailable).
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": qa_draft_prompt(payload)}],
    )
    draft = parse_qa_draft_output(response.choices[0].message.content or "")
    if draft is None:
        return _fallback_output()
    return {
        "draft": draft,
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_draft_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a post-session patient Q&A reply-draft job through the backend API contract (AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    client.complete_job(job_id, output_key="qa_draft", output=completed_qa_draft_output(payload))


def qa_revise_prompt(payload: dict[str, Any]) -> str:
    """Prompt for a Q&A reply voice edit: classify revise-vs-replace and produce the reply (AES-402).

    The doctor recorded a voice note while reviewing a draft reply. The model must decide whether the
    note is a *revision* of the current draft or an *entirely new reply*, then output the resulting
    reply. The doctor approves before anything is sent, so this is a suggestion — invent no clinical
    facts beyond the draft + spoken note + context.
    """
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
            f"Patient question:\n{qa.get('patientQuestion', '')}",
            f"Current draft reply:\n{qa.get('currentDraft', '')}",
            f"This patient's context:\n{json.dumps(qa.get('patientContext', {}), ensure_ascii=False, sort_keys=True)}",
            f"The doctor's prior answers:\n{json.dumps(qa.get('priorAnswers', []), ensure_ascii=False, sort_keys=True)}",
        )
    )


def parse_qa_revise_output(text: str) -> dict[str, Any] | None:
    """Parse the strict JSON {mode, reply} from the model; None to fall back."""
    if not text or not text.strip():
        return None
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None
    mode = parsed.get("mode") if parsed.get("mode") in {"revise", "replace"} else "revise"
    return {"mode": mode, "reply": reply.strip()}


def completed_qa_revise_output(payload: dict[str, Any], audio: bytes) -> dict[str, Any]:
    """Revise/replace the reply from the doctor's voice note via the configured Q&A model.

    Falls back to keeping the current draft unchanged when no gateway is configured or the model
    returns nothing usable, so the job always completes (the doctor can still edit by hand).
    """
    fallback = payload.get("deterministicFallback") if isinstance(payload.get("deterministicFallback"), dict) else {}

    def _fallback_output() -> dict[str, Any]:
        return {
            "mode": fallback.get("mode") or "revise",
            "reply": fallback.get("reply"),
            "source": fallback.get("source") or "mock-deterministic",
            "generated_by": "ai-engine",
            "generated_at": utc_now().isoformat(),
        }

    if not transcription_is_configured() or not audio:
        return _fallback_output()

    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("qa_draft", ai_models)
    base64_flac = audio_to_flac_mono_16khz_base64(audio)
    client = gateway_client("qa_draft")
    # A gateway/network error propagates and is retried by the task wrapper.
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": qa_revise_prompt(payload)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ],
    )
    parsed = parse_qa_revise_output(response.choices[0].message.content or "")
    if parsed is None:
        return _fallback_output()
    return {
        "mode": parsed["mode"],
        "reply": parsed["reply"],
        "source": f"ai:{model}",
        "model": model,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def run_qa_revise_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a Q&A reply voice-edit job (revise/replace from the doctor's spoken note; AES-402)."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return
    qa = payload.get("qaRevise") if isinstance(payload.get("qaRevise"), dict) else {}
    audio = b""
    endpoint = qa.get("voiceEndpoint")
    if transcription_is_configured() and endpoint:
        audio, _ = client.get_file(endpoint)
    client.complete_job(job_id, output_key="qa_revise", output=completed_qa_revise_output(payload, audio))
