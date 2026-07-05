from datetime import date, datetime, timezone
from typing import Any, Literal, NotRequired, TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import Artifact, Capture, CaptureStatus, CaptureType, Patient, Session
from app.services.reporting import (
    REPORT_MODEL_VERSION,
    empty_report_model,
    get_report_template,
    patient_information_from_assignment,
    report_template_payload,
)
from app.services.treatment_overlay import carried_forward_key, stamp_treatment_keys, stored_treatments

SESSION_PROCESSING_INPUT_VERSION = "2026-05-21.session-processing-input.v1"
SESSION_PROCESSING_OUTPUT_VERSION = "2026-05-21.session-processing-output.v1"
# Pro single-pass report synthesis + treatment extraction output (extends the processing output with
# treatments[] and the fixed-id sections). Emitted by the AI engine, post-processed below.
# v2 (2026-07-05): treatments carry areaCode/priorKey, envelopes carry a `lang` stamp. MUST stay
# byte-identical to the ai_engine copy (`contracts/synthesis.py`) — worker.py gates `is_synthesis` on it.
SESSION_SYNTHESIS_OUTPUT_VERSION = "2026-07-05.session-synthesis-output.v2"
TREATMENT_PERFORMED_SECTION_ID = "treatment-performed"

# Treatment post-processing thresholds (deterministic, clinical-safety guardrails over the LLM
# output). A field that writes doses must surface uncertainty rather than silently commit.
LOW_CONFIDENCE_TREATMENT_THRESHOLD = 0.5
CARRY_FORWARD_MAX_CONFIDENCE = 0.6
# Bound the prior-visit treatments we feed back in (for "same as last time"), keeping the context small.
MAX_PRIOR_VISIT_TREATMENTS = 12


def capture_is_out_of_context(capture: Capture) -> bool:
    """Whether a capture is flagged out-of-context and not staff-overridden.

    Out-of-context captures are kept but excluded from the (Pro) live report; a staff
    "Mark relevant" override clears the marker so the capture flows back into the report.
    """
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    marker = metadata.get("out_of_context")
    if not isinstance(marker, dict):
        return False
    if marker.get("overridden_by_staff") is True:
        return False
    return marker.get("present") is True


class SessionProcessingCaptureInput(TypedDict, total=False):
    """Capture-level input available to session processing."""

    captureId: str
    type: Literal["audio", "photo", "note"]
    status: str
    capturedAt: str | None
    artifactId: str | None
    artifactUrl: str | None
    s3Url: str | None
    transcript: str | None
    caption: str | None
    rawText: str | None
    detectedPatient: dict[str, Any] | None
    patientInformation: dict[str, Any] | None


class SessionProcessingInput(TypedDict):
    """Stable input contract for future real session AI processing."""

    schemaVersion: str
    rawReportTemplate: dict[str, str]
    clinic: dict[str, Any]
    assignedPatient: dict[str, Any] | None
    patientSummarizedHistory: str | None
    captures: dict[str, list[SessionProcessingCaptureInput]]
    session: dict[str, Any]


class SessionReportBlockOutput(TypedDict, total=False):
    """Body-level AI report block output."""

    type: Literal["paragraph", "image", "artifact"]
    text: NotRequired[str]
    artifactId: NotRequired[str]
    captureId: NotRequired[str]
    caption: NotRequired[str]


class SessionReportSectionOutput(TypedDict):
    """Body-level AI report section output."""

    id: str
    title: str
    blocks: list[SessionReportBlockOutput]


class SessionProcessingOutput(TypedDict, total=False):
    """Stable output contract returned by session processing.

    This contract intentionally contains body-level report content only. Clinic
    and patient information are rendered from backend-owned template/session
    context, not from generated output.
    """

    schemaVersion: str
    summary: str | None
    sections: list[SessionReportSectionOutput]
    artifactReferences: list[dict[str, Any]]
    sourceReferences: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    generatedBy: str
    generatedAt: str | None


def build_session_processing_input(db: DbSession, session: Session) -> SessionProcessingInput:
    """Build the session-processing input context for the AI boundary."""
    template = get_report_template(session.report_template_key)
    captures = [
        capture
        for capture in db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.created_at)
        ).scalars()
        # Out-of-context captures are kept but excluded from the synthesized report.
        if not capture_is_out_of_context(capture)
    ]
    artifact_ids = [capture.source_artifact_id for capture in captures if capture.source_artifact_id]
    artifacts_by_id = {
        artifact.id: artifact
        for artifact in db.execute(
            select(Artifact).where(Artifact.tenant_id == session.tenant_id, Artifact.id.in_(artifact_ids))
        ).scalars()
    } if artifact_ids else {}

    capture_inputs = [_capture_input(capture, artifacts_by_id.get(capture.source_artifact_id)) for capture in captures]
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None

    # Vertical-aware prompt framing (label + optional vocabulary); the worker falls back to a neutral
    # "clinic" when absent — synthesis prompts never hardcode a vertical. Imported locally to avoid an
    # import cycle (caseload/verticals sit above this module).
    from app.services.caseload import tenant_vertical
    from app.services.verticals import domain_descriptor

    current_capture_ids = [str(capture.id) for capture in captures]
    prior_report_model = session.report_model if isinstance(session.report_model, dict) else None
    changeset = _session_synthesis_changeset(current_capture_ids, synthesized_capture_ids(session))
    # The patient's EXISTING (cross-visit) safety flags, so the synthesis job can reconcile this visit's
    # newly-detected flags against them (dedup-by-meaning / supersede) — selection-only, keys out.
    from app.models import Patient
    from app.services.patient_safety import patient_safety_flags_payload

    _patient = db.get(Patient, session.patient_id) if session.patient_id else None
    existing_safety_flags = patient_safety_flags_payload(_patient) if _patient is not None else []

    return {
        "schemaVersion": SESSION_PROCESSING_INPUT_VERSION,
        "rawReportTemplate": report_template_payload(session.report_template_key),
        "domain": domain_descriptor(tenant_vertical(db, session.tenant_id)),
        "clinic": {
            "name": template.clinic_name,
            "information": list(template.clinic_information),
        },
        "assignedPatient": assigned_patient,
        "patientSummarizedHistory": _patient_summarized_history(db, session),
        "captures": {
            "audio": [capture for capture in capture_inputs if capture["type"] == CaptureType.audio.value],
            "photos": [capture for capture in capture_inputs if capture["type"] == CaptureType.photo.value],
            "text": [capture for capture in capture_inputs if capture["type"] == CaptureType.note.value],
        },
        # Stable targeted update: the prior report draft + a changeset (capture ids added/removed
        # since the last synthesis) let the synthesizer recompute only what changed.
        "priorReportModel": prior_report_model,
        "changeset": changeset,
        # Bounded prior-visit treatments enable explicit "same as last time" carry-forward. Each row
        # carries its stable `treatmentKey`, which the model may echo as `priorKey` (a re-bind hint).
        "referencePriorVisitTreatments": bounded_prior_visit_treatments(db, session),
        # This session's PRIOR synthesis treatments (with keys), so a within-session re-synthesis can
        # echo priorKey and keep overlay bindings stable across the update.
        "priorDraftTreatments": stored_treatments(session),
        # Patient's existing cross-visit safety flags (for the synthesis job's safety-reconcile pass).
        "patientSafetyFlags": existing_safety_flags,
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "metadata": session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {},
            "createdAt": _iso(session.created_at),
            "updatedAt": _iso(session.updated_at),
            "capturedAt": _iso(session.captured_at),
        },
    }


def deterministic_mock_session_processing_output(
    processing_input: SessionProcessingInput,
    *,
    generated_at: str | None = None,
) -> SessionProcessingOutput:
    """Return deterministic mock body output for local/backend-only processing."""
    now = generated_at or datetime.now(timezone.utc).isoformat()
    captures = _flatten_capture_groups(processing_input.get("captures", {}))
    source_capture_ids = [capture["captureId"] for capture in captures if capture.get("captureId")]
    paragraphs = _body_paragraphs_from_input(processing_input, captures)
    image_captures = [capture for capture in captures if capture.get("type") == CaptureType.photo.value]
    blocks: list[SessionReportBlockOutput] = [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs]
    for capture in image_captures:
        artifact_id = capture.get("artifactId")
        if artifact_id:
            blocks.append(
                {
                    "type": "image",
                    "artifactId": artifact_id,
                    "captureId": capture["captureId"],
                    "caption": capture.get("caption") or "Source image",
                }
            )

    return {
        "schemaVersion": SESSION_PROCESSING_OUTPUT_VERSION,
        "summary": _summary_from_paragraphs(paragraphs),
        "sections": [{"id": "clinical-report", "title": "Clinical report", "blocks": blocks}],
        "artifactReferences": [
            {
                "type": "artifact",
                "artifactId": capture.get("artifactId"),
                "captureId": capture.get("captureId"),
                "url": capture.get("artifactUrl"),
                "s3Url": capture.get("s3Url"),
            }
            for capture in captures
            if capture.get("artifactId")
        ],
        "sourceReferences": [{"type": "capture", "captureId": capture_id} for capture_id in source_capture_ids],
        "findings": _mock_findings(captures),
        "generatedBy": "mock-session-processing",
        "generatedAt": now,
    }


def report_model_from_session_processing_output(
    *,
    title: str | None,
    template_key: str | None,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Convert session-processing output into the internal structured report model."""
    sections = _valid_sections(output.get("sections"))
    if not sections:
        return empty_report_model(title=title, template_key=template_key)
    return {
        "schemaVersion": REPORT_MODEL_VERSION,
        "templateKey": get_report_template(template_key).key,
        "title": title or "Untitled session",
        "sections": sections,
        "findings": _valid_dict_list(output.get("findings")),
        "sourceReferences": _valid_references(output.get("sourceReferences")),
        "artifactReferences": _valid_references(output.get("artifactReferences")),
        "summary": output.get("summary") if isinstance(output.get("summary"), str) else None,
        "generatedAt": output.get("generatedAt") if isinstance(output.get("generatedAt"), str) else None,
        "generatedBy": output.get("generatedBy") if isinstance(output.get("generatedBy"), str) else None,
    }


def session_processing_output_from_legacy_report(output: dict[str, Any], *, generated_at: str) -> SessionProcessingOutput:
    """Wrap legacy markdown session output in the structured output contract."""
    report = output.get("report")
    body = report if isinstance(report, str) and report.strip() else "Mock clinical body generated from session captures."
    paragraphs = [paragraph.strip() for paragraph in body.split("\n\n") if paragraph.strip()]
    extracted_metadata = output.get("extracted_metadata") if isinstance(output.get("extracted_metadata"), dict) else {}
    source_capture_ids = extracted_metadata.get("source_capture_ids") if isinstance(extracted_metadata.get("source_capture_ids"), list) else []
    return {
        "schemaVersion": SESSION_PROCESSING_OUTPUT_VERSION,
        "summary": output.get("summary") if isinstance(output.get("summary"), str) else _summary_from_paragraphs(paragraphs),
        "sections": [
            {
                "id": "clinical-report",
                "title": "Clinical report",
                "blocks": [{"type": "paragraph", "text": paragraph} for paragraph in paragraphs],
            }
        ],
        "sourceReferences": [
            {"type": "capture", "captureId": capture_id}
            for capture_id in source_capture_ids
            if isinstance(capture_id, str)
        ],
        "artifactReferences": [],
        "findings": _valid_dict_list(extracted_metadata.get("findings")),
        "generatedBy": output.get("generated_by") if isinstance(output.get("generated_by"), str) else "mock-ai-engine",
        "generatedAt": output.get("generated_at") if isinstance(output.get("generated_at"), str) else generated_at,
    }


# --- Pro report synthesis: input context helpers + treatment post-processing -------------------
#
# These are pure functions (no DB except the bounded prior-visit query) so the clinical-safety
# guardrails over the LLM's treatments[] are unit-tested deterministically. The LLM emits the
# signals (supersedesCaptureId, carriedForward, confidence, uncertainties); this layer VALIDATES
# them against the real session captures, applies the supersede/carry-forward semantics, and surfaces
# anything a clinician must confirm — never silently overwriting a dose.


def synthesized_capture_ids(session: Session) -> list[str]:
    """The reportable capture ids the current synthesis was generated from (empty if none yet)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    record = metadata.get("report_synthesis")
    if isinstance(record, dict) and isinstance(record.get("captureIds"), list):
        return [str(value) for value in record["captureIds"] if isinstance(value, str)]
    return []


def _session_synthesis_changeset(current_ids: list[str], last_ids: list[str]) -> dict[str, list[str]]:
    """Capture ids added/removed since the last synthesis (drives the stable targeted update)."""
    current = list(dict.fromkeys(str(value) for value in current_ids))
    current_set = set(current)
    last = [str(value) for value in last_ids]
    last_set = set(last)
    return {
        "addedCaptureIds": [value for value in current if value not in last_set],
        "removedCaptureIds": [value for value in last if value not in current_set],
    }


def bounded_prior_visit_treatments(db: DbSession, session: Session) -> list[dict[str, Any]]:
    """Return the most recent OTHER visit's stored treatments for this patient (bounded).

    Feeds explicit "same as last time" carry-forward without dragging the whole history into the
    prompt. Empty when the visit has no assigned patient or no prior visit recorded treatments.
    """
    if session.patient_id is None:
        return []
    prior_sessions = db.execute(
        select(Session)
        .where(
            Session.tenant_id == session.tenant_id,
            Session.patient_id == session.patient_id,
            Session.id != session.id,
        )
        .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc())
    ).scalars()
    for prior in prior_sessions:
        metadata = prior.extracted_metadata if isinstance(prior.extracted_metadata, dict) else {}
        treatments = metadata.get("treatments")
        if isinstance(treatments, list) and treatments:
            return [treatment for treatment in treatments if isinstance(treatment, dict)][:MAX_PRIOR_VISIT_TREATMENTS]
    return []


def prior_visit_capture_ids(treatments: list[dict[str, Any]] | None) -> set[str]:
    """Capture ids cited by prior-visit treatments (allowed targets for carry-forward citations)."""
    ids: set[str] = set()
    for treatment in treatments or []:
        if not isinstance(treatment, dict):
            continue
        for capture_id in treatment.get("sourceCaptureIds") or []:
            if isinstance(capture_id, str):
                ids.add(capture_id)
    return ids


def _treatment_review_item(
    category: str, reason: str, product: str | None, source_capture_ids: list[str], key: str | None = None
) -> dict[str, Any]:
    """One human-confirmation item for treatment extraction (drives the existing needs-input surface)."""
    item: dict[str, Any] = {
        "category": category,
        "reason": reason,
        "product": product,
        "sourceCaptureIds": list(source_capture_ids or []),
    }
    if key is not None:
        item["key"] = key  # stable id so a carried-forward dose can be confirmed (Q3)
    return item


def process_synthesized_treatments(
    treatments: list[dict[str, Any]] | None,
    *,
    valid_capture_ids: list[str] | set[str],
    prior_visit_capture_ids: list[str] | set[str] | None = None,
    uncertainties: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate + finalize the LLM's treatments[] and collect items a clinician must confirm.

    Deterministic clinical-safety logic (canned-output unit-tested):
    - drop source/supersede capture ids that don't resolve to a real capture in this session;
    - a `supersedesCaptureId` resolving to a known capture is a clean correction (kept, auditable);
      one that does NOT resolve is an ambiguous correction → flagged, supersede cleared, BOTH kept;
    - `carriedForward` caps confidence and always raises a confirmation item;
    - low-confidence and missing-but-expected lot raise confirmation items;
    - synthesis-level `uncertainties[]` map straight to confirmation items.

    Returns `(treatments, review_items)`. Treatments are never silently dropped or overwritten.
    """
    valid = {str(value) for value in (valid_capture_ids or [])}
    prior = {str(value) for value in (prior_visit_capture_ids or [])}
    allowed = valid | prior
    processed: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for raw in treatments or []:
        if not isinstance(raw, dict):
            continue
        treatment = dict(raw)
        product = str(treatment.get("product") or treatment.get("area") or "treatment").strip() or "treatment"
        sources = treatment.get("sourceCaptureIds")
        treatment["sourceCaptureIds"] = (
            [str(value) for value in sources if isinstance(value, str) and str(value) in allowed]
            if isinstance(sources, list)
            else []
        )
        supersedes = treatment.get("supersedesCaptureId")
        if isinstance(supersedes, str) and supersedes in valid:
            treatment["supersedesCaptureId"] = supersedes  # clean, auditable correction
        elif supersedes:
            # The model flagged a correction but we can't resolve which capture it replaces — surface
            # for confirmation and keep BOTH statements rather than silently overwriting a dose.
            treatment["supersedesCaptureId"] = None
            review.append(
                _treatment_review_item(
                    "ambiguous",
                    f"Ambiguous correction for {product}: confirm whether it replaces an earlier entry.",
                    product,
                    treatment["sourceCaptureIds"],
                )
            )
        confidence = treatment.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) else 0.0
        if treatment.get("carriedForward") is True:
            treatment["confidence"] = min(confidence, CARRY_FORWARD_MAX_CONFIDENCE)
            review.append(
                _treatment_review_item(
                    "carried_forward",
                    f"{product} carried forward from a previous visit — confirm the dose.",
                    product,
                    treatment["sourceCaptureIds"],
                    key=carried_forward_key(treatment),
                )
            )
        else:
            treatment["confidence"] = confidence
            if confidence < LOW_CONFIDENCE_TREATMENT_THRESHOLD:
                review.append(
                    _treatment_review_item(
                        "low_confidence",
                        f"Low-confidence treatment: {product} — confirm.",
                        product,
                        treatment["sourceCaptureIds"],
                    )
                )
        attributes = treatment.get("attributes") if isinstance(treatment.get("attributes"), dict) else {}
        if attributes.get("lotExpected") is True and not treatment.get("lot"):
            review.append(_treatment_review_item("missing_lot", f"Missing lot number for {product}.", product, treatment["sourceCaptureIds"]))
        processed.append(treatment)
    for sentence in uncertainties or []:
        if isinstance(sentence, str) and sentence.strip():
            review.append(_treatment_review_item("ambiguous", sentence.strip(), None, []))
    return processed, review


def _treatment_performed_line(treatment: dict[str, Any]) -> str | None:
    """Render one treatment as a prose line (verbatim quantity/brand/lot, native script preserved)."""
    area = str(treatment.get("area") or "").strip()
    product = str(treatment.get("product") or "").strip()
    head = f"{area}: {product}" if area and product else (area or product)
    if not head:
        return None
    brand = str(treatment.get("brand") or "").strip()
    if brand:
        head = f"{head} ({brand})"
    amount = str(treatment.get("quantityText") or "").strip()
    if not amount:
        quantity = treatment.get("quantity")
        unit = str(treatment.get("unit") or "").strip()
        if isinstance(quantity, (int, float)) and not isinstance(quantity, bool):
            amount = f"{quantity:g} {unit}".strip()
    parts = [head] + ([amount] if amount else [])
    line = " — ".join(parts)
    lot = str(treatment.get("lot") or "").strip()
    if lot:
        line = f"{line} · lot {lot}"
    if treatment.get("carriedForward") is True:
        line = f"{line} (carried forward — confirm)"
    return line


def render_treatment_performed_blocks(treatments: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Render the treatment-performed section blocks FROM treatments[] (prose mirror of the store)."""
    blocks: list[dict[str, Any]] = []
    for treatment in treatments or []:
        if not isinstance(treatment, dict):
            continue
        line = _treatment_performed_line(treatment)
        if line:
            blocks.append({"type": "paragraph", "text": line})
    return blocks


def validate_synthesis_capture_ids(output: dict[str, Any], valid_capture_ids: list[str] | set[str]) -> dict[str, Any]:
    """Drop section image blocks / sourceReferences referencing captures not in this session.

    The renderer trusts model-provided capture ids, so unknown ones are dropped here before they
    reach the report model (a 404 image / phantom source otherwise).
    """
    valid = {str(value) for value in (valid_capture_ids or [])}
    sections: list[dict[str, Any]] = []
    for section in output.get("sections") or []:
        if not isinstance(section, dict):
            continue
        blocks = []
        for block in section.get("blocks") or []:
            if isinstance(block, dict) and block.get("type") == "image":
                capture_id = block.get("captureId")
                if not (isinstance(capture_id, str) and capture_id in valid):
                    continue
            blocks.append(block)
        sections.append({**section, "blocks": blocks})
    references = output.get("sourceReferences")
    cleaned_references = (
        [
            reference
            for reference in references
            if isinstance(reference, dict)
            and (reference.get("type") != "capture" or (isinstance(reference.get("captureId"), str) and reference["captureId"] in valid))
        ]
        if isinstance(references, list)
        else output.get("sourceReferences")
    )
    return {**output, "sections": sections, "sourceReferences": cleaned_references}


def set_treatment_performed_section(output: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace the treatment-performed section's blocks (rendered from treatments[])."""
    sections = []
    for section in output.get("sections") or []:
        if isinstance(section, dict) and section.get("id") == TREATMENT_PERFORMED_SECTION_ID:
            sections.append({**section, "blocks": blocks})
        else:
            sections.append(section)
    return {**output, "sections": sections}


def finalize_session_synthesis_output(
    output: dict[str, Any],
    *,
    valid_capture_ids: list[str] | set[str],
    prior_visit_capture_ids: list[str] | set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate captureIds, finalize treatments, and re-render treatment-performed FROM treatments[].

    Returns `(finalized_output, treatments, review_items)` for the backend to persist.
    """
    validated = validate_synthesis_capture_ids(output, valid_capture_ids)
    treatments, review_items = process_synthesized_treatments(
        validated.get("treatments") if isinstance(validated.get("treatments"), list) else [],
        valid_capture_ids=valid_capture_ids,
        prior_visit_capture_ids=prior_visit_capture_ids,
        uncertainties=validated.get("uncertainties") if isinstance(validated.get("uncertainties"), list) else None,
    )
    # Stamp the deterministic content-anchored treatment_key on each row (schema-v2 §4.1) so the
    # user-authored treatment overlay can bind to a stable identity that survives re-synthesis.
    treatments = stamp_treatment_keys(treatments)
    blocks = render_treatment_performed_blocks(treatments)
    finalized = set_treatment_performed_section({**validated, "treatments": treatments}, blocks)
    return finalized, treatments, review_items


def _capture_input(capture: Capture, artifact: Artifact | None) -> SessionProcessingCaptureInput:
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    transcript = _generated_text(metadata.get("transcript"))
    detected_patient = _detected_patient(metadata.get("transcript"))
    patient_information = _patient_information(metadata.get("transcript"))
    caption = _generated_text(metadata.get("caption")) or _generated_text(metadata.get("ocr"))
    # Notes are a pure passthrough (decoration removed): the synthesizer reads the raw captured text.
    raw_text = str(metadata.get("detail")).strip() if metadata.get("detail") else None
    return {
        "captureId": str(capture.id),
        "type": capture.capture_type.value,
        "status": capture.status.value,
        "capturedAt": _iso(capture.captured_at),
        "artifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
        "artifactUrl": f"/api/v1/captures/{capture.id}/file-content" if capture.source_artifact_id else None,
        "s3Url": _s3_url(artifact),
        "transcript": transcript if capture.capture_type == CaptureType.audio else None,
        "detectedPatient": detected_patient if capture.capture_type == CaptureType.audio else None,
        "patientInformation": patient_information if capture.capture_type == CaptureType.audio else None,
        "caption": caption if capture.capture_type == CaptureType.photo else None,
        "rawText": raw_text if capture.capture_type == CaptureType.note else None,
    }


def _patient_summarized_history(db: DbSession, session: Session) -> str | None:
    if session.patient_id is None:
        return None
    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        return None
    return patient.notes.strip() if isinstance(patient.notes, str) and patient.notes.strip() else None


def _generated_text(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"].strip()
    if isinstance(value, str):
        return value.strip()
    return None


def _detected_patient(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("detected_patient"), dict):
        return value["detected_patient"]
    return None


def _patient_information(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and isinstance(value.get("patient_information"), dict):
        return value["patient_information"]
    return None


def _s3_url(artifact: Artifact | None) -> str | None:
    if artifact is None:
        return None
    return f"s3://{artifact.bucket}/{artifact.object_key}"


def _body_paragraphs_from_input(
    processing_input: SessionProcessingInput,
    captures: list[SessionProcessingCaptureInput],
) -> list[str]:
    paragraphs: list[str] = []
    if processing_input.get("patientSummarizedHistory"):
        paragraphs.append(f"Known patient history summary: {processing_input['patientSummarizedHistory']}")

    audio = [capture for capture in captures if capture.get("transcript")]
    photos = [capture for capture in captures if capture.get("caption")]
    notes = [capture for capture in captures if capture.get("rawText")]
    if audio:
        paragraphs.append("Audio notes: " + " ".join(str(capture["transcript"]) for capture in audio))
    if notes:
        paragraphs.append("Written notes: " + " ".join(str(capture["rawText"]) for capture in notes))
    if photos:
        paragraphs.append("Photo observations: " + " ".join(str(capture["caption"]) for capture in photos))
    if not paragraphs:
        paragraphs.append("Mock clinical body generated from the available session context.")
    return paragraphs


def _summary_from_paragraphs(paragraphs: list[str]) -> str:
    return " ".join(paragraphs)[:240] if paragraphs else "Mock session summary generated from session context."


def _mock_findings(captures: list[SessionProcessingCaptureInput]) -> list[dict[str, Any]]:
    source_capture_ids = [capture["captureId"] for capture in captures if capture.get("captureId")]
    capture_types = sorted({str(capture.get("type")) for capture in captures if capture.get("type")})
    return [
        {
            "id": "source_capture_count",
            "label": "Source captures",
            "value": str(len(source_capture_ids)),
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
        {
            "id": "source_mix",
            "label": "Source mix",
            "value": ", ".join(capture_types) or "none",
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]


def _valid_sections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, Any]] = []
    for section in value:
        if not isinstance(section, dict) or not isinstance(section.get("id"), str):
            continue
        blocks = _valid_blocks(section.get("blocks"))
        sections.append(
            {
                "id": section["id"],
                "title": section.get("title") if isinstance(section.get("title"), str) else "Clinical report",
                "blocks": blocks,
            }
        )
    return sections


def _valid_blocks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    blocks: list[dict[str, Any]] = []
    for block in value:
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            continue
        block_type = block["type"]
        if block_type == "paragraph" and isinstance(block.get("text"), str):
            blocks.append({"type": "paragraph", "text": block["text"]})
        elif block_type in {"image", "artifact"} and (isinstance(block.get("artifactId"), str) or isinstance(block.get("captureId"), str)):
            # Synthesis emits captureId-only image blocks (the renderer resolves them to the file
            # endpoint); the legacy deterministic path emits artifactId — accept either.
            blocks.append(
                {
                    key: block[key]
                    for key in ("type", "artifactId", "captureId", "caption")
                    if isinstance(block.get(key), str)
                }
            )
    return blocks


def _valid_references(value: Any) -> list[dict[str, Any]]:
    return _valid_dict_list(value)


def _valid_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _flatten_capture_groups(captures: dict[str, Any]) -> list[SessionProcessingCaptureInput]:
    flattened: list[SessionProcessingCaptureInput] = []
    for group in ("audio", "photos", "text"):
        values = captures.get(group)
        if isinstance(values, list):
            flattened.extend(capture for capture in values if isinstance(capture, dict))
    return flattened


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None
