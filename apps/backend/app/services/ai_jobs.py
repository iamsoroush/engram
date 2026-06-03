import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import Capture, CaptureStatus, CaptureType, AiJob, AiJobStatus, AiJobType, OrganizationSource, Patient, Session, SessionStatus
from app.services.capture_storage import get_capture_for_tenant
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    patient_assignment_event,
)
from app.services.patient_matching import match_patient_from_metadata, match_patient_from_patient_information
from app.services.patients import create_patient_from_patient_information, patient_information_has_explicit_identity
from app.services.reporting import (
    DEFAULT_REPORT_TEMPLATE_KEY,
    get_report_template,
    patient_information_from_assignment,
    render_report_body_markdown,
    report_template_payload,
    structured_report_from_markdown_body,
)
from app.services.session_processing import (
    build_session_processing_input,
    report_model_from_session_processing_output,
    session_processing_output_from_legacy_report,
)
from app.services.sessions import parse_uuid

logger = logging.getLogger(__name__)

TASK_NAME_BY_JOB_TYPE = {
    AiJobType.audio_capture_process: "ai_engine.process_audio_capture",
    AiJobType.text_capture_process: "ai_engine.process_text_capture",
    AiJobType.image_capture_process: "ai_engine.process_image_capture",
    AiJobType.session_organize: "ai_engine.process_session",
}

def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def ai_job_payload(job: AiJob) -> dict[str, Any]:
    """Serialize a processing job for API responses."""
    return {
        "id": str(job.id),
        "tenantId": str(job.tenant_id),
        "sessionId": str(job.session_id) if job.session_id else None,
        "captureId": str(job.capture_id) if job.capture_id else None,
        "jobType": job.job_type.value,
        "status": job.status.value,
        "generatedBy": job.generated_by,
        "inputArtifactIds": job.input_artifact_ids,
        "resultMetadata": job.result_metadata,
        "errorMessage": job.error_message,
        "attemptCount": job.attempt_count,
        "lastAttemptedAt": job.last_attempted_at.isoformat() if job.last_attempted_at else None,
        "lastDispatchedAt": job.last_dispatched_at.isoformat() if job.last_dispatched_at else None,
        "nextRetryAt": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "lastError": job.last_error,
        "retryReason": job.retry_reason,
        "createdByUserId": str(job.created_by_user_id) if job.created_by_user_id else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


def ai_patient_action_metadata(
    *,
    action: str,
    patient: Patient,
    capture: Capture,
    patient_information: dict[str, Any],
    match_candidate: dict[str, Any] | None,
    created: bool,
) -> dict[str, Any]:
    """Return durable provenance for AI patient creation and assignment."""
    return {
        "schemaVersion": "2026-06-02.ai-patient-action.v1",
        "action": action,
        "source": "ai-engine",
        "basisCaptureId": str(capture.id),
        "patientId": str(patient.id),
        "displayName": patient.display_name,
        "created": created,
        "assigned": True,
        "needsVerification": created,
        "status": "needs_verification" if created else "assigned",
        "reason": (
            "AI created and assigned this patient from extracted audio identity."
            if created
            else "AI matched and assigned this visit to an existing patient."
        ),
        "patientInformation": patient_information,
        "matchCandidate": match_candidate,
    }


def assign_session_to_ai_patient(
    db: DbSession,
    *,
    session: Session,
    capture: Capture,
    patient: Patient,
    action: dict[str, Any],
) -> None:
    """Assign a session/capture set to an AI-selected patient with provenance."""
    assignment_source = "ai_created" if action.get("created") else "ai_matched"
    assignment_reason = action.get("reason")
    session_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    event = patient_assignment_event(
        source="ai-engine",
        action=action.get("action") if isinstance(action.get("action"), str) else assignment_source,
        patient_id=patient.id,
        display_name=patient.display_name,
        reason=assignment_reason if isinstance(assignment_reason, str) else None,
        capture_id=capture.id,
        created=bool(action.get("created")),
        action_metadata=action,
        effective_at=(capture.captured_at or capture.created_at).isoformat() if (capture.captured_at or capture.created_at) else None,
    )
    session.extracted_metadata = append_patient_assignment_event(
        {
            **session_metadata,
            "patient_match_candidate": action.get("matchCandidate"),
        },
        event,
    )
    apply_active_patient_assignment(db, session)


def resolve_ai_patient_from_match(
    db: DbSession,
    *,
    job: AiJob,
    capture: Capture,
    patient_information: dict[str, Any],
    patient_match_candidate: dict[str, Any] | None,
) -> tuple[Patient | None, bool]:
    """Return the patient selected or created by deterministic AI identity."""
    if patient_match_candidate and patient_match_candidate.get("decision") == "matched" and patient_match_candidate.get("patientId"):
        try:
            matched_patient_id = uuid.UUID(str(patient_match_candidate["patientId"]))
        except ValueError:
            return None, False
        patient = db.execute(
            select(Patient).where(Patient.id == matched_patient_id, Patient.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        return patient, False
    if patient_match_candidate and patient_match_candidate.get("decision") == "no_match":
        patient = create_patient_from_patient_information(
            db,
            tenant_id=job.tenant_id,
            created_by_user_id=job.created_by_user_id,
            patient_information=patient_information,
            source_capture_id=capture.id,
        )
        return patient, patient is not None
    return None, False


def get_ai_job(db: DbSession, principal: CurrentPrincipal, job_id: str) -> dict[str, Any]:
    """Fetch a tenant-scoped AI processing job."""
    job = db.execute(
        select(AiJob).where(
            AiJob.id == parse_uuid(job_id, "job_id"),
            AiJob.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI processing job not found")
    return ai_job_payload(job)


def ai_job_retryable(job: AiJob) -> bool:
    """Return whether a failed AI job is eligible for automatic recovery."""
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    return metadata.get("retryable", True) is not False


def classify_retry_reason(error_message: str) -> str:
    """Classify operational retry reasons from worker error text."""
    normalized = error_message.lower()
    if "source file is missing" in normalized or "source_artifact" in normalized or "404" in normalized:
        return "source_missing"
    if "conversion to flac failed" in normalized or "ffmpeg" in normalized:
        return "conversion_failed"
    if (
        "gateway" in normalized
        or "transcription" in normalized
        or "openai" in normalized
        or "timeout" in normalized
        or "connection" in normalized
        or "rate limit" in normalized
        or "temporarily unavailable" in normalized
    ):
        return "gateway_unavailable"
    return "worker_error"


def retry_delay_seconds(attempt_count: int) -> int:
    """Return bounded exponential retry delay for a durable backend attempt count."""
    base_delay = max(settings.ai_job_retry_delay_seconds, 1)
    max_delay = max(settings.ai_job_retry_max_delay_seconds, base_delay)
    exponent = max(attempt_count - 1, 0)
    return min(base_delay * (2**exponent), max_delay)


def schedule_retry(job: AiJob, *, now: datetime, error_message: str, retry_reason: str | None = None) -> None:
    """Store durable retry state for the next backend-owned dispatch."""
    reason = retry_reason or classify_retry_reason(error_message)
    delay_seconds = retry_delay_seconds(job.attempt_count or 1)
    job.status = AiJobStatus.failed
    job.error_message = error_message
    job.last_error = error_message
    job.retry_reason = reason
    job.completed_at = now
    job.next_retry_at = now + timedelta(seconds=delay_seconds)
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_error": error_message,
        "retry_reason": reason,
        "retrying": True,
        "retryable": True,
        "next_retry_at": job.next_retry_at.isoformat(),
        "retry_delay_seconds": delay_seconds,
    }


def mark_job_non_retryable(job: AiJob, *, now: datetime, reason: str, error_message: str) -> None:
    """Mark a job as terminal because backend-owned target state says it should not retry."""
    job.status = AiJobStatus.failed
    job.error_message = error_message
    job.last_error = error_message
    job.retry_reason = reason
    job.completed_at = now
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_error": error_message,
        "retry_reason": reason,
        "retryable": False,
        "terminal_at": now.isoformat(),
    }


def datetime_or_none(value: datetime | None) -> datetime | None:
    """Normalize datetimes read from different DB/test backends to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def ai_job_due_for_recovery(job: AiJob, *, now: datetime) -> bool:
    """Return whether a durable job row should be re-dispatched now."""
    if job.status == AiJobStatus.succeeded or not ai_job_retryable(job):
        return False
    next_retry_at = datetime_or_none(job.next_retry_at)
    if next_retry_at is not None and next_retry_at > now:
        return False
    if job.status == AiJobStatus.failed:
        return True
    if job.status == AiJobStatus.queued:
        last_dispatched_at = datetime_or_none(job.last_dispatched_at)
        if last_dispatched_at is None:
            return True
        return last_dispatched_at <= now - timedelta(seconds=settings.ai_job_dispatch_visibility_timeout_seconds)
    if job.status == AiJobStatus.running:
        last_activity_at = datetime_or_none(job.last_attempted_at or job.started_at or job.created_at)
        if last_activity_at is None:
            return True
        return last_activity_at <= now - timedelta(seconds=settings.ai_job_running_stale_seconds)
    return False


def stop_recovery_if_target_is_gone(db: DbSession, job: AiJob, *, now: datetime) -> str | None:
    """Return a skip reason after terminally marking deleted/missing job targets."""
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None or capture.status == CaptureStatus.deleted:
            mark_job_non_retryable(
                job,
                now=now,
                reason="capture_deleted",
                error_message="AI job target capture is deleted",
            )
            return "capture_deleted"
        capture.status = CaptureStatus.processing
        return None
    if job.session_id:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is None:
            mark_job_non_retryable(
                job,
                now=now,
                reason="session_deleted",
                error_message="AI job target session is deleted",
            )
            return "session_deleted"
        session.status = SessionStatus.processing
    return None


def recover_ai_jobs(db: DbSession, principal: CurrentPrincipal, limit: int = 50) -> dict[str, Any]:
    """Re-dispatch queued or retryable failed AI jobs for the current tenant."""
    now = utc_now()
    jobs = list(
        db.execute(
            select(AiJob)
            .where(
                AiJob.tenant_id == principal.tenant_id,
                AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.failed]),
            )
            .order_by(AiJob.created_at)
            .limit(min(limit, 100))
        ).scalars()
    )
    recovered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for job in jobs:
        if not ai_job_retryable(job):
            skipped.append({"id": str(job.id), "reason": "terminal"})
            continue
        if not ai_job_due_for_recovery(job, now=now):
            skipped.append({"id": str(job.id), "reason": "not_due"})
            continue
        target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
        if target_skip_reason is not None:
            skipped.append({"id": str(job.id), "reason": target_skip_reason})
            continue
        job.status = AiJobStatus.queued
        job.completed_at = None
        job.next_retry_at = None
        job.result_metadata = {
            **(job.result_metadata or {}),
            "retryable": True,
            "recovered_at": now.isoformat(),
            "recovery_requested_by_user_id": str(principal.user_id),
        }
        recovered.append(ai_job_payload(job))
    db.commit()

    for recovered_job in recovered:
        job = db.get(AiJob, parse_uuid(recovered_job["id"], "job_id"))
        if job is None:
            continue
        if job.capture_id:
            dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)

    return {"recovered": recovered, "skipped": skipped}


def recover_all_ai_jobs(db: DbSession, limit: int = 100) -> dict[str, Any]:
    """Re-dispatch queued or retryable failed AI jobs across tenants for worker startup recovery."""
    now = utc_now()
    jobs = list(
        db.execute(
            select(AiJob)
            .where(AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.failed]))
            .order_by(AiJob.created_at)
            .limit(min(limit, 200))
        ).scalars()
    )
    recovered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for job in jobs:
        if not ai_job_retryable(job):
            skipped.append({"id": str(job.id), "reason": "terminal"})
            continue
        if not ai_job_due_for_recovery(job, now=now):
            skipped.append({"id": str(job.id), "reason": "not_due"})
            continue
        target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
        if target_skip_reason is not None:
            skipped.append({"id": str(job.id), "reason": target_skip_reason})
            continue
        job.status = AiJobStatus.queued
        job.completed_at = None
        job.next_retry_at = None
        job.result_metadata = {
            **(job.result_metadata or {}),
            "retryable": True,
            "recovered_at": now.isoformat(),
            "recovery_source": "ai-engine-startup",
        }
        recovered.append(ai_job_payload(job))
    db.commit()

    for recovered_job in recovered:
        job = db.get(AiJob, parse_uuid(recovered_job["id"], "job_id"))
        if job is None:
            continue
        if job.capture_id:
            dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)

    return {"recovered": recovered, "skipped": skipped}


def job_type_for_capture(capture_type: CaptureType) -> AiJobType:
    """Map capture media type to the concrete AI processing job type."""
    if capture_type == CaptureType.audio:
        return AiJobType.audio_capture_process
    if capture_type == CaptureType.photo:
        return AiJobType.image_capture_process
    return AiJobType.text_capture_process


def output_key_for_capture(capture_type: CaptureType) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == CaptureType.audio:
        return "transcript"
    if capture_type == CaptureType.photo:
        return "caption"
    return "decorated_text"


def queued_metadata(job: AiJob, capture: Capture) -> dict[str, Any]:
    """Return metadata stored while a capture is waiting for a worker."""
    return {
        "status": "queued",
        "generated_by": "ai-engine",
        "job_id": str(job.id),
        "job_type": job.job_type.value,
        "output_key": output_key_for_capture(capture.capture_type),
        "queued_at": utc_now().isoformat(),
    }


def create_capture_processing_job(db: DbSession, *, principal: CurrentPrincipal, capture: Capture) -> AiJob:
    """Create a queued capture processing job and mark the capture processing."""
    source_ids = [str(capture.source_artifact_id)] if capture.source_artifact_id else []
    job = AiJob(
        tenant_id=principal.tenant_id,
        session_id=capture.session_id,
        capture_id=capture.id,
        job_type=job_type_for_capture(capture.capture_type),
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        input_artifact_ids=source_ids,
        result_metadata={"queue": "ai_jobs"},
        created_by_user_id=principal.user_id,
    )
    db.add(job)
    db.flush()
    capture.status = CaptureStatus.processing
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        "ai_processing": queued_metadata(job, capture),
    }
    return job


def load_report_template(template_key: str | None) -> dict[str, str]:
    """Load the centralized report template by stable key."""
    try:
        return report_template_payload(template_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report template") from exc


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
    return transcription_context_from_inputs(
        session=session,
        clinic={
            "name": template.clinic_name,
            "information": list(template.clinic_information),
            "assumptions": [
                "Aesthetics clinic context.",
                "Persian/Iranian patient names, identifiers, phone numbers, and mixed Persian-English visit language are common.",
            ],
        },
        assigned_patient=assigned_patient,
        patient_history_summary=patient_summarized_history_for_transcription(db, session),
        captures=captures,
        current_capture_id=capture.id,
    )


def create_session_processing_job(db: DbSession, *, principal: CurrentPrincipal, session: Session) -> AiJob:
    """Create a queued session processing job and mark the session processing."""
    source_ids = [
        str(source_id)
        for source_id in db.execute(
            select(Capture.source_artifact_id).where(
                Capture.tenant_id == principal.tenant_id,
                Capture.session_id == session.id,
                Capture.source_artifact_id.is_not(None),
            )
        ).scalars()
    ]
    job = AiJob(
        tenant_id=principal.tenant_id,
        session_id=session.id,
        capture_id=None,
        job_type=AiJobType.session_organize,
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        input_artifact_ids=source_ids,
        result_metadata={"queue": "ai_jobs", "report_template_key": session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY},
        created_by_user_id=principal.user_id,
    )
    db.add(job)
    db.flush()
    session.status = SessionStatus.processing
    session.summary = session.summary or "Session processing has started."
    return job


def dispatch_capture_processing_job(db: DbSession, job: AiJob) -> None:
    """Send a committed capture processing job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported capture processing job type: {job.job_type.value}")

    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued capture processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
        db.commit()
    except Exception as exc:
        logger.exception("Failed to queue capture processing job", extra={"job_id": str(job.id)})
        schedule_retry(job, now=utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.capture_id:
            capture = db.execute(
                select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if capture is not None and capture.status != CaptureStatus.deleted:
                capture.status = CaptureStatus.processing
        audit(
            db,
            tenant_id=job.tenant_id,
            actor_user_id=job.created_by_user_id,
            action="ai_processing.fail",
            target_type="capture",
            target_id=job.capture_id,
            details={"job_id": str(job.id), "error": str(exc), "phase": "dispatch"},
        )
        db.commit()


def dispatch_session_processing_job(db: DbSession, job: AiJob) -> None:
    """Send a committed session processing job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported session processing job type: {job.job_type.value}")

    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued session processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
        db.commit()
    except Exception as exc:
        logger.exception("Failed to queue session processing job", extra={"job_id": str(job.id)})
        schedule_retry(job, now=utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.session_id:
            session = db.execute(
                select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if session is not None:
                session.status = SessionStatus.processing
        audit(
            db,
            tenant_id=job.tenant_id,
            actor_user_id=job.created_by_user_id,
            action="ai_processing.fail",
            target_type="session",
            target_id=job.session_id,
            details={"job_id": str(job.id), "error": str(exc), "phase": "dispatch"},
        )
        db.commit()


def enqueue_capture_processing_job(db: DbSession, *, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    """Create and dispatch a capture processing job from an API route."""
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    job = create_capture_processing_job(db, principal=principal, capture=capture)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="ai_processing.enqueue",
        target_type="capture",
        target_id=capture.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    dispatch_capture_processing_job(db, job)
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def require_ai_engine_token(authorization: str = Header(default="")) -> None:
    """Authorize internal AI engine callbacks with a shared service token."""
    expected = f"Bearer {settings.ai_engine_internal_token}"
    if not settings.ai_engine_internal_token or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid AI engine token")


def get_job_for_worker(db: DbSession, job_id: str) -> AiJob:
    """Fetch a worker-visible job row by ID."""
    try:
        parsed = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id") from exc
    job = db.execute(select(AiJob).where(AiJob.id == parsed)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return job


def worker_job_payload(db: DbSession, job: AiJob) -> dict[str, Any]:
    """Serialize job input needed by the AI engine worker."""
    capture = None
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
    if capture is not None:
        transcription_context = None
        if capture.capture_type == CaptureType.audio:
            session = db.execute(
                select(Session).where(Session.id == capture.session_id, Session.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if session is not None:
                transcription_context = build_transcription_context(db, session=session, capture=capture)
        return {
            "job": ai_job_payload(job),
            "capture": {
                "id": str(capture.id),
                "tenantId": str(capture.tenant_id),
                "sessionId": str(capture.session_id),
                "type": capture.capture_type.value,
                "status": capture.status.value,
                "metadata": capture.capture_metadata,
                "sourceArtifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
            },
            "transcriptionContext": transcription_context,
        }
    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
    captures = db.execute(
        select(Capture)
        .where(
            Capture.tenant_id == job.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
        .order_by(Capture.created_at)
    ).scalars()
    # TODO(ai-integration): Real session processors should consume this stable
    # context and return the structured body-level output contract.
    processing_context = build_session_processing_input(db, session)
    return {
        "job": ai_job_payload(job),
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "patientId": str(session.patient_id) if session.patient_id else None,
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "reportTemplateKey": session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY,
            "createdAt": session.created_at.isoformat() if session.created_at else None,
            "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
        },
        "captures": [
            {
                "id": str(capture.id),
                "type": capture.capture_type.value,
                "status": capture.status.value,
                "metadata": capture.capture_metadata,
                "sourceArtifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
            }
            for capture in captures
        ],
        "reportTemplate": load_report_template(session.report_template_key),
        "sessionProcessingContext": processing_context,
    }


def start_worker_job(
    db: DbSession,
    *,
    job_id: str,
    celery_task_id: str | None,
    retry_count: int,
) -> dict[str, Any]:
    """Mark an AI job running and return its input payload."""
    job = get_job_for_worker(db, job_id)
    if job.status == AiJobStatus.succeeded:
        return worker_job_payload(db, job)

    now = utc_now()
    target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
    if target_skip_reason is not None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target is no longer available")

    job.status = AiJobStatus.running
    job.started_at = job.started_at or now
    job.last_attempted_at = now
    job.attempt_count = (job.attempt_count or 0) + 1
    job.next_retry_at = None
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
        "attempt": job.attempt_count,
        "started_at": now.isoformat(),
    }
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
        capture.status = CaptureStatus.processing
    if job.session_id and job.capture_id is None:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
        session.status = SessionStatus.processing
    db.commit()
    db.refresh(job)
    return worker_job_payload(db, job)


def complete_worker_job(
    db: DbSession,
    *,
    job_id: str,
    output_key: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Persist successful AI engine output."""
    job = get_job_for_worker(db, job_id)
    if job.capture_id is None:
        return complete_session_worker_job(db, job=job, output_key=output_key, output=output)
    capture = db.execute(
        select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")

    completed_at = utc_now()
    session = db.execute(
        select(Session).where(Session.id == capture.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    patient_match_candidate = None
    ai_patient_action = None
    patient_information = output.get("patient_information")
    if isinstance(patient_information, dict) and patient_information_has_explicit_identity(patient_information):
        may_assign_from_identity = (
            session is not None
            and (
                session.patient_id is None
                or (capture.capture_type == CaptureType.audio and session.status != SessionStatus.verified)
            )
        )
        if may_assign_from_identity:
            patient_match_candidate = match_patient_from_patient_information(
                db,
                tenant_id=job.tenant_id,
                patient_information=patient_information,
            )
            assigned_patient, created_patient = resolve_ai_patient_from_match(
                db,
                job=job,
                capture=capture,
                patient_information=patient_information,
                patient_match_candidate=patient_match_candidate,
            )
            if assigned_patient is not None:
                ai_patient_action = ai_patient_action_metadata(
                    action="created_and_assigned" if created_patient else "matched_and_assigned",
                    patient=assigned_patient,
                    capture=capture,
                    patient_information=patient_information,
                    match_candidate=patient_match_candidate,
                    created=created_patient,
                )
                assign_session_to_ai_patient(
                    db,
                    session=session,
                    capture=capture,
                    patient=assigned_patient,
                    action=ai_patient_action,
                )
        elif session is not None:
            patient_match_candidate = {
                "schemaVersion": "2026-06-02.patient-match-candidate.v1",
                "decision": "skipped_assigned_patient",
                "status": "skipped_assigned_patient",
                "patientId": str(session.patient_id) if session.patient_id else None,
                "confidence": 0.0,
                "matchedOn": [],
                "reason": "Session already has a DB-owned patient assignment; generated identity did not override it.",
                "risks": [],
                "candidateSet": [],
                "llmRanking": {"eligible": False, "status": "not_applicable", "candidateCount": 0, "maxCandidates": 5},
                "source": "deterministic-patient-matching",
                "patientInformation": patient_information,
            }
    output_with_match = (
        {**output, "patient_match_candidate": patient_match_candidate, "ai_patient_action": ai_patient_action}
        if patient_match_candidate is not None
        else output
    )
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        output_key: output_with_match,
        "ai_processing": output_with_match,
    }
    if patient_match_candidate is not None:
        capture.capture_metadata = {**capture.capture_metadata, "patient_match_candidate": patient_match_candidate}
        if ai_patient_action is not None:
            capture.capture_metadata = {**capture.capture_metadata, "ai_patient_action": ai_patient_action}
        if session is not None and session.patient_id is None:
            session_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
            session.extracted_metadata = {**session_metadata, "patient_match_candidate": patient_match_candidate}
    capture.status = CaptureStatus.processed
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.last_error = None
    job.retry_reason = None
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "capture_status": capture.status.value,
        "completed_at": completed_at.isoformat(),
        "patient_match_candidate": patient_match_candidate,
        "ai_patient_action": ai_patient_action,
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="capture",
        target_id=capture.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def progress_worker_job(
    db: DbSession,
    *,
    job_id: str,
    output_key: str,
    output: dict[str, Any],
    stage: str | None,
) -> dict[str, Any]:
    """Persist partial AI engine output without completing the job."""
    job = get_job_for_worker(db, job_id)
    if job.status == AiJobStatus.succeeded:
        return {"job": ai_job_payload(job)}

    now = utc_now()
    job.status = AiJobStatus.running
    job.result_metadata = {
        **(job.result_metadata or {}),
        "progress_stage": stage or output_key,
        "progress_output_key": output_key,
        "progress_updated_at": now.isoformat(),
    }

    if job.capture_id is not None:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
        capture.status = CaptureStatus.processing
        capture.capture_metadata = {
            **(capture.capture_metadata or {}),
            output_key: output,
            "ai_processing": output,
        }
        db.commit()
        db.refresh(job)
        return {"job": ai_job_payload(job)}

    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")

    extracted_metadata = output.get("extracted_metadata")
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    if isinstance(output.get("summary"), str):
        session.summary = str(output["summary"])
        session.generated_summary = str(output["summary"])
    if isinstance(output.get("report"), str):
        report_model = structured_report_from_markdown_body(
            title=session.title,
            body=str(output["report"]),
            template_key=session.report_template_key,
            findings=extracted_metadata.get("findings") if isinstance(extracted_metadata, dict) else None,
            source_capture_ids=metadata.get("source_capture_ids") if isinstance(metadata.get("source_capture_ids"), list) else None,
            generated_at=now.isoformat(),
        )
        session.report_model = report_model
        session.generated_report = render_report_body_markdown(
            report_model,
            db=db,
            session=session,
        )
    if isinstance(output.get("report_template_key"), str):
        session.report_template_key = str(output["report_template_key"])
    if isinstance(extracted_metadata, dict):
        metadata = {**metadata, **extracted_metadata}
    incoming_processing_status = (
        extracted_metadata.get("processing_status")
        if isinstance(extracted_metadata, dict) and isinstance(extracted_metadata.get("processing_status"), dict)
        else {}
    )
    metadata = {
        **metadata,
        "processing_status": {
            **(metadata.get("processing_status") if isinstance(metadata.get("processing_status"), dict) else {}),
            **incoming_processing_status,
            "state": "processing",
            "stage": stage or output_key,
            "updated_at": now.isoformat(),
            "source": "mock-ai-engine",
        },
        "generated_output_stale": True,
    }
    session.extracted_metadata = metadata
    session.status = SessionStatus.processing
    session.updated_at = now
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def complete_session_worker_job(
    db: DbSession,
    *,
    job: AiJob,
    output_key: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Persist successful session-level AI engine output."""
    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job is missing session_id")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")

    completed_at = utc_now()
    summary = output.get("summary")
    structured_output = output.get("structured_report")
    if not isinstance(structured_output, dict):
        structured_output = output.get("report_body")
    report = output.get("report")
    extracted_metadata = output.get("extracted_metadata")
    if not isinstance(summary, str) or not isinstance(extracted_metadata, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session job output")
    if isinstance(structured_output, dict):
        session_processing_output = structured_output
    elif isinstance(report, str):
        session_processing_output = session_processing_output_from_legacy_report(output, generated_at=completed_at.isoformat())
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session job output")
    structured_findings = session_processing_output.get("findings")
    if isinstance(structured_findings, list) and not isinstance(extracted_metadata.get("findings"), list):
        extracted_metadata = {**extracted_metadata, "findings": structured_findings}
    structured_source_references = session_processing_output.get("sourceReferences")
    if isinstance(structured_source_references, list):
        extracted_metadata = {
            **extracted_metadata,
            "source_capture_ids": [
                reference["captureId"]
                for reference in structured_source_references
                if isinstance(reference, dict) and isinstance(reference.get("captureId"), str)
            ],
        }

    patient_match = (
        match_patient_from_metadata(db, tenant_id=job.tenant_id, extracted_metadata=extracted_metadata)
        if session.patient_id is None
        else None
    )
    if patient_match:
        extracted_metadata = {**extracted_metadata, "patient_match": patient_match}
        # AI output can propose a deterministic match, but DB-owned patient
        # assignment is changed only by explicit assignment flows.

    previous_versions = []
    previous_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    raw_previous_versions = previous_metadata.get("processed_versions")
    if isinstance(raw_previous_versions, list):
        previous_versions = [version for version in raw_previous_versions if isinstance(version, dict)]
    if session.generated_summary or session.generated_report or previous_metadata:
        previous_metadata_snapshot = {
            key: value
            for key, value in previous_metadata.items()
            if key not in {"processed_versions", "generated_output_stale", "stale_reason", "stale_at"}
        }
        previous_versions.append(
            {
                "summary": session.generated_summary,
                "report": session.generated_report,
                "extracted_metadata": previous_metadata_snapshot,
                "report_template_key": session.report_template_key,
                "organization_source": session.organization_source.value,
                "replaced_at": completed_at.isoformat(),
            }
        )

    session.generated_summary = summary
    session.summary = summary
    session.report_template_key = str(output.get("report_template_key") or session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY)
    report_model = report_model_from_session_processing_output(
        title=session.title,
        template_key=session.report_template_key,
        output=session_processing_output,
    )
    session.report_model = report_model
    session.generated_report = render_report_body_markdown(
        report_model,
        db=db,
        session=session,
    )
    preserved_assignment = {
        key: previous_metadata[key]
        for key in (
            "patient_assignment_source",
            "patient_assignment_reason",
            "ai_patient_action",
            "active_patient_assignment_action",
            "patient_assignment_timeline",
        )
        if key in previous_metadata and key not in extracted_metadata
    }
    preserved_patient_match = {
        key: previous_metadata[key]
        for key in ("patient_match", "patient_match_candidate")
        if session.patient_id is None and key in previous_metadata and key not in extracted_metadata
    }
    session.extracted_metadata = {
        **preserved_assignment,
        **preserved_patient_match,
        **extracted_metadata,
        "session_processing_output": session_processing_output,
        "generated_output_stale": False,
        "processed_versions": previous_versions[-5:],
    }
    session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
    session.organization_source = OrganizationSource.ai_engine
    session.updated_at = completed_at
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.last_error = None
    job.retry_reason = None
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "session_processing_output_version": session_processing_output.get("schemaVersion"),
        "session_status": session.status.value,
        "completed_at": completed_at.isoformat(),
        "patient_match": patient_match,
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="session",
        target_id=session.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def retry_worker_job(
    db: DbSession,
    *,
    job_id: str,
    error_message: str,
    celery_task_id: str | None,
    retry_count: int,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    """Persist a failed attempt before Celery retries it."""
    job = get_job_for_worker(db, job_id)
    if not ai_job_retryable(job):
        db.commit()
        return {"job": ai_job_payload(job)}

    now = utc_now()
    schedule_retry(job, now=now, error_message=error_message, retry_reason=retry_reason)
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
    }
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def fail_worker_job(
    db: DbSession,
    *,
    job_id: str,
    error_message: str,
    celery_task_id: str | None,
    retry_count: int,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    """Persist exhausted Celery retry state while keeping backend retry durable."""
    job = get_job_for_worker(db, job_id)
    now = utc_now()
    if ai_job_retryable(job):
        schedule_retry(job, now=now, error_message=error_message, retry_reason=retry_reason)
    else:
        mark_job_non_retryable(
            job,
            now=now,
            reason=job.retry_reason or retry_reason or "non_retryable",
            error_message=error_message,
        )
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
        "attempt": job.attempt_count,
        "terminal_error": error_message,
    }
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is not None and not ai_job_retryable(job):
            capture.status = CaptureStatus.needs_attention
        elif capture is not None and capture.status != CaptureStatus.deleted:
            capture.status = CaptureStatus.processing
    if job.session_id and job.capture_id is None:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is not None and not ai_job_retryable(job):
            session.status = SessionStatus.failed
        elif session is not None:
            session.status = SessionStatus.processing
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.fail",
        target_type="capture" if job.capture_id else "session",
        target_id=job.capture_id or job.session_id,
        details={"job_id": str(job.id), "error": error_message, "retry_count": retry_count},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}
