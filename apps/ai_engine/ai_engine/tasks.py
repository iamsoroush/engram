import logging

from celery.signals import worker_ready
from celery.exceptions import MaxRetriesExceededError
import httpx

from ai_engine.celery_app import celery_app
from ai_engine.config import settings
from ai_engine.processing import (
    BackendClient,
    run_capture_processing_job,
    run_patient_memory_job,
    run_qa_draft_job,
    run_session_processing_job,
)

logger = logging.getLogger(__name__)


@worker_ready.connect
def recover_pending_ai_jobs_on_startup(**_: object) -> None:
    """Resume durable backend AI work when a worker comes online."""
    recover_pending_ai_jobs()


@celery_app.task(name="ai_engine.recover_pending_ai_jobs")
def recover_pending_ai_jobs() -> None:
    """Periodically ask the backend to dispatch due durable AI jobs."""
    try:
        result = BackendClient().recover_jobs()
        logger.info("Requested AI job recovery", extra={"result": result})
    except Exception:
        logger.exception("Failed to request AI job recovery")


def retry_reason_for_exception(exc: Exception) -> str:
    """Map worker exceptions to backend retry reason codes."""
    message = str(exc).lower()
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return "source_missing"
    if "source file is missing" in message:
        return "source_missing"
    if "conversion to flac failed" in message or "ffmpeg" in message:
        return "conversion_failed"
    if (
        isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))
        or "transcription" in message
        or "openai" in message
        or "timeout" in message
        or "connection" in message
        or "rate limit" in message
    ):
        return "gateway_unavailable"
    return "worker_error"


def run_task_with_retries(task, job_id: str, runner, label: str) -> None:
    """Run queued processing with retry-aware status updates."""
    try:
        runner(job_id, celery_task_id=task.request.id, retry_count=task.request.retries)
    except Exception as exc:
        logger.exception(
            "%s processing task failed",
            label,
            extra={
                "job_id": job_id,
                "celery_task_id": task.request.id,
                "retry_count": task.request.retries,
            },
        )
        client = BackendClient()
        retry_reason = retry_reason_for_exception(exc)
        try:
            client.retry_job(
                job_id,
                error_message=str(exc),
                celery_task_id=task.request.id,
                retry_count=task.request.retries,
                retry_reason=retry_reason,
            )
        except Exception:
            logger.exception("Failed to persist AI job retry state", extra={"job_id": job_id})
        try:
            raise task.retry(
                exc=exc,
                countdown=settings.job_retry_delay_seconds,
                max_retries=settings.job_max_retries,
            )
        except MaxRetriesExceededError:
            try:
                client.fail_job(
                    job_id,
                    error_message=str(exc),
                    celery_task_id=task.request.id,
                    retry_count=task.request.retries,
                    retry_reason=retry_reason,
                )
            except Exception:
                logger.exception("Failed to persist terminal AI job failure", extra={"job_id": job_id})
            raise


@celery_app.task(bind=True, name="ai_engine.process_audio_capture")
def process_audio_capture_task(self, job_id: str) -> None:
    """Run an audio capture processing job."""
    run_task_with_retries(self, job_id, run_capture_processing_job, "Capture")


@celery_app.task(bind=True, name="ai_engine.process_text_capture")
def process_text_capture_task(self, job_id: str) -> None:
    """Run a text capture processing job."""
    run_task_with_retries(self, job_id, run_capture_processing_job, "Capture")


@celery_app.task(bind=True, name="ai_engine.process_image_capture")
def process_image_capture_task(self, job_id: str) -> None:
    """Run an image capture processing job."""
    run_task_with_retries(self, job_id, run_capture_processing_job, "Capture")


@celery_app.task(bind=True, name="ai_engine.process_session")
def process_session_task(self, job_id: str) -> None:
    """Run a session processing job."""
    run_task_with_retries(self, job_id, run_session_processing_job, "Session")


@celery_app.task(bind=True, name="ai_engine.process_patient_memory")
def process_patient_memory_task(self, job_id: str) -> None:
    """Run a combined patient summary + history job."""
    run_task_with_retries(self, job_id, run_patient_memory_job, "Patient memory")


@celery_app.task(bind=True, name="ai_engine.process_qa_draft")
def process_qa_draft_task(self, job_id: str) -> None:
    """Run a post-session patient Q&A reply-draft job (AES-402)."""
    run_task_with_retries(self, job_id, run_qa_draft_job, "Q&A draft")
