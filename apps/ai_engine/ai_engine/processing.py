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


def capture_text(capture: dict[str, Any]) -> str:
    """Extract the best available mock/generated text for a capture."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    for key in ("transcript", "caption", "decorated_text", "ocr", "normalized_note"):
        generated = metadata.get(key)
        if isinstance(generated, dict) and generated.get("text"):
            return str(generated["text"])
    return str(metadata.get("detail") or capture.get("type") or "capture")


def extracted_patient_information(captures: list[dict[str, Any]]) -> dict[str, Any]:
    """Return deterministic patient metadata until real extraction exists."""
    combined = "\n".join(capture_text(capture) for capture in captures)
    full_name = "Demo Patient" if "demo patient" in combined.lower() else None
    national_id = "1234567890" if "1234567890" in combined else None
    missing_fields = [
        field
        for field, value in (("full_name", full_name), ("national_id", national_id))
        if not value
    ]
    return {
        "full_name": full_name,
        "national_id": national_id,
        "expected": ["full_name", "national_id"],
        "missing_fields": missing_fields,
        "status": "complete" if not missing_fields else "missing_required",
        "source": "mock-session-job",
    }


def render_report_template(template: str, values: dict[str, str]) -> str:
    """Render the simple markdown report template."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{ " + key + " }}", value)
    return rendered


def completed_session_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Return mock session summary, metadata, and report output."""
    job = payload["job"]
    session = payload["session"]
    captures = payload.get("captures") or []
    report_template = payload.get("reportTemplate") or {}
    captured_text = [capture_text(capture) for capture in captures]
    summary = "Mock session summary: " + (
        " ".join(text[:140] for text in captured_text[:3]) if captured_text else "No capture content was available."
    )
    patient_information = extracted_patient_information(captures)
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "patient_information": patient_information,
        "clinical_metadata": {
            "visit_type": "mock aesthetics consultation",
            "body_area": "mock treatment area",
            "concerns": ["mock concern"],
        },
        "source_capture_ids": [capture["id"] for capture in captures],
    }
    body = "\n\n".join(captured_text) if captured_text else "Mock clinical body generated from session captures."
    report = render_report_template(
        str(report_template.get("content") or "{{ body }}"),
        {
            "clinician_name": "AesMem clinician",
            "session_date": str(session.get("capturedAt") or session.get("createdAt") or ""),
            "patient_full_name": patient_information.get("full_name") or "[missing]",
            "patient_national_id": patient_information.get("national_id") or "[missing]",
            "body": body,
        },
    )
    return {
        "status": "completed",
        "summary": summary,
        "extracted_metadata": extracted_metadata,
        "report": report,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
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


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))
