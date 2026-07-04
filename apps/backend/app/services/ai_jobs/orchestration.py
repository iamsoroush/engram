"""Capture-chain ordering, Celery dispatch, job creation, and patient-memory dispatch."""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

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
    Patient,
    PatientStatus,
    Session,
    SessionStatus,
)
from app.services.capabilities import CROSS_VISIT_SYNTHESIS, tenant_has_capability
from app.services.capture_storage import get_capture_for_tenant
from app.services.caseload import tenant_vertical
from app.services.patient_memory_intelligence import (
    apply_patient_memory_output,
    build_patient_memory_job_input,
    mark_patient_memory_updating,
    patient_has_active_memory_job,
    patient_has_pending_capture_jobs,
    patient_memory_is_stale,
)
from app.services.reporting import DEFAULT_REPORT_TEMPLATE_KEY
from app.services.session_contracts import session_is_complete
from app.services.sessions import parse_uuid
from app.services.verticals import domain_descriptor

from app.services.ai_jobs.base import ai_job_payload, utc_now
from app.services.ai_jobs.config import tenant_report_language, tenant_tier
from app.services.ai_jobs.recovery import ai_job_retryable, schedule_retry

logger = logging.getLogger(__name__)

# Celery (Redis) priority tiers for patient-memory refreshes — lower number is consumed first. The
# three triggers map to three classes, so a queue backlog always serves the more-imminently-viewed
# patient first: a patient just OPENED (1st class) > a patient just LINED UP (2nd class) > the
# background quiescence sweep of patients nobody touched (3rd class). Capture/session jobs keep the
# default 0, so interactive work is never delayed by a memory backlog.
READ_DISPATCH_PRIORITY = 0      # 1st class: patient opened + stale
LINEUP_DISPATCH_PRIORITY = 3    # 2nd class: patient added to the line-up
SWEEP_DISPATCH_PRIORITY = 6     # 3rd class: background quiescence sweep

TASK_NAME_BY_JOB_TYPE = {
    AiJobType.audio_capture_process: "ai_engine.process_audio_capture",
    AiJobType.text_capture_process: "ai_engine.process_text_capture",
    AiJobType.image_capture_process: "ai_engine.process_image_capture",
    AiJobType.session_organize: "ai_engine.process_session",
    AiJobType.patient_memory: "ai_engine.process_patient_memory",
    # Post-session patient Q&A reply draft (AES-402). Logic lives in app/services/qa.py; recovery
    # re-dispatches it via the generic patient-scoped path (it carries patient_id).
    AiJobType.qa_draft: "ai_engine.process_qa_draft",
    # Q&A reply voice edit (AES-402) — revise/replace the draft from the doctor's spoken note.
    AiJobType.qa_revise: "ai_engine.process_qa_revise",
}

__all__ = [
    "job_type_for_capture",
    "output_key_for_capture",
    "queued_metadata",
    "create_capture_processing_job",
    "earliest_pending_capture_job",
    "is_capture_chain_head",
    "dispatch_next_session_capture",
    "requeue_failed_session_captures",
    "create_session_report_job",
    "create_session_processing_job",
    "dispatch_capture_processing_job",
    "dispatch_session_processing_job",
    "dispatch_patient_memory_job",
    "maybe_dispatch_patient_memory_job",
    "maybe_refresh_stale_patient_memory",
    "LINEUP_DISPATCH_PRIORITY",
    "sweep_stale_patient_memory",
    "patient_memory_job_payload",
    "complete_patient_memory_worker_job",
    "enqueue_capture_processing_job",
    "TASK_NAME_BY_JOB_TYPE",
]


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


def create_session_report_job(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID | None,
    session: Session,
    trigger: str = "manual",
    mark_processing: bool = True,
    escalate: bool = False,
) -> AiJob:
    """Create a queued session live-report job and (optionally) mark the session processing.

    `mark_processing=False` keeps the session at its current resting status — used by the Pro
    synthesis refinement, which runs AFTER a deterministic report already exists, so the report must
    stay visible (a quiet enrichment, never an error/processing flash).

    `escalate=True` (a pending user-correction hint) records `escalate` on the job so
    ``worker_job_payload`` sends it to the worker, which runs synthesis on the escalation tier (§3.1).
    """
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
            **({"escalate": True} if escalate else {}),
        },
        created_by_user_id=created_by_user_id,
    )
    db.add(job)
    db.flush()
    if mark_processing:
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


def _defer_if_over_budget(db: DbSession, job: AiJob) -> bool:
    """Fair-use gate for background AI enrichment (capture-first: the capture is already saved).

    When the clinic is over its monthly AI budget (or a single session exceeds its soft cap), the job
    is PARKED (kept queued, not sent to Celery) instead of dispatched; recovery resumes it once the
    budget frees. Returns True when the job was deferred (caller must not dispatch).
    """
    from app.services.ai_usage import mark_job_deferred, should_defer_dispatch

    reason = should_defer_dispatch(db, job)
    if reason is None:
        return False
    logger.info(
        "Deferring AI job for fair-use limit",
        extra={"job_id": str(job.id), "job_type": job.job_type.value, "reason": reason},
    )
    mark_job_deferred(db, job, reason)
    return True


def dispatch_capture_processing_job(db: DbSession, job: AiJob) -> None:
    """Send a committed capture processing job to Celery, marking broker failures."""
    from app.celery_app import celery_app

    task_name = TASK_NAME_BY_JOB_TYPE.get(job.job_type)
    if task_name is None:
        raise ValueError(f"Unsupported capture processing job type: {job.job_type.value}")

    if _defer_if_over_budget(db, job):
        return

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

    if _defer_if_over_budget(db, job):
        return

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
    if _defer_if_over_budget(db, job):
        return
    now = utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {
        **(job.result_metadata or {}),
        "last_dispatched_at": now.isoformat(),
        "queue": "ai_jobs",
    }
    # A background (sweep) refresh carries a lower Celery priority so it never delays interactive work
    # (default priority 0 = highest). The priority is stored on the job so recovery re-dispatch keeps it.
    priority = (job.result_metadata or {}).get("dispatch_priority")
    send_kwargs = {"priority": priority} if isinstance(priority, int) else {}
    try:
        celery_app.send_task(task_name, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs", **send_kwargs)
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
    priority: int = READ_DISPATCH_PRIORITY,
) -> None:
    """Dispatch the combined patient summary+history job (Pro only) once the data has settled.

    Gated on "report complete": the triggering session (if any) must be complete — captures
    processed, a patient assigned, and the report current — and no capture job may still be in
    flight for the patient. Coalesces bursts via a per-patient dedup. Marks the patient `updating`
    only when it will actually dispatch, so Pro memory is never left stuck. ``priority`` sets the
    Celery (Redis) queue tier — 0 (open) is served before 3 (line-up) before 6 (background sweep).
    """
    if patient_id is None:
        return
    if not tenant_has_capability(db, tenant_id, CROSS_VISIT_SYNTHESIS):
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
    result_metadata: dict[str, Any] = {"queue": "ai_jobs"}
    if priority > 0:
        # 0 routes to the base (highest) queue with no special handling; only store a real demotion.
        result_metadata["dispatch_priority"] = priority
    job = AiJob(
        tenant_id=tenant_id,
        patient_id=patient_id,
        job_type=AiJobType.patient_memory,
        status=AiJobStatus.queued,
        created_by_user_id=created_by_user_id,
        result_metadata=result_metadata,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    dispatch_patient_memory_job(db, job)


def maybe_refresh_stale_patient_memory(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient: Patient,
    sessions: list[Session],
    created_by_user_id: uuid.UUID | None = None,
    priority: int = READ_DISPATCH_PRIORITY,
) -> bool:
    """Refresh a patient's Pro memory when a visit changed since the last completed build.

    The interactive trigger shared by the two "a human is about to look at this patient" events: the
    patient page / line-up recap **opens** (1st class, ``priority`` 0) and the patient is **added to
    the line-up** (2nd class, ``priority`` 3). Memory is NOT refreshed on session completion — only
    when staleness meets one of these reads, plus the background sweep (3rd class). Dispatch
    self-gates on capability (Pro only), in-flight capture jobs, and the per-patient dedup, so Basic
    patients, fresh memory, and already-refreshing patients are a no-op. Returns whether a refresh
    was kicked off (so the caller can reflect the updating→ready lifecycle).
    """
    if not patient_memory_is_stale(patient, sessions):
        return False
    before = patient_has_active_memory_job(db, tenant_id=tenant_id, patient_id=patient.id)
    maybe_dispatch_patient_memory_job(
        db, tenant_id=tenant_id, patient_id=patient.id, created_by_user_id=created_by_user_id, priority=priority
    )
    return not before and patient_has_active_memory_job(db, tenant_id=tenant_id, patient_id=patient.id)


def sweep_stale_patient_memory(
    db: DbSession,
    *,
    now: datetime | None = None,
    idle_seconds: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Quiescence sweep: refresh Pro patient memory for visits that have gone quiet *and* stale.

    The background half of the decoupled trigger model, run on the EXISTING Celery-beat recovery
    loop (no new infra) — it catches stale patients nobody happened to open. Picks active patients
    whose latest visit activity has been idle for ``idle_seconds`` (default ~30 min, so memory is
    never rebuilt mid-visit) and whose memory is stale, newest-idle first, capped at ``limit`` per
    beat (the rest drain on later beats). Dispatch self-gates on capability + in-flight + dedup, so
    Basic and already-refreshing patients are skipped and there is ≤1 job per patient per window.
    """
    moment = now or utc_now()
    idle = idle_seconds if idle_seconds is not None else settings.patient_memory_quiescence_seconds
    cap = limit if limit is not None else settings.patient_memory_sweep_limit
    cutoff = moment - timedelta(seconds=idle)
    latest_activity = func.max(func.coalesce(Session.updated_at, Session.captured_at, Session.created_at))
    patients = list(
        db.execute(
            select(Patient)
            .join(Session, (Session.patient_id == Patient.id) & (Session.tenant_id == Patient.tenant_id))
            .where(Patient.status == PatientStatus.active)
            .group_by(Patient.id)
            .having(latest_activity <= cutoff)
            .order_by(latest_activity.desc())
            .limit(max(cap, 0))
        ).scalars()
    )
    dispatched = 0
    for patient in patients:
        if patient_has_active_memory_job(db, tenant_id=patient.tenant_id, patient_id=patient.id):
            continue
        sessions = list(
            db.execute(
                select(Session).where(Session.tenant_id == patient.tenant_id, Session.patient_id == patient.id)
            ).scalars()
        )
        if not patient_memory_is_stale(patient, sessions):
            continue
        # 3rd class: lowest Celery priority, so a sweep backlog never delays an opened/lined-up patient.
        maybe_dispatch_patient_memory_job(
            db, tenant_id=patient.tenant_id, patient_id=patient.id, priority=SWEEP_DISPATCH_PRIORITY
        )
        if patient_has_active_memory_job(db, tenant_id=patient.tenant_id, patient_id=patient.id):
            dispatched += 1
    return {"swept": len(patients), "dispatched": dispatched}


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
        patient,
        sessions,
        tier,
        language=tenant_report_language(db, job.tenant_id),
        domain=domain_descriptor(tenant_vertical(db, job.tenant_id)),
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
