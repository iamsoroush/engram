"""Durable retry-state primitives and the queued/failed job recovery loops."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.config import settings
from app.models import AiJob, AiJobStatus, Capture, CaptureStatus, Session, SessionStatus
from app.services.sessions import parse_uuid

from app.services.ai_jobs.base import ai_job_payload, utc_now

logger = logging.getLogger(__name__)

__all__ = [
    "ai_job_retryable",
    "classify_retry_reason",
    "retry_delay_seconds",
    "schedule_retry",
    "mark_job_non_retryable",
    "datetime_or_none",
    "ai_job_due_for_recovery",
    "stop_recovery_if_target_is_gone",
    "recover_ai_jobs",
    "recover_all_ai_jobs",
]


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
            # Respect per-session capture ordering: only the chain head dispatches; this also
            # makes recovery the self-healing driver of a stalled chain.
            if is_capture_chain_head(db, job):
                dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)
        elif job.patient_id:
            dispatch_patient_memory_job(db, job)

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
            # Respect per-session capture ordering: only the chain head dispatches; this also
            # makes recovery the self-healing driver of a stalled chain.
            if is_capture_chain_head(db, job):
                dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)
        elif job.patient_id:
            dispatch_patient_memory_job(db, job)

    # Trailing driver of the quiet-period synthesis debounce: fire the single coalesced synthesis for
    # visits that have gone quiet. Best-effort — never let it break job recovery.
    synthesized = 0
    try:
        from app.services.ai_jobs.reports import sweep_debounced_session_synthesis

        synthesized = sweep_debounced_session_synthesis(db)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Debounced synthesis sweep failed")

    return {"recovered": recovered, "skipped": skipped, "synthesized": synthesized}


# recover_ai_jobs / recover_all_ai_jobs re-dispatch through the orchestration layer, which in turn
# depends on this module's retry primitives (schedule_retry, ai_job_retryable). Importing those
# dispatch entry points at the bottom — after the primitives above are defined — keeps the
# recovery <-> orchestration relationship a clean ordered load rather than an import cycle.
from app.services.ai_jobs.orchestration import (  # noqa: E402
    dispatch_capture_processing_job,
    dispatch_patient_memory_job,
    dispatch_session_processing_job,
    is_capture_chain_head,
)
