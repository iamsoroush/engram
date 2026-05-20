import uuid
from datetime import datetime
from typing import Any

from app.models import CaptureType, OrganizationSource, Session, SessionStatus

SESSION_CONTRACT_VERSION = "2026-05-19.phase2.1"


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
            "# Progressive clinical report\n\n"
            f"- {count} source capture{'s' if count != 1 else ''} attached.\n"
            "- Report text is a deterministic placeholder until the AI pipeline is connected.\n"
            "- Review source captures below before using this clinically."
        )
    return (
        "# Progressive clinical report\n\n"
        "This report surface is ready before captures arrive. Content will evolve as captures are added."
    )


def _report_status(session: Session, metadata: dict[str, Any]) -> str:
    progressive_report = metadata.get("progressive_report")
    if isinstance(progressive_report, dict) and isinstance(progressive_report.get("status"), str):
        return progressive_report["status"]
    if session.status == SessionStatus.verified:
        return "verified"
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


def build_session_contracts(session: Session) -> dict[str, Any]:
    """Build frontend-stable session contracts from the current session record."""
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
    elif report_status in {"processed", "verified"} and not is_stale:
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
    summary = f"Progressive draft with {next_count} source capture{'s' if next_count != 1 else ''}. Latest: {capture_label}."
    report_body = (
        "# Progressive clinical report\n\n"
        f"- {next_count} source capture{'s' if next_count != 1 else ''} attached.\n"
        f"- Latest source type: {capture_label}.\n"
        "- This mocked draft updates deterministically so the UI can build against a stable evolving session contract."
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
    session.report_template_key = session.report_template_key or "default"
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
    if session.status == SessionStatus.verified:
        session.status = SessionStatus.needs_review
    elif session.status in {SessionStatus.failed, SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
