"""Audio capture job: transcription + patient-information extraction + intent classification.

Transcribes through the configured OpenAI-compatible gateway into strict structured JSON (transcript
+ patient_information + intents), normalizing spoken digits to Latin so quantification stays
comparable across captures. Fixture audio maps to deterministic text; a gateway-less non-fixture
capture raises so the backend can retry. Vertical-agnostic via the domain descriptor.
"""
from typing import Any

from ai_engine.core.errors import GatewayUnavailable, InvalidOutput, SourceMissing
from ai_engine.core.fixtures import TEST_CAPTURE_TEXT_BY_FILENAME
from ai_engine.core.gateway import (
    gateway_client,
    resolve_model,
    set_pending_audio_seconds,
    transcription_is_configured,
)
from ai_engine.core.media import audio_duration_seconds, audio_to_flac_mono_16khz_base64
from ai_engine.core.structured import (
    call_with_validation_retry,
    correction_message,
    response_format,
    structured_outputs_enabled,
)
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
    transcription_json_schema,
)
# The prompt lives in its own versioned module (§3.3); ``transcription_prompt`` is re-exported here so
# the shim + tests keep the old name, and the envelope stamps ``TRANSCRIPTION_PROMPT_VERSION``.
from ai_engine.prompts.transcription import PROMPT_VERSION as TRANSCRIPTION_PROMPT_VERSION
from ai_engine.prompts.transcription import build as transcription_prompt  # noqa: F401
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


def _parse_transcription(raw_text: str) -> dict[str, Any]:
    """Parse the gateway transcription output, treating an empty reply as an invalid output."""
    if not raw_text or not raw_text.strip():
        raise InvalidOutput("Audio transcription returned empty text")
    return parse_structured_transcription_output(raw_text)


def transcribe_audio_content(
    content: bytes,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    ai_models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transcribe audio through the configured OpenAI-compatible gateway (§3.2 structured output)."""
    base64_flac = audio_to_flac_mono_16khz_base64(content)
    # Duration drives per-minute transcription cost in the backend meter (set before the call so the
    # metered client attaches it to this transcription's usage record).
    set_pending_audio_seconds(audio_duration_seconds(content))
    resolved_model = resolve_model("transcription", ai_models, override=model)
    client = gateway_client("transcription")

    def invoke(call_model: str, _effort: str | None, correction: str | None) -> str:
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": transcription_prompt(transcription_context)},
                    {"type": "input_audio", "input_audio": {"data": base64_flac, "format": "audio/flac"}},
                ],
            }
        ]
        request: dict[str, Any] = {"model": call_model, "messages": messages}
        if structured_outputs_enabled():
            request["response_format"] = response_format("capture_intelligence_output", transcription_json_schema())
        if correction is not None:
            messages.append(correction_message(correction))
        response = client.chat.completions.create(**request)
        return response.choices[0].message.content or ""

    return call_with_validation_retry(
        task="transcription", ai_models=ai_models, model=resolved_model, effort=None,
        invoke=invoke, parse=_parse_transcription,
    )


def completed_audio_metadata(
    job: dict[str, Any],
    capture: dict[str, Any],
    content: bytes | None,
    transcription_context: dict[str, Any] | None = None,
    *,
    model: str | None = None,
    ai_models: dict[str, Any] | None = None,
) -> CaptureProcessingOutput:
    """Return completed audio metadata using real transcription."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        structured = structured_transcription_from_text(TEST_CAPTURE_TEXT_BY_FILENAME[filename])
    elif transcription_is_configured():
        if content is None:
            raise SourceMissing("Audio capture source file is missing")
        structured = transcribe_audio_content(content, transcription_context, model=model, ai_models=ai_models)
    else:
        raise GatewayUnavailable("Audio transcription gateway is not configured")
    text = structured["transcript"]
    patient_information = structured["patient_information"]

    return {
        "status": "completed",
        "schemaVersion": CAPTURE_INTELLIGENCE_OUTPUT_VERSION,
        "promptVersion": TRANSCRIPTION_PROMPT_VERSION,
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
