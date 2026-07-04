"""Session lifecycle routes: sessions, therapy sub-plane, and AI-job status/recovery.

A self-contained router mounted by ``main.py``. Handlers stay thin — logic lives in
``app/services/sessions``, ``app/services/therapy_reporting``, ``app/services/assignment_suggestions``,
and ``app/services/ai_jobs``.
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentPrincipal, staff_or_admin_required, staff_required
from app.db.session import get_db
from app.schemas.api import (
    AssignPatientRequest,
    SessionCreate,
    SessionSaveRequest,
    SessionUpdate,
    TherapyFormatRequest,
    TherapyReflectionsRequest,
    TherapyReleaseRequest,
    TherapyRiskRequest,
)
from app.services.ai_jobs import get_ai_job, recover_ai_jobs
from app.services.assignment_suggestions import suggest_session_assignment
from app.services.sessions import (
    assign_session_patient,
    confirm_carried_forward_dose,
    create_session,
    get_session,
    list_session_ai_jobs,
    list_session_artifacts,
    list_session_captures,
    list_sessions,
    save_session,
    set_aftercare_dismissed,
    set_safety_flag_rejected,
    start_review,
    update_session,
)
from app.services.therapy_reporting import (
    update_therapy_format,
    update_therapy_reflections,
    update_therapy_release,
    update_therapy_risk,
)

sessions_api = APIRouter(prefix="/api/v1")


@sessions_api.get("/sessions")
def get_sessions(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    clinician_id: str | None = Query(default=None, alias="clinicianId"),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List sessions in the current tenant, optionally filtered by status or owning clinician.

    Pass ``clinicianId`` (e.g. the caller's own id) for the AES-904 "Mine" view; omit for "Clinic".
    """
    return list_sessions(db, principal, status, limit, clinician_id)


@sessions_api.post("/sessions")
def create_session_route(
    request: SessionCreate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create an empty draft session for later captures."""
    return create_session(db, principal, request)


@sessions_api.get("/sessions/{session_id}")
def get_session_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one session, including generated report fields when available."""
    return get_session(db, principal, session_id)


@sessions_api.patch("/sessions/{session_id}")
def update_session_route(
    session_id: str,
    request: SessionUpdate,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update editable session fields such as title, summary, or status."""
    return update_session(db, principal, session_id, request)


@sessions_api.post("/sessions/{session_id}/confirm-carried-forward")
def confirm_carried_forward_route(
    session_id: str,
    key: str = Body(..., embed=True),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Q3: confirm a carried-forward dose (by its area|product key) so the report can read Complete."""
    return confirm_carried_forward_dose(db, principal, session_id, key)


@sessions_api.post("/sessions/{session_id}/aftercare-dismissal")
def set_aftercare_dismissal_route(
    session_id: str,
    templateId: str = Body(..., embed=True),
    dismissed: bool = Body(..., embed=True),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Opt a clinic aftercare template (auto-included for a matched procedure) in/out of this visit."""
    return set_aftercare_dismissed(db, principal, session_id, templateId, dismissed)


@sessions_api.post("/sessions/{session_id}/safety-flag-rejection")
def set_safety_flag_rejection_route(
    session_id: str,
    flagKey: str = Body(..., embed=True),
    rejected: bool = Body(..., embed=True),
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reject (or re-accept) an auto-kept session safety flag (allergy/contraindication/consent)."""
    return set_safety_flag_rejected(db, principal, session_id, flagKey, rejected)


@sessions_api.post("/sessions/{session_id}/save")
def save_session_route(
    session_id: str,
    request: SessionSaveRequest | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save a draft session and queue session-level AI report processing."""
    return save_session(db, principal, session_id, request or SessionSaveRequest())


@sessions_api.post("/sessions/{session_id}/retry-processing")
def retry_session_processing_route(
    session_id: str,
    request: SessionSaveRequest | None = None,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retry failed or reopened session-level AI report processing."""
    return save_session(db, principal, session_id, request or SessionSaveRequest())


@sessions_api.post("/sessions/{session_id}/assign-patient")
def assign_session_patient_route(
    session_id: str,
    request: AssignPatientRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Assign or clear the patient associated with a session."""
    return assign_session_patient(db, principal, session_id, request)


@sessions_api.get("/sessions/{session_id}/assignment-suggestion")
def session_assignment_suggestion_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return a deterministic, rule-based 'Assign to …?' suggestion for an unassigned visit (AES-301)."""
    return suggest_session_assignment(db, principal, session_id)


@sessions_api.post("/sessions/{session_id}/start-review")
def start_review_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Move an organized session into human review."""
    return start_review(db, principal, session_id)


@sessions_api.post("/sessions/{session_id}/therapy/format")
def therapy_set_format_route(
    session_id: str,
    request: TherapyFormatRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Switch the therapy shareable-plane note format (DAP/SOAP/BIRP); re-projects the same content."""
    return update_therapy_format(db, principal, session_id, request.format)


@sessions_api.post("/sessions/{session_id}/therapy/release")
def therapy_release_route(
    session_id: str,
    request: TherapyReleaseRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Explicitly release (or withdraw) the shareable summary to the client — a deliberate act."""
    return update_therapy_release(db, principal, session_id, request.released)


@sessions_api.post("/sessions/{session_id}/therapy/risk")
def therapy_risk_route(
    session_id: str,
    request: TherapyRiskRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Clinician-confirm (or clear) a dated risk flag; assisted detection only suggests."""
    return update_therapy_risk(db, principal, session_id, active=request.active, level=request.level, note=request.note)


@sessions_api.post("/sessions/{session_id}/therapy/reflections")
def therapy_reflections_route(
    session_id: str,
    request: TherapyReflectionsRequest,
    principal: CurrentPrincipal = Depends(staff_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save the private-plane reflections (therapist-only; never exported)."""
    return update_therapy_reflections(db, principal, session_id, request.reflections)


@sessions_api.get("/sessions/{session_id}/captures")
def list_session_captures_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all captures attached to a session."""
    return list_session_captures(db, principal, session_id)


@sessions_api.get("/sessions/{session_id}/artifacts")
def list_session_artifacts_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List stored source and generated artifacts attached to a session."""
    return list_session_artifacts(db, principal, session_id)


@sessions_api.get("/sessions/{session_id}/ai-jobs")
def list_session_ai_jobs_route(
    session_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List AI processing jobs associated with a session."""
    return list_session_ai_jobs(db, principal, session_id)


@sessions_api.post("/ai-jobs/recover")
def recover_ai_jobs_route(
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Requeue queued or retryable failed AI jobs after worker recovery."""
    return recover_ai_jobs(db, principal, limit)


@sessions_api.get("/ai-jobs/{job_id}")
def get_ai_job_route(
    job_id: str,
    principal: CurrentPrincipal = Depends(staff_or_admin_required),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one AI processing job and its current lifecycle state."""
    return get_ai_job(db, principal, job_id)
