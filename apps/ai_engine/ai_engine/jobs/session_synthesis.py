"""Session processing job (process_session): Pro single-pass synthesis + the legacy baseline path.

The keystone Pro job. When the backend sets ``reportSynthesis`` (Pro + gateway), ONE structured call
emits the per-visit report sections AND the performed treatments[] together (the A↔B contract),
followed by the in-job cross-visit safety reconcile. Gateway-less / malformed → a SKIP sentinel so
the deterministic baseline stands (Basic + gateway-less run zero AI and must never break). The rest
of this module is that deterministic baseline path (the legacy progressive stages + fixtures) that
the same Celery job falls back to. Vertical-agnostic via the domain descriptor.
"""
from time import sleep
from typing import Any

from ai_engine.config import settings
# The A↔B synthesis contract (report sections + performed treatments) now lives in
# ``contracts.synthesis``; these are re-exported so the ``processing`` shim and tests keep importing
# them from the job module.
from ai_engine.contracts.synthesis import (  # noqa: F401
    SESSION_SYNTHESIS_OUTPUT_VERSION,
    SYNTHESIS_LANGUAGES,
    SYNTHESIS_SECTION_IDS,
    SYNTHESIS_SECTION_TITLES_FA,
    SYNTHESIS_SECTIONS,
    parse_session_synthesis_output,
    synthesis_section_title,
)
from ai_engine.core.backend_client import BackendClient
from ai_engine.core.fixtures import TEST_CAPTURE_TEXT_BY_FILENAME, TEST_FINAL_SUMMARY
from ai_engine.core.gateway import (
    gateway_client,
    resolve_model,
    resolve_reasoning_effort,
    transcription_is_configured,
)
from ai_engine.core.structured import escalation_requested, retry_tier
from ai_engine.core.util import utc_now
# The synthesis prompt lives in its own versioned module (§3.3); ``report_synthesis_prompt`` is
# re-exported for the shim + tests, and the envelope stamps ``REPORT_SYNTHESIS_PROMPT_VERSION``.
from ai_engine.prompts.synthesis import PROMPT_VERSION as REPORT_SYNTHESIS_PROMPT_VERSION
from ai_engine.prompts.synthesis import build as report_synthesis_prompt  # noqa: F401
from ai_engine.jobs.safety_reconcile import _safety_flag_key, reconcile_safety_flags


def capture_text(capture: dict[str, Any]) -> str:
    """Extract the best available mock/generated text for a capture."""
    metadata = capture.get("metadata") if isinstance(capture.get("metadata"), dict) else {}
    for key in ("transcript", "caption", "note_text", "ocr"):
        generated = metadata.get(key)
        if isinstance(generated, dict) and generated.get("text"):
            return str(generated["text"])
    filename = str(metadata.get("original_filename") or "").strip()
    if filename in TEST_CAPTURE_TEXT_BY_FILENAME:
        return TEST_CAPTURE_TEXT_BY_FILENAME[filename]
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


def flattened_processing_captures(processing_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return captures from the stable session-processing input context.

    (G3) captures is now a flat chronological list (append-only for prefix-cache stability); the legacy
    grouped {audio, photos, text} dict is still tolerated so an in-flight pre-G3 payload processes.
    """
    captures = processing_context.get("captures")
    if isinstance(captures, list):
        return [capture for capture in captures if isinstance(capture, dict)]
    flattened: list[dict[str, Any]] = []
    if isinstance(captures, dict):
        for group in ("audio", "photos", "text"):
            values = captures.get(group)
            if isinstance(values, list):
                flattened.extend(capture for capture in values if isinstance(capture, dict))
    return flattened


def capture_id(capture: dict[str, Any]) -> str | None:
    """Read capture IDs from either the new context or legacy worker payload."""
    value = capture.get("captureId") or capture.get("id")
    return str(value) if value else None


def session_capture_text(capture: dict[str, Any]) -> str:
    """Extract text from the session-processing context or legacy capture metadata."""
    for key in ("transcript", "caption", "rawText"):
        value = capture.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return capture_text(capture)


def extracted_patient_information_from_context(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return deterministic patient extraction without owning assignment."""
    assigned_patient = processing_context.get("assignedPatient")
    if isinstance(assigned_patient, dict):
        return {
            "status": "assigned_context_available",
            "patient_id": assigned_patient.get("patientId"),
            "display_name": assigned_patient.get("displayName"),
            "source": "db-session-assignment",
        }
    for capture in captures:
        patient_information = capture.get("patientInformation")
        if isinstance(patient_information, dict):
            meaningful_values = [
                patient_information.get("raw_mentioned_name"),
                patient_information.get("standardized_display_name"),
                patient_information.get("national_id"),
                patient_information.get("phone"),
            ]
            if any(isinstance(value, str) and value.strip() for value in meaningful_values):
                return {
                    **patient_information,
                    "source": "capture-transcription-patient-information",
                }
    return extracted_patient_information(captures)


def structured_session_report_body(
    processing_context: dict[str, Any],
    captures: list[dict[str, Any]],
    summary: str,
) -> dict[str, Any]:
    """Build deterministic body-level structured output for session processing."""
    if is_expected_test_fixture(captures):
        return expected_test_structured_report(captures, summary)

    paragraphs: list[str] = []
    history = processing_context.get("patientSummarizedHistory")
    if isinstance(history, str) and history.strip():
        paragraphs.append(f"Known patient history summary: {history.strip()}")

    audio: list[str] = []
    notes: list[str] = []
    photos: list[str] = []
    for capture in captures:
        text = session_capture_text(capture)
        if not text:
            continue
        if capture.get("type") == "audio":
            audio.append(text)
        elif capture.get("type") == "note":
            notes.append(text)
        elif capture.get("type") == "photo":
            photos.append(text)
    if audio:
        paragraphs.append("Audio notes: " + " ".join(audio))
    if notes:
        paragraphs.append("Written notes: " + " ".join(notes))
    if photos:
        paragraphs.append("Photo observations: " + " ".join(photos))
    if not paragraphs:
        paragraphs.append("Mock clinical body generated from the available session context.")

    blocks: list[dict[str, Any]] = [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs]
    for capture in captures:
        if capture.get("type") == "photo" and capture.get("artifactId"):
            blocks.append(
                {
                    "type": "image",
                    "artifactId": str(capture["artifactId"]),
                    "captureId": capture_id(capture),
                    "caption": capture.get("caption") or "Source image",
                }
            )

    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [{"id": "clinical-report", "title": "Clinical report", "blocks": blocks}],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def is_expected_test_fixture(captures: list[dict[str, Any]]) -> bool:
    """Return true when uploads match the deterministic QA fixture."""
    combined = "\n".join(session_capture_text(capture) for capture in captures)
    markers = (
        "follow-up after cheek filler",
        "mild asymmetry on the left cheek",
        "0.3 mL hyaluronic acid filler",
        "avoid heavy exercise for 24 hours",
    )
    return all(marker.lower() in combined.lower() for marker in markers)


def first_capture_by_text(captures: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    """Find a fixture capture by deterministic mock text."""
    for capture in captures:
        if needle.lower() in session_capture_text(capture).lower():
            return capture
    return None


def expected_test_structured_report(captures: list[dict[str, Any]], summary: str) -> dict[str, Any]:
    """Return the final structured report for the provided QA fixture."""
    pre_photo = first_capture_by_text(captures, "Pre-correction image")
    post_photo = first_capture_by_text(captures, "Post-correction image")
    photo_blocks: list[dict[str, Any]] = []
    for capture in (pre_photo, post_photo):
        if capture is None:
            continue
        photo_blocks.append(
            {
                "type": "image",
                "artifactId": str(capture.get("artifactId") or capture.get("sourceArtifactId") or ""),
                "captureId": capture_id(capture),
                "caption": session_capture_text(capture),
            }
        )
    source_references = [{"type": "capture", "captureId": value} for value in (capture_id(capture) for capture in captures) if value]
    artifact_references = [
        {
            "type": "artifact",
            "artifactId": capture.get("artifactId") or capture.get("sourceArtifactId"),
            "captureId": capture_id(capture),
            "url": capture.get("artifactUrl"),
            "s3Url": capture.get("s3Url"),
        }
        for capture in captures
        if capture.get("artifactId") or capture.get("sourceArtifactId")
    ]
    return {
        "schemaVersion": "2026-05-21.session-processing-output.v1",
        "summary": summary,
        "sections": [
            {
                "id": "visit-reason",
                "title": "Visit Reason",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Follow-up visit after cheek filler. Patient reported mild left cheek asymmetry and requested a conservative correction.",
                    }
                ],
            },
            {
                "id": "relevant-history",
                "title": "Relevant History",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "No pain, fever, or allergy was reported during the visit. Patient prefers subtle correction and wants to avoid visible overfilling.",
                    }
                ],
            },
            {
                "id": "procedure",
                "title": "Procedure",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Injected 0.3 mL hyaluronic acid filler into the left mid cheek using cannula technique. Patient tolerated the procedure well.",
                    }
                ],
            },
            {"id": "photos", "title": "Photos", "blocks": photo_blocks},
            {
                "id": "aftercare",
                "title": "Aftercare",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "Aftercare instructions were given. Patient was advised not to massage the area and to avoid heavy exercise for 24 hours. Patient should send a follow-up photo in 2 weeks if asymmetry persists.",
                    }
                ],
            },
        ],
        "artifactReferences": artifact_references,
        "sourceReferences": source_references,
        "findings": mock_findings(captures),
        "generatedBy": "mock-ai-engine",
        "generatedAt": utc_now().isoformat(),
    }


def completed_session_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Return mock session summary, metadata, and report output."""
    job = payload["job"]
    session = payload["session"]
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    report_template = payload.get("reportTemplate") or {}
    captured_text = [session_capture_text(capture) for capture in captures]
    summary = (
        TEST_FINAL_SUMMARY
        if is_expected_test_fixture(captures)
        else "Mock session summary: " + (
            " ".join(text[:140] for text in captured_text[:3]) if captured_text else "No capture content was available."
        )
    )
    patient_information = extracted_patient_information_from_context(processing_context, captures)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    structured_report = structured_session_report_body(processing_context, captures, summary)
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
        "source_capture_ids": source_capture_ids,
    }
    body = "\n\n".join(captured_text) if captured_text else "Mock clinical body generated from session captures."
    # The backend owns report templating and patient-information injection.
    # The AI engine returns structured clinical body content only.
    report = body
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
        "structured_report": structured_report,
        "report": report,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def mock_findings(captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic extracted finding rows for progressive session UX."""
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    if is_expected_test_fixture(captures):
        return [
            {
                "id": "procedure",
                "label": "Procedure",
                "value": "Cheek filler touch-up",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "anatomical_area",
                "label": "Anatomical area",
                "value": "Left mid cheek",
                "category": "clinical",
                "confidence": 0.94,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "product",
                "label": "Product",
                "value": "Hyaluronic acid filler",
                "category": "clinical",
                "confidence": 0.91,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "volume",
                "label": "Volume",
                "value": "0.3 mL",
                "category": "clinical",
                "confidence": 0.96,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "technique",
                "label": "Technique",
                "value": "Cannula technique",
                "category": "clinical",
                "confidence": 0.9,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
            {
                "id": "aftercare",
                "label": "Aftercare",
                "value": "No massage; avoid heavy exercise for 24 hours",
                "category": "clinical",
                "confidence": 0.93,
                "sourceCaptureIds": source_capture_ids,
                "status": "extracted",
            },
        ]
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
    if any("botox" in session_capture_text(capture).lower() for capture in captures):
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
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context) or payload.get("captures") or []
    captured_text = [session_capture_text(capture) for capture in captures]
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    body_source = "\n\n".join(captured_text[:2]) if captured_text else "Mock clinical body is waiting for source capture text."
    stage_copy = {
        "transcripts": "Reading source captures and preparing the report surface.",
        "report": "Drafting the clinical report from available source material.",
        "findings": "Extracting structured findings from the draft.",
        "summary": "Condensing the session into a short clinical summary.",
    }
    summary = stage_copy.get(stage, "Processing session.")
    findings = mock_findings(captures) if stage in {"findings", "summary"} else []
    return {
        "status": "processing",
        "summary": summary,
        "report_template_key": session.get("reportTemplateKey") or "default",
        "extracted_metadata": {
            "status": "processing",
            "generated_by": "ai-engine",
            "job_id": payload["job"]["id"],
            "job_type": payload["job"]["jobType"],
            "generated_at": utc_now().isoformat(),
            "source_capture_ids": source_capture_ids,
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


# --- Session report synthesis + treatment extraction (Pro, single-pass) ------------------------
#
# The keystone of the Pro capture-intelligence wave. ONE structured call emits the per-visit report
# sections AND the performed treatments[] together (the A↔B contract). It is dispatched by the
# backend (the revived `session_organize` job) only for Pro tenants with a gateway, AFTER the
# deterministic baseline already wrote a report — so synthesis is a refinement that never blocks the
# capture. Gateway-less / malformed → a SKIP sentinel; the backend keeps the deterministic baseline
# and treatments stay empty (Basic + gateway-less run zero AI and must never break).

# A malformed/refused synthesis is retried this many times (Celery re-dispatch) before falling back to
# the deterministic baseline skip sentinel — bounded so a persistently-bad input still settles (S-F3).
SYNTHESIS_MALFORMED_RETRY_LIMIT = 2


def reconcile_memo_decisions(prior: Any, candidate_keys: list[str]) -> dict[str, Any] | None:
    """Reuse the prior reconcile decisions when the candidate-flag set is byte-unchanged (G6).

    `prior` is the context's `priorSafetyReconciliation` = {candidateKeys, decisions} from the previous
    synthesis of this session. Returns the stored decisions to reuse (skip the LLM call) when the sorted
    candidate keys match exactly; None to run a fresh reconcile.
    """
    if not isinstance(prior, dict):
        return None
    prior_keys = prior.get("candidateKeys")
    prior_decisions = prior.get("decisions")
    if not (isinstance(prior_keys, list) and isinstance(prior_decisions, dict)):
        return None
    return prior_decisions if sorted(str(key) for key in prior_keys) == sorted(candidate_keys) else None


def report_synthesis_json_schema() -> dict[str, Any]:
    """JSON schema for the single-pass synthesis structured output (the A↔B contract)."""
    block = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["paragraph", "image"]},
            "text": {"type": ["string", "null"]},
            "captureId": {"type": ["string", "null"]},
            "caption": {"type": ["string", "null"]},
        },
        "required": ["type"],
    }
    section = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "blocks": {"type": "array", "items": block},
        },
        "required": ["id", "title", "blocks"],
    }
    treatment = {
        "type": "object",
        "properties": {
            "area": {"type": "string"},
            "areaCode": {"type": ["string", "null"]},
            "product": {"type": "string"},
            "brand": {"type": ["string", "null"]},
            "quantity": {"type": ["number", "null"]},
            "unit": {"type": ["string", "null"]},
            "quantityText": {"type": ["string", "null"]},
            "lot": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
            "status": {"type": "string", "enum": ["performed", "planned", "uncertain"]},
            "sourceCaptureIds": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": ["string", "null"]},
            "carriedForward": {"type": "boolean"},
            "supersedesCaptureId": {"type": ["string", "null"]},
            "priorKey": {"type": ["string", "null"]},
            "attributes": {"type": "object"},
        },
        "required": ["area", "product", "confidence", "sourceCaptureIds", "carriedForward"],
    }
    uncertainty = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "enum": [
                    "ambiguous_correction", "missing_lot", "low_confidence",
                    "carried_forward_dose", "ambiguous_quantity", "other",
                ],
            },
            "text": {"type": "string"},
        },
        "required": ["code", "text"],
    }
    aftercare_selection = {
        "type": "object",
        "properties": {
            "templateId": {"type": "string"},
            "status": {"type": "string", "enum": ["applies", "conflicts", "superseded"]},
            "note": {"type": ["string", "null"]},
        },
        "required": ["templateId", "status"],
    }
    safety_flag = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["allergy", "contraindication", "consent"]},
            "text": {"type": "string"},
            "sourceCaptureIds": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "text"],
    }
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "language": {"type": "string", "enum": ["fa", "en", "mixed"]},
            "sections": {"type": "array", "items": section},
            "treatments": {"type": "array", "items": treatment},
            "uncertainties": {"type": "array", "items": uncertainty},
            "aftercareSelections": {"type": "array", "items": aftercare_selection},
            "safetyFlags": {"type": "array", "items": safety_flag},
        },
        "required": [
            "summary",
            "language",
            "sections",
            "treatments",
            "uncertainties",
            "aftercareSelections",
            "safetyFlags",
        ],
    }


def synthesize_session_report(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run the single-pass report synthesis through the gateway; None to fall back to baseline.

    Network/gateway EXCEPTIONS propagate (retryable). Empty/malformed CONTENT returns None so the
    caller emits the skip sentinel and the deterministic baseline stands (never breaks).
    """
    processing_context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    captures = flattened_processing_captures(processing_context)
    source_capture_ids = [capture_id(capture) for capture in captures if capture_id(capture)]
    ai_models = payload.get("aiModels") if isinstance(payload.get("aiModels"), dict) else None
    model = resolve_model("report_synthesis", ai_models)
    effort = resolve_reasoning_effort(
        "report_synthesis", ai_models, default=(settings.report_synthesis_reasoning_effort or None)
    )
    # Correction-triggered escalation (§3.1): a fix-at-source / treatment-overlay / assignment correction
    # sets `escalate: true` — a correction is proof the cheap tier failed on this input, so re-run on the
    # strongest configured tier. No-op when no escalation tier is configured (falls back to the base pair).
    if escalation_requested(payload):
        model, effort = retry_tier("report_synthesis", ai_models, model=model, effort=effort)
    client = gateway_client("report_synthesis")
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": report_synthesis_prompt(processing_context)}],
        # Schema-enforced JSON; NO temperature (GPT-5-class rejects it — stability from low effort).
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "session_synthesis_output", "schema": report_synthesis_json_schema()},
        },
    }
    if effort:
        request["extra_body"] = {"reasoning_effort": effort}
    response = client.chat.completions.create(**request)
    return parse_session_synthesis_output(
        response.choices[0].message.content or "",
        source_capture_ids=source_capture_ids,
        report_language=processing_context.get("reportLanguage") if isinstance(processing_context, dict) else None,
    )


def session_synthesis_skip_output(reason: str) -> dict[str, Any]:
    """Sentinel telling the backend synthesis did not run — keep the deterministic baseline."""
    return {
        "status": "skipped",
        "synthesis_skipped": True,
        "reason": reason,
        "generated_by": "ai-engine",
        "generated_at": utc_now().isoformat(),
    }


def completed_session_synthesis_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the worker completion envelope for a Pro session synthesis job.

    Wraps the A↔B synthesis output as `structured_report` plus the top-level summary +
    extracted_metadata the backend's `complete_session_worker_job` expects. Gateway-less or
    malformed → a skip sentinel so the deterministic baseline is preserved (treatments empty).
    """
    job = payload["job"]
    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    report_template = payload.get("reportTemplate") if isinstance(payload.get("reportTemplate"), dict) else {}
    if not transcription_is_configured():
        return session_synthesis_skip_output("gateway_not_configured")
    synthesis = synthesize_session_report(payload)
    if synthesis is None:
        return session_synthesis_skip_output("empty_or_malformed_synthesis")

    source_capture_ids = [reference["captureId"] for reference in synthesis["sourceReferences"] if reference.get("captureId")]
    extracted_metadata = {
        "status": "completed",
        "generated_by": "ai-engine",
        "promptVersion": REPORT_SYNTHESIS_PROMPT_VERSION,
        "job_id": job["id"],
        "job_type": job["jobType"],
        "generated_at": utc_now().isoformat(),
        "source_capture_ids": source_capture_ids,
        # BCP-47 stamp of the report language the extracted display strings were generated in (schema-v2).
        "lang": synthesis.get("lang"),
        # The backend post-processes treatments (validate/supersede/carry-forward) before storing.
        "treatments": synthesis["treatments"],
        "uncertainties": synthesis["uncertainties"],
        "uncertainty_reasons": synthesis.get("uncertaintyReasons", []),
        # The model's intelligent aftercare matches (which clinic protocols apply + dictation conflicts).
        "aftercare_selections": synthesis.get("aftercareSelections", []),
        # Session-level safety flags (allergy/contraindication/consent) detected from the captures.
        # Auto-kept (opt-out): the clinician rejects a wrong one; the backend persists the rest to the
        # patient so they surface cross-visit. Clinical text stays in the report language (never translated).
        "safety_flags": synthesis.get("safetyFlags", []),
        "processing_status": {
            "state": "complete",
            "label": "Complete",
            "stage": "complete",
            "source": "ai-engine",
            "updated_at": utc_now().isoformat(),
        },
    }
    # Cross-visit SAFETY RECONCILE (selection-only): dedup-by-meaning / supersede this visit's newly
    # detected flags against the patient's existing ones. Best-effort + gated — a failure or sparse set
    # leaves the deterministic union (the safety floor) intact; never breaks the synthesis.
    context = payload.get("sessionProcessingContext") if isinstance(payload.get("sessionProcessingContext"), dict) else {}
    existing_flags = context.get("patientSafetyFlags") if isinstance(context.get("patientSafetyFlags"), list) else []
    new_flags = [
        {"key": _safety_flag_key(flag.get("kind"), flag.get("text")), "kind": flag.get("kind"), "text": flag.get("text")}
        for flag in extracted_metadata["safety_flags"]
        if isinstance(flag, dict) and flag.get("kind") and flag.get("text")
    ]
    if len(existing_flags) + len(new_flags) >= 2:
        # (G6) Memoize the reconcile by candidate-flag-set key. Synthesis re-runs on every settle
        # (queue-collapse) — often for a capture change that does NOT touch safety flags — so the SAME
        # candidate set is reconciled again minutes apart. When the set is byte-unchanged from the prior
        # synthesis of this session, reuse the stored decisions and SKIP the LLM call entirely (a saving
        # that beats any prompt-cache win at this pass's ~364-token size). The candidate-set key is
        # stamped into extracted_metadata so the NEXT run can compare against it.
        candidate_keys = sorted({str(f.get("key")) for f in [*existing_flags, *new_flags] if isinstance(f, dict) and f.get("key")})
        extracted_metadata["safety_reconciliation_keys"] = candidate_keys
        memo = reconcile_memo_decisions(context.get("priorSafetyReconciliation"), candidate_keys)
        if memo is not None:
            # Unchanged candidate set → reuse the memoized decisions, no gateway call.
            extracted_metadata["safety_reconciliation"] = memo
        else:
            try:
                decisions = reconcile_safety_flags(
                    {"existingFlags": existing_flags, "newFlags": new_flags, "aiModels": payload.get("aiModels")}
                )
                if decisions:
                    extracted_metadata["safety_reconciliation"] = decisions
            except Exception:  # noqa: BLE001 — reconcile is additive; never fail the synthesis on it
                pass
    return {
        "status": "completed",
        "summary": synthesis["summary"],
        "structured_report": synthesis,
        "extracted_metadata": extracted_metadata,
        "report_template_key": report_template.get("key") or session.get("reportTemplateKey") or "default",
        "generated_by": "ai-engine",
        "job_id": job["id"],
        "generated_at": utc_now().isoformat(),
    }


def run_session_processing_job(job_id: str, *, celery_task_id: str | None, retry_count: int) -> None:
    """Run a session processing job through the backend API contract."""
    client = BackendClient()
    payload = client.start_job(job_id, celery_task_id=celery_task_id, retry_count=retry_count)
    job = payload["job"]
    if job.get("status") == "succeeded":
        return

    # Pro single-pass report synthesis + treatment extraction (the revived `session_organize`). The
    # backend sets `reportSynthesis` only for Pro tenants with a gateway, AFTER the deterministic
    # baseline already wrote a report. Gateway-less / malformed yields a skip sentinel that the
    # backend treats as "keep the deterministic baseline" (treatments empty) — never breaks.
    if payload.get("reportSynthesis"):
        output = completed_session_synthesis_output(payload)
        # (S-F3) A malformed/refused completion is exactly as transient as a network error — one bad
        # response should not permanently downgrade a Pro visit to no-treatments. Retry a bounded number
        # of times (raise → Celery re-dispatch), THEN fall back to the skip sentinel so the deterministic
        # baseline stands. A gateway-not-configured skip is NOT transient and is never retried.
        if (
            output.get("synthesis_skipped")
            and output.get("reason") == "empty_or_malformed_synthesis"
            and retry_count < SYNTHESIS_MALFORMED_RETRY_LIMIT
        ):
            raise RuntimeError("empty_or_malformed_synthesis: retrying before falling back to the baseline")
        client.complete_job(job_id, output_key="session_outputs", output=output)
        return

    # Legacy deterministic progressive stages (placeholder pipeline + recovery of pre-synthesis jobs).
    for stage in ("transcripts", "report", "findings", "summary"):
        client.progress_job(job_id, output_key="session_progress", output=session_progress_output(payload, stage), stage=stage)
        sleep(settings.mock_stage_delay_seconds)

    client.complete_job(job_id, output_key="session_outputs", output=completed_session_output(payload))
