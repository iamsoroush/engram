import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import Artifact, Capture, CaptureStatus, AiJob, OrganizationSource, Patient, Session, SessionStatus
from app.schemas.patients import AssignPatientRequest
from app.schemas.sessions import SessionCreate, SessionSaveRequest, SessionUpdate
from app.services.capture_storage import artifact_payload, capture_payload, get_session_for_tenant, session_payload
from app.services.feedback import record_feedback_event
from app.services.patient_safety import session_detected_safety_flags, sync_patient_safety_flags
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    patient_assignment_event,
)
from app.services.permissions import (
    can_edit,
    can_reassign,
    session_permission_for_roles,
    tenant_role_permissions,
)
from app.services.reporting import DEFAULT_REPORT_TEMPLATE_KEY, render_report_body_markdown, structured_report_from_markdown_body
from app.services.session_processing import render_treatment_performed_blocks, set_treatment_performed_section
from app.services.synthesis_escalation import mark_synthesis_escalation
from app.services.treatment_overlay import (
    TREATMENT_OVERLAY_FIELDS,
    find_treatment_by_key,
    remove_overlay_edit,
    session_treatment_overlay,
    stamp_treatment_keys,
    stored_treatments,
    upsert_overlay_edit,
)


def session_permission_for_principal(db: DbSession, principal: CurrentPrincipal, session: Session) -> str:
    """The viewer's effective preset on a session (owner → full, else by tenant role policy).

    Uses ``principal.roles`` from the token, so no extra membership query is needed.
    """
    return session_permission_for_roles(
        is_owner=session.created_by_user_id == principal.user_id,
        roles=principal.roles,
        role_permissions=tenant_role_permissions(db, principal.tenant_id),
    )


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_uuid(value: str, name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {name}") from exc


def require_patient(db: DbSession, tenant_id: uuid.UUID, patient_id: str | None) -> uuid.UUID | None:
    if patient_id is None:
        return None
    parsed = parse_uuid(patient_id, "patient_id")
    exists = db.execute(select(Patient.id).where(Patient.id == parsed, Patient.tenant_id == tenant_id)).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return parsed


def create_session(db: DbSession, principal: CurrentPrincipal, request: SessionCreate) -> dict[str, Any]:
    patient_id = require_patient(db, principal.tenant_id, request.patient_id)
    session = Session(
        tenant_id=principal.tenant_id,
        patient_id=patient_id,
        status=SessionStatus.draft,
        title=request.title,
        summary=request.summary,
        organization_source=OrganizationSource.none,
        created_by_user_id=principal.user_id,
        captured_at=parse_datetime(request.captured_at),
    )
    # Record a session-level assignment event when a session is started FOR a patient (e.g. the
    # worklist "Start visit"). It carries no captureId, so it stays valid through capture deletes —
    # apply_active_patient_assignment recomputes the patient from the timeline, and without this event
    # deleting any capture would wrongly unassign the visit. Capture-based assignments still tie their
    # event to a captureId (so removing that capture correctly reverts).
    if patient_id is not None:
        patient = db.get(Patient, patient_id)
        session.extracted_metadata = append_patient_assignment_event(
            session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {},
            patient_assignment_event(
                source="staff",
                action="manually_assigned",
                patient_id=patient_id,
                display_name=patient.display_name if patient is not None else None,
                reason=None,
                capture_id=None,
                actor_user_id=principal.user_id,
            ),
        )
    db.add(session)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.create",
        target_type="session",
        target_id=session.id,
        details={"patient_id": str(patient_id) if patient_id else None},
    )
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def save_session(db: DbSession, principal: CurrentPrincipal, session_id: str, request: SessionSaveRequest) -> dict[str, Any]:
    """Request session-level report processing without enforcing workflow state."""
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    capture_exists = db.execute(
        select(Capture.id)
        .where(
            Capture.tenant_id == principal.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
        .limit(1)
    ).scalar_one_or_none()
    if capture_exists is None:
        session.report_template_key = request.report_template_key or session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="session.process.request_empty",
            target_type="session",
            target_id=session.id,
            details={"report_template_key": session.report_template_key},
        )
        db.commit()
        db.refresh(session)
        return {"session": session_payload(session, db), "processingJob": None}

    from app.services.ai_jobs import regenerate_session_report_if_idle

    session.report_template_key = request.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY
    # The live report regenerates automatically and deterministically as captures land (no AI job,
    # no LLM), so the manual Generate button is gone; this endpoint now just rebuilds on demand
    # (e.g. an explicit retry). No-op while the capture chain is still processing.
    regenerate_session_report_if_idle(
        db,
        tenant_id=principal.tenant_id,
        session_id=session.id,
        created_by_user_id=principal.user_id,
        force=True,
    )
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.save",
        target_type="session",
        target_id=session.id,
        details={"report_template_key": session.report_template_key},
    )
    db.commit()
    db.refresh(session)
    return {"session": session_payload(session, db), "processingJob": None}


def list_sessions(
    db: DbSession,
    principal: CurrentPrincipal,
    status_filter: str | None,
    limit: int = 50,
    clinician_id: str | None = None,
) -> list[dict[str, Any]]:
    from app.services.caseload import is_federated_caseload

    statement = select(Session).where(Session.tenant_id == principal.tenant_id)
    # Therapy: the active session is user-scoped (foundation §7) — a clinician lists only their own
    # sessions. Aesthetics is a shared workspace, so no owner scoping there.
    if is_federated_caseload(db, principal.tenant_id):
        statement = statement.where(Session.created_by_user_id == principal.user_id)
    if status_filter:
        try:
            statement = statement.where(Session.status == SessionStatus(status_filter))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    if clinician_id:
        # AES-904 "Mine vs Clinic": a session belongs to the clinician who created (owns) it.
        statement = statement.where(Session.created_by_user_id == parse_uuid(clinician_id, "clinician_id"))
    sessions = db.execute(statement.order_by(Session.updated_at.desc()).limit(min(limit, 100))).scalars()
    return [session_payload(session, db) for session in sessions]


def get_session(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    return session_payload(session, db)


def update_session(db: DbSession, principal: CurrentPrincipal, session_id: str, request: SessionUpdate) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    # AES-902: editing/curating a session is the owner's by default. A non-owner may edit only when
    # the tenant's policy grants their role the "full" preset (admins always can). We refuse with
    # 403 rather than silently no-op, so a read-only viewer sees the attributed/read-only state.
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't edit it.",
        )
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    original_treatments = metadata.get("treatments")
    if request.title is not None:
        session.title = request.title
    if request.summary is not None:
        session.summary = request.summary
    if request.generated_summary is not None:
        session.generated_summary = request.generated_summary
    if request.generated_report is not None:
        session.generated_report = request.generated_report
        session.report_model = structured_report_from_markdown_body(
            title=session.title,
            body=request.generated_report,
            template_key=session.report_template_key,
        )
    if request.report_model is not None:
        session.report_model = request.report_model
    if request.report is not None:
        body = request.report.get("body")
        if isinstance(body, str):
            session.generated_report = body
            session.report_model = structured_report_from_markdown_body(
                title=session.title,
                body=body,
                template_key=session.report_template_key,
                findings=request.findings,
            )
        metadata = {**metadata, "progressive_report": request.report}
    if request.summaries is not None:
        short = request.summaries.get("short")
        if isinstance(short, str):
            session.summary = short
            session.generated_summary = short
        metadata = {**metadata, "summaries": request.summaries}
    if request.findings is not None:
        metadata = {**metadata, "findings": request.findings}
    if request.processing_status is not None:
        metadata = {**metadata, "processing_status": request.processing_status}
    if request.extracted_metadata is not None:
        metadata = {**metadata, **request.extracted_metadata}
        # (S-F14) A staff bulk edit of treatments[] must not strip the content-anchored treatmentKey the
        # overlay binds to — re-stamp keys so a hand-edited row keeps a stable identity (rows without a
        # key would otherwise orphan every overlay edit on the next fold/re-synthesis).
        if isinstance(request.extracted_metadata.get("treatments"), list):
            metadata["treatments"] = stamp_treatment_keys(metadata.get("treatments"))
    if metadata != (session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}):
        session.extracted_metadata = metadata
    if request.status is not None:
        try:
            session.status = SessionStatus(request.status)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status") from exc
    # Harvest a staff edit of the AI-extracted treatments as a candidate eval case (eval-epic §1b):
    # the structured before→after of the treatments[] store feeds the report-synthesis/treatments eval.
    if isinstance(request.extracted_metadata, dict) and "treatments" in request.extracted_metadata:
        new_treatments = request.extracted_metadata.get("treatments")
        if new_treatments != original_treatments:
            import json

            record_feedback_event(
                db,
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                kind="correction",
                ai_output_type="treatment",
                before_value=json.dumps(original_treatments, ensure_ascii=False) if original_treatments is not None else None,
                after_value=json.dumps(new_treatments, ensure_ascii=False) if new_treatments is not None else None,
                session_id=session.id,
                patient_id=session.patient_id,
                context={"source": "session-update"},
            )
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.update", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def confirm_carried_forward_dose(db: DbSession, principal: CurrentPrincipal, session_id: str, key: str) -> dict[str, Any]:
    """Q3: record that the doctor confirmed a carried-forward dose so the report can read Complete.

    An unconfirmed carried-forward dose holds the report at "needs confirmation"
    (`session_is_complete`); confirming it by its `area|product` key clears that one item. Other
    review items stay non-blocking. Confirmation persists in `extracted_metadata.confirmed_carried_forward`
    and survives re-synthesis (the same carried item keeps its key).
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't confirm its doses.",
        )
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    confirmed = [str(value) for value in (metadata.get("confirmed_carried_forward") or []) if isinstance(value, str)]
    if key not in confirmed:
        confirmed.append(key)
    metadata["confirmed_carried_forward"] = confirmed
    session.extracted_metadata = metadata
    # A confirmed carried-forward dose is a positive signal: the AI's carry-forward was accepted. Harvest
    # it (keyed by area|product) so the patient-memory/carry-forward eval has true positives too.
    record_feedback_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        kind="confirmation",
        ai_output_type="treatment",
        session_id=session.id,
        patient_id=session.patient_id,
        context={"action": "confirm_carried_forward", "key": key},
    )
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.confirm_carried_forward", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def _rerender_treatment_performed(db: DbSession, session: Session) -> None:
    """Re-render the report's treatment-performed section from the overlay-folded treatments (S-F8).

    Keeps the printed/shared report prose consistent with the human-corrected treatment values without a
    re-synthesis. No-op when there is no structured report model or no treatment-performed section
    (Basic / deterministic baseline), so it is safe to call on any session.
    """
    from app.services.treatment_overlay import effective_treatments

    report_model = session.report_model if isinstance(session.report_model, dict) else None
    if not (report_model and report_model.get("sections")):
        return
    blocks = render_treatment_performed_blocks(effective_treatments(session))
    session.report_model = set_treatment_performed_section(report_model, blocks)
    session.generated_report = render_report_body_markdown(session.report_model, db=db, session=session)


def set_treatment_overlay_edit(
    db: DbSession, principal: CurrentPrincipal, session_id: str, treatment_key: str, field: str, value: str
) -> dict[str, Any]:
    """AES-1101: record a human field edit on one treatment row as a user-owned overlay entry.

    Deterministic + instant — NO synthesis, NO AI budget. The edit is authoritative on render
    (``report_version ⊕ overlay``) and immune to re-mis-extraction: a later re-synthesis re-binds it to
    the fresh row and surfaces any disagreement (``{aiValue, value}``) rather than overwriting it. v1 is
    field-edit only (owner-gated per pipeline-versioning permissions); row add/remove are v2.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't edit its treatments.",
        )
    if field not in TREATMENT_OVERLAY_FIELDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Field '{field}' is not editable")
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A non-empty value is required")
    treatment = find_treatment_by_key(stored_treatments(session), treatment_key)
    if treatment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No treatment matches that key")
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    overlay, ai_value = upsert_overlay_edit(
        session_treatment_overlay(session),
        treatment=treatment,
        field=field,
        value=value.strip(),
        edited_by_user_id=str(principal.user_id),
    )
    metadata["treatment_overlay"] = overlay
    session.extracted_metadata = metadata
    # (S-F8) Re-render the treatment-performed prose from the folded (effective) treatments so the
    # printed/shared report line shows the human-corrected value immediately — the prose was baked from
    # raw treatments at synthesis time and would otherwise keep showing the AI value until a re-synthesis.
    _rerender_treatment_performed(db, session)
    # A treatment-overlay edit is a user correction → the NEXT synthesis for this session escalates (§3.1).
    mark_synthesis_escalation(session)
    # Harvest the field-granular before→after as a candidate eval case (epic Q5, eval-epic §3a).
    record_feedback_event(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        kind="correction",
        ai_output_type="treatment",
        before_value=ai_value,
        after_value=value.strip(),
        session_id=session.id,
        patient_id=session.patient_id,
        context={"source": "treatment-overlay", "treatmentKey": treatment_key, "field": field},
    )
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.treatment_overlay_edit", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def remove_treatment_overlay_edit(
    db: DbSession, principal: CurrentPrincipal, session_id: str, treatment_key: str, field: str
) -> dict[str, Any]:
    """AES-1101: Revert-to-AI — drop the overlay edit for (treatmentKey, field) so the AI value returns."""
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't edit its treatments.",
        )
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    metadata["treatment_overlay"] = remove_overlay_edit(
        session_treatment_overlay(session), treatment_key=treatment_key, field=field
    )
    session.extracted_metadata = metadata
    # (S-F8) Reverting an edit re-renders the prose back to the AI value (mirror of the edit path).
    _rerender_treatment_performed(db, session)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.treatment_overlay_revert", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def set_aftercare_dismissed(
    db: DbSession, principal: CurrentPrincipal, session_id: str, template_id: str, dismissed: bool
) -> dict[str, Any]:
    """Record whether a clinic aftercare template auto-included for this visit was dismissed.

    Aftercare matching a performed procedure is included in the report by default (opt-out); removing
    it records the template id in ``extracted_metadata.dismissed_aftercare`` so it stays removed across
    re-synthesis and reloads. Re-adding (``dismissed=False``) clears it. User state, not AI output.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't change its aftercare.",
        )
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    dismissed_ids = [str(value) for value in (metadata.get("dismissed_aftercare") or []) if isinstance(value, str)]
    if dismissed and template_id not in dismissed_ids:
        dismissed_ids.append(template_id)
    elif not dismissed:
        dismissed_ids = [value for value in dismissed_ids if value != template_id]
    metadata["dismissed_aftercare"] = dismissed_ids
    session.extracted_metadata = metadata
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.dismiss_aftercare", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def set_safety_flag_rejected(
    db: DbSession, principal: CurrentPrincipal, session_id: str, flag_key: str, rejected: bool
) -> dict[str, Any]:
    """Record whether a detected session safety flag was rejected by the clinician (opt-out).

    Safety flags (allergy/contraindication/consent) detected by the synthesis are auto-kept and shown
    by default; the clinician acts only to REJECT a wrong one. The rejected flag's stable ``flag_key``
    is stored in ``extracted_metadata.rejected_safety_flags`` so it stays rejected across re-synthesis
    and reloads (user state, not AI output). Re-accepting (``rejected=False``) clears it. The patient's
    cross-visit safety store is re-synced from the visit's kept flags, and a rejection is harvested as
    an AI-feedback signal (the rejected flag IS the eval target). User state, not AI output.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    if not can_edit(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This session is owned by another clinician; your role can't change its safety flags.",
        )
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    rejected_keys = [str(value) for value in (metadata.get("rejected_safety_flags") or []) if isinstance(value, str)]
    rejected_records = [record for record in (metadata.get("rejected_safety_flag_records") or []) if isinstance(record, dict) and isinstance(record.get("key"), str)]
    rejected_flag = next((flag for flag in session_detected_safety_flags(session) if flag["key"] == flag_key), None)
    if rejected and flag_key not in rejected_keys:
        rejected_keys.append(flag_key)
    elif not rejected:
        rejected_keys = [value for value in rejected_keys if value != flag_key]
    # (S-F7) Maintain a rich rejection record (kind + source captures) alongside the key so the rejection
    # follows the flag across a re-synthesis that rewords its text — a bare key can't survive rewording.
    rejected_records = [record for record in rejected_records if record.get("key") != flag_key]
    if rejected and rejected_flag is not None:
        rejected_records.append(
            {
                "key": flag_key,
                "kind": rejected_flag["kind"],
                "text": rejected_flag["text"],
                "sourceCaptureIds": rejected_flag.get("sourceCaptureIds") or [],
            }
        )
    metadata["rejected_safety_flags"] = rejected_keys
    metadata["rejected_safety_flag_records"] = rejected_records
    session.extracted_metadata = metadata
    if rejected:
        # A rejection is a failure signal: the synthesis surfaced a wrong safety flag. Harvest it (the
        # rejected flag text is the eval target) so the safety-flags eval gathers real negatives.
        record_feedback_event(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            kind="rejection",
            ai_output_type="safety_flag",
            before_value=rejected_flag["text"] if rejected_flag else None,
            session_id=session.id,
            patient_id=session.patient_id,
            context={"action": "reject_safety_flag", "key": flag_key, "flagKind": rejected_flag["kind"] if rejected_flag else None},
        )
    # Re-project this visit's kept flags onto the patient so the rejection (or re-accept) is reflected
    # cross-visit immediately.
    if session.patient_id is not None:
        patient = db.get(Patient, session.patient_id)
        if patient is not None:
            sync_patient_safety_flags(patient, session)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.reject_safety_flag", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def assign_session_patient(
    db: DbSession,
    principal: CurrentPrincipal,
    session_id: str,
    request: AssignPatientRequest,
) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    previous = session.patient_id
    next_patient_id = require_patient(db, principal.tenant_id, request.patient_id)
    # AES-902: *changing* an already-assigned visit to a different patient (or clearing it) is a
    # reassignment and needs the reassign permission. Initial filing of an unassigned visit is the
    # capture-first / assign-later floor — open to all staff, never blocked.
    is_reassignment = previous is not None and (next_patient_id is None or str(previous) != str(next_patient_id))
    if is_reassignment and not can_reassign(session_permission_for_principal(db, principal, session)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role can't reassign a visit owned by another clinician.",
        )
    patient = (
        db.execute(
            select(Patient).where(Patient.id == next_patient_id, Patient.tenant_id == principal.tenant_id)
        ).scalar_one_or_none()
        if next_patient_id
        else None
    )
    existing_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    # When staff apply a per-capture suggestion, attribute the assignment to that capture so it
    # becomes the source (and the prior basis capture turns into a switchable alternate).
    basis_capture = None
    if request.basis_capture_id and next_patient_id:
        basis_capture = db.execute(
            select(Capture).where(
                Capture.id == parse_uuid(request.basis_capture_id, "basis_capture_id"),
                Capture.tenant_id == principal.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalar_one_or_none()
    event = patient_assignment_event(
        source=request.source or "staff",
        action="manually_assigned" if next_patient_id else "manually_unassigned",
        patient_id=next_patient_id,
        display_name=patient.display_name if patient else None,
        reason=request.reason,
        capture_id=basis_capture.id if basis_capture is not None else None,
        actor_user_id=principal.user_id,
    )
    session.extracted_metadata = append_patient_assignment_event(existing_metadata, event)
    apply_active_patient_assignment(db, session)
    match_candidate = (
        (basis_capture.capture_metadata or {}).get("patient_match_candidate") if basis_capture is not None else None
    )
    if basis_capture is not None:
        # The suggestion on the now-applied capture is consumed — drop it so the chip clears.
        basis_capture.capture_metadata = {
            key: value
            for key, value in (basis_capture.capture_metadata or {}).items()
            if key != "patient_match_candidate"
        }
    # Harvest the patient-match decision as a candidate eval case (eval-epic §1b): a reassignment is a
    # correction of the prior (often AI) match; acting on a suggestion to file an unassigned visit is a
    # confirmation. Only IDs + match metadata are stored — names/evidence are scrubbed out (PII).
    if is_reassignment or match_candidate is not None:
        record_feedback_event(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            kind="correction" if is_reassignment else "confirmation",
            ai_output_type="patient_match",
            session_id=session.id,
            patient_id=next_patient_id,
            context={
                "previous_patient_id": str(previous) if previous else None,
                "next_patient_id": str(next_patient_id) if next_patient_id else None,
                "source": request.source,
                "reassignment": is_reassignment,
                "basis_capture_id": str(basis_capture.id) if basis_capture is not None else None,
                "match_candidate": match_candidate if isinstance(match_candidate, dict) else None,
            },
        )
    # Safety-flag drop/sync AND the reassignment invalidation (carry-forward confirmations + reconcile) +
    # the escalation marker are all handled centrally in apply_active_patient_assignment above — the one
    # place patient_id changes — so every assignment path (staff, AI-driven, capture-delete) is covered.
    # A reassignment is a correction of a prior (often wrong-patient) synthesis: force a fresh re-synthesis
    # so carry-forward + safety-reconcile recompute against the corrected patient. The patient-scoped
    # version cache (report_versions) prevents a stale cross-patient cache-hit from short-circuiting it.
    if is_reassignment:
        from app.services.ai_jobs import regenerate_session_report_if_idle

        db.flush()
        regenerate_session_report_if_idle(
            db,
            tenant_id=principal.tenant_id,
            session_id=session.id,
            created_by_user_id=principal.user_id,
            force=True,
        )
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="session.assign_patient",
        target_type="session",
        target_id=session.id,
        details={
            "previous_patient_id": str(previous) if previous else None,
            "next_patient_id": str(next_patient_id) if next_patient_id else None,
            "reason": request.reason,
            "source": request.source,
        },
    )
    db.commit()
    db.refresh(session)
    return {**session_payload(session, db), "assignmentSource": request.source}


def _consume_capture_suggestion(db: DbSession, tenant_id: uuid.UUID, session_id: uuid.UUID, basis_capture_id: str | None) -> Capture | None:
    """Drop a capture's ``patient_match_candidate`` so its suggestion chip clears once applied.

    Returns the capture (for source attribution) or None. Mirrors the suggestion-consume that
    ``assign_session_patient`` does when a per-capture reassignment is applied.
    """
    if not basis_capture_id:
        return None
    capture = db.execute(
        select(Capture).where(
            Capture.id == parse_uuid(basis_capture_id, "basis_capture_id"),
            Capture.tenant_id == tenant_id,
            Capture.session_id == session_id,
            Capture.status != CaptureStatus.deleted,
        )
    ).scalar_one_or_none()
    if capture is not None and isinstance(capture.capture_metadata, dict) and "patient_match_candidate" in capture.capture_metadata:
        capture.capture_metadata = {key: value for key, value in capture.capture_metadata.items() if key != "patient_match_candidate"}
    return capture


def apply_patient_name_correction(
    db: DbSession, principal: CurrentPrincipal, session_id: str, spoken_name: str, basis_capture_id: str | None = None
) -> dict[str, Any]:
    """E1 one-tap: apply a ``suggested_name_correction`` — rename the assigned patient in place.

    The chip appears when the AI detected the visit's patient is (probably) the assigned one but the
    spoken name differs and it wasn't auto-renamed (implicit basis, or a role/verification gate). Tapping
    it is the human's explicit confirmation, so we rename in place (deterministic, no re-synthesis): an
    unverified AI-created record renames freely (its whole point); a verified/human record is a real
    chart, so the edit is gated on the full (owner-class) preset. The verbatim before→after is harvested.
    """
    from app.services.patients import rename_patient_in_place

    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    perm = session_permission_for_principal(db, principal, session)
    if not can_edit(perm):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This session is owned by another clinician; your role can't correct its patient.")
    if session.patient_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No patient is assigned to correct")
    if not (isinstance(spoken_name, str) and spoken_name.strip()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A spoken name is required")
    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The assigned patient no longer exists")
    # The chip carries the spoken name; rename to it (rename_patient_in_place also registers it as a
    # search alias so future captures resolve to the corrected record).
    capture = _consume_capture_suggestion(db, principal.tenant_id, session.id, basis_capture_id)
    new_name = rename_patient_in_place(
        db,
        patient=patient,
        patient_information={"raw_mentioned_name": spoken_name.strip()},
        actor_user_id=principal.user_id,
        source_capture_id=capture.id if capture is not None else None,
    )
    if new_name is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No name change to apply")
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.apply_name_correction", target_type="session", target_id=session.id, details={"new_display_name": new_name})
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def unassign_session_patient(
    db: DbSession, principal: CurrentPrincipal, session_id: str, basis_capture_id: str | None = None
) -> dict[str, Any]:
    """E1 one-tap: apply a ``suggested_unassign`` (detach/negation, A-F9) — clear the visit's patient.

    Unassign is destructive, so it is only ever suggested, never auto-applied; this is where the human
    confirms it. Appends a ``manually_unassigned`` timeline event and routes through the one assignment
    choke point (``apply_active_patient_assignment``) so the wrong patient's safety flags / carry-forward
    confirmations / reconcile are all invalidated. Clearing an assigned visit needs the reassign permission.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    perm = session_permission_for_principal(db, principal, session)
    if session.patient_id is not None and not can_reassign(perm):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your role can't unassign a visit owned by another clinician.")
    previous = session.patient_id
    _consume_capture_suggestion(db, principal.tenant_id, session.id, basis_capture_id)
    event = patient_assignment_event(
        source="staff",
        action="manually_unassigned",
        patient_id=None,
        display_name=None,
        reason=None,
        capture_id=None,
        actor_user_id=principal.user_id,
    )
    session.extracted_metadata = append_patient_assignment_event(
        session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}, event
    )
    apply_active_patient_assignment(db, session)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.unassign_patient", target_type="session", target_id=session.id, details={"previous_patient_id": str(previous) if previous else None})
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def start_review(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"), for_update=True)
    session.status = SessionStatus.reviewing
    session.review_started_by_user_id = principal.user_id
    session.review_started_at = datetime.now(timezone.utc)
    audit(db, tenant_id=principal.tenant_id, actor_user_id=principal.user_id, action="session.review_start", target_type="session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session_payload(session, db)


def list_session_captures(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    captures = db.execute(
        select(Capture)
        .where(
            Capture.tenant_id == principal.tenant_id,
            Capture.session_id == session.id,
            Capture.status != CaptureStatus.deleted,
        )
        .order_by(Capture.created_at)
    ).scalars()
    payloads = [capture_payload(capture, db=db) for capture in captures]
    if db.dirty:
        db.commit()
    return payloads


def list_session_artifacts(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    artifacts = db.execute(
        select(Artifact).where(Artifact.tenant_id == principal.tenant_id, Artifact.session_id == session.id).order_by(Artifact.created_at)
    ).scalars()
    return [artifact_payload(artifact) for artifact in artifacts]


def list_session_ai_jobs(db: DbSession, principal: CurrentPrincipal, session_id: str) -> list[dict[str, Any]]:
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    jobs = db.execute(
        select(AiJob).where(AiJob.tenant_id == principal.tenant_id, AiJob.session_id == session.id).order_by(AiJob.created_at)
    ).scalars()
    return [
        {
            "id": str(job.id),
            "sessionId": str(job.session_id) if job.session_id else None,
            "captureId": str(job.capture_id) if job.capture_id else None,
            "jobType": job.job_type.value,
            "status": job.status.value,
            "generatedBy": job.generated_by,
            "resultMetadata": job.result_metadata,
            "errorMessage": job.error_message,
            "createdAt": job.created_at.isoformat() if job.created_at else None,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        }
        for job in jobs
    ]
