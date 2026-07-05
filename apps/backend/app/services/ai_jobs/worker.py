"""Worker job lifecycle: payload assembly, start/progress/complete/retry/fail, and AI assignment."""
import logging
import uuid
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

logger = logging.getLogger(__name__)

# ``match_patient_from_patient_information`` is resolved through the package namespace (see
# intents.py) so package-level monkeypatching keeps working on the worker path too.
import app.services.ai_jobs as ai_jobs_pkg
from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import (
    AftercareTemplate,
    AiJob,
    AiJobStatus,
    AiJobType,
    Capture,
    CaptureStatus,
    CaptureType,
    OrganizationSource,
    Patient,
    Session,
    SessionStatus,
)
from app.services.ai_model_config import ai_models_worker_payload
from app.services.capabilities import (
    IMAGE_CAPTION,
    LIVE_REPORT_SYNTHESIS,
    tenant_has_capability,
)
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    active_patient_assignment_event,
    patient_assignment_event,
)
from app.services.patient_matching import find_patient_duplicates, match_patient_from_metadata, spoken_name_matches_patient
from app.services.patients import (
    create_patient_from_patient_information,
    display_name_from_patient_information,
    is_ai_created_unverified_patient,
    patient_information_has_explicit_identity,
    rename_patient_in_place,
)
from app.services.permissions import user_can_reassign_session
from app.services.reporting import (
    DEFAULT_REPORT_TEMPLATE_KEY,
    render_report_body_markdown,
    structured_report_from_markdown_body,
)
from app.services.session_processing import (
    SESSION_SYNTHESIS_OUTPUT_VERSION,
    bounded_prior_visit_treatments,
    build_session_processing_input,
    capture_is_out_of_context,
    finalize_session_synthesis_output,
    prior_visit_capture_ids,
    render_treatment_performed_blocks,
    report_model_from_session_processing_output,
    session_processing_output_from_legacy_report,
    set_treatment_performed_section,
)
from app.services.synthesis_escalation import SYNTHESIS_ESCALATE_KEY
from app.services.patient_safety import apply_safety_reconciliation, sync_patient_safety_flags
from app.services.report_versions import record_report_version
from app.services.treatment_overlay import rebind_treatment_overlay
from app.services.sessions import parse_uuid

from app.services.ai_jobs.base import ai_job_payload, utc_now
from app.services.ai_jobs.config import (
    load_report_template,
    tenant_match_strictness,
    tenant_report_language,
)
from app.services.ai_jobs.context import build_capture_enrichment_context, build_transcription_context
from app.services.ai_jobs.intents import (
    assignment_intent_basis,
    caption_review_marker,
    detach_intent_basis,
    explicit_no_effect_notice,
    fuzzy_auto_apply_candidate,
    inert_assignment_conflict,
    name_correction_suggestion,
    near_match_suggestion,
    out_of_context_marker,
    resolved_match_patient_id,
    similar_existing_note,
    spoken_name_from_information,
    suggested_reassignment_candidate,
    suggested_unassign_candidate,
)
from app.services.ai_jobs.orchestration import (
    complete_patient_memory_worker_job,
    dispatch_next_session_capture,
    patient_memory_job_payload,
    requeue_failed_session_captures,
)
from app.services.ai_jobs.recovery import (
    ai_job_retryable,
    mark_job_non_retryable,
    schedule_retry,
    stop_recovery_if_target_is_gone,
)
from app.services.ai_jobs.reports import (
    has_append_intent,
    mark_session_report_contributions,
    maybe_dispatch_session_synthesis,
    regenerate_session_report_if_idle,
    report_contribution_effect,
    reportable_session_captures,
    session_report_content_signature,
    session_synthesis_enabled,
)

__all__ = [
    "ai_patient_action_metadata",
    "assign_session_to_ai_patient",
    "resolve_ai_patient_from_match",
    "get_ai_job",
    "require_ai_engine_token",
    "get_job_for_worker",
    "worker_job_payload",
    "start_worker_job",
    "complete_worker_job",
    "progress_worker_job",
    "complete_session_worker_job",
    "retry_worker_job",
    "fail_worker_job",
]


def ai_patient_action_metadata(
    *,
    action: str,
    patient: Patient,
    capture: Capture,
    patient_information: dict[str, Any],
    match_candidate: dict[str, Any] | None,
    created: bool,
) -> dict[str, Any]:
    """Return durable provenance for AI patient creation and assignment."""
    return {
        "schemaVersion": "2026-06-02.ai-patient-action.v1",
        "action": action,
        "source": "ai-engine",
        "basisCaptureId": str(capture.id),
        "patientId": str(patient.id),
        "displayName": patient.display_name,
        "created": created,
        "assigned": True,
        "needsVerification": created,
        "status": "needs_verification" if created else "assigned",
        "reason": (
            "AI created and assigned this patient from extracted audio identity."
            if created
            else "AI matched and assigned this visit to an existing patient."
        ),
        "patientInformation": patient_information,
        "matchCandidate": match_candidate,
    }


def assign_session_to_ai_patient(
    db: DbSession,
    *,
    session: Session,
    capture: Capture,
    patient: Patient,
    action: dict[str, Any],
) -> bool:
    """Assign a session/capture set to an AI-selected patient with provenance.

    Returns whether the just-appended event actually became the ACTIVE assignment. It may not (A-F7):
    a recovered older capture's event has an earlier ``effectiveAt`` than a later capture already in
    the timeline, so latest-valid-wins leaves the visit filed under the later patient — the caller
    surfaces that as a conflict instead of a success-shaped no-op.
    """
    assignment_source = "ai_created" if action.get("created") else "ai_matched"
    assignment_reason = action.get("reason")
    session_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    event = patient_assignment_event(
        source="ai-engine",
        action=action.get("action") if isinstance(action.get("action"), str) else assignment_source,
        patient_id=patient.id,
        display_name=patient.display_name,
        reason=assignment_reason if isinstance(assignment_reason, str) else None,
        capture_id=capture.id,
        created=bool(action.get("created")),
        action_metadata=action,
        effective_at=(capture.captured_at or capture.created_at).isoformat() if (capture.captured_at or capture.created_at) else None,
    )
    session.extracted_metadata = append_patient_assignment_event(
        {
            **session_metadata,
            "patient_match_candidate": action.get("matchCandidate"),
        },
        event,
    )
    apply_active_patient_assignment(db, session)
    return session.patient_id is not None and str(session.patient_id) == str(patient.id)


def resolve_ai_patient_from_match(
    db: DbSession,
    *,
    job: AiJob,
    capture: Capture,
    patient_information: dict[str, Any],
    patient_match_candidate: dict[str, Any] | None,
) -> tuple[Patient | None, bool]:
    """Return the patient selected or created by deterministic AI identity."""
    if patient_match_candidate and patient_match_candidate.get("decision") == "matched" and patient_match_candidate.get("patientId"):
        try:
            matched_patient_id = uuid.UUID(str(patient_match_candidate["patientId"]))
        except ValueError:
            return None, False
        patient = db.execute(
            select(Patient).where(Patient.id == matched_patient_id, Patient.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        return patient, False
    if patient_match_candidate and patient_match_candidate.get("decision") == "no_match":
        patient = create_patient_from_patient_information(
            db,
            tenant_id=job.tenant_id,
            created_by_user_id=job.created_by_user_id,
            patient_information=patient_information,
            source_capture_id=capture.id,
        )
        return patient, patient is not None
    return None, False


def _lock_session_row(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> Session | None:
    """INV-LOCK: load a session row with ``SELECT … FOR UPDATE`` so concurrent completions serialize.

    Two capture completions for the same session both read-modify-write the single JSONB
    ``extracted_metadata`` column; without a row lock the last committer erases the other capture's
    timeline event (A-F1/A-F2). Holding the row lock for the whole assignment write orders them. FOR
    UPDATE is a no-op on SQLite (dialect-ignored), so unit fakes and the sqlite tests are unaffected.
    """
    return db.execute(
        select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id).with_for_update()
    ).scalar_one_or_none()


def _spoken_names(patient_information: dict[str, Any]) -> list[str]:
    """The spoken/transcribed names to cross-check against a patient's stored aliases."""
    names = []
    for key in ("raw_mentioned_name", "standardized_display_name", "full_name", "display_name"):
        value = patient_information.get(key)
        if isinstance(value, str) and value.strip():
            names.append(value.strip())
    return list(dict.fromkeys(names))


def _ai_assign_to_patient(
    db: DbSession,
    *,
    session: Session,
    capture: Capture,
    patient: Patient,
    patient_information: dict[str, Any],
    match_candidate: dict[str, Any] | None,
    created: bool,
    extra_action: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Assign the visit to ``patient`` and return ``(patient_match_candidate, ai_patient_action)``.

    On a successful active assignment returns the match candidate + provenance action. If the append
    did not become the active assignment (A-F7 inert), returns a conflict chip and no action so the
    job never reports a phantom success.
    """
    action = ai_patient_action_metadata(
        action="created_and_assigned" if created else "matched_and_assigned",
        patient=patient,
        capture=capture,
        patient_information=patient_information,
        match_candidate=match_candidate,
        created=created,
    )
    if extra_action:
        action = {**action, **extra_action}
    became_active = assign_session_to_ai_patient(db, session=session, capture=capture, patient=patient, action=action)
    if not became_active:
        active = active_patient_assignment_event(db, session)
        conflict = inert_assignment_conflict(
            applied_patient_id=str(patient.id),
            applied_display_name=patient.display_name,
            active_patient_id=active.get("patientId") if isinstance(active, dict) else (str(session.patient_id) if session.patient_id else None),
            active_display_name=active.get("displayName") if isinstance(active, dict) else None,
        )
        return conflict, None
    return match_candidate, action


def _apply_first_identity(
    db: DbSession,
    *,
    job: AiJob,
    session: Session,
    capture: Capture,
    patient_information: dict[str, Any],
    match: dict[str, Any] | None,
    strictness: str,
    assignment_basis: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """First-identity-wins for an UNASSIGNED visit (capture-first), incl. the dead-zone fallback.

    Deterministic match → assign. no_match → create+assign (after a duplicate guard). A fuzzy
    possible_match auto-applies only when strictness permits a single dominant variant; a dominant
    but not-auto-applied variant surfaces a near-match suggestion; and a sub-threshold near-miss —
    the 0.762 dead zone (incident Fix 7) — creates+assigns the spoken patient while keeping the
    look-alike visible as an informational "similar to existing" note.
    """
    # Deterministic existing match → assign (never creates here, so creation always flows through the
    # duplicate guard below — A-F16).
    if isinstance(match, dict) and match.get("decision") == "matched" and match.get("patientId"):
        assigned_patient, _created = resolve_ai_patient_from_match(
            db, job=job, capture=capture, patient_information=patient_information, patient_match_candidate=match
        )
        if assigned_patient is not None:
            return _ai_assign_to_patient(
                db, session=session, capture=capture, patient=assigned_patient,
                patient_information=patient_information, match_candidate=match, created=False,
            )
    # Fuzzy possible_match: strictness may auto-apply a single dominant variant (reversible + notify).
    auto_top = fuzzy_auto_apply_candidate(match, strictness=strictness, assignment_basis=assignment_basis)
    auto_patient = _load_candidate_patient(db, tenant_id=job.tenant_id, candidate=auto_top)
    if auto_patient is not None:
        spoken_name = spoken_name_from_information(patient_information)
        candidate = {
            **(match or {}),
            "decision": "matched", "status": "matched",
            "patientId": str(auto_patient.id), "displayName": auto_patient.display_name,
            "appliedAutomatically": True, "autoAppliedCloseMatch": True,
            "matchedName": auto_patient.display_name, "spokenName": spoken_name,
        }
        return _ai_assign_to_patient(
            db, session=session, capture=capture, patient=auto_patient,
            patient_information=patient_information, match_candidate=candidate, created=False,
            extra_action={"closeMatch": True, "matchedName": auto_patient.display_name, "spokenName": spoken_name},
        )
    near_match = near_match_suggestion(match, patient_information=patient_information)
    if near_match is not None:
        return near_match, None
    # Create path — covers a clean `no_match` AND the sub-threshold dead zone (Fix 7): create + assign
    # the spoken patient (first-identity-wins), but only after the duplicate guard (A-F16), keeping the
    # closest look-alike as an informational note when one exists.
    duplicate = _strong_duplicate(db, tenant_id=job.tenant_id, patient_information=patient_information)
    if duplicate is not None:
        return duplicate, None
    created = create_patient_from_patient_information(
        db, tenant_id=job.tenant_id, created_by_user_id=job.created_by_user_id,
        patient_information=patient_information, source_capture_id=capture.id,
    )
    if created is not None:
        note = similar_existing_note(match)
        return _ai_assign_to_patient(
            db, session=session, capture=capture, patient=created,
            patient_information=patient_information, match_candidate=match, created=True,
            extra_action={"similarExisting": note} if note else None,
        )
    # Detected identity but nothing to match or create (e.g. id/phone-only, no display name): never
    # silent — surface an actionable notice carrying the spoken identity.
    return explicit_no_effect_notice(session=session, patient_information=patient_information, match=match), None


def _load_candidate_patient(db: DbSession, *, tenant_id: uuid.UUID, candidate: dict[str, Any] | None) -> Patient | None:
    """Load the Patient referenced by a match-candidate dict, if any."""
    if not isinstance(candidate, dict) or not candidate.get("patientId"):
        return None
    try:
        return db.execute(
            select(Patient).where(Patient.id == uuid.UUID(str(candidate["patientId"])), Patient.tenant_id == tenant_id)
        ).scalar_one_or_none()
    except (ValueError, KeyError):
        return None


def _strong_duplicate(db: DbSession, *, tenant_id: uuid.UUID, patient_information: dict[str, Any]) -> dict[str, Any] | None:
    """Return a use-existing suggestion when AI creation would strongly duplicate a patient (A-F16).

    Runs the AES-205 duplicate guard at AI-create time (it is otherwise staff-create only): a strong
    hit (national ID / phone / email / exact name) — typically a concurrent create or a front-desk
    record made while the job was in flight — suggests the existing patient instead of splitting it.
    """
    result = find_patient_duplicates(
        db, tenant_id=tenant_id,
        display_name=display_name_from_patient_information(patient_information),
        national_id=patient_information.get("national_id"),
        phone=patient_information.get("phone"),
        email=patient_information.get("email"),
    )
    if not result.get("hasLikelyDuplicate"):
        return None
    top = (result.get("candidates") or [None])[0]
    if not isinstance(top, dict) or not top.get("patientId"):
        return None
    return {
        "schemaVersion": "2026-06-02.patient-match-candidate.v1",
        "decision": "suggested_reassignment", "status": "suggested_reassignment",
        "appliedAutomatically": False, "duplicateGuard": True,
        "patientId": top.get("patientId"), "displayName": top.get("displayName"), "matchedName": top.get("displayName"),
        "spokenName": spoken_name_from_information(patient_information),
        "reason": "A matching patient already exists — use the existing record instead of creating a duplicate.",
        "patientInformation": patient_information,
    }


def _resolve_capture_identity(
    db: DbSession,
    *,
    job: AiJob,
    session: Session | None,
    capture: Capture,
    output: dict[str, Any],
    strictness: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve a capture's identity/assignment intents to ``(patient_match_candidate, action)``.

    The single decision point for the assignment lattice: detach/negation (A-F9), first-identity-wins
    on an unassigned visit (incl. the dead-zone fallback), same-patient name correction (incident
    Fix 1), explicit reassignment (policy-gated per AES-906), and implicit-mention suggestions — each
    ending in an applied effect, a visible suggestion, or a visible notice (INV-SILENT), never silence.
    """
    patient_information = output.get("patient_information")
    detach_basis = detach_intent_basis(output)
    has_identity = isinstance(patient_information, dict) and patient_information_has_explicit_identity(patient_information)

    # A-F9 — detach/negation ("this isn't her / wrong patient, remove"): no replacement identity, so
    # it is handled before the identity gate and only ever suggested (unassign is destructive).
    if detach_basis is not None and session is not None and session.patient_id is not None:
        current = db.get(Patient, session.patient_id)
        return (
            suggested_unassign_candidate(
                session=session,
                patient_information=patient_information if isinstance(patient_information, dict) else None,
                current_display_name=current.display_name if current is not None else None,
                basis=detach_basis,
            ),
            None,
        )

    if not has_identity or session is None:
        return None, None

    assignment_basis = assignment_intent_basis(output)
    match = ai_jobs_pkg.match_patient_from_patient_information(
        db, tenant_id=job.tenant_id, patient_information=patient_information
    )

    # A-F4 — an out-of-context capture must NOT file or create a patient. Downgrade any identity to a
    # suggestion staff can still apply, but never auto-apply/create/rename from a capture the model (or
    # staff) flagged as non-visit content ("remind me to call Ms. Karimi").
    if out_of_context_marker(output) is not None:
        spoken = spoken_name_from_information(patient_information)
        resolved = resolved_match_patient_id(match)
        return (
            {
                **(match or {}),
                "schemaVersion": "2026-06-02.patient-match-candidate.v1",
                "decision": "suggested_reassignment", "status": "suggested_reassignment",
                "appliedAutomatically": False, "outOfContext": True,
                "currentPatientId": str(session.patient_id) if session.patient_id else None,
                "patientId": resolved, "spokenName": spoken, "matchedName": match.get("displayName") if isinstance(match, dict) else None,
                "reason": "Identity heard in an out-of-context capture — not applied. Confirm to file this visit.",
                "patientInformation": patient_information,
            },
            None,
        )

    if session.patient_id is None:
        return _apply_first_identity(
            db, job=job, session=session, capture=capture, patient_information=patient_information,
            match=match, strictness=strictness, assignment_basis=assignment_basis,
        )

    # --- Already-assigned visit ---
    current_patient = db.get(Patient, session.patient_id)
    names = _spoken_names(patient_information)
    resolved_pid = resolved_match_patient_id(match)
    resolves_to_current = resolved_pid is not None and str(resolved_pid) == str(session.patient_id)
    role_permitted = user_can_reassign_session(db, session=session, user_id=capture.created_by_user_id)
    name_is_echo = spoken_name_matches_patient(db, tenant_id=job.tenant_id, patient_id=session.patient_id, names=names)

    # Incident Fix 1 — same-patient name CORRECTION: the mention resolves to the currently-assigned
    # patient (or to nobody better) but the spoken name differs from the stored one. An explicit,
    # role-permitted correction of an AI-created unverified patient renames it in place; anything else
    # becomes a one-tap "Correct name to X?" suggestion (never a silent echo-suppression).
    is_name_correction = bool(names) and not name_is_echo and (resolves_to_current or resolved_pid is None)
    if is_name_correction:
        if (
            assignment_basis == "explicit"
            and role_permitted
            and current_patient is not None
            and is_ai_created_unverified_patient(current_patient)
        ):
            new_name = rename_patient_in_place(
                db, patient=current_patient, patient_information=patient_information,
                actor_user_id=capture.created_by_user_id, source_capture_id=capture.id,
            )
            if new_name is not None:
                candidate = {
                    "schemaVersion": "2026-06-02.patient-match-candidate.v1",
                    "decision": "name_corrected", "status": "name_corrected", "appliedAutomatically": True,
                    "patientId": str(current_patient.id), "displayName": new_name, "spokenName": new_name,
                    "reason": "Renamed this AI-created patient from an explicit spoken correction.",
                    "patientInformation": patient_information,
                }
                action = ai_patient_action_metadata(
                    action="renamed", patient=current_patient, capture=capture,
                    patient_information=patient_information, match_candidate=candidate, created=False,
                )
                return candidate, {**action, "nameCorrection": True}
        return (
            name_correction_suggestion(
                session=session,
                current_display_name=current_patient.display_name if current_patient is not None else None,
                patient_information=patient_information, match=match,
            ),
            None,
        )

    # --- Reassignment to a DIFFERENT patient ---
    if assignment_basis == "explicit" and role_permitted:
        # Deterministic match → reassign (creation is routed through the duplicate guard below).
        if isinstance(match, dict) and match.get("decision") == "matched" and match.get("patientId"):
            assigned_patient, _created = resolve_ai_patient_from_match(
                db, job=job, capture=capture, patient_information=patient_information, patient_match_candidate=match
            )
            if assigned_patient is not None:
                return _ai_assign_to_patient(
                    db, session=session, capture=capture, patient=assigned_patient,
                    patient_information=patient_information, match_candidate=match, created=False,
                )
        auto_top = fuzzy_auto_apply_candidate(match, strictness=strictness, assignment_basis=assignment_basis)
        auto_patient = _load_candidate_patient(db, tenant_id=job.tenant_id, candidate=auto_top)
        if auto_patient is not None:
            spoken_name = spoken_name_from_information(patient_information)
            candidate = {
                **(match or {}), "decision": "matched", "status": "matched",
                "patientId": str(auto_patient.id), "displayName": auto_patient.display_name,
                "appliedAutomatically": True, "autoAppliedCloseMatch": True,
                "matchedName": auto_patient.display_name, "spokenName": spoken_name,
            }
            return _ai_assign_to_patient(
                db, session=session, capture=capture, patient=auto_patient,
                patient_information=patient_information, match_candidate=candidate, created=False,
                extra_action={"closeMatch": True, "matchedName": auto_patient.display_name, "spokenName": spoken_name},
            )
        near_match = near_match_suggestion(match, patient_information=patient_information)
        if near_match is not None:
            return near_match, None
        # An explicit reassignment to a brand-new person (no_match) may create + assign — after the
        # duplicate guard (A-F16). A strong duplicate suggests use-existing instead.
        if isinstance(match, dict) and match.get("decision") == "no_match":
            duplicate = _strong_duplicate(db, tenant_id=job.tenant_id, patient_information=patient_information)
            if duplicate is not None:
                return duplicate, None
            created = create_patient_from_patient_information(
                db, tenant_id=job.tenant_id, created_by_user_id=job.created_by_user_id,
                patient_information=patient_information, source_capture_id=capture.id,
            )
            if created is not None:
                return _ai_assign_to_patient(
                    db, session=session, capture=capture, patient=created,
                    patient_information=patient_information, match_candidate=match, created=True,
                )
        # A-F12 — explicit reassignment that resolved to no applicable patient must never no-op silently.
        return explicit_no_effect_notice(session=session, patient_information=patient_information, match=match), None

    # Explicit but the capturer's role can't reassign (AES-906) → suggestion to the owner, never blocked.
    if assignment_basis == "explicit" and not role_permitted:
        return (
            suggested_reassignment_candidate(
                db, tenant_id=job.tenant_id, session=session,
                patient_information=patient_information, policy_deferred=True,
            ),
            None,
        )

    # Implicit mention of a different patient on an assigned visit → suggestion (echo-suppressed when
    # it resolves to the already-assigned patient with a matching name — that path returned above).
    return (
        suggested_reassignment_candidate(
            db, tenant_id=job.tenant_id, session=session,
            patient_information=patient_information, policy_deferred=False,
        ),
        None,
    )


def _explicit_instruction_unsatisfied(db: DbSession, *, job: AiJob, session: Session, output: dict[str, Any]) -> bool:
    """Whether an explicit assignment/detach instruction was heard but left genuinely unresolved.

    The predicate behind the INV-SILENT completion backstop. True only for a real miss: an explicit
    identity instruction that does NOT already resolve to the assigned patient, or a detach of an
    assigned visit. A mention of the already-assigned patient (echo) and a detach of an already-
    unassigned visit are already satisfied — not silence — so they return False.
    """
    if detach_intent_basis(output) is not None:
        return session.patient_id is not None
    if assignment_intent_basis(output) != "explicit":
        return False
    patient_information = output.get("patient_information")
    if not isinstance(patient_information, dict) or not patient_information_has_explicit_identity(patient_information):
        return False
    if session.patient_id is None:
        return True  # unassigned + explicit identity should always have produced an effect
    match = ai_jobs_pkg.match_patient_from_patient_information(
        db, tenant_id=job.tenant_id, patient_information=patient_information
    )
    resolved = resolved_match_patient_id(match)
    names = _spoken_names(patient_information)
    is_echo = (
        resolved is not None
        and str(resolved) == str(session.patient_id)
        and spoken_name_matches_patient(db, tenant_id=job.tenant_id, patient_id=session.patient_id, names=names)
    )
    return not is_echo


def get_ai_job(db: DbSession, principal: CurrentPrincipal, job_id: str) -> dict[str, Any]:
    """Fetch a tenant-scoped AI processing job."""
    job = db.execute(
        select(AiJob).where(
            AiJob.id == parse_uuid(job_id, "job_id"),
            AiJob.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI processing job not found")
    return ai_job_payload(job)


def require_ai_engine_token(authorization: str = Header(default="")) -> None:
    """Authorize internal AI engine callbacks with a shared service token."""
    expected = f"Bearer {settings.ai_engine_internal_token}"
    if not settings.ai_engine_internal_token or authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid AI engine token")


def get_job_for_worker(db: DbSession, job_id: str) -> AiJob:
    """Fetch a worker-visible job row by ID."""
    try:
        parsed = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id") from exc
    job = db.execute(select(AiJob).where(AiJob.id == parsed)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI job not found")
    return job


def _aftercare_templates_for_synthesis(db: DbSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """Compact list of the tenant's ACTIVE aftercare protocols for the synthesizer to match against."""
    rows = db.execute(
        select(AftercareTemplate).where(
            AftercareTemplate.tenant_id == tenant_id,
            AftercareTemplate.is_active.is_(True),
        )
    ).scalars()
    return [
        {"id": str(template.id), "name": template.name, "procedureType": template.procedure_type, "body": template.body}
        for template in rows
    ]


def worker_job_payload(db: DbSession, job: AiJob) -> dict[str, Any]:
    """Serialize job input needed by the AI engine worker."""
    # Live per-task model + reasoning-effort selection, resolved per request so a change applies to
    # the next job. Each task is a bare model string or a {model, reasoningEffort} object.
    ai_models = ai_models_worker_payload(db)
    if job.job_type == AiJobType.patient_memory:
        return patient_memory_job_payload(db, job, ai_models)
    if job.job_type == AiJobType.qa_draft:
        # Post-session patient Q&A reply draft (AES-402); logic localized in app/services/qa.py.
        from app.services.qa import qa_draft_worker_payload

        return qa_draft_worker_payload(db, job, ai_models)
    if job.job_type == AiJobType.qa_revise:
        # Q&A reply voice edit (AES-402); logic localized in app/services/qa.py.
        from app.services.qa import qa_revise_worker_payload

        return qa_revise_worker_payload(db, job, ai_models)
    capture = None
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
    if capture is not None:
        transcription_context = None
        enrichment_context = None
        if capture.capture_type in (CaptureType.audio, CaptureType.photo, CaptureType.note):
            session = db.execute(
                select(Session).where(Session.id == capture.session_id, Session.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if session is not None:
                if capture.capture_type == CaptureType.audio:
                    transcription_context = build_transcription_context(db, session=session, capture=capture)
                # Image captioning is a gated capability; the gate attaches the enrichment context. Notes
                # are a pure passthrough (decoration removed) — they never get an enrichment context.
                elif capture.capture_type == CaptureType.photo and tenant_has_capability(db, job.tenant_id, IMAGE_CAPTION):
                    enrichment_context = build_capture_enrichment_context(db, session=session, capture=capture)
        return {
            "job": ai_job_payload(job),
            "capture": {
                "id": str(capture.id),
                "tenantId": str(capture.tenant_id),
                "sessionId": str(capture.session_id),
                "type": capture.capture_type.value,
                "status": capture.status.value,
                "metadata": capture.capture_metadata,
                "sourceArtifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
            },
            "transcriptionContext": transcription_context,
            "enrichmentContext": enrichment_context,
            "aiModels": ai_models,
        }
    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
    captures = [
        capture
        for capture in db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == job.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.created_at)
        ).scalars()
        # Out-of-context captures are kept but excluded from the synthesized report.
        if not capture_is_out_of_context(capture)
    ]
    # Stable session context for the synthesizer (captures, prior report draft + changeset,
    # prior-visit treatments, domain descriptor) plus the preferred report language.
    processing_context = build_session_processing_input(db, session)
    processing_context = {
        **processing_context,
        "reportLanguage": tenant_report_language(db, job.tenant_id),
        # The clinic's active aftercare protocols, so the synthesis decides — intelligently, by clinical
        # relevance — which apply this visit and flags any that conflict with the clinician's dictation.
        "aftercareTemplates": _aftercare_templates_for_synthesis(db, job.tenant_id),
    }
    # `reportSynthesis` tells the worker to run the single-pass LLM synthesis (vs the legacy
    # placeholder pipeline). The backend only dispatches this job for synthesis-enabled tenants, so
    # the flag is the explicit contract; a gateway-less worker still degrades to the deterministic
    # baseline via the skip sentinel.
    report_synthesis = session_synthesis_enabled(db, job.tenant_id)
    return {
        "job": ai_job_payload(job),
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "patientId": str(session.patient_id) if session.patient_id else None,
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "reportTemplateKey": session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY,
            "createdAt": session.created_at.isoformat() if session.created_at else None,
            "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
        },
        "captures": [
            {
                "id": str(capture.id),
                "type": capture.capture_type.value,
                "status": capture.status.value,
                "metadata": capture.capture_metadata,
                "sourceArtifactId": str(capture.source_artifact_id) if capture.source_artifact_id else None,
            }
            for capture in captures
        ],
        "reportTemplate": load_report_template(session.report_template_key),
        "sessionProcessingContext": processing_context,
        "reportSynthesis": report_synthesis,
        # Correction-triggered escalation hint (§3.1): the worker runs synthesis on the strongest tier
        # when a user correction (fix-at-source / treatment-overlay / assignment) caused this re-dispatch.
        "escalate": bool(isinstance(job.result_metadata, dict) and job.result_metadata.get("escalate") is True),
        "aiModels": ai_models,
    }


def start_worker_job(
    db: DbSession,
    *,
    job_id: str,
    celery_task_id: str | None,
    retry_count: int,
) -> dict[str, Any]:
    """Mark an AI job running and return its input payload."""
    job = get_job_for_worker(db, job_id)
    if job.status == AiJobStatus.succeeded:
        return worker_job_payload(db, job)

    now = utc_now()
    target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
    if target_skip_reason is not None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target is no longer available")

    job.status = AiJobStatus.running
    job.started_at = job.started_at or now
    job.last_attempted_at = now
    job.attempt_count = (job.attempt_count or 0) + 1
    job.next_retry_at = None
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
        "attempt": job.attempt_count,
        "started_at": now.isoformat(),
    }
    if job.job_type == AiJobType.patient_memory:
        # INV-SNAPSHOT / M-P5: freeze the memory build's inputs NOW (at start) and carry them to
        # completion, so the finished memory's freshness reflects "inputs as of build T" and a visit
        # that changes while the job runs correctly leaves the memory stale.
        from app.services.ai_jobs.orchestration import patient_memory_job_snapshot

        job.result_metadata = {**job.result_metadata, "memory_snapshot": patient_memory_job_snapshot(db, job)}
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
        capture.status = CaptureStatus.processing
    if job.session_id and job.capture_id is None:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
        # The Pro synthesis refinement runs AFTER a deterministic report already exists — keep it
        # visible (a quiet enrichment, not a processing flash). Only flip to `processing` when there
        # is no report yet (the legacy first-pass session job).
        report_model = session.report_model if isinstance(session.report_model, dict) else None
        if not (report_model and report_model.get("sections")):
            session.status = SessionStatus.processing
        # (S-F5, INV-SNAPSHOT) Freeze the job's INPUT capture-set + content signature at START. The
        # synthesis reflects the payload built now; if a fix-at-source capture EDIT lands mid-job, the DB
        # state at completion diverges from these. Completion stamps freshness + records the version from
        # THIS snapshot, and dispatches a follow-up when the current set no longer matches — so a stale
        # report is never marked current and the version store is never keyed to content it doesn't reflect.
        if job.job_type == AiJobType.session_organize:
            from app.services.report_versions import session_capture_set

            start_reportable = reportable_session_captures(db, tenant_id=job.tenant_id, session_id=session.id)
            start_set_hash, start_set_items = session_capture_set(db, session)
            job.result_metadata = {
                **(job.result_metadata or {}),
                "input_signature": session_report_content_signature(start_reportable),
                "input_capture_ids": [str(capture.id) for capture in start_reportable],
                "input_capture_set_hash": start_set_hash,
                "input_capture_set_items": start_set_items,
            }
    db.commit()
    db.refresh(job)
    return worker_job_payload(db, job)


def complete_worker_job(
    db: DbSession,
    *,
    job_id: str,
    output_key: str,
    output: dict[str, Any],
    usage: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist successful AI engine output."""
    job = get_job_for_worker(db, job_id)
    # Fair-use metering: record this job's REAL gateway spend against the clinic/seat period counter.
    # Best-effort — a metering hiccup must never fail job completion.
    try:
        from app.services.ai_usage import record_job_usage

        record_job_usage(
            db,
            tenant_id=job.tenant_id,
            user_id=job.created_by_user_id,
            job_type=job.job_type,
            usage_records=usage,
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to record AI usage", extra={"job_id": job_id})
    if job.job_type == AiJobType.patient_memory:
        return complete_patient_memory_worker_job(db, job=job, output=output)
    if job.job_type == AiJobType.qa_draft:
        # Post-session patient Q&A reply draft (AES-402); logic localized in app/services/qa.py.
        from app.services.qa import complete_qa_draft_worker_job

        return complete_qa_draft_worker_job(db, job=job, output=output)
    if job.job_type == AiJobType.qa_revise:
        # Q&A reply voice edit (AES-402); logic localized in app/services/qa.py.
        from app.services.qa import complete_qa_revise_worker_job

        return complete_qa_revise_worker_job(db, job=job, output=output)
    if job.capture_id is None:
        return complete_session_worker_job(db, job=job, output_key=output_key, output=output)
    capture = db.execute(
        select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")

    completed_at = utc_now()
    # INV-LOCK: hold the session row for the whole assignment write so two capture completions for the
    # same session serialize instead of clobbering each other's timeline event (A-F1/A-F2).
    session = _lock_session_row(db, tenant_id=job.tenant_id, session_id=capture.session_id)
    strictness = tenant_match_strictness(db, job.tenant_id)
    patient_information = output.get("patient_information")
    # Resolve identity/assignment intents to a single (candidate, action) decision. The full lattice —
    # first-identity-wins (+ dead-zone), same-patient name correction, explicit/policy-gated
    # reassignment, detach, and suggestions — lives in _resolve_capture_identity so every branch ends
    # in an applied effect, a visible suggestion, or a visible notice (INV-SILENT). Matching runs for
    # both tiers (it is the core memory-accuracy feature); capabilities gate only enrichment + report.
    patient_match_candidate, ai_patient_action = _resolve_capture_identity(
        db, job=job, session=session, capture=capture, output=output, strictness=strictness
    )
    # INV-SILENT completion assertion (defensive backstop): an explicit instruction that changed
    # nothing AND is not already satisfied by the current assignment must never vanish — surface a
    # "couldn't apply — assign manually" notice. Legitimate echoes (a mention of the already-assigned
    # patient, a detach of an already-unassigned visit) are excluded, so this fires only on a true miss.
    if (
        patient_match_candidate is None
        and ai_patient_action is None
        and session is not None
        and _explicit_instruction_unsatisfied(db, job=job, session=session, output=output)
    ):
        logger.warning(
            "INV-SILENT backstop: explicit assignment instruction produced no visible outcome",
            extra={"job_id": str(job.id), "capture_id": str(capture.id), "session_id": str(session.id)},
        )
        patient_match_candidate = explicit_no_effect_notice(
            session=session,
            patient_information=patient_information if isinstance(patient_information, dict) else {},
            match=None,
        )
    output_with_match = (
        {**output, "patient_match_candidate": patient_match_candidate, "ai_patient_action": ai_patient_action}
        if patient_match_candidate is not None
        else output
    )
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        output_key: output_with_match,
        "ai_processing": output_with_match,
    }
    ooc_marker = out_of_context_marker(output)
    if ooc_marker is not None:
        capture.capture_metadata = {**capture.capture_metadata, "out_of_context": ooc_marker}
    # §7 uncertainty → needs-input for captions: a low-confidence / flagged photo caption raises a
    # per-capture review chip (reusing the existing capture-chip surface). Cleared when a re-run
    # produces a confident caption, so the chip never lingers after the caption improves.
    if capture.capture_type == CaptureType.photo:
        review_marker = caption_review_marker(output)
        metadata = dict(capture.capture_metadata or {})
        if review_marker is not None:
            metadata["needs_review"] = review_marker
        else:
            metadata.pop("needs_review", None)
        capture.capture_metadata = metadata
    # Pro folds each in-context capture into the synthesized live report (E2). The capture is
    # marked `pending` here; the report job flips it to `added` once it's folded in. Basic is a
    # chronological render with no synthesis, so it carries no contribution effect, and an
    # out-of-context capture is set aside rather than contributed.
    if tenant_has_capability(db, job.tenant_id, LIVE_REPORT_SYNTHESIS) and ooc_marker is None:
        capture.capture_metadata = {
            **capture.capture_metadata,
            "report_contribution": report_contribution_effect("pending", had_append_intent=has_append_intent(output)),
        }
    if patient_match_candidate is not None:
        capture.capture_metadata = {**capture.capture_metadata, "patient_match_candidate": patient_match_candidate}
        if ai_patient_action is not None:
            capture.capture_metadata = {**capture.capture_metadata, "ai_patient_action": ai_patient_action}
        if session is not None and session.patient_id is None:
            session_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
            session.extracted_metadata = {**session_metadata, "patient_match_candidate": patient_match_candidate}
    capture.status = CaptureStatus.processed
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.last_error = None
    job.retry_reason = None
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "capture_status": capture.status.value,
        "completed_at": completed_at.isoformat(),
        "patient_match_candidate": patient_match_candidate,
        "ai_patient_action": ai_patient_action,
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="capture",
        target_id=capture.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    if capture.session_id is not None:
        # This capture succeeded, so the gateway is up: make failed-retryable siblings
        # eligible to retry now instead of waiting for the periodic recovery beat.
        requeue_failed_session_captures(db, tenant_id=job.tenant_id, session_id=capture.session_id)
    db.commit()
    db.refresh(job)
    # Captures in a session process strictly in order: dispatch the next one now that this
    # capture's assignment has been applied to the session.
    if capture.session_id is not None:
        dispatch_next_session_capture(db, tenant_id=job.tenant_id, session_id=capture.session_id)
        # Once the chain has drained, rebuild the live report from the cumulative session state
        # deterministically (no-op while more captures are still in flight).
        regenerate_session_report_if_idle(
            db,
            tenant_id=job.tenant_id,
            session_id=capture.session_id,
            created_by_user_id=job.created_by_user_id,
        )
        # Deterministic before/after photo pairing over the caption pairing attributes (not an LLM
        # job). Idempotent + cheap; recomputed as each photo's caption lands so the final pass is
        # complete once the chain drains.
        if session is not None:
            from app.services.photo_pairing import recompute_session_photo_pairing

            recompute_session_photo_pairing(db, session=session)
            db.commit()
        # NOTE: patient AI memory is intentionally NOT refreshed on session/capture completion. It is
        # refreshed only when a human is about to look at the patient — the patient page / line-up
        # recap opens while stale (1st class), the patient is added to the line-up (2nd class) — plus
        # the Celery-beat quiescence sweep for patients nobody touched (3rd class). See orchestration.
        # maybe_refresh_stale_patient_memory / sweep_stale_patient_memory.
    return {"job": ai_job_payload(job)}


def progress_worker_job(
    db: DbSession,
    *,
    job_id: str,
    output_key: str,
    output: dict[str, Any],
    stage: str | None,
) -> dict[str, Any]:
    """Persist partial AI engine output without completing the job."""
    job = get_job_for_worker(db, job_id)
    if job.status == AiJobStatus.succeeded:
        return {"job": ai_job_payload(job)}

    now = utc_now()
    job.status = AiJobStatus.running
    job.result_metadata = {
        **(job.result_metadata or {}),
        "progress_stage": stage or output_key,
        "progress_output_key": output_key,
        "progress_updated_at": now.isoformat(),
    }

    if job.capture_id is not None:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target capture is missing")
        capture.status = CaptureStatus.processing
        capture.capture_metadata = {
            **(capture.capture_metadata or {}),
            output_key: output,
            "ai_processing": output,
        }
        db.commit()
        db.refresh(job)
        return {"job": ai_job_payload(job)}

    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")

    extracted_metadata = output.get("extracted_metadata")
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    if isinstance(output.get("summary"), str):
        session.summary = str(output["summary"])
        session.generated_summary = str(output["summary"])
    if isinstance(output.get("report"), str):
        report_model = structured_report_from_markdown_body(
            title=session.title,
            body=str(output["report"]),
            template_key=session.report_template_key,
            findings=extracted_metadata.get("findings") if isinstance(extracted_metadata, dict) else None,
            source_capture_ids=metadata.get("source_capture_ids") if isinstance(metadata.get("source_capture_ids"), list) else None,
            generated_at=now.isoformat(),
        )
        session.report_model = report_model
        session.generated_report = render_report_body_markdown(
            report_model,
            db=db,
            session=session,
        )
    if isinstance(output.get("report_template_key"), str):
        session.report_template_key = str(output["report_template_key"])
    if isinstance(extracted_metadata, dict):
        metadata = {**metadata, **extracted_metadata}
    incoming_processing_status = (
        extracted_metadata.get("processing_status")
        if isinstance(extracted_metadata, dict) and isinstance(extracted_metadata.get("processing_status"), dict)
        else {}
    )
    metadata = {
        **metadata,
        "processing_status": {
            **(metadata.get("processing_status") if isinstance(metadata.get("processing_status"), dict) else {}),
            **incoming_processing_status,
            "state": "processing",
            "stage": stage or output_key,
            "updated_at": now.isoformat(),
            "source": "mock-ai-engine",
        },
        "generated_output_stale": True,
    }
    session.extracted_metadata = metadata
    session.status = SessionStatus.processing
    session.updated_at = now
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def _synthesis_output_has_body(output: dict[str, Any]) -> bool:
    """Whether a synthesis output has ANY content block across its sections (S-F12 hollow-report floor).

    A structurally-valid synthesis can pass the summary gate yet carry zero blocks in every section — a
    hollow report that would replace the deterministic baseline (which held the real transcripts/photos)
    with a near-empty one. Checked AFTER finalize, so the treatment-performed section rendered from a
    non-empty treatments[] counts as body; only an all-empty output is hollow.
    """
    for section in output.get("sections") or []:
        if isinstance(section, dict) and section.get("blocks"):
            return True
    return False


def _complete_session_synthesis_skip(
    db: DbSession, *, job: AiJob, output_key: str, session: Session, reason: str | None = None
) -> dict[str, Any]:
    """Persist a synthesis SKIP: the worker couldn't synthesize, so the deterministic baseline stands.

    Mark the baseline's captures contributed (so the freshness strip reads "current" and we don't loop
    re-dispatching a synthesis that keeps skipping) and the job succeeded — without touching the
    report (Basic + gateway-less run zero AI and must never break).
    """
    completed_at = utc_now()
    reportable = reportable_session_captures(db, tenant_id=job.tenant_id, session_id=session.id)
    capture_ids = [str(capture.id) for capture in reportable]
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    contribution_summary = None
    if tenant_has_capability(db, job.tenant_id, LIVE_REPORT_SYNTHESIS):
        contribution_summary = mark_session_report_contributions(
            db, session=session, generated_at=completed_at.isoformat(), source_capture_ids=capture_ids
        )
    session.extracted_metadata = {
        **metadata,
        "generated_output_stale": False,
        "report_synthesis": {
            "status": "skipped",
            "captureIds": capture_ids,
            "signature": session_report_content_signature(reportable),
            "generatedAt": completed_at.isoformat(),
        },
        **({"report_contribution_summary": contribution_summary} if contribution_summary is not None else {}),
    }
    session.updated_at = completed_at
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.last_error = None
    job.retry_reason = None
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "synthesis_skipped": True,
        "synthesis_skip_reason": reason,
        "completed_at": completed_at.isoformat(),
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="session",
        target_id=session.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value, "synthesis_skipped": True},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def complete_session_worker_job(
    db: DbSession,
    *,
    job: AiJob,
    output_key: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Persist successful session-level AI engine output."""
    if job.session_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job is missing session_id")
    # (S-F15, INV-LOCK) Serialize this completion against the concurrent user-state writers
    # (dose confirmations / safety-flag rejections / overlay edits) that the capture screen actively
    # encourages DURING the "Organizing with AI" window: take a row lock so their read-modify-write of
    # extracted_metadata can't be clobbered by, or clobber, this handler's rebuild. No-op on SQLite.
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id).with_for_update()
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target session is missing")

    # Synthesis skip sentinel — gateway-less / malformed synthesis. Keep the deterministic baseline.
    if output.get("synthesis_skipped") is True or output.get("status") == "skipped":
        reason = output.get("reason") if isinstance(output.get("reason"), str) else None
        return _complete_session_synthesis_skip(db, job=job, output_key=output_key, session=session, reason=reason)

    completed_at = utc_now()
    summary = output.get("summary")
    structured_output = output.get("structured_report")
    if not isinstance(structured_output, dict):
        structured_output = output.get("report_body")
    report = output.get("report")
    extracted_metadata = output.get("extracted_metadata")
    if not isinstance(summary, str) or not isinstance(extracted_metadata, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session job output")
    if isinstance(structured_output, dict):
        session_processing_output = structured_output
    elif isinstance(report, str):
        session_processing_output = session_processing_output_from_legacy_report(output, generated_at=completed_at.isoformat())
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session job output")

    # Pro single-pass synthesis path: validate every captureId against this session's captures (drop
    # unknowns), finalize treatments (correction/addition/carry-forward/supersede + uncertainty
    # confirmation items), and re-render the treatment-performed section FROM treatments[] so the
    # prose mirror can never diverge from the queryable store.
    is_synthesis = session_processing_output.get("schemaVersion") == SESSION_SYNTHESIS_OUTPUT_VERSION
    reportable_captures: list[Capture] = []
    synthesis_capture_ids: list[str] = []
    synthesis_treatments: list[dict[str, Any]] = []
    synthesis_review: list[dict[str, Any]] = []
    if is_synthesis:
        reportable_captures = reportable_session_captures(db, tenant_id=job.tenant_id, session_id=session.id)
        synthesis_capture_ids = [str(capture.id) for capture in reportable_captures]
        prior_ids = prior_visit_capture_ids(bounded_prior_visit_treatments(db, session))
        session_processing_output, synthesis_treatments, synthesis_review = finalize_session_synthesis_output(
            session_processing_output,
            valid_capture_ids=synthesis_capture_ids,
            prior_visit_capture_ids=prior_ids,
        )
        # (S-F12) Hollow-report floor: a valid-JSON synthesis with a non-empty summary but zero content
        # blocks across every section (including the treatment-performed prose re-rendered from
        # treatments[]) is malformed — keep the deterministic baseline instead of blanking the report.
        if not _synthesis_output_has_body(session_processing_output):
            return _complete_session_synthesis_skip(
                db, job=job, output_key=output_key, session=session, reason="hollow_synthesis"
            )
        # (S-F3) Zero treatments over the SAME captures a prior synthesis extracted some from is far more
        # likely a transient miss than a real change — never silently downgrade a Pro visit to
        # no-treatments. Keep the prior rows, re-render the prose from them, and raise a review item.
        prior_md = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
        prior_treatments = [item for item in (prior_md.get("treatments") or []) if isinstance(item, dict)]
        prior_synth = prior_md.get("report_synthesis") if isinstance(prior_md.get("report_synthesis"), dict) else {}
        prior_synth_ids = prior_synth.get("captureIds") if isinstance(prior_synth.get("captureIds"), list) else []
        same_capture_set = set(str(value) for value in prior_synth_ids) == set(synthesis_capture_ids)
        if not synthesis_treatments and prior_treatments and same_capture_set:
            synthesis_treatments = prior_treatments
            session_processing_output = set_treatment_performed_section(
                session_processing_output, render_treatment_performed_blocks(prior_treatments)
            )
            synthesis_review = [
                *synthesis_review,
                {
                    "category": "treatments_vanished",
                    "reason": "This re-synthesis found no treatments though the previous one recorded some "
                    "for the same captures — confirm before they are removed.",
                    "product": None,
                    "sourceCaptureIds": [],
                },
            ]

    structured_findings = session_processing_output.get("findings")
    if isinstance(structured_findings, list) and not isinstance(extracted_metadata.get("findings"), list):
        extracted_metadata = {**extracted_metadata, "findings": structured_findings}
    if is_synthesis:
        # treatments[] → the queryable store (recall / lot tracking / smart lists); treatment_review →
        # the existing needs-input surface (see _session_needs_input_item).
        extracted_metadata = {
            **extracted_metadata,
            "treatments": synthesis_treatments,
            "treatment_review": synthesis_review,
        }
    structured_source_references = session_processing_output.get("sourceReferences")
    if isinstance(structured_source_references, list):
        extracted_metadata = {
            **extracted_metadata,
            "source_capture_ids": [
                reference["captureId"]
                for reference in structured_source_references
                if isinstance(reference, dict) and isinstance(reference.get("captureId"), str)
            ],
        }

    patient_match = (
        match_patient_from_metadata(db, tenant_id=job.tenant_id, extracted_metadata=extracted_metadata)
        if session.patient_id is None
        else None
    )
    if patient_match:
        extracted_metadata = {**extracted_metadata, "patient_match": patient_match}
        # AI output can propose a deterministic match, but DB-owned patient
        # assignment is changed only by explicit assignment flows.

    previous_versions = []
    previous_metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    raw_previous_versions = previous_metadata.get("processed_versions")
    if isinstance(raw_previous_versions, list):
        previous_versions = [version for version in raw_previous_versions if isinstance(version, dict)]
    if session.generated_summary or session.generated_report or previous_metadata:
        previous_metadata_snapshot = {
            key: value
            for key, value in previous_metadata.items()
            if key not in {"processed_versions", "generated_output_stale", "stale_reason", "stale_at"}
        }
        previous_versions.append(
            {
                "summary": session.generated_summary,
                "report": session.generated_report,
                "extracted_metadata": previous_metadata_snapshot,
                "report_template_key": session.report_template_key,
                "organization_source": session.organization_source.value,
                "replaced_at": completed_at.isoformat(),
            }
        )

    session.generated_summary = summary
    session.summary = summary
    session.report_template_key = str(output.get("report_template_key") or session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY)
    report_model = report_model_from_session_processing_output(
        title=session.title,
        template_key=session.report_template_key,
        output=session_processing_output,
    )
    session.report_model = report_model
    session.generated_report = render_report_body_markdown(
        report_model,
        db=db,
        session=session,
    )
    preserved_assignment = {
        key: previous_metadata[key]
        for key in (
            "patient_assignment_source",
            "patient_assignment_reason",
            "ai_patient_action",
            "active_patient_assignment_action",
            "patient_assignment_timeline",
        )
        if key in previous_metadata and key not in extracted_metadata
    }
    preserved_patient_match = {
        key: previous_metadata[key]
        for key in ("patient_match", "patient_match_candidate")
        if session.patient_id is None and key in previous_metadata and key not in extracted_metadata
    }
    # The clinician's carried-forward dose confirmations (Q3), aftercare opt-outs, and safety-flag
    # rejections are USER state, not AI output — a re-synthesis regenerates treatments/review/flags but
    # must not silently revert them (or the confirmed dose / removed aftercare / rejected safety flag
    # reappears). Preserve all three across regeneration.
    prior_confirmed = previous_metadata.get("confirmed_carried_forward")
    prior_dismissed_aftercare = previous_metadata.get("dismissed_aftercare")
    prior_rejected_safety_flags = previous_metadata.get("rejected_safety_flags")
    prior_rejected_records = previous_metadata.get("rejected_safety_flag_records")
    # The user-authored treatment overlay (AES-1101) is user state too — re-bind each edit to the freshly
    # synthesized rows (exact key → bound; priorKey-first → re-bind across an area re-key; shared
    # source-capture + normalized area → re-bind; else PARK the entry as an orphan — never delete a human
    # edit, S-F4), refreshing aiValue so a fresh-extraction disagreement surfaces via {aiValue, value}.
    # Prior orphans are re-fed so a row that reappears re-binds out of the orphan list. On the legacy path
    # (no fresh treatments) preserve overlay + orphans as-is.
    prior_treatment_overlay = previous_metadata.get("treatment_overlay")
    prior_overlay_orphans_raw = previous_metadata.get("treatment_overlay_orphans")
    prior_overlay_entries = [entry for entry in prior_treatment_overlay if isinstance(entry, dict)] if isinstance(prior_treatment_overlay, list) else []
    prior_overlay_orphans = [entry for entry in prior_overlay_orphans_raw if isinstance(entry, dict)] if isinstance(prior_overlay_orphans_raw, list) else []
    if is_synthesis:
        rebound_treatment_overlay, rebound_overlay_orphans = rebind_treatment_overlay(
            synthesis_treatments, [*prior_overlay_entries, *prior_overlay_orphans]
        )
    else:
        rebound_treatment_overlay, rebound_overlay_orphans = prior_overlay_entries, prior_overlay_orphans
    preserved_confirmations = {
        **(
            {"confirmed_carried_forward": [value for value in prior_confirmed if isinstance(value, str)]}
            if isinstance(prior_confirmed, list) and prior_confirmed
            else {}
        ),
        **(
            {"dismissed_aftercare": [value for value in prior_dismissed_aftercare if isinstance(value, str)]}
            if isinstance(prior_dismissed_aftercare, list) and prior_dismissed_aftercare
            else {}
        ),
        **(
            {"rejected_safety_flags": [value for value in prior_rejected_safety_flags if isinstance(value, str)]}
            if isinstance(prior_rejected_safety_flags, list) and prior_rejected_safety_flags
            else {}
        ),
        # Rich rejection records (key, kind, sourceCaptureIds) let a rejection follow a flag across a
        # re-synthesis that rewords its text (S-F7) — preserved alongside the plain key list.
        **(
            {"rejected_safety_flag_records": [record for record in prior_rejected_records if isinstance(record, dict)]}
            if isinstance(prior_rejected_records, list) and prior_rejected_records
            else {}
        ),
        **({"treatment_overlay": rebound_treatment_overlay} if rebound_treatment_overlay else {}),
        **({"treatment_overlay_orphans": rebound_overlay_orphans} if rebound_overlay_orphans else {}),
    }
    # (S-F9) Preserve a correction-set escalation marker that landed DURING this job so the follow-up
    # dispatch escalates (the rebuild below otherwise wipes it — it is not an AI artifact).
    preserved_control = {
        SYNTHESIS_ESCALATE_KEY: True
    } if previous_metadata.get(SYNTHESIS_ESCALATE_KEY) is True else {}
    # The synthesized live report is a Pro capability: mark the captures it folded in as
    # contributed and record the included / set-aside counts for the report meta strip.
    report_contribution_summary: dict[str, int] | None = None
    synthesized = tenant_has_capability(db, job.tenant_id, LIVE_REPORT_SYNTHESIS)
    if synthesized:
        report_source_ids = extracted_metadata.get("source_capture_ids") if isinstance(extracted_metadata.get("source_capture_ids"), list) else None
        report_contribution_summary = mark_session_report_contributions(
            db, session=session, generated_at=completed_at.isoformat(), source_capture_ids=report_source_ids
        )
    # (S-F5, INV-SNAPSHOT) Stamp freshness from the job-START snapshot, not the completion-time DB. If a
    # fix-at-source capture EDIT landed mid-job, the current content signature no longer matches what this
    # job actually synthesized — so we mark it NOT current (stale) and force a follow-up, instead of
    # stamping a stale report "current" for the post-edit signature (which would suppress the follow-up).
    start_snapshot = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    start_signature = start_snapshot.get("input_signature")
    start_capture_ids = start_snapshot.get("input_capture_ids") if isinstance(start_snapshot.get("input_capture_ids"), list) else synthesis_capture_ids
    start_set_hash = start_snapshot.get("input_capture_set_hash")
    start_set_items = start_snapshot.get("input_capture_set_items")
    current_signature = session_report_content_signature(reportable_captures) if is_synthesis else None
    input_matches_current = (not is_synthesis) or start_signature is None or start_signature == current_signature
    session.extracted_metadata = {
        **preserved_assignment,
        **preserved_patient_match,
        **extracted_metadata,
        **preserved_confirmations,
        **preserved_control,
        "session_processing_output": session_processing_output,
        # A mid-job content edit (input != current) leaves the report stale so the floor + a fresh
        # synthesis re-run against the new content; otherwise the synthesis is current.
        "generated_output_stale": is_synthesis and not input_matches_current,
        "processed_versions": previous_versions[-5:],
        **({"report_contribution_summary": report_contribution_summary} if report_contribution_summary is not None else {}),
        # Mark the synthesis current for the exact reportable content it was BUILT from (the START
        # snapshot) so a later deterministic regen doesn't clobber the LLM report; a mid-job edit stamps
        # `stale` so the floor rebuilds and re-synthesizes.
        **(
            {
                "report_synthesis": {
                    "status": "current" if input_matches_current else "stale",
                    "captureIds": start_capture_ids,
                    "signature": start_signature if start_signature is not None else current_signature,
                    "generatedAt": completed_at.isoformat(),
                }
            }
            if is_synthesis
            else {}
        ),
    }
    # Persist this visit's kept safety flags (allergy/contraindication/consent) onto the patient so
    # they surface cross-visit at the point of care. Only when the synthesis produced the field — a
    # skip sentinel (gateway-less / malformed) leaves the field absent so prior flags are untouched.
    if session.patient_id is not None and isinstance(session.extracted_metadata.get("safety_flags"), list):
        safety_patient = db.get(Patient, session.patient_id)
        if safety_patient is not None:
            sync_patient_safety_flags(safety_patient, session)
            # Apply the synthesis job's cross-visit safety-reconcile (D7) decisions over the freshly
            # synced union: hide meaning-duplicates, annotate supersedes. Best-effort (raw union floor).
            reconciliation = session.extracted_metadata.get("safety_reconciliation")
            if isinstance(reconciliation, dict):
                apply_safety_reconciliation(safety_patient, reconciliation)
    # Snapshot this synthesis as a content-addressed report_version (pipeline-versioning): a future undo
    # that returns the session to this capture set restores it deterministically (no re-synthesis).
    if is_synthesis:
        # Key the version by the job-START capture set (S-F5) so a mid-job edit can't store pre-edit
        # artifacts under the post-edit content hash (a deterministic wrong-restore later).
        version_capture_set = (
            (start_set_hash, start_set_items)
            if isinstance(start_set_hash, str) and isinstance(start_set_items, list)
            else None
        )
        record_report_version(
            db, session, generated_by="ai-engine", generated_at=completed_at, capture_set=version_capture_set
        )
    # (S-F10) Settle status only from a transient processing/draft state — never stomp a clinician who
    # hit "start review" (reviewing) while a slow synthesis was in flight back to needs_review.
    if session.status in {SessionStatus.processing, SessionStatus.draft}:
        session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
    session.organization_source = OrganizationSource.ai_engine
    session.updated_at = completed_at
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.last_error = None
    job.retry_reason = None
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "output_key": output_key,
        "session_processing_output_version": session_processing_output.get("schemaVersion"),
        "session_status": session.status.value,
        "completed_at": completed_at.isoformat(),
        "patient_match": patient_match,
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="session",
        target_id=session.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    if is_synthesis:
        # The LLM write is FINAL on the synthesis path — do NOT re-run the deterministic regen (it
        # would clobber the synthesized report). Re-dispatch synthesis if a capture landed mid-job
        # (debounced + guarded), so a late capture still gets folded in — and FORCE it when a mid-job
        # content EDIT means the current set no longer matches what this job synthesized (S-F5), where
        # every capture is already contributed so the uncontributed-capture guard wouldn't fire.
        maybe_dispatch_session_synthesis(
            db,
            tenant_id=job.tenant_id,
            session_id=job.session_id,
            created_by_user_id=job.created_by_user_id,
            force=not input_matches_current,
        )
    elif job.session_id is not None:
        # Legacy/placeholder path: deterministic regen is the source of truth.
        regenerate_session_report_if_idle(
            db,
            tenant_id=job.tenant_id,
            session_id=job.session_id,
            created_by_user_id=job.created_by_user_id,
        )
    # Patient AI memory is NOT refreshed here — it is read/line-up-triggered (when a human is about to
    # look at the patient) + a background sweep. See maybe_refresh_stale_patient_memory.
    return {"job": ai_job_payload(job)}


def retry_worker_job(
    db: DbSession,
    *,
    job_id: str,
    error_message: str,
    celery_task_id: str | None,
    retry_count: int,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    """Persist a failed attempt before Celery retries it."""
    job = get_job_for_worker(db, job_id)
    if not ai_job_retryable(job):
        db.commit()
        return {"job": ai_job_payload(job)}

    now = utc_now()
    schedule_retry(job, now=now, error_message=error_message, retry_reason=retry_reason)
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
    }
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def fail_worker_job(
    db: DbSession,
    *,
    job_id: str,
    error_message: str,
    celery_task_id: str | None,
    retry_count: int,
    retry_reason: str | None = None,
) -> dict[str, Any]:
    """Persist exhausted Celery retry state while keeping backend retry durable."""
    job = get_job_for_worker(db, job_id)
    now = utc_now()
    if ai_job_retryable(job):
        schedule_retry(job, now=now, error_message=error_message, retry_reason=retry_reason)
    else:
        mark_job_non_retryable(
            job,
            now=now,
            reason=job.retry_reason or retry_reason or "non_retryable",
            error_message=error_message,
        )
    job.result_metadata = {
        **(job.result_metadata or {}),
        "celery_task_id": celery_task_id,
        "celery_retry_count": retry_count,
        "attempt": job.attempt_count,
        "terminal_error": error_message,
    }
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is not None and not ai_job_retryable(job):
            capture.status = CaptureStatus.needs_attention
        elif capture is not None and capture.status != CaptureStatus.deleted:
            capture.status = CaptureStatus.processing
    if job.session_id and job.capture_id is None:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        # A synthesis refinement that fails terminally must NOT mark the session failed — the
        # deterministic baseline is already a complete report (terminal failure → session still
        # "complete"). Only the legacy first-pass session job (no report yet) flips to failed.
        report_model = session.report_model if session is not None and isinstance(session.report_model, dict) else None
        has_baseline_report = bool(report_model and report_model.get("sections"))
        if session is not None and not has_baseline_report:
            if not ai_job_retryable(job):
                session.status = SessionStatus.failed
            else:
                session.status = SessionStatus.processing
    # A terminally-failed Q&A draft/revise must leave a VISIBLE failed state on its target question —
    # otherwise the inbox shows "Drafting…" forever (the self-heal deliberately skips an in-flight
    # draft). Delegated to services/qa so the state machine stays in one place (Q-7).
    if job.job_type in (AiJobType.qa_draft, AiJobType.qa_revise) and not ai_job_retryable(job):
        from app.services.qa import mark_qa_job_failed

        mark_qa_job_failed(db, job)
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.fail",
        target_type="capture" if job.capture_id else "session",
        target_id=job.capture_id or job.session_id,
        details={"job_id": str(job.id), "error": error_message, "retry_count": retry_count},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}
