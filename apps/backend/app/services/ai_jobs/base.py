"""Foundational helpers shared across the ai_jobs package (time + job serialization)."""
from datetime import datetime, timezone
from typing import Any

from app.models import AiJob

__all__ = [
    "utc_now",
    "ai_job_payload",
]


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
