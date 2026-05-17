import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import Capture, CaptureStatus, CaptureType, FakeJob, FakeJobStatus, FakeJobType
from app.services.capture_storage import get_capture_for_tenant
from app.services.sessions import parse_uuid

logger = logging.getLogger(__name__)

TASK_NAME_BY_JOB_TYPE = {
    FakeJobType.audio_capture_process: "ai_engine.process_audio_capture",
    FakeJobType.text_capture_process: "ai_engine.process_text_capture",
    FakeJobType.image_capture_process: "ai_engine.process_image_capture",
}


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def ai_job_payload(job: FakeJob) -> dict[str, Any]:
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


def job_type_for_capture(capture_type: CaptureType) -> FakeJobType:
    """Map capture media type to the concrete AI processing job type."""
    if capture_type == CaptureType.audio:
        return FakeJobType.audio_capture_process
    if capture_type == CaptureType.photo:
        return FakeJobType.image_capture_process
    return FakeJobType.text_capture_process


def output_key_for_capture(capture_type: CaptureType) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == CaptureType.audio:
        return "transcript"
    if capture_type == CaptureType.photo:
        return "caption"
    return "decorated_text"


def queued_metadata(job: FakeJob, capture: Capture) -> dict[str, Any]:
    """Return metadata stored while a capture is waiting for a worker."""
    return {
        "status": "queued",
        "generated_by": "ai-engine",
        "job_id": str(job.id),
        "job_type": job.job_type.value,
        "output_key": output_key_for_capture(capture.capture_type),
        "queued_at": utc_now().isoformat(),
    }


def create_capture_processing_job(db: DbSession, *, principal: CurrentPrincipal, capture: Capture) -> FakeJob:
    """Create a queued capture processing job and mark the capture processing."""
    source_ids = [str(capture.source_artifact_id)] if capture.source_artifact_id else []
    job = FakeJob(
        tenant_id=principal.tenant_id,
        session_id=capture.session_id,
        capture_id=capture.id,
        job_type=job_type_for_capture(capture.capture_type),
        status=FakeJobStatus.queued,
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


def dispatch_capture_processing_job(db: DbSession, job: FakeJob) -> None:
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
        job.status = FakeJobStatus.failed
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


def get_job_for_worker(db: DbSession, job_id: str) -> FakeJob:
    """Fetch a worker-visible job row by ID."""
    try:
        parsed = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id") from exc
    job = db.execute(select(FakeJob).where(FakeJob.id == parsed)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return job


def worker_job_payload(db: DbSession, job: FakeJob) -> dict[str, Any]:
    """Serialize job input needed by the AI engine worker."""
    capture = None
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
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


def start_worker_job(
    db: DbSession,
    *,
    job_id: str,
    celery_task_id: str | None,
    retry_count: int,
) -> dict[str, Any]:
    """Mark an AI job running and return its input payload."""
    job = get_job_for_worker(db, job_id)
    if job.status == FakeJobStatus.succeeded:
        return worker_job_payload(db, job)
    if job.capture_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job is missing capture_id")
    capture = db.execute(
        select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")

    now = utc_now()
    job.status = FakeJobStatus.running
    job.started_at = job.started_at or now
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "attempt": retry_count + 1,
        "started_at": now.isoformat(),
    }
    capture.status = CaptureStatus.processing
    db.commit()
    db.refresh(job)
    db.refresh(capture)
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job is missing capture_id")
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
    job.status = FakeJobStatus.succeeded
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
    job.status = FakeJobStatus.queued
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
    job.status = FakeJobStatus.failed
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
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.fail",
        target_type="capture",
        target_id=job.capture_id,
        details={"job_id": str(job.id), "error": error_message, "retry_count": retry_count},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}
