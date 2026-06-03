from typing import Any
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, CaptureStatus, CaptureType, Patient, Session, SessionStatus
from app.schemas.api import AssignPatientRequest, CaptureUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_capture_for_tenant, session_payload
from app.services.patient_assignment_timeline import apply_active_patient_assignment
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
        capture.capture_metadata = merged_capture_metadata_for_staff_edit(capture.capture_metadata or {}, request.metadata, principal)
        if capture.capture_type == CaptureType.photo and "caption" in request.metadata:
            session = db.get(Session, capture.session_id)
            if session is not None and session.tenant_id == principal.tenant_id:
                mark_session_stale_after_source_text_update(session, str(capture.id), "caption-edit", "A photo caption was edited after the last processed session output.", datetime.now(timezone.utc))
        if capture.capture_type == CaptureType.audio and "transcript" in request.metadata:
            session = db.get(Session, capture.session_id)
            if session is not None and session.tenant_id == principal.tenant_id:
                mark_session_stale_after_source_text_update(session, str(capture.id), "transcript-edit", "An audio transcript was edited after the last processed session output.", datetime.now(timezone.utc))
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="capture.update", target_type="capture", target_id=capture.id)
    db.commit()
    db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact)


def merged_capture_metadata_for_staff_edit(
    existing_metadata: dict[str, Any],
    incoming_metadata: dict[str, Any],
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    """Merge editable text while retaining the first AI-generated text object."""
    merged = {**existing_metadata, **incoming_metadata}
    edited_at = datetime.now(timezone.utc).isoformat()
    for field in ("caption", "transcript"):
        incoming_value = incoming_metadata.get(field)
        if not isinstance(incoming_value, dict) or incoming_value.get("source") != "staff_edit":
            continue
        ai_field = f"ai_{field}"
        existing_value = existing_metadata.get(field)
        existing_record = existing_value if isinstance(existing_value, dict) else {}
        if ai_field not in merged and existing_value is not None and existing_record.get("source") != "staff_edit":
            merged[ai_field] = existing_value
        merged[field] = {
            **incoming_value,
            "source": "staff_edit",
            "edited_at": edited_at,
            "edited_by_user_id": str(principal.user_id),
            "edited_by_name": principal.user.full_name or principal.user.email,
            "edited_by_email": principal.user.email,
        }
    return merged


def mark_session_stale_after_source_text_update(
    session: Session,
    capture_id: str,
    source: str,
    stale_reason: str,
    changed_at: datetime,
) -> None:
    """Flag generated session output when staff edits source-generated text."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    session.extracted_metadata = {
        **metadata,
        "generated_output_stale": True,
        "stale_reason": stale_reason,
        "stale_at": changed_at.isoformat(),
        "processing_status": {
            **(metadata.get("processing_status") if isinstance(metadata.get("processing_status"), dict) else {}),
            "state": "queued",
            "source": source,
            "updated_at": changed_at.isoformat(),
        },
        "last_source_text_edit": {
            "capture_id": capture_id,
            "source": source,
            "updated_at": changed_at.isoformat(),
        },
    }
    if session.status == SessionStatus.verified:
        session.status = SessionStatus.needs_review
    elif session.status in {SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned


def delete_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    """Soft-delete a capture and recompute patient assignment from the timeline."""
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
    # Patient assignment is recomputed from the timeline (cheap; no AI job): the deleted
    # capture's assignment event is dropped and the active assignment recomputed.
    # NOTE: live-report regeneration on capture change is deferred to Epic E — no report
    # job runs for now, so deleting a capture never puts the session into a processing lock.
    apply_active_patient_assignment(db, session)
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
        "- A capture was removed."
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
