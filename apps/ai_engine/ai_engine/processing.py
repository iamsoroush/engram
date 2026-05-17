from datetime import datetime, timezone
from typing import Any

import httpx

from ai_engine.config import settings


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def output_key_for_capture(capture_type: str) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == "audio":
        return "transcript"
    if capture_type == "photo":
        return "caption"
    return "decorated_text"


def placeholder_text_for_capture(capture: dict[str, Any]) -> str:
    """Build deterministic placeholder output until real AI processors land."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    detail = str(metadata.get("detail") or "").strip()
    capture_type = capture.get("type")
    if capture_type == "audio":
        return "Transcript placeholder. Audio capture processing completed successfully."
    if capture_type == "photo":
        return "Caption placeholder. Image capture processing completed successfully."
    return detail or "Text placeholder. Text capture processing completed successfully."


def completed_metadata(job: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    """Return metadata for a completed placeholder capture processor."""
    return {
        "status": "completed",
        "text": placeholder_text_for_capture(capture),
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_artifact_ids": job.get("inputArtifactIds") or [],
    }


class BackendClient:
    """HTTP client for backend-owned AI job state."""

    def __init__(self) -> None:
        self.base_url = settings.backend_internal_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.internal_token}"}

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to an internal backend endpoint."""
        response = httpx.post(
            f"{self.base_url}{path}",
            json=payload,
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def start_job(self, job_id: str, *, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Mark a job running and fetch its input payload."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/start",
            {"celery_task_id": celery_task_id, "retry_count": retry_count},
        )

    def complete_job(self, job_id: str, *, output_key: str, output: dict[str, Any]) -> dict[str, Any]:
        """Submit successful job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/complete",
            {"output_key": output_key, "output": output},
        )

    def retry_job(self, job_id: str, *, error_message: str, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Record a failed attempt before Celery retries."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/retry",
            {"error_message": error_message, "celery_task_id": celery_task_id, "retry_count": retry_count},
        )

    def fail_job(self, job_id: str, *, error_message: str, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Record terminal job failure."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/fail",
            {"error_message": error_message, "celery_task_id": celery_task_id, "retry_count": retry_count},
        )


def run_capture_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a capture processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    capture = payload["capture"]
    if job.get("status") == "succeeded":
        return

    output_key = output_key_for_capture(capture["type"])
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))
