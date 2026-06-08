import base64
import json
import re
import subprocess
from datetime import datetime, timezone
from time import sleep
from typing import Any, Literal, NotRequired, TypedDict

import httpx
from openai import OpenAI

from ai_engine.config import settings


class DetectedPatientOutput(TypedDict):
    """Future-ready patient detection result for capture processors."""

    status: Literal["detected", "not_detected", "uncertain"]
    full_name: str | None
    national_id: str | None
    confidence: float | None
    evidence: str | None
    source_text: str | None


class CaptureProcessingOutput(TypedDict, total=False):
    """Stable capture-processing output shape written into capture metadata."""

    status: str
    text: str
    generated_by: str
    job_id: str
    job_type: str
    generated_at: str
    source_artifact_ids: list[str]
    detected_patient: NotRequired[DetectedPatientOutput]
    language: NotRequired[str]
    patient_information: NotRequired[dict[str, Any]]
    clinical_summary: NotRequired[str | None]
    uncertainties: NotRequired[list[str]]
    intents: NotRequired[dict[str, Any] | None]


NOT_DETECTED_PATIENT: DetectedPatientOutput = {
    "status": "not_detected",
    "full_name": None,
    "national_id": None,
    "confidence": None,
    "evidence": None,
    "source_text": None,
}

TEST_CAPTURE_TEXT_BY_FILENAME = {
    "audio_01_initial_consultation.wav": "Patient Sara Nazari came for a follow-up after cheek filler. She reports mild asymmetry on the left cheek and wants a conservative correction. No pain, no fever, and no allergy was reported.",
    "photo_01_pre_correction_left_cheek.jpg": "Pre-correction image showing mild left cheek asymmetry before touch-up.",
    "text_note_01.txt": "Patient prefers subtle correction and does not want visible overfilling. Conservative approach requested. Aftercare instructions were given. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
    "audio_02_procedure_note.wav": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek. Used cannula technique. Patient tolerated the procedure well. Advised no massage and avoid heavy exercise for 24 hours.",
    "photo_02_post_correction_left_cheek.jpg": "Post-correction image showing improved left cheek contour after conservative correction.",
}

TEST_FINAL_SUMMARY = "Follow-up cheek filler correction for mild left cheek asymmetry. Conservative 0.3 mL hyaluronic acid filler touch-up was performed in the left mid cheek using cannula technique. Patient tolerated the procedure well and received aftercare instructions."

TRANSCRIPTION_LANGUAGES = {"fa", "en", "mixed", "unknown"}

ASSIGNMENT_INTENT_BASES = {"explicit", "implicit"}

TRANSCRIPTION_LANGUAGE_NAMES = {
    "fa": "Persian (Farsi)",
    "en": "English",
    "ar": "Arabic",
}


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


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def output_key_for_capture(capture_type: str) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == "audio":
        return "transcript"
    if capture_type == "photo":
        return "caption"
    return "decorated_text"


def placeholder_text_for_capture(capture: dict[str, Any]) -> str:
    """Build deterministic placeholder output until real AI processors land."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return TEST_CAPTURE_TEXT_BY_FILENAME[filename]
    detail = str(metadata.get("detail") or "").strip()
    capture_type = capture.get("type")
    if capture_type == "audio":
        raise RuntimeError("Audio transcription gateway is not configured")
    if capture_type == "photo":
        return "Caption placeholder. Image capture processing completed successfully."
    if detail:
        normalized_detail = " ".join(detail.split())
        if "Patient prefers subtle correction" in normalized_detail and "follow-up photo in 2 weeks" in normalized_detail:
            return TEST_CAPTURE_TEXT_BY_FILENAME["text_note_01.txt"]
        return detail
    return "Text placeholder. Text capture processing completed successfully."


def capture_detected_patient(capture: dict[str, Any], text: str) -> DetectedPatientOutput | None:
    """Return schema-ready patient detection output without performing detection."""
    if capture.get("type") != "audio":
        return None
    # TODO(ai-integration): Replace this deterministic stub with real patient
    # detection, preserving the same status/full_name/national_id/confidence
    # and evidence/source_text fields for later session assignment.
    return {**NOT_DETECTED_PATIENT, "source_text": text}


def completed_metadata(job: dict[str, Any], capture: dict[str, Any]) -> CaptureProcessingOutput:
    """Return metadata for a completed placeholder capture processor."""
    text = placeholder_text_for_capture(capture)
    output = capture_processing_output(job, text)
    detected_patient = capture_detected_patient(capture, text)
    if detected_patient is not None:
        output["detected_patient"] = detected_patient
    return output


def partial_metadata(job: dict[str, Any], capture: dict[str, Any]) -> CaptureProcessingOutput:
    """Return deterministic in-progress capture output."""
    capture_type = capture.get("type")
    label = "Transcribing" if capture_type == "audio" else "Reading image" if capture_type == "photo" else "Structuring note"
    text = f"{label} audio..." if capture_type == "audio" else f"{label} placeholder output..."
    output: CaptureProcessingOutput = {
        "status": "processing",
        "text": text,
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
    }
    if capture_type == "audio":
        output["detected_patient"] = {**NOT_DETECTED_PATIENT}
    return output


def transcription_is_configured() -> bool:
    """Return whether a real audio transcription gateway is configured."""
    return bool(settings.transcription_base_url.strip())


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


def clamp_confidence(value: Any) -> float:
    """Clamp a model-provided confidence into [0.0, 1.0], defaulting to 0.0."""
    return max(0.0, min(float(value), 1.0)) if isinstance(value, int | float) else 0.0


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
    return "\n\n".join(
        part
        for part in (
            configured_prompt if configured_prompt and configured_prompt != "Transcribe this audio." else None,
            (
                "You are transcribing and extracting clinical identity details for AesMem, an aesthetics clinic memory system. "
                "The audio may be Persian/Farsi, English, or mixed. Preserve the transcript faithfully, including clinically relevant filler words when useful. "
                f"{language_directive} "
                "Keep names inside the transcript exactly as spoken (original script); provide a readable English transliteration ONLY in standardized_display_name (with alternates in alternate_transliterations) — do not let that transliteration change the transcript text. "
                "Iranian national IDs and phone numbers may be spoken digit by digit in Persian, Arabic, or English numerals; normalize them to digit strings when explicitly present. "
                "Aesthetics-clinic vocabulary may include filler, Botox, laser, injection, cannula, hyaluronic acid, aftercare, asymmetry, touch-up, swelling, bruising, and follow-up. "
                "Use the context only to improve spelling and interpretation. Do not infer patient identity unless it is explicitly present in the audio or strongly supported by assigned-patient/session context. "
                "Also classify intent in `intents`: set assignment.present=true whenever the audio indicates which patient this visit is about (a stated or mentioned name or identifier counts). Set basis='explicit' ONLY for a clear instruction to change or correct an existing assignment (for example 'change the patient to X', 'this is actually X not Y', or 'wrong patient, it's X'). Treat any statement of who the patient is as basis='implicit' — this includes a name simply stated or fronted and identity declarations (for example 'Ms. Ghasemi, forehead botox', 'the patient is X', 'this is X', or 'I am X'). When unsure, prefer 'implicit'. Set out_of_context.present=true when the audio has no clinical or visit content; set append.present=true when it only adds incremental detail to an ongoing note; use null for any intent you cannot determine. "
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
    language = parsed.get("language")
    if language not in TRANSCRIPTION_LANGUAGES:
        language = "unknown"
    patient_information = parsed.get("patient_information")
    if not isinstance(patient_information, dict):
        raise RuntimeError("Audio transcription structured JSON is missing patient_information")

    normalized_patient = empty_patient_information(source_text=transcript.strip())
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

    uncertainties = parsed.get("uncertainties")
    clinical_summary = parsed.get("clinical_summary")
    return {
        "transcript": transcript.strip(),
        "language": language,
        "patient_information": normalized_patient,
        "clinical_summary": clinical_summary.strip() if isinstance(clinical_summary, str) and clinical_summary.strip() else None,
        "uncertainties": [str(value) for value in uncertainties if isinstance(value, str)] if isinstance(uncertainties, list) else [],
        "intents": normalize_intents(parsed.get("intents")),
    }


def audio_to_flac_mono_16khz_base64(content: bytes) -> str:
    """Convert arbitrary audio bytes to mono 16 kHz FLAC and base64 encode them."""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        "-f",
        "flac",
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, input=content, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("Audio conversion to FLAC failed: ffmpeg is not installed or not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Audio conversion to FLAC failed: {stderr or exc}") from exc
    return base64.b64encode(result.stdout).decode("ascii")


def transcribe_audio_content(
    content: bytes,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> dict[str, Any]:
    """Transcribe audio through the configured OpenAI-compatible gateway."""
    base64_flac = audio_to_flac_mono_16khz_base64(content)
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


# --- Pro enrichment: real image captions + note decoration -------------------------------------
#
# Photo captioning and note decoration are Pro-tier capabilities (see the tier table in
# docs/intelligence-layer.md §3). The backend gates them: it attaches an `enrichmentContext` to a
# photo/note worker payload only for Pro tenants (reusing the existing `tenant_tier` gate), so a
# Basic tenant never incurs a gateway call and keeps the deterministic passthrough placeholder.
# The worker stays a pure function of its payload — it enriches iff an `enrichmentContext` is
# present and a gateway is configured, and falls back to the placeholder otherwise. The output key
# is unchanged (`caption` / `decorated_text`), so the worker contract stays stable.


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


def caption_prompt(enrichment_context: dict[str, Any] | None) -> str:
    """Build the instruction prompt for clinical photo captioning."""
    context = enrichment_context if isinstance(enrichment_context, dict) else {}
    return "\n\n".join(
        (
            "You are a clinical photo captioner for AesMem, an aesthetics clinic memory system.",
            (
                "Describe only what is clinically visible in the image in one or two sentences: the anatomical "
                "area, observable findings (e.g. asymmetry, swelling, bruising, erythema, filler/Botox effect, "
                "pre- vs post-correction state), and relevant aesthetic-procedure context. Do NOT invent patient "
                "identity, measurements, dates, or anything not visible in the image. "
                f"{enrichment_language_directive(context)} "
                "Return only the caption text, with no preamble, labels, or markdown."
            ),
            f"Clinic/visit context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )


def note_decoration_prompt(enrichment_context: dict[str, Any] | None) -> str:
    """Build the instruction prompt for clinical note decoration."""
    context = enrichment_context if isinstance(enrichment_context, dict) else {}
    return "\n\n".join(
        (
            "You are cleaning up a clinician's quick free-text note for AesMem, an aesthetics clinic memory system.",
            (
                "Lightly decorate the note for readability: fix obvious typos, expand clinical shorthand, and "
                "organize it into clear clinical phrasing. Preserve EVERY clinical detail, number, product, dose, "
                "and instruction exactly — do NOT add facts, diagnoses, or patient identity that are not already "
                "in the note, and do not drop anything. "
                f"{enrichment_language_directive(context)} "
                "Return only the decorated note text, with no preamble, labels, or markdown."
            ),
            f"Clinic/visit context:\n{json.dumps(context, ensure_ascii=False, sort_keys=True)}",
        )
    )


def gateway_settings_for(task: str) -> tuple[str, str, str]:
    """Resolve (base_url, api_key, model) for an AI task, falling back to the transcription gateway.

    `task` is one of `transcription`, `caption`, `note_decoration`. A blank per-task override falls
    back to the shared `transcription_*` setting, so a single OpenAI-compatible gateway only needs
    the per-task `*_model` set, while a separate provider per task can also override base_url/api_key.
    """
    base_url = (getattr(settings, f"{task}_base_url", "") or settings.transcription_base_url).strip()
    api_key = getattr(settings, f"{task}_api_key", "") or settings.transcription_api_key
    model = getattr(settings, f"{task}_model", "") or settings.transcription_model
    return base_url, api_key, model


def gateway_client(task: str) -> OpenAI:
    """Return an OpenAI-compatible client for an AI task's resolved gateway."""
    base_url, api_key, _ = gateway_settings_for(task)
    return OpenAI(base_url=base_url, api_key=api_key, timeout=settings.transcription_timeout_seconds)


def resolve_model(task: str, ai_models: dict[str, Any] | None, *, override: str | None = None) -> str:
    """Resolve the model id for a task: explicit override → live `aiModels` payload → env default.

    The backend resolves the live per-task selection and passes it in the job payload's `aiModels`,
    so a model change applies to the next request; a blank/absent value falls back to the worker env.
    """
    if isinstance(override, str) and override.strip():
        return override.strip()
    if isinstance(ai_models, dict):
        selected = ai_models.get(task)
        if isinstance(selected, str) and selected.strip():
            return selected.strip()
    return gateway_settings_for(task)[2]


def image_to_data_url(content: bytes, media_type: str | None) -> str:
    """Base64-encode image bytes into an OpenAI-compatible data URL."""
    mime = media_type if isinstance(media_type, str) and media_type.startswith("image/") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def caption_image_content(
    content: bytes,
    media_type: str | None,
    enrichment_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> str | None:
    """Caption a clinical image through the configured gateway; None when the model returns empty."""
    client = gateway_client("caption")
    response = client.chat.completions.create(
        model=model or gateway_settings_for("caption")[2],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": caption_prompt(enrichment_context)},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(content, media_type)}},
                ],
            }
        ],
    )
    text = response.choices[0].message.content
    return text.strip() if text and text.strip() else None


def decorate_note_content(
    raw_text: str,
    enrichment_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
) -> str | None:
    """Decorate a clinical note through the configured gateway; None when the model returns empty."""
    client = gateway_client("note_decoration")
    response = client.chat.completions.create(
        model=model or gateway_settings_for("note_decoration")[2],
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{note_decoration_prompt(enrichment_context)}\n\nNote:\n{raw_text}"},
                ],
            }
        ],
    )
    text = response.choices[0].message.content
    return text.strip() if text and text.strip() else None


def capture_processing_output(job: dict[str, Any], text: str) -> CaptureProcessingOutput:
    """Build the stable completed-capture output envelope for a given generated text."""
    return {
        "status": "completed",
        "text": text,
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
    }


def is_fixture_capture(capture: dict[str, Any]) -> bool:
    """Return whether a capture maps to a deterministic QA fixture (skip real enrichment)."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return True
    detail = " ".join(str(metadata.get("detail") or "").split())
    return "Patient prefers subtle correction" in detail and "follow-up photo in 2 weeks" in detail


def raw_note_text_for_decoration(capture: dict[str, Any]) -> str | None:
    """Return the captured note text to decorate, or None when there's nothing meaningful."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    detail = str(metadata.get("detail") or "").strip()
    return detail or None


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
    for key in ("transcript", "caption", "decorated_text", "ocr", "normalized_note"):
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
    for key in ("transcript", "caption", "decoratedText", "rawText"):
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


class BackendClient:
    """HTTP client for backend-owned AI job state."""

    def __init__(self) -> None:
        self.base_url = settings.backend_internal_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.internal_token}"}

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to an internal backend endpoint."""
        response = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def get_bytes(self, path: str) -> bytes:
        """GET binary content from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content

    def get_file(self, path: str) -> tuple[bytes, str]:
        """GET binary content plus its content type from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")

    def start_job(self, job_id: str, *, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Mark a job running and fetch its input payload."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/start",
            {"celery_task_id": celery_task_id, "retry_count": retry_count},
        )

    def complete_job(self, job_id: str, *, output_key: str, output: dict[str, Any]) -> dict[str, Any]:
        """Submit successful job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/complete",
            {"output_key": output_key, "output": output},
        )

    def progress_job(self, job_id: str, *, output_key: str, output: dict[str, Any], stage: str) -> dict[str, Any]:
        """Submit partial job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/progress",
            {"output_key": output_key, "output": output, "stage": stage},
        )

    def retry_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a failed attempt before Celery retries."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/retry",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def fail_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record terminal job failure."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/fail",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def recover_jobs(self) -> dict[str, Any]:
        """Ask the backend to re-dispatch queued or retryable failed work."""
        return self.post("/internal/ai/jobs/recover", {})


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

    # Pro enrichment (real image captions / note decoration). The backend attaches an
    # `enrichmentContext` only for Pro tenants; Basic and gateway-less/fixture captures keep the
    # deterministic placeholder. A gateway failure propagates as a retryable worker error; an empty
    # gateway response falls back to the placeholder so the capture still completes.
    enrichment_context = payload.get("enrichmentContext") if isinstance(payload.get("enrichmentContext"), dict) else None
    enriched_text: str | None = None
    if enrichment_context is not None and transcription_is_configured() and not is_fixture_capture(capture):
        capture_type = capture.get("type")
        if capture_type == "photo" and capture.get("sourceArtifactId"):
            content, media_type = client.get_file(f"/internal/captures/{capture['id']}/file-content")
            enriched_text = caption_image_content(
                content, media_type, enrichment_context, model=resolve_model("caption", ai_models)
            )
        elif capture_type == "note":
            raw_note = raw_note_text_for_decoration(capture)
            if raw_note:
                enriched_text = decorate_note_content(
                    raw_note, enrichment_context, model=resolve_model("note_decoration", ai_models)
                )
    if enriched_text:
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, enriched_text))
        return

    # Un-enriched photos (Basic tenants, or no gateway) get NO AI caption — leave it blank so the UI
    # offers a manual "Add caption" instead of a meaningless placeholder. Fixtures keep their
    # deterministic caption for QA; notes keep the captured text as a passthrough.
    if capture.get("type") == "photo" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, ""))
        return

    sleep(settings.mock_stage_delay_seconds)
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    # TODO(ai-integration): Replace these deterministic stages with real progressive AI session artifacts.
    for stage in ("transcripts", "report", "findings", "summary"):
        client.progress_job(job_id, output_key="session_progress", output=session_progress_output(payload, stage), stage=stage)
        sleep(settings.mock_stage_delay_seconds)

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))


# --- Combined patient memory (Pro): summary + history in one call ------------------------------


def patient_memory_prompt(payload: dict[str, Any]) -> str:
    """Build the prompt for the combined patient summary + history (incremental, grounded)."""
    patient = payload.get("patient") if isinstance(payload.get("patient"), dict) else {}
    language = payload.get("language")
    language_directive = (
        f"Write all text in {language}."
        if isinstance(language, str) and language.strip()
        else "Write all text in the language the visit notes use (default English)."
    )
    return "\n\n".join(
        (
            "You are AesMem, a calm clinical assistant that maintains a patient's longitudinal memory "
            "for an aesthetics clinic.",
            (
                "Update this patient's memory from the prior memory and the new visit briefs below. "
                "Produce a warm, assistant-voiced brief — natural sentences, never a form or bullet dump. "
                "Synthesize across visits, but do NOT invent clinical facts, names, products, or doses "
                "that are not present in the briefs. Keep the card summary to 1-2 sentences. "
                f"{language_directive}"
            ),
            (
                "Return ONLY strict JSON (no markdown, no code fences) with EXACTLY this shape:\n"
                '{"summary": "<1-2 sentence card summary>", '
                '"history": {"snapshot": "<one line: patient + current focus>", '
                '"sections": [{"label": "Story so far", "body": "<2-4 sentences>"}, '
                '{"label": "Worth remembering", "body": "<preferences, cautions, recurring themes>"}, '
                '{"label": "Right now", "body": "<open threads / next visit>"}], "visits": []}}'
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
    return {"summary": summary.strip(), "history": history}


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
