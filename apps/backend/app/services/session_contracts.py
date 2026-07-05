import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import (
    AiJob,
    AiJobStatus,
    AiJobType,
    CaptureType,
    OrganizationSource,
    Session,
    SessionStatus,
)
from app.services.reporting import (
    DEFAULT_REPORT_TEMPLATE_KEY,
    structured_report_from_markdown_body,
)
from app.services.treatment_overlay import overlay_satisfied_carry_forward_keys

SESSION_CONTRACT_VERSION = "2026-05-19.phase2.1"


def session_is_complete(session: Session) -> bool:
    """Whether a session is auto-"complete" (replaces the manual "verified" gate).

    Complete = captures processed (not mid-processing), a patient is assigned, a report has been
    generated, and that report is current (not stale) for the latest capture. Adding/editing a
    capture marks the report stale and flips the session back to processing, so it naturally drops
    to incomplete until the deterministic report regenerates.
    """
    if session.patient_id is None or not session.generated_report:
        return False
    if session.status == SessionStatus.processing:
        return False
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    if metadata.get("generated_output_stale"):
        return False
    # Q3: an unconfirmed carried-forward DOSE must NOT let the report read "Complete" — the doctor
    # confirms the carried dose first (redesign-pro-report §5). Other review items (low-confidence,
    # ambiguous, missing-lot) stay non-blocking. Confirmation is recorded per area|product key.
    review = metadata.get("treatment_review")
    # A carried-forward dose is confirmed either explicitly (confirmed_carried_forward) OR implicitly by
    # a human overlay dose edit on that row — the edit IS the confirmation, so the row stops asking
    # "confirm dose" (AES-1101 Q4 auto-confirm collapse).
    confirmed = set(metadata.get("confirmed_carried_forward") or []) | overlay_satisfied_carry_forward_keys(session)
    if isinstance(review, list) and any(
        isinstance(item, dict)
        and item.get("category") == "carried_forward"
        and item.get("key") not in confirmed
        for item in review
    ):
        return False
    return True


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _metadata(session: Session) -> dict[str, Any]:
    return session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}


def _capture_count(metadata: dict[str, Any]) -> int:
    value = metadata.get("capture_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _report_body(session: Session, metadata: dict[str, Any]) -> str:
    progressive_report = metadata.get("progressive_report")
    if isinstance(progressive_report, dict) and isinstance(progressive_report.get("body"), str):
        return progressive_report["body"]
    if session.generated_report:
        return session.generated_report
    count = _capture_count(metadata)
    if count:
        return (
            "# Draft report\n\n"
            f"- {count} source capture{'s' if count != 1 else ''} attached.\n"
            "- Generate a structured report when you are ready to organize the full session."
        )
    return (
        "# Draft report\n\n"
        "This report surface is ready before captures arrive."
    )


def _report_status(session: Session, metadata: dict[str, Any]) -> str:
    progressive_report = metadata.get("progressive_report")
    if isinstance(progressive_report, dict) and isinstance(progressive_report.get("status"), str):
        return progressive_report["status"]
    if session.generated_report:
        return "processed"
    if session.status == SessionStatus.processing:
        return "generating"
    return "partial"


def _normal_findings(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    findings = metadata.get("findings")
    if isinstance(findings, list):
        return [finding for finding in findings if isinstance(finding, dict)]

    clinical = metadata.get("clinical_metadata")
    clinical_metadata = clinical if isinstance(clinical, dict) else {}
    candidates = [
        ("visit_type", "Visit type", clinical_metadata.get("visit_type")),
        ("body_area", "Body area", clinical_metadata.get("body_area") or clinical_metadata.get("area")),
        ("product", "Product", clinical_metadata.get("product")),
    ]
    return [
        {
            "id": key,
            "label": label,
            "value": str(value),
            "category": "clinical",
            "confidence": None,
            "sourceCaptureIds": metadata.get("source_capture_ids") if isinstance(metadata.get("source_capture_ids"), list) else [],
            "status": "extracted",
        }
        for key, label, value in candidates
        if value
    ]


# Calm, persistent "AI is still organizing" copy, surfaced while a Pro report-synthesis job is in
# flight even though the deterministic baseline already reads complete. The frontend keys the
# organizing indicator off `stage == "organizing"` (with `state == "processing"`).
SYNTHESIS_ORGANIZING_STAGE = "organizing"
SYNTHESIS_ORGANIZING_LABEL = "Organizing with AI"
SYNTHESIS_ORGANIZING_DETAIL = "This report will update shortly."


def _has_inflight_synthesis_job(db: DbSession, session: Session) -> bool:
    """Whether a Pro report-synthesis job for this session is still going to run.

    A ``session_organize`` job that is queued/running — or failed-but-retryable (a transient gateway
    error the recovery loop will re-dispatch) — means AI is still organizing the report, even though
    the deterministic baseline already settled to "complete". Basic / gateway-less tenants dispatch
    no such job, so this is never true for them (the deterministic report is final there).
    """
    # Local import keeps session_contracts free of an ai_jobs import cycle (ai_jobs.reports ->
    # orchestration -> session_contracts). The retryable check is the canonical one.
    from app.services.ai_jobs.recovery import ai_job_retryable

    jobs = db.execute(
        select(AiJob).where(
            AiJob.tenant_id == session.tenant_id,
            AiJob.session_id == session.id,
            AiJob.capture_id.is_(None),
            AiJob.job_type == AiJobType.session_organize,
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.failed]),
        )
    ).scalars()
    for job in jobs:
        if job.status in (AiJobStatus.queued, AiJobStatus.running):
            return True
        if job.status == AiJobStatus.failed and ai_job_retryable(job):
            return True
    return False


def build_session_contracts(session: Session, db: DbSession | None = None) -> dict[str, Any]:
    """Build frontend-stable session contracts from the current session record.

    When ``db`` is provided and the deterministic baseline has settled (captures drained) while a Pro
    synthesis job is still in flight, the processing status is nudged to a calm working state
    (``state=processing``, ``stage=organizing``) so the frontend can keep the baseline visible and
    show a persistent "Organizing with AI" notice — never shown for Basic / gateway-less (no job).
    """
    metadata = _metadata(session)
    count = _capture_count(metadata)
    is_stale = bool(metadata.get("generated_output_stale"))
    generated_at = metadata.get("generated_at") if isinstance(metadata.get("generated_at"), str) else None
    source = session.organization_source.value if session.organization_source else OrganizationSource.none.value
    report_body = _report_body(session, metadata)
    report = {
        "schemaVersion": SESSION_CONTRACT_VERSION,
        "status": _report_status(session, metadata),
        "format": "markdown",
        "title": session.title or "Untitled session",
        "body": report_body,
        "sections": [{"id": "body", "title": "Clinical report", "body": report_body}],
        "source": source,
        "generatedAt": generated_at,
        "updatedAt": _iso(session.updated_at),
        "isStale": is_stale,
    }
    raw_summaries = metadata.get("summaries")
    stored_summaries = raw_summaries if isinstance(raw_summaries, dict) else {}
    short_summary = (
        stored_summaries.get("short")
        if isinstance(stored_summaries.get("short"), str)
        else session.generated_summary or session.summary or (
        f"{count} source capture{'s' if count != 1 else ''} attached." if count else "No captures have been added yet."
        )
    )
    summaries = {
        "schemaVersion": SESSION_CONTRACT_VERSION,
        "status": stored_summaries.get("status") if isinstance(stored_summaries.get("status"), str) else "partial" if is_stale or not session.generated_summary else "processed",
        "short": short_summary,
        "clinical": stored_summaries.get("clinical") if isinstance(stored_summaries.get("clinical"), str) else short_summary,
        "patientHistory": stored_summaries.get("patient_history") if isinstance(stored_summaries.get("patient_history"), str) else None,
        "source": stored_summaries.get("source") if isinstance(stored_summaries.get("source"), str) else source,
        "generatedAt": generated_at,
        "updatedAt": _iso(session.updated_at),
    }
    report_status = report["status"]
    processing_state = "failed" if session.status == SessionStatus.failed else "idle"
    if session.status == SessionStatus.processing:
        processing_state = "processing"
    elif report_status == "processed" and not is_stale:
        processing_state = "complete"
    elif report_status in {"partial", "generating"} or is_stale:
        processing_state = "queued" if count else "idle"
    raw_processing_status = metadata.get("processing_status")
    stored_processing_status = raw_processing_status if isinstance(raw_processing_status, dict) else {}
    default_label = {
        "idle": "Ready",
        "queued": "Queued",
        "processing": "Processing",
        "complete": "Complete",
        "failed": "Failed",
    }[processing_state]
    stage = stored_processing_status.get("stage")
    processing_status = {
        "schemaVersion": SESSION_CONTRACT_VERSION,
        "state": processing_state,
        "label": stored_processing_status.get("label") if isinstance(stored_processing_status.get("label"), str) else default_label,
        "detail": stored_processing_status.get("detail") if isinstance(stored_processing_status.get("detail"), str) else metadata.get("stale_reason") if isinstance(metadata.get("stale_reason"), str) else None,
        "stage": stage if isinstance(stage, str) else None,
        "progress": 1 if processing_state == "complete" else None,
        "canEdit": True,
        "canReview": True,
        "source": stored_processing_status.get("source") if isinstance(stored_processing_status.get("source"), str) else "mock-session-contract",
        "updatedAt": _iso(session.updated_at),
    }
    # Pro "organizing with AI": the deterministic baseline has settled (captures drained — not
    # actively `processing`/`failed`), but a synthesis job is still in flight (gateway slow/down or
    # queued). Surface a calm, persistent working state so the baseline stays readable AND the user
    # knows AI is still organizing. Gated off the in-flight job (Basic / gateway-less dispatch none),
    # and skipped while captures are still processing (that already shows its own working UI).
    if db is not None and processing_state not in {"processing", "failed"} and _has_inflight_synthesis_job(db, session):
        processing_status = {
            **processing_status,
            "state": "processing",
            "stage": SYNTHESIS_ORGANIZING_STAGE,
            "label": SYNTHESIS_ORGANIZING_LABEL,
            "detail": SYNTHESIS_ORGANIZING_DETAIL,
            "progress": None,
        }
    return {
        "contractVersion": SESSION_CONTRACT_VERSION,
        "report": report,
        "summaries": summaries,
        "findings": _normal_findings(metadata),
        "processingStatus": processing_status,
    }


def evolve_session_after_capture(
    session: Session,
    *,
    capture_type: CaptureType,
    captured_at: datetime,
    capture_id: uuid.UUID | None = None,
) -> None:
    """Apply deterministic mocked session evolution after a capture is attached."""
    metadata = _metadata(session)
    next_count = _capture_count(metadata) + 1
    capture_label = {
        CaptureType.audio: "audio capture",
        CaptureType.photo: "photo capture",
        CaptureType.note: "written note",
    }[capture_type]
    source_capture_ids = metadata.get("source_capture_ids")
    if not isinstance(source_capture_ids, list):
        source_capture_ids = []
    if capture_id is not None:
        source_capture_ids = [*source_capture_ids, str(capture_id)]

    # TODO(ai-integration): Replace this deterministic contract update with real progressive AI report/finding writes.
    summary = f"Draft with {next_count} source capture{'s' if next_count != 1 else ''}. Latest: {capture_label}."
    report_body = (
        "# Draft report\n\n"
        f"- {next_count} source capture{'s' if next_count != 1 else ''} attached.\n"
        f"- Latest source type: {capture_label}.\n"
        "- Generate a structured report when you are ready to organize the full session."
    )
    findings = [
        {
            "id": "capture_count",
            "label": "Source captures",
            "value": str(next_count),
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
        {
            "id": "latest_capture_type",
            "label": "Latest capture",
            "value": capture_label,
            "category": "session",
            "confidence": None,
            "sourceCaptureIds": source_capture_ids,
            "status": "observed",
        },
    ]
    session.summary = summary
    session.generated_summary = session.generated_summary or summary
    session.generated_report = report_body
    session.report_template_key = session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY
    session.report_model = structured_report_from_markdown_body(
        title=session.title,
        body=report_body,
        template_key=session.report_template_key,
        findings=findings,
        source_capture_ids=source_capture_ids,
        generated_at=captured_at.isoformat(),
    )
    session.extracted_metadata = {
        **metadata,
        "session_contract_version": SESSION_CONTRACT_VERSION,
        "capture_count": next_count,
        "source_capture_ids": source_capture_ids,
        "latest_capture_type": capture_type.value,
        "progressive_report": {
            "status": "partial",
            "format": "markdown",
            "body": report_body,
            "model": session.report_model,
            "source": "mock-session-contract",
            "updated_at": captured_at.isoformat(),
        },
        "summaries": {
            "status": "partial",
            "short": summary,
            "clinical": summary,
            "source": "mock-session-contract",
            "updated_at": captured_at.isoformat(),
        },
        "findings": findings,
        "processing_status": {
            "state": "queued",
            "source": "mock-session-contract",
            "updated_at": captured_at.isoformat(),
        },
        "generated_output_stale": True,
        "stale_reason": "A capture was added after the last processed session output.",
        "stale_at": captured_at.isoformat(),
    }
    if session.status in {SessionStatus.failed, SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
