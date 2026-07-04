"""Internal AI-engine → backend callback router (a distinct trust boundary).

A self-contained router mounted by ``main.py``, mirroring the existing ``qa_internal_api`` pattern.
Every route is authenticated with the shared ``require_ai_engine_token`` (NOT user auth) and hidden
from the public schema (``include_in_schema=False``): these are the worker-callback endpoints the
AI engine posts to as it drives AI jobs (start/complete/progress/retry/fail) plus the trusted
capture-bytes fetch it reads source files through, and the beat-driven recovery sweep.

Handlers stay thin; the AI-job lifecycle logic lives in ``app/services/ai_jobs``. See
``docs/backend/processing.md``.
"""

from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.observability.metrics import record_ai_job
from app.schemas.ai_jobs import (
    AiJobCompleteRequest,
    AiJobErrorRequest,
    AiJobProgressRequest,
    AiJobStartRequest,
)
from app.services.ai_jobs import (
    complete_worker_job,
    fail_worker_job,
    progress_worker_job,
    recover_all_ai_jobs,
    require_ai_engine_token,
    retry_worker_job,
    start_worker_job,
    sweep_stale_patient_memory,
)
from app.services.capture_storage import internal_source_file_content
from app.storage import ObjectStore, get_object_store

internal_api = APIRouter(
    prefix="/internal",
    dependencies=[Depends(require_ai_engine_token)],
    include_in_schema=False,
)


@internal_api.post("/ai/jobs/recover")
def internal_ai_jobs_recover(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Recover queued/retryable failed AI jobs and sweep stale Pro patient memory.

    The Celery-beat recovery task drives this. Besides re-dispatching durable jobs, it runs the
    patient-memory quiescence sweep (idle ~30 min + stale → refresh) — the background half of the
    decoupled memory trigger model, reusing the existing beat so no new infra is added.
    """
    result = recover_all_ai_jobs(db)
    result["memorySweep"] = sweep_stale_patient_memory(db)
    return result


@internal_api.post("/ai/jobs/{job_id}/start")
def internal_ai_job_start(
    job_id: str,
    request: AiJobStartRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark an AI processing job as running and return worker input."""
    return start_worker_job(
        db,
        job_id=job_id,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
    )


@internal_api.post("/ai/jobs/{job_id}/complete")
def internal_ai_job_complete(
    job_id: str,
    request: AiJobCompleteRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist successful AI processing output from the worker."""
    result = complete_worker_job(
        db, job_id=job_id, output_key=request.output_key, output=request.output, usage=request.usage
    )
    # AI-job outcome metric (engram_ai_jobs_total): completion is always a terminal success.
    record_ai_job("succeeded")
    return result


@internal_api.post("/ai/jobs/{job_id}/progress")
def internal_ai_job_progress(
    job_id: str,
    request: AiJobProgressRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Persist partial AI processing output from the worker."""
    return progress_worker_job(db, job_id=job_id, output_key=request.output_key, output=request.output, stage=request.stage)


@internal_api.post("/ai/jobs/{job_id}/retry")
def internal_ai_job_retry(
    job_id: str,
    request: AiJobErrorRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record a failed AI worker attempt before Celery retries the job."""
    return retry_worker_job(
        db,
        job_id=job_id,
        error_message=request.error_message,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
        retry_reason=request.retry_reason,
    )


@internal_api.post("/ai/jobs/{job_id}/fail")
def internal_ai_job_fail(
    job_id: str,
    request: AiJobErrorRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record terminal AI processing failure after retries are exhausted."""
    result = fail_worker_job(
        db,
        job_id=job_id,
        error_message=request.error_message,
        celery_task_id=request.celery_task_id,
        retry_count=request.retry_count,
        retry_reason=request.retry_reason,
    )
    # AI-job outcome metric (engram_ai_jobs_total): count a failure only when the job is now
    # terminal. fail_worker_job may instead schedule a durable retry (status stays failed but
    # retryable) — that is a transient attempt, not a terminal failure, so it must not inflate the
    # failure rate the AIJobFailureRate alert watches.
    job_view = result.get("job", {}) if isinstance(result, dict) else {}
    metadata = job_view.get("resultMetadata") or {}
    is_terminal = job_view.get("status") == "failed" and metadata.get("retryable") is False
    if is_terminal:
        record_ai_job("failed")
    return result


@internal_api.get("/captures/{capture_id}/file-content")
def internal_capture_file_content(
    capture_id: str,
    db: Session = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store),
) -> Response:
    """Stream capture source bytes to trusted internal AI processors."""
    file_content = internal_source_file_content(db, object_store=object_store, capture_id=capture_id)
    return Response(
        content=file_content["content"],
        media_type=file_content["media_type"],
        headers={"Content-Disposition": f'inline; filename="{file_content["filename"]}"'},
    )
