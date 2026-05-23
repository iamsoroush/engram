from typing import Any
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, CaptureStatus, Patient, Session, SessionStatus
from app.schemas.api import AssignPatientRequest, CaptureUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_capture_for_tenant, session_payload
from app.services.sessions import parse_uuid


def get_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    payload = capture_payload(capture, artifact)
    if db.is_modified(capture, include_collections=True):
        db.commit()
        db.refresh(capture)
        payload = capture_payload(capture, artifact)
    return payload


def update_capture(
    db: DbSession,
    principal: CurrentPrincipal,
    capture_id: str,
    request: CaptureUpdate,
) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    if request.status is not None:
        try:
            capture.status = CaptureStatus(request.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid capture status") from exc
    if request.metadata is not None:
        capture.capture_metadata = {**(capture.capture_metadata or {}), **request.metadata}
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="capture.update", target_type="capture", target_id=capture.id)
    db.commit()
    db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def delete_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    """Soft-delete a capture and move generated session output back to draft."""
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    session = db.get(Session, capture.session_id)
    if session is None or session.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    now = datetime.now(timezone.utc)
    capture.status = CaptureStatus.deleted
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        "deleted_at": now.isoformat(),
        "deleted_by_user_id": str(principal.user_id),
    }
    mark_session_draft_after_capture_delete(session, str(capture.id), now)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="capture.delete",
        target_type="capture",
        target_id=capture.id,
        details={"session_id": str(session.id)},
    )
    db.commit()
    db.refresh(session)
    return {"session": session_payload(session, db)}


def mark_session_draft_after_capture_delete(session: Session, capture_id: str, changed_at: datetime) -> None:
    """Keep session contracts coherent after a source capture is removed."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    source_capture_ids = metadata.get("source_capture_ids")
    if not isinstance(source_capture_ids, list):
        source_capture_ids = []
    remaining_capture_ids = [source_id for source_id in source_capture_ids if source_id != capture_id]
    remaining_count = max(0, len(remaining_capture_ids))
    report_body = (
        "# Draft report\n\n"
        f"- {remaining_count} source capture{'s' if remaining_count != 1 else ''} attached.\n"
        "- A capture was removed. Generate a structured report again when you are ready."
    )
    session.generated_report = report_body
    session.summary = (
        f"Draft with {remaining_count} source capture{'s' if remaining_count != 1 else ''}. A capture was removed."
        if remaining_count
        else "Draft with no source captures. A capture was removed."
    )
    session.extracted_metadata = {
        **metadata,
        "capture_count": remaining_count,
        "source_capture_ids": remaining_capture_ids,
        "progressive_report": {
            "status": "partial",
            "format": "markdown",
            "body": report_body,
            "source": "capture-delete",
            "updated_at": changed_at.isoformat(),
        },
        "summaries": {
            "status": "partial",
            "short": session.summary,
            "clinical": session.summary,
            "source": "capture-delete",
            "updated_at": changed_at.isoformat(),
        },
        "processing_status": {
            "state": "queued" if remaining_count else "idle",
            "source": "capture-delete",
            "updated_at": changed_at.isoformat(),
        },
        "generated_output_stale": True,
        "stale_reason": "A capture was deleted after the last processed session output.",
        "stale_at": changed_at.isoformat(),
    }
    if session.status == SessionStatus.verified:
        session.status = SessionStatus.needs_review
    elif session.status in {SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned


def assign_capture_patient(
    db: DbSession,
    principal: CurrentPrincipal,
    capture_id: str,
    request: AssignPatientRequest,
) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    previous = capture.patient_id
    next_patient_id = None
    if request.patient_id:
        next_patient_id = parse_uuid(request.patient_id, "patient_id")
        exists = db.execute(
            select(Patient.id).where(Patient.id == next_patient_id, Patient.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    capture.patient_id = next_patient_id
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        "patient_assignment_source": request.source,
        "patient_assignment_reason": request.reason,
    }
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="capture.assign_patient",
        target_type="capture",
        target_id=capture.id,
        details={
            "previous_patient_id": str(previous) if previous else None,
            "next_patient_id": str(next_patient_id) if next_patient_id else None,
            "reason": request.reason,
            "source": request.source,
        },
    )
    db.commit()
    db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def capture_metadata(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    return {"captureId": str(capture.id), "metadata": capture.capture_metadata}
