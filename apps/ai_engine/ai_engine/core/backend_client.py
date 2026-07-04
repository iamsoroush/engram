"""HTTP client for backend-owned AI job state (start/complete/progress/retry/fail/recover + files).

The worker owns no job state; the backend does. Every job runner drives its lifecycle through this
client over the internal API, and ``complete_job`` ships the real gateway usage collected for the job
(see ``core.gateway``). The worker never imports backend code — JSON-over-HTTP is the boundary.
"""
from typing import Any

import httpx

from ai_engine.config import settings
from ai_engine.core.gateway import drain_usage_sink


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

    def get_bytes(self, path: str) -> bytes:
        """GET binary content from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content

    def get_file(self, path: str) -> tuple[bytes, str]:
        """GET binary content plus its content type from an internal backend endpoint."""
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self.headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "")

    def start_job(self, job_id: str, *, celery_task_id: str | None, retry_count: int) -> dict[str, Any]:
        """Mark a job running and fetch its input payload."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/start",
            {"celery_task_id": celery_task_id, "retry_count": retry_count},
        )

    def complete_job(self, job_id: str, *, output_key: str, output: dict[str, Any]) -> dict[str, Any]:
        """Submit successful job output to the backend, with the real gateway usage for this job."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/complete",
            {"output_key": output_key, "output": output, "usage": drain_usage_sink()},
        )

    def progress_job(self, job_id: str, *, output_key: str, output: dict[str, Any], stage: str) -> dict[str, Any]:
        """Submit partial job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/progress",
            {"output_key": output_key, "output": output, "stage": stage},
        )

    def retry_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a failed attempt before Celery retries."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/retry",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def fail_job(
        self,
        job_id: str,
        *,
        error_message: str,
        celery_task_id: str | None,
        retry_count: int,
        retry_reason: str | None = None,
    ) -> dict[str, Any]:
        """Record terminal job failure."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/fail",
            {
                "error_message": error_message,
                "celery_task_id": celery_task_id,
                "retry_count": retry_count,
                "retry_reason": retry_reason,
            },
        )

    def recover_jobs(self) -> dict[str, Any]:
        """Ask the backend to re-dispatch queued or retryable failed work."""
        return self.post("/internal/ai/jobs/recover", {})
