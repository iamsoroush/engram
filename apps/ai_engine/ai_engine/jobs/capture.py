"""Capture job dispatcher: routes an audio/photo/note capture to its type processor.

The three ``process_{audio,text,image}_capture`` Celery tasks all run this one job. It drives the
backend lifecycle (start → progress → complete) and dispatches by capture type: real transcription
(audio), Pro captioning (photo, when an ``enrichmentContext`` is present + a gateway is configured),
a raw passthrough (note), and the deterministic placeholder / blank-caption fallbacks otherwise.
"""
from time import sleep

from ai_engine.config import settings
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.fixtures import is_fixture_capture
from ai_engine.core.gateway import resolve_model, transcription_is_configured
from ai_engine.jobs.capture_audio import completed_audio_metadata
from ai_engine.jobs.capture_note import raw_note_text
from ai_engine.jobs.capture_photo import caption_image_content, caption_output_metadata
from ai_engine.jobs.captures_common import (
    capture_processing_output,
    completed_metadata,
    output_key_for_capture,
    partial_metadata,
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
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    # Audio transcription and Pro photo/note enrichment are real (gateway-backed); Basic, gateway-less,
    # and QA-fixture captures fall back to the deterministic placeholder below.
    client.progress_job(job_id, output_key=output_key, output=partial_metadata(job, capture), stage="transcript")
    if capture.get("type") == "audio":
        source_content = None
        if transcription_is_configured() and capture.get("sourceArtifactId"):
            source_content = client.get_bytes(f"/internal/captures/{capture['id']}/file-content")
        if not transcription_is_configured():
            sleep(settings.mock_stage_delay_seconds)
        client.complete_job(
            job_id,
            output_key=output_key,
            output=completed_audio_metadata(
                job,
                capture,
                source_content,
                payload.get("transcriptionContext"),
                model=resolve_model("transcription", ai_models),
            ),
        )
        return

    # Notes are a pure passthrough (note decoration removed): no gateway call ever. The job marks the
    # note processed with its RAW text — preserving chain ordering + report_contribution wiring — and
    # the report reads the raw `detail`. Fixtures keep their deterministic text for QA.
    if capture.get("type") == "note" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, raw_note_text(capture) or ""))
        return

    # Pro photo captioning. The backend attaches an `enrichmentContext` only for Pro tenants; Basic and
    # gateway-less/fixture captures keep the deterministic/blank fallback. A gateway failure propagates
    # as a retryable worker error; an empty gateway response leaves the caption blank (manual add).
    enrichment_context = payload.get("enrichmentContext") if isinstance(payload.get("enrichmentContext"), dict) else None
    if (
        capture.get("type") == "photo"
        and enrichment_context is not None
        and transcription_is_configured()
        and not is_fixture_capture(capture)
        and capture.get("sourceArtifactId")
    ):
        content, media_type = client.get_file(f"/internal/captures/{capture['id']}/file-content")
        caption_result = caption_image_content(
            content, media_type, enrichment_context, model=resolve_model("caption", ai_models)
        )
        output = caption_output_metadata(job, caption_result) if caption_result else capture_processing_output(job, "")
        client.complete_job(job_id, output_key=output_key, output=output)
        return

    # Un-enriched photos (Basic tenants, or no gateway) get NO AI caption — leave it blank so the UI
    # offers a manual "Add caption" instead of a meaningless placeholder. Fixtures keep their
    # deterministic caption for QA.
    if capture.get("type") == "photo" and not is_fixture_capture(capture):
        client.complete_job(job_id, output_key=output_key, output=capture_processing_output(job, ""))
        return

    sleep(settings.mock_stage_delay_seconds)
    client.complete_job(job_id, output_key=output_key, output=completed_metadata(job, capture))
