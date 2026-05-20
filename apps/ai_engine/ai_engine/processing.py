from datetime import datetime, timezone
from time import sleep
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


def partial_metadata(job: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic in-progress capture output."""
    capture_type = capture.get("type")
    label = "Transcribing" if capture_type == "audio" else "Reading image" if capture_type == "photo" else "Structuring note"
    return {
        "status": "processing",
        "text": f"{label} placeholder output...",
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
        "extracted_metadata": {
            **extracted_metadata,
            "progressive_report": {
                "status": "processed",
                "format": "markdown",
                "body": report,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "summaries": {
                "status": "processed",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": mock_findings(captures),
            "processing_status": {
                "state": "complete",
                "label": "Complete",
                "stage": "complete",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
        "report": report,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def mock_findings(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic extracted finding rows for progressive session UX."""
    source_capture_ids = [str(capture.get("id")) for capture in captures if capture.get("id")]
    capture_types = [str(capture.get("type")) for capture in captures if capture.get("type")]
    findings = [
        {
            "id": "visit_type",
            "label": "Visit type",
            "value": "Mock aesthetics consultation",
            "category": "clinical",
            "confidence": 0.82,
            "sourceCaptureIds": source_capture_ids,
            "status": "extracted",
        },
        {
            "id": "source_mix",
            "label": "Source mix",
            "value": ", ".join(sorted(set(capture_types))) or "capture",
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]
    if any("botox" in capture_text(capture).lower() for capture in captures):
        findings.append(
            {
                "id": "product",
                "label": "Product",
                "value": "Botox",
                "category": "clinical",
                "confidence": 0.76,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            }
        )
    return findings


def session_progress_output(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    """Return deterministic partial session output for one mock processing stage."""
    session = payload["session"]
    captures = payload.get("captures") or []
    captured_text = [capture_text(capture) for capture in captures]
    source_capture_ids = [str(capture.get("id")) for capture in captures if capture.get("id")]
    body_source = "\n\n".join(captured_text[:2]) if captured_text else "Mock clinical body is waiting for source capture text."
    stage_copy = {
        "transcripts": "Reading source captures and preparing the report surface.",
        "report": "Drafting the clinical report from available source material.",
        "findings": "Extracting structured findings from the draft.",
        "summary": "Condensing the session into a short clinical summary.",
    }
    summary = stage_copy.get(stage, "Processing session.")
    report = (
        "# Progressive clinical report\n\n"
        f"## Current stage\n{summary}\n\n"
        f"## Source material\n{body_source}"
    )
    findings = mock_findings(captures) if stage in {"findings", "summary"} else []
    return {
        "status": "processing",
        "summary": summary,
        "report": report,
        "report_template_key": session.get("reportTemplateKey") or "default",
        "extracted_metadata": {
            "status": "processing",
            "generated_by": "ai-engine",
            "job_id": payload["job"]["id"],
            "job_type": payload["job"]["jobType"],
            "generated_at": utc_now().isoformat(),
            "source_capture_ids": source_capture_ids,
            "progressive_report": {
                "status": "generating" if stage in {"transcripts", "report"} else "partial",
                "format": "markdown",
                "body": report,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "summaries": {
                "status": "partial",
                "short": summary,
                "clinical": summary,
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
            "findings": findings,
            "processing_status": {
                "state": "processing",
                "label": summary,
                "stage": stage,
                "detail": f"Mock AI stage: {stage}",
                "source": "mock-ai-engine",
                "updated_at": utc_now().isoformat(),
            },
        },
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

    def progress_job(self, job_id: str, *, output_key: str, output: dict[str, Any], stage: str) -> dict[str, Any]:
        """Submit partial job output to the backend."""
        return self.post(
            f"/internal/ai/jobs/{job_id}/progress",
            {"output_key": output_key, "output": output, "stage": stage},
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
    # TODO(ai-integration): Replace this staged placeholder with real media/text processors.
    client.progress_job(job_id, output_key=output_key, output=partial_metadata(job, capture), stage="transcript")
    sleep(settings.mock_stage_delay_seconds)
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    # TODO(ai-integration): Replace these deterministic stages with real progressive AI session artifacts.
    for stage in ("transcripts", "report", "findings", "summary"):
        client.progress_job(job_id, output_key="session_progress", output=session_progress_output(payload, stage), stage=stage)
        sleep(settings.mock_stage_delay_seconds)

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))
