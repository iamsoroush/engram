import uuid
from typing import Any
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, Capture, CaptureStatus, CaptureType, Patient, PatientStatus, Session, SessionStatus
from app.schemas.captures import CaptureUpdate
from app.schemas.patients import AssignPatientRequest
from app.services.capture_storage import artifact_payload, capture_payload, get_capture_for_tenant, session_payload
from app.services.feedback import record_capture_text_correction, record_feedback_event
from app.services.patient_assignment_timeline import apply_active_patient_assignment
from app.services.patient_safety import drop_session_safety_flags, sync_patient_safety_flags
from app.services.patients import AI_CREATED_PATIENT_NOTE
from app.services.report_versions import find_report_version_for_current_set, restore_report_version
from app.services.sessions import parse_uuid


def get_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    payload = capture_payload(capture, artifact, db)
    if db.is_modified(capture, include_collections=True):
        db.commit()
        db.refresh(capture)
        payload = capture_payload(capture, artifact, db)
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
    relevance_marked = False
    previous_metadata = dict(capture.capture_metadata or {})
    if request.metadata is not None:
        incoming_metadata = dict(request.metadata)
        # Staff "Mark relevant" clears the AI out-of-context marker non-destructively so the
        # capture flows back into the (Pro) live report, while keeping the AI marker for audit.
        if isinstance(incoming_metadata.get("out_of_context"), dict):
            relevance_marked = True
            existing_ooc = (capture.capture_metadata or {}).get("out_of_context")
            existing_present = isinstance(existing_ooc, dict) and existing_ooc.get("present") is True
            incoming_metadata["out_of_context"] = {
                "present": False,
                "overridden_by_staff": True,
                "source": "staff",
                "overridden_by_user_id": str(principal.user_id),
                "overridden_at": datetime.now(timezone.utc).isoformat(),
                "ai_marker": existing_ooc if existing_present else (existing_ooc.get("ai_marker") if isinstance(existing_ooc, dict) else None),
            }
        capture.capture_metadata = merged_capture_metadata_for_staff_edit(capture.capture_metadata or {}, incoming_metadata, principal)
        if capture.capture_type == CaptureType.photo and "caption" in request.metadata:
            session = db.get(Session, capture.session_id)
            if session is not None and session.tenant_id == principal.tenant_id:
                mark_session_stale_after_source_text_update(session, str(capture.id), "caption-edit", "A photo caption was edited after the last processed session output.", datetime.now(timezone.utc))
        if capture.capture_type == CaptureType.audio and "transcript" in request.metadata:
            session = db.get(Session, capture.session_id)
            if session is not None and session.tenant_id == principal.tenant_id:
                mark_session_stale_after_source_text_update(session, str(capture.id), "transcript-edit", "An audio transcript was edited after the last processed session output.", datetime.now(timezone.utc))
        # Harvest a transcript/caption staff edit as a candidate eval case (eval-epic §1b). Staged in
        # this same transaction (like audit); never raises into the edit.
        record_capture_text_correction(db, principal, capture, previous_metadata, request.metadata)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="capture.update", target_type="capture", target_id=capture.id)
    db.commit()
    db.refresh(capture)
    # A capture moving in/out of the report changes its contents, so regenerate the live report
    # (no-op while the capture chain is still processing).
    if relevance_marked and capture.session_id is not None:
        from app.services.ai_jobs import regenerate_session_report_if_idle

        regenerate_session_report_if_idle(
            db,
            tenant_id=principal.tenant_id,
            session_id=capture.session_id,
            created_by_user_id=principal.user_id,
            force=True,
        )
        db.refresh(capture)
    artifact = db.get(Artifact, capture.source_artifact_id) if capture.source_artifact_id else None
    return capture_payload(capture, artifact, db)


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
    if session.status in {SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned


def can_remove_capture(session: Session, principal: CurrentPrincipal) -> bool:
    """Single policy point for capture removal (undo / delete).

    v1 = OWNER-ONLY: only the clinician who owns the session may remove a capture (a destructive,
    de-effecting action), even an admin cannot touch another clinician's visit. The tenant-configurable
    strict / standard / open edit policy + non-owner-edit attribution are a fast-follow; they slot in
    here without changing call sites.
    """
    return session.created_by_user_id == principal.user_id


def _patient_created_by_capture(session: Session, capture_id: uuid.UUID) -> uuid.UUID | None:
    """The patient an AI 'create patient from spoken identity' action created from THIS capture, if any.

    Reads the assignment timeline for a `created` event sourced by this capture — so removing the capture
    can clean up the patient it spuriously created (the motivating case: a mis-transcribed name).
    """
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    timeline = metadata.get("patient_assignment_timeline")
    for event in timeline if isinstance(timeline, list) else []:
        if not isinstance(event, dict):
            continue
        if event.get("created") is True and str(event.get("captureId")) == str(capture_id) and event.get("patientId"):
            try:
                return uuid.UUID(str(event["patientId"]))
            except ValueError:
                return None
    return None


def _archive_orphaned_ai_patient(db: DbSession, principal: CurrentPrincipal, patient_id: uuid.UUID | None) -> bool:
    """Soft-delete (archive) an AI-created patient that a capture removal just orphaned.

    Reversible (``status=archived``; the row is kept and accessible). Guarded to be safe: only an
    **unverified AI-created** patient (its note is the AI-creation breadcrumb) with **no remaining
    dependents** (no assigned session, no live capture) is ever archived — never a real/verified patient.
    Returns whether it archived. The wrong AI patient action is harvested as a feedback signal.
    """
    if patient_id is None:
        return False
    patient = db.get(Patient, patient_id)
    if patient is None or patient.tenant_id != principal.tenant_id or patient.status != PatientStatus.active:
        return False
    if (patient.notes or "").strip() != AI_CREATED_PATIENT_NOTE:
        return False  # only the unverified AI-created breadcrumb patient is eligible
    has_session = db.execute(
        select(Session.id).where(Session.tenant_id == principal.tenant_id, Session.patient_id == patient.id).limit(1)
    ).scalar_one_or_none()
    has_capture = db.execute(
        select(Capture.id).where(
            Capture.tenant_id == principal.tenant_id,
            Capture.patient_id == patient.id,
            Capture.status != CaptureStatus.deleted,
        ).limit(1)
    ).scalar_one_or_none()
    if has_session is not None or has_capture is not None:
        return False
    patient.status = PatientStatus.archived
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="patient.archive_orphaned_ai",
        target_type="patient",
        target_id=patient.id,
    )
    # The spurious patient came from a wrong AI patient action (typically a mis-transcribed identity).
    # Harvest it as a candidate eval case (eval-epic §1b).
    record_feedback_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        kind="correction",
        ai_output_type="patient_match",
        patient_id=patient.id,
        context={"action": "undo_orphaned_ai_patient"},
    )
    return True


def delete_capture(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    """Remove a capture and **de-effect** it: revert the patient assignment it drove, soft-delete a
    patient it spuriously created (when orphaned), and keep the patient's safety flags consistent.

    One removal operation; "Undo" (one-tap, last capture) and per-capture "Delete" both land here.
    Owner-only (see :func:`can_remove_capture`).
    """
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    session = db.get(Session, capture.session_id)
    if session is None or session.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not can_remove_capture(session, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the clinician who owns this session can remove its captures.",
        )

    # Capture the pre-removal assignment state so we can de-effect: which patient this capture CREATED
    # (to clean up if orphaned) and which patient the session was on (to keep safety flags consistent).
    former_patient_id = session.patient_id
    created_patient_id = _patient_created_by_capture(session, capture.id)

    now = datetime.now(timezone.utc)
    capture.status = CaptureStatus.deleted
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        "deleted_at": now.isoformat(),
        "deleted_by_user_id": str(principal.user_id),
    }
    mark_session_draft_after_capture_delete(session, str(capture.id), now)
    # Flush the soft-delete before recomputing: the session uses autoflush=False, and
    # `apply_active_patient_assignment` queries for non-deleted captures to drop the deleted
    # capture's assignment event. Without this flush that query still sees the capture as
    # active, so deleting the assignment-source capture would NOT revert to the prior patient.
    db.flush()
    # Patient assignment is recomputed from the timeline (cheap; no AI job): the deleted
    # capture's assignment event is dropped and the active assignment recomputed.
    apply_active_patient_assignment(db, session)
    # De-effect the removal: if this capture spuriously CREATED a patient that is now orphaned, soft-
    # delete it (the motivating bug — a mis-transcribed name spawned a patient that lingered); and if the
    # removal changed the session's patient, drop this visit's safety-flag contribution from the former
    # patient so the cross-visit safety set stays consistent.
    _archive_orphaned_ai_patient(db, principal, created_patient_id)
    if former_patient_id is not None and session.patient_id != former_patient_id:
        former_patient = db.get(Patient, former_patient_id)
        if former_patient is not None:
            drop_session_safety_flags(former_patient, session)
    # Cache-hit restore (pipeline-versioning): if removing this capture returns the session to a
    # previously-synthesized capture set, restore that exact report_version deterministically — no
    # re-synthesis, no "wrong entries". Otherwise fall through to a recompute (below).
    cached_version = find_report_version_for_current_set(db, session)
    if cached_version is not None:
        restore_report_version(session, cached_version)
        if session.patient_id is not None and isinstance(session.extracted_metadata.get("safety_flags"), list):
            restored_patient = db.get(Patient, session.patient_id)
            if restored_patient is not None:
                sync_patient_safety_flags(restored_patient, session)
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
    if cached_version is None:
        # Never-seen capture set → recompute the live report from the remaining captures (no-op while
        # the capture chain is still processing). A cache-hit above already restored it deterministically.
        from app.services.ai_jobs import regenerate_session_report_if_idle

        regenerate_session_report_if_idle(
            db,
            tenant_id=principal.tenant_id,
            session_id=session.id,
            created_by_user_id=principal.user_id,
            force=True,
        )
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
    if session.status in {SessionStatus.organized, SessionStatus.reviewing, SessionStatus.reopened}:
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
    return capture_payload(capture, artifact, db)


def capture_metadata(db: DbSession, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    return {"captureId": str(capture.id), "metadata": capture.capture_metadata}
