"""Worker job lifecycle: payload assembly, start/progress/complete/retry/fail, and AI assignment."""
import uuid
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

# ``match_patient_from_patient_information`` is resolved through the package namespace (see
# intents.py) so package-level monkeypatching keeps working on the worker path too.
import app.services.ai_jobs as ai_jobs_pkg
from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import (
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
    NOTE_DECORATION,
    tenant_has_capability,
)
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    patient_assignment_event,
)
from app.services.patient_matching import match_patient_from_metadata
from app.services.patients import create_patient_from_patient_information, patient_information_has_explicit_identity
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
    report_model_from_session_processing_output,
    session_processing_output_from_legacy_report,
)
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
    fuzzy_auto_apply_candidate,
    near_match_suggestion,
    out_of_context_marker,
    should_apply_identity_assignment,
    spoken_name_from_information,
    suggested_reassignment_candidate,
)
from app.services.ai_jobs.orchestration import (
    complete_patient_memory_worker_job,
    dispatch_next_session_capture,
    maybe_dispatch_patient_memory_job,
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
) -> None:
    """Assign a session/capture set to an AI-selected patient with provenance."""
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
                # Image captions (photo) and note decoration (note) are gated capabilities; the gate attaches the context.
                elif tenant_has_capability(
                    db, job.tenant_id, IMAGE_CAPTION if capture.capture_type == CaptureType.photo else NOTE_DECORATION
                ):
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
    processing_context = {**processing_context, "reportLanguage": tenant_report_language(db, job.tenant_id)}
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
    db.commit()
    db.refresh(job)
    return worker_job_payload(db, job)


def complete_worker_job(
    db: DbSession,
    *,
    job_id: str,
    output_key: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    """Persist successful AI engine output."""
    job = get_job_for_worker(db, job_id)
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
    session = db.execute(
        select(Session).where(Session.id == capture.session_id, Session.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    patient_match_candidate = None
    ai_patient_action = None
    patient_information = output.get("patient_information")
    # Intelligent patient matching (match/create/reassign/suggest) runs for both tiers — it is the
    # core memory-accuracy feature. Capabilities gate enrichment (captions/decoration) and the
    # synthesized report below; matching itself is never gated.
    if (
        isinstance(patient_information, dict)
        and patient_information_has_explicit_identity(patient_information)
    ):
        assignment_basis = assignment_intent_basis(output)
        strictness = tenant_match_strictness(db, job.tenant_id)
        has_existing_patient = session is not None and session.patient_id is not None
        wants_apply = should_apply_identity_assignment(
            has_session=session is not None,
            has_existing_patient=has_existing_patient,
            assignment_basis=assignment_basis,
        )
        # AES-906 (policy-aware intent): an explicit reassignment of an already-assigned visit
        # auto-applies only if the *capturer's* role is permitted to reassign (AES-905). If not, it
        # is routed to the owner as a suggestion (`policy_deferred`) — never applied silently, never
        # blocked. Initial filing of an unassigned visit is the capture-first floor and is not gated.
        reassignment_blocked_by_policy = (
            wants_apply
            and has_existing_patient
            and session is not None
            and not user_can_reassign_session(db, session=session, user_id=capture.created_by_user_id)
        )
        # First identity on an unassigned visit is always applied; once a patient is
        # assigned, only an explicit (re)assignment instruction the capturer is permitted to make
        # overrides it. An implicit mention — or a reassignment the capturer's role can't make —
        # becomes a suggestion, not a silent change.
        if wants_apply and not reassignment_blocked_by_policy:
            patient_match_candidate = ai_jobs_pkg.match_patient_from_patient_information(
                db,
                tenant_id=job.tenant_id,
                patient_information=patient_information,
            )
            assigned_patient, created_patient = resolve_ai_patient_from_match(
                db,
                job=job,
                capture=capture,
                patient_information=patient_information,
                patient_match_candidate=patient_match_candidate,
            )
            if assigned_patient is not None:
                ai_patient_action = ai_patient_action_metadata(
                    action="created_and_assigned" if created_patient else "matched_and_assigned",
                    patient=assigned_patient,
                    capture=capture,
                    patient_information=patient_information,
                    match_candidate=patient_match_candidate,
                    created=created_patient,
                )
                assign_session_to_ai_patient(
                    db,
                    session=session,
                    capture=capture,
                    patient=assigned_patient,
                    action=ai_patient_action,
                )
            else:
                # Apply was intended but the match is only a confident fuzzy one. Under
                # balanced/lenient strictness a single high-confidence variant with an explicit
                # instruction auto-applies (reversible, with notify); the national-ID conflict
                # guard and ambiguity always win. Otherwise surface a one-tap suggestion instead
                # of a silent no-op (never silently apply a fuzzy name).
                auto_top = fuzzy_auto_apply_candidate(
                    patient_match_candidate, strictness=strictness, assignment_basis=assignment_basis
                )
                auto_patient = None
                if auto_top is not None:
                    try:
                        auto_patient = db.execute(
                            select(Patient).where(
                                Patient.id == uuid.UUID(str(auto_top["patientId"])),
                                Patient.tenant_id == job.tenant_id,
                            )
                        ).scalar_one_or_none()
                    except (ValueError, KeyError):
                        auto_patient = None
                if auto_patient is not None:
                    spoken_name = spoken_name_from_information(patient_information)
                    patient_match_candidate = {
                        **patient_match_candidate,
                        "decision": "matched",
                        "status": "matched",
                        "patientId": str(auto_patient.id),
                        "displayName": auto_patient.display_name,
                        "appliedAutomatically": True,
                        "autoAppliedCloseMatch": True,
                        "matchedName": auto_patient.display_name,
                        "spokenName": spoken_name,
                    }
                    ai_patient_action = {
                        **ai_patient_action_metadata(
                            action="matched_and_assigned",
                            patient=auto_patient,
                            capture=capture,
                            patient_information=patient_information,
                            match_candidate=patient_match_candidate,
                            created=False,
                        ),
                        # Flag the close match so the chip shows "· close match" + matched-vs-spoken.
                        "closeMatch": True,
                        "matchedName": auto_patient.display_name,
                        "spokenName": spoken_name,
                    }
                    assign_session_to_ai_patient(
                        db, session=session, capture=capture, patient=auto_patient, action=ai_patient_action
                    )
                else:
                    near_match = near_match_suggestion(patient_match_candidate, patient_information=patient_information)
                    if near_match is not None:
                        patient_match_candidate = near_match
        elif has_existing_patient:
            patient_match_candidate = suggested_reassignment_candidate(
                db,
                tenant_id=job.tenant_id,
                session=session,
                patient_information=patient_information,
                policy_deferred=reassignment_blocked_by_policy,
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
        # With the report now current, refresh the patient's AI memory (Pro). Gated on the session
        # being complete (captures processed, patient assigned, report up to date) + dedup.
        maybe_dispatch_patient_memory_job(
            db,
            tenant_id=job.tenant_id,
            patient_id=session.patient_id if session is not None else None,
            created_by_user_id=job.created_by_user_id,
            trigger_session=session,
        )
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
    session = db.execute(
        select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
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
    # The synthesized live report is a Pro capability: mark the captures it folded in as
    # contributed and record the included / set-aside counts for the report meta strip.
    report_contribution_summary: dict[str, int] | None = None
    synthesized = tenant_has_capability(db, job.tenant_id, LIVE_REPORT_SYNTHESIS)
    if synthesized:
        report_source_ids = extracted_metadata.get("source_capture_ids") if isinstance(extracted_metadata.get("source_capture_ids"), list) else None
        report_contribution_summary = mark_session_report_contributions(
            db, session=session, generated_at=completed_at.isoformat(), source_capture_ids=report_source_ids
        )
    session.extracted_metadata = {
        **preserved_assignment,
        **preserved_patient_match,
        **extracted_metadata,
        "session_processing_output": session_processing_output,
        "generated_output_stale": False,
        "processed_versions": previous_versions[-5:],
        **({"report_contribution_summary": report_contribution_summary} if report_contribution_summary is not None else {}),
        # Mark the synthesis current for this exact reportable content so a later deterministic regen
        # doesn't clobber the LLM report (the floor only rebuilds when the content signature changes).
        **(
            {
                "report_synthesis": {
                    "status": "current",
                    "captureIds": synthesis_capture_ids,
                    "signature": session_report_content_signature(reportable_captures),
                    "generatedAt": completed_at.isoformat(),
                }
            }
            if is_synthesis
            else {}
        ),
    }
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
        # would clobber the synthesized report). Only re-dispatch synthesis if a capture landed mid-job
        # (debounced + guarded), so a late capture still gets folded in.
        maybe_dispatch_session_synthesis(
            db, tenant_id=job.tenant_id, session_id=job.session_id, created_by_user_id=job.created_by_user_id
        )
    elif job.session_id is not None:
        # Legacy/placeholder path: deterministic regen is the source of truth.
        regenerate_session_report_if_idle(
            db,
            tenant_id=job.tenant_id,
            session_id=job.session_id,
            created_by_user_id=job.created_by_user_id,
        )
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
