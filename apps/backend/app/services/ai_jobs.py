import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import Capture, CaptureStatus, CaptureType, AiJob, AiJobStatus, AiJobType, OrganizationSource, Patient, PatientIdentifier, Session, SessionStatus
from app.services.capture_storage import get_capture_for_tenant
from app.services.sessions import parse_uuid

logger = logging.getLogger(__name__)

TASK_NAME_BY_JOB_TYPE = {
    AiJobType.audio_capture_process: "ai_engine.process_audio_capture",
    AiJobType.text_capture_process: "ai_engine.process_text_capture",
    AiJobType.image_capture_process: "ai_engine.process_image_capture",
    AiJobType.session_organize: "ai_engine.process_session",
}

REPORT_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "report_templates"
DEFAULT_REPORT_TEMPLATE_KEY = "default"


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
        "createdByUserId": str(job.created_by_user_id) if job.created_by_user_id else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


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
    """Load a markdown report template by stable key."""
    safe_key = template_key or DEFAULT_REPORT_TEMPLATE_KEY
    if safe_key != DEFAULT_REPORT_TEMPLATE_KEY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report template")
    path = REPORT_TEMPLATE_DIR / "default_session_report.md"
    return {"key": safe_key, "content": path.read_text(encoding="utf-8")}


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

    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued capture processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
    except Exception as exc:
        logger.exception("Failed to queue capture processing job", extra={"job_id": str(job.id)})
        job.status = AiJobStatus.failed
        job.error_message = str(exc)
        job.completed_at = utc_now()
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.capture_id:
            capture = db.execute(
                select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if capture is not None:
                capture.status = CaptureStatus.needs_attention
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

    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued session processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
    except Exception as exc:
        logger.exception("Failed to queue session processing job", extra={"job_id": str(job.id)})
        job.status = AiJobStatus.failed
        job.error_message = str(exc)
        job.completed_at = utc_now()
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.session_id:
            session = db.execute(
                select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if session is not None:
                session.status = SessionStatus.failed
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
        }
    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
    captures = db.execute(
        select(Capture).where(Capture.tenant_id == job.tenant_id, Capture.session_id == session.id).order_by(Capture.created_at)
    ).scalars()
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
    job.status = AiJobStatus.running
    job.started_at = job.started_at or now
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "attempt": retry_count + 1,
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
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        output_key: output,
        "ai_processing": output,
    }
    capture.status = CaptureStatus.processed
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "capture_status": capture.status.value,
        "completed_at": completed_at.isoformat(),
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


def normalize_patient_national_id(value: Any) -> str | None:
    """Normalize patient national IDs for deterministic matching."""
    if value is None:
        return None
    normalized = "".join(character for character in str(value) if character.isdigit())
    return normalized or None


def match_patient_from_metadata(db: DbSession, *, tenant_id: uuid.UUID, extracted_metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Find an existing patient using extracted patient metadata."""
    patient_info = extracted_metadata.get("patient_information")
    if not isinstance(patient_info, dict):
        return None

    national_id = normalize_patient_national_id(patient_info.get("national_id"))
    if national_id:
        identifier = db.execute(
            select(PatientIdentifier)
            .where(
                PatientIdentifier.tenant_id == tenant_id,
                PatientIdentifier.identifier_type == "national_id",
                PatientIdentifier.normalized_value == national_id,
            )
            .order_by(PatientIdentifier.created_at.desc())
        ).scalars().first()
        if identifier is not None:
            patient = db.get(Patient, identifier.patient_id)
            if patient is not None:
                return {
                    "status": "matched",
                    "patient_id": str(patient.id),
                    "display_name": patient.display_name,
                    "matched_on": "national_id",
                }

    full_name = patient_info.get("full_name")
    if isinstance(full_name, str) and full_name.strip():
        patient = db.execute(
            select(Patient).where(Patient.tenant_id == tenant_id, Patient.display_name.ilike(full_name.strip())).limit(1)
        ).scalar_one_or_none()
        if patient is not None:
            return {
                "status": "possible_match",
                "patient_id": str(patient.id),
                "display_name": patient.display_name,
                "matched_on": "full_name",
            }
    return None


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
    report = output.get("report")
    extracted_metadata = output.get("extracted_metadata")
    if not isinstance(summary, str) or not isinstance(report, str) or not isinstance(extracted_metadata, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session job output")

    patient_match = match_patient_from_metadata(db, tenant_id=job.tenant_id, extracted_metadata=extracted_metadata)
    if patient_match:
        extracted_metadata = {**extracted_metadata, "patient_match": patient_match}
        if patient_match["status"] == "matched" and session.patient_id is None:
            session.patient_id = uuid.UUID(patient_match["patient_id"])

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
    session.generated_report = report
    session.extracted_metadata = {
        **extracted_metadata,
        "generated_output_stale": False,
        "processed_versions": previous_versions[-5:],
    }
    session.report_template_key = str(output.get("report_template_key") or session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY)
    session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
    session.organization_source = OrganizationSource.ai_engine
    session.updated_at = completed_at
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
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
) -> dict[str, Any]:
    """Persist a failed attempt before Celery retries it."""
    job = get_job_for_worker(db, job_id)
    job.status = AiJobStatus.queued
    job.error_message = error_message
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "attempt": retry_count + 1,
        "last_error": error_message,
        "retrying": True,
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
) -> dict[str, Any]:
    """Persist terminal AI job failure."""
    job = get_job_for_worker(db, job_id)
    job.status = AiJobStatus.failed
    job.error_message = error_message
    job.completed_at = utc_now()
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "attempt": retry_count + 1,
        "terminal_error": error_message,
    }
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is not None:
            capture.status = CaptureStatus.needs_attention
    if job.session_id and job.capture_id is None:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is not None:
            session.status = SessionStatus.failed
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
