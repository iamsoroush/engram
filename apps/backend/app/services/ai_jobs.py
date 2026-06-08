import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.config import settings
from app.models import Capture, CaptureStatus, CaptureType, AiJob, AiJobStatus, AiJobType, OrganizationSource, Patient, Session, SessionStatus, Tenant
from app.services.ai_model_config import get_ai_model_overrides
from app.services.capture_storage import get_capture_for_tenant
from app.services.patient_memory_intelligence import (
    apply_patient_memory_output,
    build_patient_memory_job_input,
    mark_patient_memory_updating,
    patient_has_active_memory_job,
    patient_has_pending_capture_jobs,
)
from app.services.session_contracts import session_is_complete
from app.services.patient_assignment_timeline import (
    append_patient_assignment_event,
    apply_active_patient_assignment,
    patient_assignment_event,
)
from app.services.patient_matching import (
    NATIONAL_ID_CONFLICT_RISK,
    match_patient_from_metadata,
    match_patient_from_patient_information,
)
from app.services.patients import create_patient_from_patient_information, patient_information_has_explicit_identity
from app.services.reporting import (
    DEFAULT_REPORT_TEMPLATE_KEY,
    empty_report_model,
    get_report_template,
    patient_information_from_assignment,
    render_report_body_markdown,
    report_template_payload,
    structured_report_from_markdown_body,
)
from app.services.session_processing import (
    build_session_processing_input,
    capture_is_out_of_context,
    report_model_from_session_processing_output,
    session_processing_output_from_legacy_report,
)
from app.services.sessions import parse_uuid

logger = logging.getLogger(__name__)

TASK_NAME_BY_JOB_TYPE = {
    AiJobType.audio_capture_process: "ai_engine.process_audio_capture",
    AiJobType.text_capture_process: "ai_engine.process_text_capture",
    AiJobType.image_capture_process: "ai_engine.process_image_capture",
    AiJobType.session_organize: "ai_engine.process_session",
    AiJobType.patient_memory: "ai_engine.process_patient_memory",
}

def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def ai_job_payload(job: AiJob) -> dict[str, Any]:
    """Serialize a processing job for API responses."""
    return {
        "id": str(job.id),
        "tenantId": str(job.tenant_id),
        "sessionId": str(job.session_id) if job.session_id else None,
        "captureId": str(job.capture_id) if job.capture_id else None,
        "jobType": job.job_type.value,
        "status": job.status.value,
        "generatedBy": job.generated_by,
        "inputArtifactIds": job.input_artifact_ids,
        "resultMetadata": job.result_metadata,
        "errorMessage": job.error_message,
        "attemptCount": job.attempt_count,
        "lastAttemptedAt": job.last_attempted_at.isoformat() if job.last_attempted_at else None,
        "lastDispatchedAt": job.last_dispatched_at.isoformat() if job.last_dispatched_at else None,
        "nextRetryAt": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "lastError": job.last_error,
        "retryReason": job.retry_reason,
        "createdByUserId": str(job.created_by_user_id) if job.created_by_user_id else None,
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "startedAt": job.started_at.isoformat() if job.started_at else None,
        "completedAt": job.completed_at.isoformat() if job.completed_at else None,
    }


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


def tenant_tier(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return a tenant's intelligence tier ('basic'|'pro'); AI auto-assignment is Pro-only."""
    tier = db.execute(select(Tenant.tier).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return tier if tier in {"basic", "pro"} else "pro"


def tenant_transcription_language(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's preferred transcription language ('auto' | a BCP-47-ish code).

    'auto' = transcribe verbatim in the spoken language/script; a specific code asks the model
    to transcribe in that language (improves accuracy/matching for known-language clinics).
    """
    value = db.execute(select(Tenant.transcription_language).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else "auto"


def tenant_report_language(db: DbSession, tenant_id: uuid.UUID) -> str | None:
    """Return the tenant's preferred report language, or None to follow the template default."""
    value = db.execute(select(Tenant.report_language).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value.strip() if isinstance(value, str) and value.strip() else None


def tenant_match_strictness(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's fuzzy-match auto-apply strictness ('strict'|'balanced'|'lenient')."""
    value = db.execute(select(Tenant.match_strictness).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return value if value in {"strict", "balanced", "lenient"} else "strict"


def assignment_intent_basis(output: dict[str, Any]) -> str | None:
    """Return the assignment-intent basis ('explicit'/'implicit') from AI output, if present."""
    intents = output.get("intents")
    if not isinstance(intents, dict):
        return None
    assignment = intents.get("assignment")
    if not isinstance(assignment, dict) or assignment.get("present") is not True:
        return None
    basis = assignment.get("basis")
    return basis if basis in {"explicit", "implicit"} else "implicit"


def out_of_context_marker(output: dict[str, Any]) -> dict[str, Any] | None:
    """Return a staff-overridable out-of-context marker from AI intents, if flagged."""
    intents = output.get("intents")
    if not isinstance(intents, dict):
        return None
    ooc = intents.get("out_of_context")
    if not isinstance(ooc, dict) or ooc.get("present") is not True:
        return None
    reason = ooc.get("reason")
    confidence = ooc.get("confidence")
    return {
        "present": True,
        "confidence": float(confidence) if isinstance(confidence, int | float) else 0.0,
        "reason": str(reason).strip() if isinstance(reason, str) and reason.strip() else None,
        "source": "ai",
    }


def should_apply_identity_assignment(
    *,
    has_session: bool,
    has_existing_patient: bool,
    assignment_basis: str | None,
) -> bool:
    """Decide whether extracted identity may be applied to the session.

    First identity on an unassigned visit is always applied (basis irrelevant). Once a
    patient is assigned, only an explicit (re)assignment instruction overrides it; an
    implicit mention is handled as a suggestion, not an application.
    """
    if not has_session:
        return False
    return not has_existing_patient or assignment_basis == "explicit"


NEAR_MATCH_SUGGEST_THRESHOLD = 0.78
# Fuzzy auto-apply line per match strictness (H3): the single-candidate confidence a fuzzy
# `possible_match` must clear to auto-apply. `strict` (None) = never; deterministic matches only.
# Fuzzy confidence is capped at 0.84 in patient_matching, so `balanced` catches a strong single
# variant (e.g. معاضد→معاصد @0.84) while `lenient` reaches down to the suggestion floor.
MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD: dict[str, float | None] = {"strict": None, "balanced": 0.82, "lenient": 0.78}


def spoken_name_from_information(patient_information: dict[str, Any] | None) -> str | None:
    """The patient name as spoken/transcribed, for the 'Matched X · you said Y' surface (H4)."""
    if not isinstance(patient_information, dict):
        return None
    for key in ("raw_mentioned_name", "standardized_display_name", "full_name", "display_name"):
        value = patient_information.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _dominant_match_candidate(candidate: dict[str, Any] | None, *, threshold: float) -> dict[str, Any] | None:
    """Return the single high-confidence candidate from a match result, else None.

    None when the top candidate is below `threshold` or ties with the runner-up — an ambiguous
    or weak match stays a choose-patient decision rather than a one-tap target.
    """
    if not isinstance(candidate, dict):
        return None
    ranked = [c for c in (candidate.get("candidateSet") or []) if isinstance(c, dict) and c.get("patientId")]
    if not ranked:
        return None
    top = ranked[0]
    top_confidence = float(top.get("confidence") or 0.0)
    if top_confidence < threshold:
        return None
    if len(ranked) > 1 and float(ranked[1].get("confidence") or 0.0) >= top_confidence:
        return None  # tie at the top -> ambiguous
    return top


def suggested_reassignment_candidate(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    session: Session,
    patient_information: dict[str, Any],
) -> dict[str, Any]:
    """Build an actionable but unapplied reassignment suggestion for an already-assigned visit.

    Used when a later capture only implicitly mentions a patient: the assignment is not
    changed, but staff can apply the suggestion in one tap. A dominant fuzzy candidate is
    promoted to `patientId` so Apply reassigns to the existing patient rather than creating one.
    """
    match = match_patient_from_patient_information(db, tenant_id=tenant_id, patient_information=patient_information)
    match = match if isinstance(match, dict) else {}
    patient_id = match.get("patientId")
    matched_name = match.get("displayName")
    if not patient_id:
        dominant = _dominant_match_candidate(match, threshold=NEAR_MATCH_SUGGEST_THRESHOLD)
        if dominant is not None:
            patient_id = dominant.get("patientId")
            matched_name = dominant.get("displayName")
    return {
        **match,
        "schemaVersion": "2026-06-02.patient-match-candidate.v1",
        "decision": "suggested_reassignment",
        "status": "suggested_reassignment",
        "appliedAutomatically": False,
        "currentPatientId": str(session.patient_id) if session.patient_id else None,
        "patientId": patient_id,
        "displayName": matched_name,
        "matchedName": matched_name,
        "spokenName": spoken_name_from_information(patient_information),
        "reason": "Implicit patient mention on an already-assigned visit; suggested for review, not applied.",
        "patientInformation": patient_information,
    }


def near_match_suggestion(candidate: dict[str, Any] | None, *, patient_information: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a single confident fuzzy/`possible_match` into an actionable reassignment suggestion.

    Fuzzy matches are never auto-applied here (a near-spelling could be a different person), but a
    clear single front-runner is surfaced as a one-tap suggestion instead of a silent no-op —
    this covers ASR name variance (e.g. spoke معاصد, transcribed معاضد). Returns None when
    there is no dominant high-confidence candidate, so it stays a choose-patient decision.
    """
    if not isinstance(candidate, dict) or candidate.get("decision") != "possible_match":
        return None
    top = _dominant_match_candidate(candidate, threshold=NEAR_MATCH_SUGGEST_THRESHOLD)
    if top is None:
        return None
    matched_name = top.get("displayName")
    return {
        **candidate,
        "decision": "suggested_reassignment",
        "status": "suggested_reassignment",
        "appliedAutomatically": False,
        "patientId": top.get("patientId"),
        "displayName": matched_name,
        "matchedName": matched_name,
        "spokenName": spoken_name_from_information(patient_information),
        "reason": "Close name match found; confirm to apply.",
        "patientInformation": patient_information,
    }


def fuzzy_auto_apply_candidate(
    candidate: dict[str, Any] | None,
    *,
    strictness: str,
    assignment_basis: str | None,
) -> dict[str, Any] | None:
    """Return the single fuzzy candidate that match strictness permits auto-applying, else None.

    H3/H4: a partial (fuzzy) `possible_match` auto-applies only under `balanced`/`lenient`
    strictness, with an **explicit** reassignment instruction and a single dominant
    high-confidence candidate (no tie). The national-ID conflict guard and ambiguous routing
    win at every strictness level — a candidate carrying a national-ID conflict is never
    auto-applied, and an implicit mention is always a suggestion, not an application.
    """
    threshold = MATCH_STRICTNESS_AUTOAPPLY_THRESHOLD.get(strictness)
    if threshold is None:  # strict — deterministic matches only
        return None
    if assignment_basis != "explicit":  # implicit partial is always a suggestion
        return None
    if not isinstance(candidate, dict) or candidate.get("decision") != "possible_match":
        return None
    if NATIONAL_ID_CONFLICT_RISK in (candidate.get("risks") or []):
        return None
    top = _dominant_match_candidate(candidate, threshold=threshold)
    if top is None or NATIONAL_ID_CONFLICT_RISK in (top.get("risks") or []):
        return None
    return top


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


def ai_job_retryable(job: AiJob) -> bool:
    """Return whether a failed AI job is eligible for automatic recovery."""
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    return metadata.get("retryable", True) is not False


def classify_retry_reason(error_message: str) -> str:
    """Classify operational retry reasons from worker error text."""
    normalized = error_message.lower()
    if "source file is missing" in normalized or "source_artifact" in normalized or "404" in normalized:
        return "source_missing"
    if "conversion to flac failed" in normalized or "ffmpeg" in normalized:
        return "conversion_failed"
    if (
        "gateway" in normalized
        or "transcription" in normalized
        or "openai" in normalized
        or "timeout" in normalized
        or "connection" in normalized
        or "rate limit" in normalized
        or "temporarily unavailable" in normalized
    ):
        return "gateway_unavailable"
    return "worker_error"


def retry_delay_seconds(attempt_count: int) -> int:
    """Return bounded exponential retry delay for a durable backend attempt count."""
    base_delay = max(settings.ai_job_retry_delay_seconds, 1)
    max_delay = max(settings.ai_job_retry_max_delay_seconds, base_delay)
    exponent = max(attempt_count - 1, 0)
    return min(base_delay * (2**exponent), max_delay)


def schedule_retry(job: AiJob, *, now: datetime, error_message: str, retry_reason: str | None = None) -> None:
    """Store durable retry state for the next backend-owned dispatch."""
    reason = retry_reason or classify_retry_reason(error_message)
    delay_seconds = retry_delay_seconds(job.attempt_count or 1)
    job.status = AiJobStatus.failed
    job.error_message = error_message
    job.last_error = error_message
    job.retry_reason = reason
    job.completed_at = now
    job.next_retry_at = now + timedelta(seconds=delay_seconds)
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_error": error_message,
        "retry_reason": reason,
        "retrying": True,
        "retryable": True,
        "next_retry_at": job.next_retry_at.isoformat(),
        "retry_delay_seconds": delay_seconds,
    }


def mark_job_non_retryable(job: AiJob, *, now: datetime, reason: str, error_message: str) -> None:
    """Mark a job as terminal because backend-owned target state says it should not retry."""
    job.status = AiJobStatus.failed
    job.error_message = error_message
    job.last_error = error_message
    job.retry_reason = reason
    job.completed_at = now
    job.next_retry_at = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_error": error_message,
        "retry_reason": reason,
        "retryable": False,
        "terminal_at": now.isoformat(),
    }


def datetime_or_none(value: datetime | None) -> datetime | None:
    """Normalize datetimes read from different DB/test backends to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def ai_job_due_for_recovery(job: AiJob, *, now: datetime) -> bool:
    """Return whether a durable job row should be re-dispatched now."""
    if job.status == AiJobStatus.succeeded or not ai_job_retryable(job):
        return False
    next_retry_at = datetime_or_none(job.next_retry_at)
    if next_retry_at is not None and next_retry_at > now:
        return False
    if job.status == AiJobStatus.failed:
        return True
    if job.status == AiJobStatus.queued:
        last_dispatched_at = datetime_or_none(job.last_dispatched_at)
        if last_dispatched_at is None:
            return True
        return last_dispatched_at <= now - timedelta(seconds=settings.ai_job_dispatch_visibility_timeout_seconds)
    if job.status == AiJobStatus.running:
        last_activity_at = datetime_or_none(job.last_attempted_at or job.started_at or job.created_at)
        if last_activity_at is None:
            return True
        return last_activity_at <= now - timedelta(seconds=settings.ai_job_running_stale_seconds)
    return False


def stop_recovery_if_target_is_gone(db: DbSession, job: AiJob, *, now: datetime) -> str | None:
    """Return a skip reason after terminally marking deleted/missing job targets."""
    if job.capture_id:
        capture = db.execute(
            select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if capture is None or capture.status == CaptureStatus.deleted:
            mark_job_non_retryable(
                job,
                now=now,
                reason="capture_deleted",
                error_message="AI job target capture is deleted",
            )
            return "capture_deleted"
        capture.status = CaptureStatus.processing
        return None
    if job.session_id:
        session = db.execute(
            select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if session is None:
            mark_job_non_retryable(
                job,
                now=now,
                reason="session_deleted",
                error_message="AI job target session is deleted",
            )
            return "session_deleted"
        session.status = SessionStatus.processing
    return None


def recover_ai_jobs(db: DbSession, principal: CurrentPrincipal, limit: int = 50) -> dict[str, Any]:
    """Re-dispatch queued or retryable failed AI jobs for the current tenant."""
    now = utc_now()
    jobs = list(
        db.execute(
            select(AiJob)
            .where(
                AiJob.tenant_id == principal.tenant_id,
                AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.failed]),
            )
            .order_by(AiJob.created_at)
            .limit(min(limit, 100))
        ).scalars()
    )
    recovered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for job in jobs:
        if not ai_job_retryable(job):
            skipped.append({"id": str(job.id), "reason": "terminal"})
            continue
        if not ai_job_due_for_recovery(job, now=now):
            skipped.append({"id": str(job.id), "reason": "not_due"})
            continue
        target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
        if target_skip_reason is not None:
            skipped.append({"id": str(job.id), "reason": target_skip_reason})
            continue
        job.status = AiJobStatus.queued
        job.completed_at = None
        job.next_retry_at = None
        job.result_metadata = {
            **(job.result_metadata or {}),
            "retryable": True,
            "recovered_at": now.isoformat(),
            "recovery_requested_by_user_id": str(principal.user_id),
        }
        recovered.append(ai_job_payload(job))
    db.commit()

    for recovered_job in recovered:
        job = db.get(AiJob, parse_uuid(recovered_job["id"], "job_id"))
        if job is None:
            continue
        if job.capture_id:
            # Respect per-session capture ordering: only the chain head dispatches; this also
            # makes recovery the self-healing driver of a stalled chain.
            if is_capture_chain_head(db, job):
                dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)
        elif job.patient_id:
            dispatch_patient_memory_job(db, job)

    return {"recovered": recovered, "skipped": skipped}


def recover_all_ai_jobs(db: DbSession, limit: int = 100) -> dict[str, Any]:
    """Re-dispatch queued or retryable failed AI jobs across tenants for worker startup recovery."""
    now = utc_now()
    jobs = list(
        db.execute(
            select(AiJob)
            .where(AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.failed]))
            .order_by(AiJob.created_at)
            .limit(min(limit, 200))
        ).scalars()
    )
    recovered: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for job in jobs:
        if not ai_job_retryable(job):
            skipped.append({"id": str(job.id), "reason": "terminal"})
            continue
        if not ai_job_due_for_recovery(job, now=now):
            skipped.append({"id": str(job.id), "reason": "not_due"})
            continue
        target_skip_reason = stop_recovery_if_target_is_gone(db, job, now=now)
        if target_skip_reason is not None:
            skipped.append({"id": str(job.id), "reason": target_skip_reason})
            continue
        job.status = AiJobStatus.queued
        job.completed_at = None
        job.next_retry_at = None
        job.result_metadata = {
            **(job.result_metadata or {}),
            "retryable": True,
            "recovered_at": now.isoformat(),
            "recovery_source": "ai-engine-startup",
        }
        recovered.append(ai_job_payload(job))
    db.commit()

    for recovered_job in recovered:
        job = db.get(AiJob, parse_uuid(recovered_job["id"], "job_id"))
        if job is None:
            continue
        if job.capture_id:
            # Respect per-session capture ordering: only the chain head dispatches; this also
            # makes recovery the self-healing driver of a stalled chain.
            if is_capture_chain_head(db, job):
                dispatch_capture_processing_job(db, job)
        elif job.session_id:
            dispatch_session_processing_job(db, job)
        elif job.patient_id:
            dispatch_patient_memory_job(db, job)

    return {"recovered": recovered, "skipped": skipped}


def job_type_for_capture(capture_type: CaptureType) -> AiJobType:
    """Map capture media type to the concrete AI processing job type."""
    if capture_type == CaptureType.audio:
        return AiJobType.audio_capture_process
    if capture_type == CaptureType.photo:
        return AiJobType.image_capture_process
    return AiJobType.text_capture_process


def output_key_for_capture(capture_type: CaptureType) -> str:
    """Return the metadata field written by a completed capture job."""
    if capture_type == CaptureType.audio:
        return "transcript"
    if capture_type == CaptureType.photo:
        return "caption"
    return "decorated_text"


def queued_metadata(job: AiJob, capture: Capture) -> dict[str, Any]:
    """Return metadata stored while a capture is waiting for a worker."""
    return {
        "status": "queued",
        "generated_by": "ai-engine",
        "job_id": str(job.id),
        "job_type": job.job_type.value,
        "output_key": output_key_for_capture(capture.capture_type),
        "queued_at": utc_now().isoformat(),
    }


def create_capture_processing_job(db: DbSession, *, principal: CurrentPrincipal, capture: Capture) -> AiJob:
    """Create a queued capture processing job and mark the capture processing."""
    source_ids = [str(capture.source_artifact_id)] if capture.source_artifact_id else []
    job = AiJob(
        tenant_id=principal.tenant_id,
        session_id=capture.session_id,
        capture_id=capture.id,
        job_type=job_type_for_capture(capture.capture_type),
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        input_artifact_ids=source_ids,
        result_metadata={"queue": "ai_jobs"},
        created_by_user_id=principal.user_id,
    )
    db.add(job)
    db.flush()
    capture.status = CaptureStatus.processing
    capture.capture_metadata = {
        **(capture.capture_metadata or {}),
        "ai_processing": queued_metadata(job, capture),
    }
    return job


def _capture_chain_order_key(capture: Capture, job: AiJob) -> tuple[datetime, datetime]:
    """Ordering key for a session's capture chain: capture time first, then job creation."""
    return (capture.captured_at or capture.created_at, job.created_at)


def earliest_pending_capture_job(ordered: list[tuple[tuple[datetime, datetime], AiJob]]) -> AiJob | None:
    """Return the job with the smallest order key (pure helper for capture-chain ordering)."""
    if not ordered:
        return None
    return min(ordered, key=lambda item: item[0])[1]


def _session_capture_jobs(
    db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID, statuses: list[AiJobStatus]
) -> list[tuple[tuple[datetime, datetime], AiJob]]:
    rows = db.execute(
        select(AiJob, Capture)
        .join(Capture, Capture.id == AiJob.capture_id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id == session_id,
            AiJob.capture_id.is_not(None),
            AiJob.status.in_(statuses),
            Capture.status != CaptureStatus.deleted,
        )
    ).all()
    return [(_capture_chain_order_key(capture, job), job) for job, capture in rows]


def is_capture_chain_head(db: DbSession, job: AiJob) -> bool:
    """Whether a capture-processing job is the earliest unfinished one in its session.

    Captures must process in capture order because the assignment gate depends on cumulative
    session state; a job is the head when no earlier capture in the same session still has an
    in-flight (queued/running) job. Session-level jobs are never gated.
    """
    if job.capture_id is None or job.session_id is None:
        return True
    if db.get(Capture, job.capture_id) is None:
        return True
    in_flight = _session_capture_jobs(
        db,
        tenant_id=job.tenant_id,
        session_id=job.session_id,
        statuses=[AiJobStatus.queued, AiJobStatus.running],
    )
    head = earliest_pending_capture_job(in_flight)
    return head is None or head.id == job.id


def dispatch_next_session_capture(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """Dispatch the next queued capture job in a session's chain, in capture order.

    No-op while a capture job is already running for the session (wait for it) or none queued.
    """
    if _session_capture_jobs(db, tenant_id=tenant_id, session_id=session_id, statuses=[AiJobStatus.running]):
        return
    head = earliest_pending_capture_job(
        _session_capture_jobs(db, tenant_id=tenant_id, session_id=session_id, statuses=[AiJobStatus.queued])
    )
    if head is not None:
        dispatch_capture_processing_job(db, head)


def requeue_failed_session_captures(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """Make failed-retryable capture jobs in a session eligible to retry immediately.

    Called when a capture just succeeded — the gateway is up, so instead of waiting for the
    periodic recovery beat, reset retryable siblings to queued for the chain to pick up.
    """
    rows = db.execute(
        select(AiJob)
        .join(Capture, Capture.id == AiJob.capture_id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id == session_id,
            AiJob.capture_id.is_not(None),
            AiJob.status == AiJobStatus.failed,
            Capture.status != CaptureStatus.deleted,
        )
    ).scalars()
    for job in rows:
        if ai_job_retryable(job):
            job.status = AiJobStatus.queued
            job.completed_at = None
            job.next_retry_at = None


def load_report_template(template_key: str | None) -> dict[str, str]:
    """Load the centralized report template by stable key."""
    try:
        return report_template_payload(template_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported report template") from exc


def generated_capture_text(value: Any) -> str | None:
    """Return generated/display text from a capture metadata field."""
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        text = value["text"].strip()
        return text or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def patient_summarized_history_for_transcription(db: DbSession, session: Session) -> str | None:
    """Return a safe assigned-patient history summary for transcription context."""
    if session.patient_id is None:
        return None
    patient = db.execute(
        select(Patient).where(Patient.id == session.patient_id, Patient.tenant_id == session.tenant_id)
    ).scalar_one_or_none()
    if patient is None or not isinstance(patient.notes, str):
        return None
    history = patient.notes.strip()
    return history or None


def transcription_context_from_inputs(
    *,
    session: Session,
    clinic: dict[str, Any],
    assigned_patient: dict[str, Any] | None,
    patient_history_summary: str | None,
    captures: list[Capture],
    current_capture_id: uuid.UUID,
    preferred_language: str = "auto",
) -> dict[str, Any]:
    """Build the stable tenant-scoped context sent to audio transcription."""
    previous_transcripts: list[dict[str, Any]] = []
    text_notes: list[dict[str, Any]] = []
    for capture in captures:
        if capture.id == current_capture_id or capture.status == CaptureStatus.deleted:
            continue
        metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
        if capture.capture_type == CaptureType.audio:
            transcript = generated_capture_text(metadata.get("transcript"))
            if transcript:
                previous_transcripts.append(
                    {
                        "captureId": str(capture.id),
                        "capturedAt": capture.captured_at.isoformat() if capture.captured_at else None,
                        "text": transcript,
                    }
                )
        elif capture.capture_type == CaptureType.note:
            note_text = (
                generated_capture_text(metadata.get("decorated_text"))
                or generated_capture_text(metadata.get("normalized_note"))
                or generated_capture_text(metadata.get("detail"))
            )
            if note_text:
                text_notes.append(
                    {
                        "captureId": str(capture.id),
                        "capturedAt": capture.captured_at.isoformat() if capture.captured_at else None,
                        "text": note_text,
                    }
                )

    return {
        "schemaVersion": "2026-06-02.audio-transcription-context.v1",
        "clinic": clinic,
        "preferredLanguage": preferred_language,
        "assignedPatient": assigned_patient,
        "patientSummarizedHistory": patient_history_summary,
        "session": {
            "id": str(session.id),
            "tenantId": str(session.tenant_id),
            "status": session.status.value,
            "title": session.title,
            "summary": session.summary,
            "createdAt": session.created_at.isoformat() if session.created_at else None,
            "updatedAt": session.updated_at.isoformat() if session.updated_at else None,
            "capturedAt": session.captured_at.isoformat() if session.captured_at else None,
        },
        "previousTranscripts": previous_transcripts[-5:],
        "textNotes": text_notes[-10:],
    }


def build_transcription_context(db: DbSession, *, session: Session, capture: Capture) -> dict[str, Any]:
    """Build the audio transcription context for the AI engine worker."""
    template = get_report_template(session.report_template_key)
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None
    captures = list(
        db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.created_at)
        ).scalars()
    )
    return transcription_context_from_inputs(
        session=session,
        clinic={
            "name": template.clinic_name,
            "information": list(template.clinic_information),
            "assumptions": [
                "Aesthetics clinic context.",
                "Persian/Iranian patient names, identifiers, phone numbers, and mixed Persian-English visit language are common.",
            ],
        },
        assigned_patient=assigned_patient,
        patient_history_summary=patient_summarized_history_for_transcription(db, session),
        captures=captures,
        current_capture_id=capture.id,
        preferred_language=tenant_transcription_language(db, session.tenant_id),
    )


def capture_enrichment_context_from_inputs(
    *,
    clinic: dict[str, Any],
    assigned_patient: dict[str, Any] | None,
    preferred_language: str,
    capture_type: str,
) -> dict[str, Any]:
    """Build the Pro-only context for photo captioning / note decoration."""
    return {
        "schemaVersion": "2026-06-06.capture-enrichment-context.v1",
        "clinic": clinic,
        "assignedPatient": assigned_patient,
        "preferredLanguage": preferred_language,
        "captureType": capture_type,
    }


def build_capture_enrichment_context(db: DbSession, *, session: Session, capture: Capture) -> dict[str, Any]:
    """Build the Pro-only enrichment context for the worker.

    Mirrors the audio transcription context but lighter: it carries clinic and assigned-patient
    context plus the preferred language so a real captioner/decorator can stay on-script. Attaching
    this context is the tier gate — the backend only builds it for Pro tenants (see
    `worker_job_payload`), so a Basic tenant's worker never enriches and never calls the gateway.
    """
    template = get_report_template(session.report_template_key)
    patient_information = patient_information_from_assignment(db, session)
    assigned_patient = patient_information if patient_information.get("status") == "assigned" else None
    return capture_enrichment_context_from_inputs(
        clinic={
            "name": template.clinic_name,
            "information": list(template.clinic_information),
            "assumptions": ["Aesthetics clinic context."],
        },
        assigned_patient=assigned_patient,
        preferred_language=tenant_transcription_language(db, session.tenant_id),
        capture_type=capture.capture_type.value,
    )


def create_session_report_job(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    session: Session,
    trigger: str = "manual",
) -> AiJob:
    """Create a queued session live-report job and mark the session processing."""
    source_ids = [
        str(source_id)
        for source_id in db.execute(
            select(Capture.source_artifact_id).where(
                Capture.tenant_id == tenant_id,
                Capture.session_id == session.id,
                Capture.source_artifact_id.is_not(None),
            )
        ).scalars()
    ]
    job = AiJob(
        tenant_id=tenant_id,
        session_id=session.id,
        capture_id=None,
        job_type=AiJobType.session_organize,
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        input_artifact_ids=source_ids,
        result_metadata={
            "queue": "ai_jobs",
            "report_template_key": session.report_template_key or DEFAULT_REPORT_TEMPLATE_KEY,
            "trigger": trigger,
        },
        created_by_user_id=created_by_user_id,
    )
    db.add(job)
    db.flush()
    session.status = SessionStatus.processing
    session.summary = session.summary or "Session processing has started."
    return job


def create_session_processing_job(db: DbSession, *, principal: CurrentPrincipal, session: Session) -> AiJob:
    """Create a queued session processing job and mark the session processing."""
    return create_session_report_job(
        db,
        tenant_id=principal.tenant_id,
        created_by_user_id=principal.user_id,
        session=session,
    )


def report_contribution_effect(status: str, *, generated_at: str | None = None, had_append_intent: bool = False) -> dict[str, Any]:
    """Build the per-capture report-contribution effect (Pro live report).

    `status` is one of `pending` (processed, awaiting the report job), `updating` (report
    job in flight), or `added` (folded into the current report).
    """
    return {
        "type": "report_contribution",
        "status": status,
        "appendIntent": had_append_intent,
        "generatedAt": generated_at,
        "source": "ai-engine",
    }


def mark_session_report_contributions(
    db: DbSession, *, session: Session, generated_at: str, source_capture_ids: list[str] | None = None
) -> dict[str, int]:
    """Flip the captures this report actually folded in to `added`; return included/set-aside counts.

    Run after a Pro live-report job completes. Only captures in the report's source set are
    marked `added` — a capture that arrived *while the job ran* (not in the source set) stays
    `pending` so the follow-up refinement folds it in. Out-of-context captures are counted as
    set aside for the report meta strip ("Generated from N captures · M set aside"). With no
    source set (legacy/empty output) all in-context captures are marked, to avoid a re-dispatch loop.
    """
    source_set = {str(value) for value in source_capture_ids} if source_capture_ids else None
    captures = list(
        db.execute(
            select(Capture).where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status == CaptureStatus.processed,
            )
        ).scalars()
    )
    included = 0
    set_aside = 0
    for capture in captures:
        if capture_is_out_of_context(capture):
            set_aside += 1
            continue
        if source_set is not None and str(capture.id) not in source_set:
            continue  # arrived after this report was built — left pending for the next pass
        included += 1
        capture.capture_metadata = {
            **(capture.capture_metadata or {}),
            "report_contribution": report_contribution_effect("added", generated_at=generated_at),
        }
    return {"included": included, "set_aside": set_aside}


def has_append_intent(output: dict[str, Any]) -> bool:
    """Whether AI output carries an explicit append intent (Pro report-refinement signal)."""
    intents = output.get("intents")
    if not isinstance(intents, dict):
        return False
    append = intents.get("append")
    return isinstance(append, dict) and append.get("present") is True


def session_has_pending_capture_jobs(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Whether a session still has queued/running capture jobs (chain not yet drained)."""
    return bool(
        _session_capture_jobs(
            db,
            tenant_id=tenant_id,
            session_id=session_id,
            statuses=[AiJobStatus.queued, AiJobStatus.running],
        )
    )


def session_has_active_report_job(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Whether a session-level live-report job is already queued/running (avoid duplicates)."""
    row = db.execute(
        select(AiJob.id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id == session_id,
            AiJob.capture_id.is_(None),
            AiJob.job_type == AiJobType.session_organize,
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _reportable_captures(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> list[Capture]:
    """Processed, in-context captures of a session (eligible to feed the live report)."""
    captures = db.execute(
        select(Capture).where(
            Capture.tenant_id == tenant_id,
            Capture.session_id == session_id,
            Capture.status == CaptureStatus.processed,
        )
    ).scalars()
    return [capture for capture in captures if not capture_is_out_of_context(capture)]


def session_has_reportable_capture(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Whether a session has at least one processed capture eligible for the report (not out-of-context)."""
    return bool(_reportable_captures(db, tenant_id=tenant_id, session_id=session_id))


def session_has_uncontributed_capture(db: DbSession, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    """Whether a reportable capture isn't yet folded into the report (its contribution != `added`).

    Lets refinement self-heal: a capture added *while a report job was running* stays
    uncontributed, so the next idle moment regenerates — without looping once everything is in.
    """
    for capture in _reportable_captures(db, tenant_id=tenant_id, session_id=session_id):
        metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
        contribution = metadata.get("report_contribution")
        status = contribution.get("status") if isinstance(contribution, dict) else None
        if status != "added":
            return True
    return False


def _capture_report_text(capture: Capture) -> str | None:
    """Return a capture's generated text for the report (transcript / decorated note / caption)."""
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    if capture.capture_type == CaptureType.audio:
        return generated_capture_text(metadata.get("transcript"))
    if capture.capture_type == CaptureType.note:
        return (
            generated_capture_text(metadata.get("decorated_text"))
            or generated_capture_text(metadata.get("normalized_note"))
            or generated_capture_text(metadata.get("detail"))
        )
    if capture.capture_type == CaptureType.photo:
        return generated_capture_text(metadata.get("caption"))
    return None


def build_session_report_model(session: Session, captures: list[Capture], *, grouped: bool) -> dict[str, Any]:
    """Build a deterministic (no-LLM) report model from a session's captures.

    `grouped` (Pro) groups blocks into fixed by-type sections (Audio notes / Written notes /
    Photos); otherwise (Basic) the body is a single chronological section. Photos render as image
    blocks (the markdown renderer resolves the source URL); transcripts/notes render as paragraphs.
    """
    model = empty_report_model(title=session.title or "Session report", template_key=session.report_template_key)
    audio_blocks: list[dict[str, Any]] = []
    note_blocks: list[dict[str, Any]] = []
    photo_blocks: list[dict[str, Any]] = []
    chronological_blocks: list[dict[str, Any]] = []
    source_references: list[dict[str, Any]] = []
    for capture in captures:
        capture_id = str(capture.id)
        source_references.append({"type": "capture", "captureId": capture_id})
        text = _capture_report_text(capture)
        if capture.capture_type == CaptureType.photo:
            block = {"type": "image", "captureId": capture_id, "caption": text or "Source image"}
            photo_blocks.append(block)
            chronological_blocks.append(block)
        elif text:
            block = {"type": "paragraph", "text": text}
            (audio_blocks if capture.capture_type == CaptureType.audio else note_blocks).append(block)
            chronological_blocks.append(block)
    if grouped:
        sections = [
            {"id": section_id, "title": title, "blocks": blocks}
            for section_id, title, blocks in (
                ("audio-notes", "Audio notes", audio_blocks),
                ("written-notes", "Written notes", note_blocks),
                ("photos", "Photos", photo_blocks),
            )
            if blocks
        ]
    else:
        sections = [{"id": "clinical-report", "title": "Clinical report", "blocks": chronological_blocks}] if chronological_blocks else []
    model["sections"] = sections
    model["sourceReferences"] = source_references
    model["generatedAt"] = utc_now().isoformat()
    return model


def regenerate_session_report(db: DbSession, *, session: Session) -> None:
    """Rebuild a session's live report deterministically (no AI job, no LLM).

    Pro reports group captures by type; Basic reports are chronological. Either way the report is a
    pure function of the session's processed, in-context captures, rebuilt synchronously whenever
    the capture chain is idle — so it is always current for the latest capture. Pro additionally
    records each folded-in capture's `report_contribution` and the included/set-aside meta counts.
    """
    is_pro = tenant_tier(db, session.tenant_id) == "pro"
    captures = sorted(
        _reportable_captures(db, tenant_id=session.tenant_id, session_id=session.id),
        key=lambda capture: (capture.captured_at or capture.created_at or utc_now()),
    )
    generated_at = utc_now()
    model = build_session_report_model(session, captures, grouped=is_pro)
    session.report_model = model
    session.generated_report = render_report_body_markdown(model, db=db, session=session)
    session.organization_source = OrganizationSource.ai_engine
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    metadata = {**metadata, "generated_output_stale": False, "generated_at": generated_at.isoformat()}
    if is_pro:
        # The "Added to report" chip + meta strip are a Pro affordance; Basic is a plain chronological render.
        metadata["report_contribution_summary"] = mark_session_report_contributions(
            db, session=session, generated_at=generated_at.isoformat()
        )
    session.extracted_metadata = metadata
    # A processed session settles to needs_review (assigned) / unassigned (no patient); completeness
    # is then derived (is_session_complete) rather than set by a manual verify.
    session.status = SessionStatus.needs_review if session.patient_id else SessionStatus.unassigned
    session.updated_at = generated_at


def regenerate_session_report_if_idle(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None = None,
    force: bool = False,
) -> None:
    """Regenerate a session's live report once its capture chain is idle (no AI job).

    No-op while captures are still processing (the report would be incomplete). Replaces the old
    async `session_organize` job: the report is now built deterministically and synchronously, so
    there is no "updating" churn and the report is always current once captures settle.
    """
    if session_has_pending_capture_jobs(db, tenant_id=tenant_id, session_id=session_id):
        return
    session = db.execute(
        select(Session).where(Session.id == session_id, Session.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if session is None:
        return
    regenerate_session_report(db, session=session)
    db.commit()


def dispatch_capture_processing_job(db: DbSession, job: AiJob) -> None:
    """Send a committed capture processing job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported capture processing job type: {job.job_type.value}")

    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued capture processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
        db.commit()
    except Exception as exc:
        logger.exception("Failed to queue capture processing job", extra={"job_id": str(job.id)})
        schedule_retry(job, now=utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.capture_id:
            capture = db.execute(
                select(Capture).where(Capture.id == job.capture_id, Capture.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if capture is not None and capture.status != CaptureStatus.deleted:
                capture.status = CaptureStatus.processing
        audit(
            db,
            tenant_id=job.tenant_id,
            actor_user_id=job.created_by_user_id,
            action="ai_processing.fail",
            target_type="capture",
            target_id=job.capture_id,
            details={"job_id": str(job.id), "error": str(exc), "phase": "dispatch"},
        )
        db.commit()


def dispatch_session_processing_job(db: DbSession, job: AiJob) -> None:
    """Send a committed session processing job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported session processing job type: {job.job_type.value}")

    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info(
            "Queued session processing job",
            extra={"job_id": str(job.id), "job_type": job.job_type.value, "task_name": task_name},
        )
        db.commit()
    except Exception as exc:
        logger.exception("Failed to queue session processing job", extra={"job_id": str(job.id)})
        schedule_retry(job, now=utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {
            **(job.result_metadata or {}),
            "queue_error": str(exc),
        }
        if job.session_id:
            session = db.execute(
                select(Session).where(Session.id == job.session_id, Session.tenant_id == job.tenant_id)
            ).scalar_one_or_none()
            if session is not None:
                session.status = SessionStatus.processing
        audit(
            db,
            tenant_id=job.tenant_id,
            actor_user_id=job.created_by_user_id,
            action="ai_processing.fail",
            target_type="session",
            target_id=job.session_id,
            details={"job_id": str(job.id), "error": str(exc), "phase": "dispatch"},
        )
        db.commit()


def dispatch_patient_memory_job(db: DbSession, job: AiJob) -> None:
    """Send a committed patient-memory job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported patient memory job type: {job.job_type.value}")
    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        logger.info("Queued patient memory job", extra={"job_id": str(job.id), "patient_id": str(job.patient_id)})
        db.commit()
    except Exception as exc:
        logger.exception("Failed to queue patient memory job", extra={"job_id": str(job.id)})
        schedule_retry(job, now=utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {**(job.result_metadata or {}), "queue_error": str(exc)}
        db.commit()


def maybe_dispatch_patient_memory_job(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None,
    created_by_user_id: uuid.UUID | None = None,
    trigger_session: Session | None = None,
) -> None:
    """Dispatch the combined patient summary+history job (Pro only) once the data has settled.

    Gated on "report complete": the triggering session (if any) must be complete — captures
    processed, a patient assigned, and the report current — and no capture job may still be in
    flight for the patient. Coalesces bursts via a per-patient dedup. Marks the patient `updating`
    only when it will actually dispatch, so Pro memory is never left stuck.
    """
    if patient_id is None:
        return
    if tenant_tier(db, tenant_id) != "pro":
        return
    if trigger_session is not None and not session_is_complete(trigger_session):
        return
    if patient_has_pending_capture_jobs(db, tenant_id=tenant_id, patient_id=patient_id):
        return
    if patient_has_active_memory_job(db, tenant_id=tenant_id, patient_id=patient_id):
        return
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        return
    mark_patient_memory_updating(db, patient_id)
    job = AiJob(
        tenant_id=tenant_id,
        patient_id=patient_id,
        job_type=AiJobType.patient_memory,
        status=AiJobStatus.queued,
        created_by_user_id=created_by_user_id,
        result_metadata={"queue": "ai_jobs"},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    dispatch_patient_memory_job(db, job)


def patient_memory_job_payload(db: DbSession, job: AiJob, ai_models: dict[str, str]) -> dict[str, Any]:
    """Build the worker payload for a patient-memory job (patient context + deterministic fallback)."""
    patient = db.execute(
        select(Patient).where(Patient.id == job.patient_id, Patient.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI job target patient is missing")
    sessions = list(
        db.execute(
            select(Session)
            .where(Session.tenant_id == job.tenant_id, Session.patient_id == patient.id)
            .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc())
        ).scalars()
    )
    tier = tenant_tier(db, job.tenant_id)
    job_input = build_patient_memory_job_input(
        patient, sessions, tier, language=tenant_report_language(db, job.tenant_id)
    )
    return {"job": ai_job_payload(job), "aiModels": ai_models, **job_input}


def complete_patient_memory_worker_job(db: DbSession, *, job: AiJob, output: dict[str, Any]) -> dict[str, Any]:
    """Persist a completed patient-memory job: write the patient's summary+history (status → ready)."""
    completed_at = utc_now()
    patient = db.execute(
        select(Patient).where(Patient.id == job.patient_id, Patient.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if patient is not None:
        apply_patient_memory_output(patient, output, tenant_tier(db, job.tenant_id), now=completed_at)
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.result_metadata = {
        **(job.result_metadata or {}),
        "completed_at": completed_at.isoformat(),
        "source": output.get("source"),
    }
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="patient",
        target_id=job.patient_id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


def enqueue_capture_processing_job(db: DbSession, *, principal: CurrentPrincipal, capture_id: str) -> dict[str, Any]:
    """Create and dispatch a capture processing job from an API route."""
    capture = get_capture_for_tenant(db, principal.tenant_id, parse_uuid(capture_id, "capture_id"))
    job = create_capture_processing_job(db, principal=principal, capture=capture)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="ai_processing.enqueue",
        target_type="capture",
        target_id=capture.id,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    dispatch_capture_processing_job(db, job)
    db.refresh(job)
    return {"job": ai_job_payload(job)}


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
    # Live per-task model selection, resolved per request so a change applies to the next job.
    ai_models = get_ai_model_overrides(db)
    if job.job_type == AiJobType.patient_memory:
        return patient_memory_job_payload(db, job, ai_models)
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
                # Image captions and note decoration are Pro-only; the gate is attaching the context.
                elif tenant_tier(db, job.tenant_id) == "pro":
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
    # TODO(ai-integration): Real session processors should consume this stable
    # context and return the structured body-level output contract.
    processing_context = build_session_processing_input(db, session)
    # The preferred report language (None = follow the report template's default) is consumed by
    # a real synthesizer; the placeholder body is language-neutral.
    processing_context = {**processing_context, "reportLanguage": tenant_report_language(db, job.tenant_id)}
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
    tier = tenant_tier(db, job.tenant_id)
    # Intelligent patient matching (match/create/reassign/suggest) runs for both tiers — it is the
    # core memory-accuracy feature. Tier only gates enrichment (captions/decoration) and the Pro
    # synthesized report below.
    if (
        isinstance(patient_information, dict)
        and patient_information_has_explicit_identity(patient_information)
    ):
        assignment_basis = assignment_intent_basis(output)
        strictness = tenant_match_strictness(db, job.tenant_id)
        has_existing_patient = session is not None and session.patient_id is not None
        # First identity on an unassigned visit is always applied; once a patient is
        # assigned, only an explicit (re)assignment instruction overrides it. An implicit
        # mention on an assigned visit becomes a suggestion, not a silent change.
        if should_apply_identity_assignment(
            has_session=session is not None,
            has_existing_patient=has_existing_patient,
            assignment_basis=assignment_basis,
        ):
            patient_match_candidate = match_patient_from_patient_information(
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
    if tier == "pro" and ooc_marker is None:
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
    structured_findings = session_processing_output.get("findings")
    if isinstance(structured_findings, list) and not isinstance(extracted_metadata.get("findings"), list):
        extracted_metadata = {**extracted_metadata, "findings": structured_findings}
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
    is_pro = tenant_tier(db, job.tenant_id) == "pro"
    if is_pro:
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
    # Deterministic regen is the source of truth now; if a capture is idle, rebuild from cumulative state.
    if job.session_id is not None:
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
        if session is not None and not ai_job_retryable(job):
            session.status = SessionStatus.failed
        elif session is not None:
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
