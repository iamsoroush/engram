"""Builders for the transcription and capture-enrichment context sent to the worker."""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, CaptureType, Patient, Session
from app.services.caseload import tenant_vertical
from app.services.reporting import get_report_template, patient_information_from_assignment
from app.services.verticals import domain_descriptor

from app.services.ai_jobs.config import tenant_transcription_language

__all__ = [
    "generated_capture_text",
    "patient_summarized_history_for_transcription",
    "transcription_context_from_inputs",
    "build_transcription_context",
    "capture_enrichment_context_from_inputs",
    "build_capture_enrichment_context",
]


def generated_capture_text(value: Any) -> str | None:
    """Return generated/display text from a capture metadata field."""
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        text = value["text"].strip()
        return text or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def patient_summarized_history_for_transcription(db: DbSession, session: Session) -> str | None:
    """Return a safe assigned-patient history summary for transcription context."""
    if session.patient_id is None:
        return None
    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
    ).scalar_one_or_none()
    if patient is None or not isinstance(patient.notes, str):
        return None
    history = patient.notes.strip()
    return history or None


def transcription_context_from_inputs(
    *,
    session: Session,
    clinic: dict[str, Any],
    assigned_patient: dict[str, Any] | None,
    patient_history_summary: str | None,
    captures: list[Capture],
    current_capture_id: uuid.UUID,
    preferred_language: str = "auto",
    domain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable tenant-scoped context sent to audio transcription."""
    previous_transcripts: list[dict[str, Any]] = []
    text_notes: list[dict[str, Any]] = []
    for capture in captures:
        if capture.id == current_capture_id or capture.status == CaptureStatus.deleted:
            continue
        metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
        if capture.capture_type == CaptureType.audio:
            transcript = generated_capture_text(metadata.get("transcript"))
            if transcript:
                previous_transcripts.append(
                    {
                        "captureId": str(capture.id),
                        "capturedAt": capture.captured_at.isoformat() if capture.captured_at else None,
                        "text": transcript,
                    }
                )
        elif capture.capture_type == CaptureType.note:
            note_text = (
                generated_capture_text(metadata.get("decorated_text"))
                or generated_capture_text(metadata.get("normalized_note"))
                or generated_capture_text(metadata.get("detail"))
            )
            if note_text:
                text_notes.append(
                    {
                        "captureId": str(capture.id),
                        "capturedAt": capture.captured_at.isoformat() if capture.captured_at else None,
                        "text": note_text,
                    }
                )

    return {
        "schemaVersion": "2026-06-02.audio-transcription-context.v1",
        "clinic": clinic,
        # Vertical-aware prompt framing (label + optional vocabulary). The worker reads this and
        # falls back to a neutral "clinic" when absent — it never hardcodes a vertical.
        "domain": domain,
        "preferredLanguage": preferred_language,
        "assignedPatient": assigned_patient,
        "patientSummarizedHistory": patient_history_summary,
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "createdAt": session.created_at.isoformat() if session.created_at else None,
            "updatedAt": session.updated_at.isoformat() if session.updated_at else None,
            "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
        },
        "previousTranscripts": previous_transcripts[-5:],
        "textNotes": text_notes[-10:],
    }


def build_transcription_context(db: DbSession, *, session: Session, capture: Capture) -> dict[str, Any]:
    """Build the audio transcription context for the AI engine worker."""
    template = get_report_template(session.report_template_key)
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None
    captures = list(
        db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.created_at)
        ).scalars()
    )
    domain = domain_descriptor(tenant_vertical(db, session.tenant_id))
    return transcription_context_from_inputs(
        session=session,
        clinic={
            "name": template.clinic_name,
            "information": list(template.clinic_information),
            "assumptions": [
                f"{domain['label'].capitalize()} context.",
                "Persian/Iranian patient names, identifiers, phone numbers, and mixed Persian-English visit language are common.",
            ],
        },
        assigned_patient=assigned_patient,
        patient_history_summary=patient_summarized_history_for_transcription(db, session),
        captures=captures,
        current_capture_id=capture.id,
        preferred_language=tenant_transcription_language(db, session.tenant_id),
        domain=domain,
    )


def capture_enrichment_context_from_inputs(
    *,
    clinic: dict[str, Any],
    assigned_patient: dict[str, Any] | None,
    preferred_language: str,
    capture_type: str,
    domain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Pro-only context for photo captioning / note decoration."""
    return {
        "schemaVersion": "2026-06-06.capture-enrichment-context.v1",
        "clinic": clinic,
        # Vertical-aware prompt framing; the worker falls back to a neutral "clinic" when absent.
        "domain": domain,
        "assignedPatient": assigned_patient,
        "preferredLanguage": preferred_language,
        "captureType": capture_type,
    }


def build_capture_enrichment_context(db: DbSession, *, session: Session, capture: Capture) -> dict[str, Any]:
    """Build the Pro-only enrichment context for the worker.

    Mirrors the audio transcription context but lighter: it carries clinic and assigned-patient
    context plus the preferred language so a real captioner/decorator can stay on-script. Attaching
    this context is the tier gate — the backend only builds it for Pro tenants (see
    `worker_job_payload`), so a Basic tenant's worker never enriches and never calls the gateway.
    """
    template = get_report_template(session.report_template_key)
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None
    domain = domain_descriptor(tenant_vertical(db, session.tenant_id))
    return capture_enrichment_context_from_inputs(
        clinic={
            "name": template.clinic_name,
            "information": list(template.clinic_information),
            "assumptions": [f"{domain['label'].capitalize()} context."],
        },
        assigned_patient=assigned_patient,
        preferred_language=tenant_transcription_language(db, session.tenant_id),
        capture_type=capture.capture_type.value,
        domain=domain,
    )
