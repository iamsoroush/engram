import logging

from celery.exceptions import MaxRetriesExceededError

from ai_engine.celery_app import celery_app
from ai_engine.config import settings
from ai_engine.processing import BackendClient, run_capture_processing_job, run_session_processing_job

logger = logging.getLogger(__name__)


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
        try:
            client.retry_job(
                job_id,
                error_message=str(exc),
                celery_task_id=task.request.id,
                retry_count=task.request.retries,
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
