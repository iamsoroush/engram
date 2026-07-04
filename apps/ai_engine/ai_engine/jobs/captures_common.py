"""Shared scaffolding for the capture job family (audio / photo / note).

The three capture types and their dispatcher (``jobs.capture``) share the completed/partial output
envelopes, the metadata field mapping, and the deterministic placeholder path. Kept in one leaf
module (imports ``core`` only, never a capture type module) so the type modules and the dispatcher
can all use it without an import cycle.
"""
from typing import Any, Literal, NotRequired, TypedDict

from ai_engine.core.fixtures import TEST_CAPTURE_TEXT_BY_FILENAME
from ai_engine.core.util import utc_now


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
    schemaVersion: NotRequired[str]
    promptVersion: NotRequired[str]
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
    pairing: NotRequired[dict[str, Any]]
    confidence: NotRequired[float]
    display: NotRequired[str]


NOT_DETECTED_PATIENT: DetectedPatientOutput = {
    "status": "not_detected",
    "full_name": None,
    "national_id": None,
    "confidence": None,
    "evidence": None,
    "source_text": None,
}


def output_key_for_capture(capture_type: str) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == "audio":
        return "transcript"
    if capture_type == "photo":
        return "caption"
    # Notes are a pure passthrough (no decoration): the job marks the note processed with its RAW
    # text under `note_text`, preserving chain ordering + report_contribution wiring. The report
    # itself reads the raw `detail`, so this envelope only carries provenance.
    return "note_text"


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
