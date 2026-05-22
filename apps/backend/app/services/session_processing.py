from datetime import date, datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Artifact, Capture, CaptureType, Patient, Session
from app.services.reporting import (
    REPORT_MODEL_VERSION,
    empty_report_model,
    get_report_template,
    patient_information_from_assignment,
    report_template_payload,
)

SESSION_PROCESSING_INPUT_VERSION = "2026-05-21.session-processing-input.v1"
SESSION_PROCESSING_OUTPUT_VERSION = "2026-05-21.session-processing-output.v1"


class SessionProcessingCaptureInput(TypedDict, total=False):
    """Capture-level input available to session processing."""

    captureId: str
    type: Literal["audio", "photo", "note"]
    status: str
    capturedAt: str | None
    artifactId: str | None
    artifactUrl: str | None
    s3Url: str | None
    transcript: str | None
    caption: str | None
    rawText: str | None
    decoratedText: str | None
    detectedPatient: dict[str, Any] | None


class SessionProcessingInput(TypedDict):
    """Stable input contract for future real session AI processing."""

    schemaVersion: str
    rawReportTemplate: dict[str, str]
    clinic: dict[str, Any]
    assignedPatient: dict[str, Any] | None
    patientSummarizedHistory: str | None
    captures: dict[str, list[SessionProcessingCaptureInput]]
    session: dict[str, Any]


class SessionReportBlockOutput(TypedDict, total=False):
    """Body-level AI report block output."""

    type: Literal["paragraph", "image", "artifact"]
    text: NotRequired[str]
    artifactId: NotRequired[str]
    captureId: NotRequired[str]
    caption: NotRequired[str]


class SessionReportSectionOutput(TypedDict):
    """Body-level AI report section output."""

    id: str
    title: str
    blocks: list[SessionReportBlockOutput]


class SessionProcessingOutput(TypedDict, total=False):
    """Stable output contract returned by session processing.

    This contract intentionally contains body-level report content only. Clinic
    and patient information are rendered from backend-owned template/session
    context, not from generated output.
    """

    schemaVersion: str
    summary: str | None
    sections: list[SessionReportSectionOutput]
    artifactReferences: list[dict[str, Any]]
    sourceReferences: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    generatedBy: str
    generatedAt: str | None


def build_session_processing_input(db: DbSession, session: Session) -> SessionProcessingInput:
    """Build the session-processing input context for the AI boundary."""
    template = get_report_template(session.report_template_key)
    captures = list(
        db.execute(
            select(Capture)
            .where(Capture.tenant_id == session.tenant_id, Capture.session_id == session.id)
            .order_by(Capture.created_at)
        ).scalars()
    )
    artifact_ids = [capture.source_artifact_id for capture in captures if capture.source_artifact_id]
    artifacts_by_id = {
        artifact.id: artifact
        for artifact in db.execute(
            select(Artifact).where(Artifact.tenant_id == session.tenant_id, Artifact.id.in_(artifact_ids))
        ).scalars()
    } if artifact_ids else {}

    capture_inputs = [_capture_input(capture, artifacts_by_id.get(capture.source_artifact_id)) for capture in captures]
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None

    return {
        "schemaVersion": SESSION_PROCESSING_INPUT_VERSION,
        "rawReportTemplate": report_template_payload(session.report_template_key),
        "clinic": {
            "name": template.clinic_name,
            "information": list(template.clinic_information),
        },
        "assignedPatient": assigned_patient,
        "patientSummarizedHistory": _patient_summarized_history(db, session),
        "captures": {
            "audio": [capture for capture in capture_inputs if capture["type"] == CaptureType.audio.value],
            "photos": [capture for capture in capture_inputs if capture["type"] == CaptureType.photo.value],
            "text": [capture for capture in capture_inputs if capture["type"] == CaptureType.note.value],
        },
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "metadata": session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {},
            "createdAt": _iso(session.created_at),
            "updatedAt": _iso(session.updated_at),
            "capturedAt": _iso(session.captured_at),
        },
    }


def deterministic_mock_session_processing_output(
    processing_input: SessionProcessingInput,
    *,
    generated_at: str | None = None,
) -> SessionProcessingOutput:
    """Return deterministic mock body output for local/backend-only processing."""
    now = generated_at or datetime.now(timezone.utc).isoformat()
    captures = _flatten_capture_groups(processing_input.get("captures", {}))
    source_capture_ids = [capture["captureId"] for capture in captures if capture.get("captureId")]
    paragraphs = _body_paragraphs_from_input(processing_input, captures)
    image_captures = [capture for capture in captures if capture.get("type") == CaptureType.photo.value]
    blocks: list[SessionReportBlockOutput] = [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs]
    for capture in image_captures:
        artifact_id = capture.get("artifactId")
        if artifact_id:
            blocks.append(
                {
                    "type": "image",
                    "artifactId": artifact_id,
                    "captureId": capture["captureId"],
                    "caption": capture.get("caption") or "Source image",
                }
            )

    return {
        "schemaVersion": SESSION_PROCESSING_OUTPUT_VERSION,
        "summary": _summary_from_paragraphs(paragraphs),
        "sections": [{"id": "clinical-report", "title": "Clinical report", "blocks": blocks}],
        "artifactReferences": [
            {
                "type": "artifact",
                "artifactId": capture.get("artifactId"),
                "captureId": capture.get("captureId"),
                "url": capture.get("artifactUrl"),
                "s3Url": capture.get("s3Url"),
            }
            for capture in captures
            if capture.get("artifactId")
        ],
        "sourceReferences": [{"type": "capture", "captureId": capture_id} for capture_id in source_capture_ids],
        "findings": _mock_findings(captures),
        "generatedBy": "mock-session-processing",
        "generatedAt": now,
    }


def report_model_from_session_processing_output(
    *,
    title: str | None,
    template_key: str | None,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Convert session-processing output into the internal structured report model."""
    sections = _valid_sections(output.get("sections"))
    if not sections:
        return empty_report_model(title=title, template_key=template_key)
    return {
        "schemaVersion": REPORT_MODEL_VERSION,
        "templateKey": get_report_template(template_key).key,
        "title": title or "Untitled session",
        "sections": sections,
        "findings": _valid_dict_list(output.get("findings")),
        "sourceReferences": _valid_references(output.get("sourceReferences")),
        "artifactReferences": _valid_references(output.get("artifactReferences")),
        "summary": output.get("summary") if isinstance(output.get("summary"), str) else None,
        "generatedAt": output.get("generatedAt") if isinstance(output.get("generatedAt"), str) else None,
        "generatedBy": output.get("generatedBy") if isinstance(output.get("generatedBy"), str) else None,
    }


def session_processing_output_from_legacy_report(output: dict[str, Any], *, generated_at: str) -> SessionProcessingOutput:
    """Wrap legacy markdown session output in the structured output contract."""
    report = output.get("report")
    body = report if isinstance(report, str) and report.strip() else "Mock clinical body generated from session captures."
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    extracted_metadata = output.get("extracted_metadata") if isinstance(output.get("extracted_metadata"), dict) else {}
    source_capture_ids = extracted_metadata.get("source_capture_ids") if isinstance(extracted_metadata.get("source_capture_ids"), list) else []
    return {
        "schemaVersion": SESSION_PROCESSING_OUTPUT_VERSION,
        "summary": output.get("summary") if isinstance(output.get("summary"), str) else _summary_from_paragraphs(paragraphs),
        "sections": [
            {
                "id": "clinical-report",
                "title": "Clinical report",
                "blocks": [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs],
            }
        ],
        "sourceReferences": [
            {"type": "capture", "captureId": capture_id}
            for capture_id in source_capture_ids
            if isinstance(capture_id, str)
        ],
        "artifactReferences": [],
        "findings": _valid_dict_list(extracted_metadata.get("findings")),
        "generatedBy": output.get("generated_by") if isinstance(output.get("generated_by"), str) else "mock-ai-engine",
        "generatedAt": output.get("generated_at") if isinstance(output.get("generated_at"), str) else generated_at,
    }


def _capture_input(capture: Capture, artifact: Artifact | None) -> SessionProcessingCaptureInput:
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    transcript = _generated_text(metadata.get("transcript"))
    detected_patient = _detected_patient(metadata.get("transcript"))
    caption = _generated_text(metadata.get("caption")) or _generated_text(metadata.get("ocr"))
    decorated_text = _generated_text(metadata.get("decorated_text")) or _generated_text(metadata.get("normalized_note"))
    raw_text = str(metadata.get("detail")).strip() if metadata.get("detail") else None
    return {
        "captureId": str(capture.id),
        "type": capture.capture_type.value,
        "status": capture.status.value,
        "capturedAt": _iso(capture.captured_at),
        "artifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
        "artifactUrl": f"/api/v1/captures/{capture.id}/file-content" if capture.source_artifact_id else None,
        "s3Url": _s3_url(artifact),
        "transcript": transcript if capture.capture_type == CaptureType.audio else None,
        "detectedPatient": detected_patient if capture.capture_type == CaptureType.audio else None,
        "caption": caption if capture.capture_type == CaptureType.photo else None,
        "rawText": raw_text if capture.capture_type == CaptureType.note else None,
        "decoratedText": decorated_text if capture.capture_type == CaptureType.note else None,
    }


def _patient_summarized_history(db: DbSession, session: Session) -> str | None:
    if session.patient_id is None:
        return None
    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        return None
    return patient.notes.strip() if isinstance(patient.notes, str) and patient.notes.strip() else None


def _generated_text(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"].strip()
    if isinstance(value, str):
        return value.strip()
    return None


def _detected_patient(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("detected_patient"), dict):
        return value["detected_patient"]
    return None


def _s3_url(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    return f"s3://{artifact.bucket}/{artifact.object_key}"


def _body_paragraphs_from_input(
    processing_input: SessionProcessingInput,
    captures: list[SessionProcessingCaptureInput],
) -> list[str]:
    paragraphs: list[str] = []
    if processing_input.get("patientSummarizedHistory"):
        paragraphs.append(f"Known patient history summary: {processing_input['patientSummarizedHistory']}")

    audio = [capture for capture in captures if capture.get("transcript")]
    photos = [capture for capture in captures if capture.get("caption")]
    notes = [capture for capture in captures if capture.get("decoratedText") or capture.get("rawText")]
    if audio:
        paragraphs.append("Audio notes: " + " ".join(str(capture["transcript"]) for capture in audio))
    if notes:
        paragraphs.append("Written notes: " + " ".join(str(capture.get("decoratedText") or capture.get("rawText")) for capture in notes))
    if photos:
        paragraphs.append("Photo observations: " + " ".join(str(capture["caption"]) for capture in photos))
    if not paragraphs:
        paragraphs.append("Mock clinical body generated from the available session context.")
    return paragraphs


def _summary_from_paragraphs(paragraphs: list[str]) -> str:
    return " ".join(paragraphs)[:240] if paragraphs else "Mock session summary generated from session context."


def _mock_findings(captures: list[SessionProcessingCaptureInput]) -> list[dict[str, Any]]:
    source_capture_ids = [capture["captureId"] for capture in captures if capture.get("captureId")]
    capture_types = sorted({str(capture.get("type")) for capture in captures if capture.get("type")})
    return [
        {
            "id": "source_capture_count",
            "label": "Source captures",
            "value": str(len(source_capture_ids)),
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
        {
            "id": "source_mix",
            "label": "Source mix",
            "value": ", ".join(capture_types) or "none",
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]


def _valid_sections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for section in value:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str):
            continue
        blocks = _valid_blocks(section.get("blocks"))
        sections.append(
            {
                "id": section["id"],
                "title": section.get("title") if isinstance(section.get("title"), str) else "Clinical report",
                "blocks": blocks,
            }
        )
    return sections


def _valid_blocks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    blocks: list[dict[str, Any]] = []
    for block in value:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            continue
        block_type = block["type"]
        if block_type == "paragraph" and isinstance(block.get("text"), str):
            blocks.append({"type": "paragraph", "text": block["text"]})
        elif block_type in {"image", "artifact"} and isinstance(block.get("artifactId"), str):
            blocks.append(
                {
                    key: block[key]
                    for key in ("type", "artifactId", "captureId", "caption")
                    if isinstance(block.get(key), str)
                }
            )
    return blocks


def _valid_references(value: Any) -> list[dict[str, Any]]:
    return _valid_dict_list(value)


def _valid_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flatten_capture_groups(captures: dict[str, Any]) -> list[SessionProcessingCaptureInput]:
    flattened: list[SessionProcessingCaptureInput] = []
    for group in ("audio", "photos", "text"):
        values = captures.get(group)
        if isinstance(values, list):
            flattened.extend(capture for capture in values if isinstance(capture, dict))
    return flattened


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None
