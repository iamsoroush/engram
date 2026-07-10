"""Post-session patient↔clinic Q&A (Pro payload of the patient surface; AES-402 / AES-403).

The Pro payload of the shared clinic→patient primitive ([foundation §4]): a tokenized, revocable
Q&A thread per patient. Between visits a patient asks a question; the system drafts a reply from the
treating doctor's prior answers + this patient's context (a backend-owned ``qa_draft`` AI job) and
surfaces it in the doctor's inbox — *"Patient X asks … · Suggested reply … · Send / Edit / Dismiss."*
Nothing sends without a human approving it; every sent exchange is captured into patient memory.

Routing (foundation §7): admin-configurable per tenant (``qa_routing_mode``). The default
(``ai_default``) routes a new thread to the patient's **treating doctor** — the doctor who owns the
most (then most recent) of the patient's visits — with deterministic ranking; ``manual`` leaves it
unrouted for staff to route. A manual re-route to any of the patient's treating doctors is always
available.

Withholding (AES-403): the public read serves a patient ONLY their own questions + the
doctor-verified replies. Drafts, routing, internal status, and every other patient are never
projected, so clinic internals cannot leak through the token.

This module is self-contained: all Q&A logic lives here; the only shared-file seam is the
``qa_draft`` branch in ``ai_jobs.worker_job_payload`` / ``complete_worker_job`` (which delegate to
``qa_draft_worker_payload`` / ``complete_qa_draft_worker_job`` below) and the ``qa_draft`` enum value.
"""

import secrets
import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession, aliased

from app.auth.dependencies import CurrentPrincipal
from app.auth.service import audit
from app.models import (
    AiJob,
    AiJobStatus,
    AiJobType,
    MembershipRole,
    MembershipStatus,
    Patient,
    QaMessage,
    QaThread,
    Session,
    Tenant,
    TenantMembership,
    User,
)
from app.services.ai_jobs import ai_job_payload, schedule_retry
from app.services.capabilities import POST_SESSION_QA, tenant_has_capability
from app.services.patient_memory_intelligence import persisted_summary
from app.services.patients import get_patient
from app.services.qa_knowledge import library as qa_library
from app.services.qa_knowledge import retrieval as qa_retrieval
from app.services.sessions import parse_uuid
from app.storage import ObjectStore

QA_SCHEMA_VERSION = "2026-06-13.patient-qa.v1"
QA_DRAFT_TASK_NAME = "ai_engine.process_qa_draft"
QA_REVISE_TASK_NAME = "ai_engine.process_qa_revise"

THREAD_ACTIVE = "active"
THREAD_REVOKED = "revoked"

ROUTING_AI_DEFAULT = "ai_default"
ROUTING_MANUAL = "manual"
ROUTING_UNROUTED = "unrouted"
ROUTING_MODES = {ROUTING_AI_DEFAULT, ROUTING_MANUAL}

ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"

# Patient-question lifecycle.
Q_PENDING = "pending"
Q_ANSWERED = "answered"
Q_DISMISSED = "dismissed"
# Doctor-reply lifecycle.
R_SENT = "sent"

DRAFT_NONE = "none"
DRAFT_PENDING = "pending"
DRAFT_READY = "ready"
DRAFT_FAILED = "failed"
DRAFT_REVISING = "revising"  # a voice-edit job is rewriting/revising the current draft
# A voice edit that could not be applied (unusable model output / no gateway / audio fetch failed):
# the current draft is UNCHANGED and the doctor must be told so — never a silent success (Q-1, INV-SILENT).
DRAFT_FAILED_REVISE = "failed_revise"
# Draft states the self-heal MUST leave alone (a job is in flight or a good draft already exists);
# ``revising`` is here so an inbox read during a voice edit never dispatches a racing qa_draft (Q-2).
_DRAFT_INFLIGHT = {DRAFT_PENDING, DRAFT_READY, DRAFT_REVISING}

MAX_QUESTION_CHARS = 4000
MAX_REPLY_CHARS = 8000
PRIOR_ANSWERS_LIMIT = 8
RECENT_VISIT_SUMMARIES = 3
CARE_TEAM_BYLINE = "Your care team"

# Public-ask abuse limits (Q-8): a leaked token must not flood the inbox or buy unbounded LLM calls.
MAX_PENDING_QUESTIONS = 5  # concurrent unanswered questions allowed on one thread
ASK_RATE_WINDOW_SECONDS = 60
ASK_RATE_MAX_IN_WINDOW = 6  # questions accepted per rolling window on one thread


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --- Capability gate ------------------------------------------------------------------------------


def require_qa_capability(db: DbSession, tenant_id: uuid.UUID) -> None:
    """Gate the Q&A surface on the Pro ``post_session_qa`` capability (never on tier directly)."""
    if not tenant_has_capability(db, tenant_id, POST_SESSION_QA):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Post-session patient Q&A is a Pro feature.",
        )


# --- Treating-doctor routing ----------------------------------------------------------------------


def _rank_treating_doctors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank treating-doctor candidates: most visits first, then most recent, then name (stable).

    Pure function (no DB) so the routing rule is unit-testable. Each row carries ``userId``,
    ``name``, ``sessionCount`` and ``lastVisitAt`` (ISO string or None).
    """
    return sorted(
        rows,
        key=lambda row: (
            -int(row.get("sessionCount") or 0),
            _sort_desc_key(row.get("lastVisitAt")),
            (row.get("name") or "").lower(),
        ),
    )


def _sort_desc_key(iso_value: str | None) -> str:
    """Key that sorts ISO timestamps newest-first within an ascending sort (None last)."""
    # Invert the string so a later timestamp ranks before an earlier one under ascending order.
    if not iso_value:
        return "\x00"  # sorts first under inversion → pushed last (most recent wins)
    return "".join(chr(255 - ord(ch)) if ord(ch) < 255 else ch for ch in iso_value)


def treating_doctors(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return the patient's treating doctors (visit owners with an active doctor role), ranked.

    A "treating doctor" is a clinician who owns at least one of the patient's visits (capture-first →
    the capturer owns the session, [foundation §7]); ranked most-frequent then most-recent.
    """
    rows = db.execute(
        select(
            Session.created_by_user_id,
            func.count(Session.id),
            func.max(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at)),
            User.full_name,
        )
        .join(
            TenantMembership,
            (TenantMembership.user_id == Session.created_by_user_id)
            & (TenantMembership.tenant_id == tenant_id)
            & (TenantMembership.role == MembershipRole.doctor)
            & (TenantMembership.status == MembershipStatus.active),
        )
        .join(User, User.id == Session.created_by_user_id)
        .where(Session.tenant_id == tenant_id, Session.patient_id == patient_id)
        .group_by(Session.created_by_user_id, User.full_name)
    ).all()
    candidates = [
        {
            "userId": str(user_id),
            "name": full_name or "Doctor",
            "sessionCount": int(count or 0),
            "lastVisitAt": _iso(last_visit_at),
        }
        for user_id, count, last_visit_at, full_name in rows
    ]
    return _rank_treating_doctors(candidates)


def _active_doctor_ids(db: DbSession, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """All active doctors in the tenant (fallback routing target + manual re-route validation)."""
    rows = db.execute(
        select(User.id, User.full_name, TenantMembership.created_at)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == MembershipRole.doctor,
            TenantMembership.status == MembershipStatus.active,
        )
        .order_by(TenantMembership.created_at)
    ).all()
    return [{"userId": str(uid), "name": name or "Doctor"} for uid, name, _ in rows]


def _resolve_default_route(
    db: DbSession, *, tenant: Tenant, patient_id: uuid.UUID
) -> tuple[uuid.UUID | None, str]:
    """Resolve the initial routing for a new thread per the tenant's ``qa_routing_mode``.

    ``manual`` → unrouted (staff route it). ``ai_default`` → the top treating doctor; if the patient
    has no treating doctor yet, the earliest active doctor; if the tenant has no doctor, unrouted.
    """
    if tenant.qa_routing_mode == ROUTING_MANUAL:
        return None, ROUTING_UNROUTED
    ranked = treating_doctors(db, tenant_id=tenant.id, patient_id=patient_id)
    if ranked:
        return uuid.UUID(ranked[0]["userId"]), ROUTING_AI_DEFAULT
    fallback = _active_doctor_ids(db, tenant.id)
    if fallback:
        return uuid.UUID(fallback[0]["userId"]), ROUTING_AI_DEFAULT
    return None, ROUTING_UNROUTED


# --- Q&A settings (admin-configurable routing) ----------------------------------------------------


def qa_settings_payload(db: DbSession, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Return the tenant's Q&A routing policy."""
    tenant = db.get(Tenant, tenant_id)
    mode = tenant.qa_routing_mode if tenant and tenant.qa_routing_mode in ROUTING_MODES else ROUTING_AI_DEFAULT
    return {"schemaVersion": QA_SCHEMA_VERSION, "routingMode": mode}


def set_qa_routing_mode(db: DbSession, principal: CurrentPrincipal, mode: str) -> dict[str, Any]:
    """Set the tenant's Q&A routing policy (admin-configurable; foundation §7)."""
    normalized = (mode or "").strip().lower()
    if normalized not in ROUTING_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported Q&A routing mode")
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.qa_routing_mode = normalized
    audit(
        db,
        tenant_id=tenant.id,
        actor_user_id=principal.user_id,
        action="qa.set_routing_mode",
        target_type="tenant",
        target_id=tenant.id,
        details={"qa_routing_mode": normalized},
    )
    db.commit()
    return {"schemaVersion": QA_SCHEMA_VERSION, "routingMode": normalized}


# --- Thread lifecycle (staff) ---------------------------------------------------------------------


def _get_thread(db: DbSession, tenant_id: uuid.UUID, thread_id: str) -> QaThread:
    thread = db.execute(
        select(QaThread).where(
            QaThread.id == parse_uuid(thread_id, "thread_id"),
            QaThread.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Q&A thread not found")
    return thread


def _doctor_name(db: DbSession, user_id: uuid.UUID | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return (user.full_name if user else None) or None


def _pending_question_count(db: DbSession, thread_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count(QaMessage.id)).where(
                QaMessage.thread_id == thread_id,
                QaMessage.role == ROLE_PATIENT,
                QaMessage.status == Q_PENDING,
            )
        ).scalar_one()
    )


def staff_thread_payload(db: DbSession, thread: QaThread, *, include_messages: bool = False) -> dict[str, Any]:
    """Serialize a thread for staff (internal view — includes routing + drafts when messages asked)."""
    assigned_name = _doctor_name(db, thread.assigned_doctor_user_id)
    payload: dict[str, Any] = {
        "id": str(thread.id),
        "tenantId": str(thread.tenant_id),
        "patientId": str(thread.patient_id),
        "token": thread.token,
        "publicPath": f"/qa/{thread.token}",
        "payloadType": "post_session_qa",
        "status": thread.status,
        "assignedDoctor": (
            {"userId": str(thread.assigned_doctor_user_id), "name": assigned_name or "Doctor"}
            if thread.assigned_doctor_user_id
            else None
        ),
        "routingSource": thread.routing_source,
        "pendingCount": _pending_question_count(db, thread.id),
        "createdAt": _iso(thread.created_at),
        "updatedAt": _iso(thread.updated_at),
        "revokedAt": _iso(thread.revoked_at),
    }
    if include_messages:
        payload["messages"] = _staff_messages(db, thread)
        payload["treatingDoctors"] = treating_doctors(db, tenant_id=thread.tenant_id, patient_id=thread.patient_id)
    return payload


def _staff_messages(db: DbSession, thread: QaThread) -> list[dict[str, Any]]:
    """All messages in a thread, staff view (includes the AI draft on each pending question)."""
    messages = list(
        db.execute(
            select(QaMessage)
            .where(QaMessage.tenant_id == thread.tenant_id, QaMessage.thread_id == thread.id)
            .order_by(QaMessage.created_at)
        ).scalars()
    )
    return [
        {
            "id": str(message.id),
            "role": message.role,
            "body": message.body,
            "status": message.status,
            "inReplyToId": str(message.in_reply_to_id) if message.in_reply_to_id else None,
            "draft": message.draft if message.role == ROLE_PATIENT else None,
            "draftStatus": message.draft_status if message.role == ROLE_PATIENT else DRAFT_NONE,
            "draftSource": message.draft_source if message.role == ROLE_PATIENT else None,
            "draftProvenance": message.draft_provenance if message.role == ROLE_PATIENT else None,
            "createdByUserId": str(message.created_by_user_id) if message.created_by_user_id else None,
            "createdAt": _iso(message.created_at),
        }
        for message in messages
    ]


def create_or_get_thread(db: DbSession, principal: CurrentPrincipal, patient_id: str) -> dict[str, Any]:
    """Open (or reuse) the Q&A channel for a patient — the explicit clinic 'Share Q&A' gesture.

    Idempotent: one thread per patient. A revoked thread is re-activated so the channel can re-open.
    A new thread auto-routes per the tenant's ``qa_routing_mode``.
    """
    require_qa_capability(db, principal.tenant_id)
    patient = get_patient(db, principal.tenant_id, patient_id)
    existing = db.execute(
        select(QaThread).where(QaThread.tenant_id == principal.tenant_id, QaThread.patient_id == patient.id)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status == THREAD_REVOKED:
            existing.status = THREAD_ACTIVE
            existing.revoked_at = None
            existing.revoked_by_user_id = None
            # Rotate the token on re-activation (Q-9): a revoked link was handed out to be dead, so
            # re-opening the channel must mint a fresh URL — the previously-leaked link stays 404.
            existing.token = secrets.token_urlsafe(32)
            audit(
                db,
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                action="qa.thread.reactivate",
                target_type="qa_thread",
                target_id=existing.id,
                details={"token_rotated": True},
            )
            db.commit()
            db.refresh(existing)
        return staff_thread_payload(db, existing)

    tenant = db.get(Tenant, principal.tenant_id)
    assigned_doctor_id, routing_source = _resolve_default_route(db, tenant=tenant, patient_id=patient.id)
    thread = QaThread(
        tenant_id=principal.tenant_id,
        patient_id=patient.id,
        token=secrets.token_urlsafe(32),
        status=THREAD_ACTIVE,
        assigned_doctor_user_id=assigned_doctor_id,
        routing_source=routing_source,
        created_by_user_id=principal.user_id,
    )
    db.add(thread)
    db.flush()
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.thread.create",
        target_type="qa_thread",
        target_id=thread.id,
        details={"patient_id": str(patient.id), "routing_source": routing_source, "assigned_doctor": str(assigned_doctor_id) if assigned_doctor_id else None},
    )
    db.commit()
    db.refresh(thread)
    return staff_thread_payload(db, thread)


def list_threads(db: DbSession, principal: CurrentPrincipal, *, patient_id: str | None = None) -> list[dict[str, Any]]:
    """List the tenant's Q&A threads, newest first (optionally one patient)."""
    require_qa_capability(db, principal.tenant_id)
    statement = select(QaThread).where(QaThread.tenant_id == principal.tenant_id)
    if patient_id:
        statement = statement.where(QaThread.patient_id == parse_uuid(patient_id, "patient_id"))
    threads = db.execute(statement.order_by(QaThread.created_at.desc())).scalars()
    return [staff_thread_payload(db, thread) for thread in threads]


def get_thread_detail(db: DbSession, principal: CurrentPrincipal, thread_id: str) -> dict[str, Any]:
    """One thread with its full message history + drafts + treating-doctor list (staff view)."""
    require_qa_capability(db, principal.tenant_id)
    return staff_thread_payload(db, _get_thread(db, principal.tenant_id, thread_id), include_messages=True)


def get_patient_treating_doctors(db: DbSession, principal: CurrentPrincipal, patient_id: str) -> dict[str, Any]:
    """The patient's treating-doctor list (the manual re-route picker source; foundation §7)."""
    require_qa_capability(db, principal.tenant_id)
    patient = get_patient(db, principal.tenant_id, patient_id)
    return {
        "patientId": str(patient.id),
        "treatingDoctors": treating_doctors(db, tenant_id=principal.tenant_id, patient_id=patient.id),
    }


def route_thread(db: DbSession, principal: CurrentPrincipal, thread_id: str, doctor_user_id: str) -> dict[str, Any]:
    """Manually re-route a thread to a chosen doctor (must be an active doctor in the tenant)."""
    require_qa_capability(db, principal.tenant_id)
    thread = _get_thread(db, principal.tenant_id, thread_id)
    target_id = parse_uuid(doctor_user_id, "doctorUserId")
    valid_doctor_ids = {doc["userId"] for doc in _active_doctor_ids(db, principal.tenant_id)}
    if str(target_id) not in valid_doctor_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target is not an active doctor in this clinic")
    reassigned = thread.assigned_doctor_user_id != target_id
    thread.assigned_doctor_user_id = target_id
    thread.routing_source = ROUTING_MANUAL
    # A draft is signed with the treating doctor's name and grounded in THAT doctor's prior answers
    # (qa.py `doctorName` / `_prior_doctor_answers` bake in the old doctor at draft time). Re-routing to
    # a new doctor must not hand them a reply signed by someone else — invalidate the pending drafts so
    # the inbox self-heal re-drafts them for the new doctor (Q-5, INV-INVALIDATE).
    if reassigned:
        _invalidate_thread_drafts(db, thread)
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.thread.route",
        target_type="qa_thread",
        target_id=thread.id,
        details={"assigned_doctor": str(target_id)},
    )
    db.commit()
    db.refresh(thread)
    return staff_thread_payload(db, thread, include_messages=True)


# --- Draft invalidation (INV-INVALIDATE; Q-5) -----------------------------------------------------


def _reset_pending_draft(question: QaMessage) -> None:
    """Clear a pending question's draft to a clean ``none`` so the self-heal re-drafts it.

    Zeroes the draft text, status, source, provenance and the optimistic-lock ``draft_job_id`` — the
    last means any in-flight job for the old draft finds ``draft_job_id != job.id`` on completion and
    quietly declines to write (never clobbering the re-drafted state).
    """
    question.draft = None
    question.draft_status = DRAFT_NONE
    question.draft_source = None
    question.draft_provenance = None
    question.draft_job_id = None


def _invalidate_thread_drafts(db: DbSession, thread: QaThread) -> int:
    """Invalidate every pending question's draft on a thread (re-route / re-open). Caller commits."""
    count = 0
    for question in db.execute(
        select(QaMessage).where(
            QaMessage.thread_id == thread.id, QaMessage.role == ROLE_PATIENT, QaMessage.status == Q_PENDING
        )
    ).scalars():
        _reset_pending_draft(question)
        count += 1
    return count


def invalidate_drafts_for_patient(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> int:
    """Invalidate all pending Q&A drafts for a patient — call on patient reassignment (INV-INVALIDATE).

    A visit reassigned away changes the patient's grounding (visits, memory, treating doctor); a draft
    built from the old grounding is stale. Reset the affected pending drafts so the inbox self-heal
    re-drafts them. Exposed for the reassignment path (``services/sessions.assign_session_patient``),
    which owns the reassignment transaction; Q&A owns the reset. Caller commits.
    """
    threads = db.execute(
        select(QaThread).where(
            QaThread.tenant_id == tenant_id, QaThread.patient_id == patient_id, QaThread.status == THREAD_ACTIVE
        )
    ).scalars()
    total = 0
    for thread in threads:
        total += _invalidate_thread_drafts(db, thread)
    return total


def invalidate_drafts_for_exemplar(db: DbSession, *, tenant_id: uuid.UUID, exemplar_id: str) -> int:
    """Invalidate pending drafts grounded on a now-excluded exemplar (Q-5(c)). Caller commits.

    Excluding a library exemplar implies the clinic no longer wants it grounding replies — but a draft
    already built on it keeps quoting it until re-drafted. Reset every pending draft whose provenance
    points at this exemplar so the self-heal re-drafts without it.
    """
    count = 0
    for question in db.execute(
        select(QaMessage).where(
            QaMessage.tenant_id == tenant_id,
            QaMessage.role == ROLE_PATIENT,
            QaMessage.status == Q_PENDING,
            QaMessage.draft_status != DRAFT_NONE,
        )
    ).scalars():
        provenance = question.draft_provenance if isinstance(question.draft_provenance, dict) else None
        if provenance and str(provenance.get("exemplarId") or "") == str(exemplar_id):
            _reset_pending_draft(question)
            count += 1
    return count


def revoke_thread(db: DbSession, principal: CurrentPrincipal, thread_id: str) -> dict[str, Any]:
    """Revoke a thread so its public link stops working (AES-403); idempotent."""
    require_qa_capability(db, principal.tenant_id)
    thread = _get_thread(db, principal.tenant_id, thread_id)
    if thread.status != THREAD_REVOKED:
        thread.status = THREAD_REVOKED
        thread.revoked_at = _utc_now()
        thread.revoked_by_user_id = principal.user_id
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="qa.thread.revoke",
            target_type="qa_thread",
            target_id=thread.id,
            details={},
        )
        db.commit()
        db.refresh(thread)
    return staff_thread_payload(db, thread)


def revoke_patient_qa_threads_on_archive(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> int:
    """Revoke a patient's active Q&A threads when the patient is archived (Q-9 archive half).

    Additive internal primitive (no ``principal``) so the patient-lifecycle/archive path can call it
    directly. Token rotation on re-activation is owned separately (Track D+). Caller commits."""
    threads = list(
        db.execute(
            select(QaThread).where(
                QaThread.tenant_id == tenant_id,
                QaThread.patient_id == patient_id,
                QaThread.status == THREAD_ACTIVE,
            )
        ).scalars()
    )
    now = _utc_now()
    for thread in threads:
        thread.status = THREAD_REVOKED
        thread.revoked_at = now
        thread.revoked_by_user_id = actor_user_id
        audit(
            db,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="qa.thread.revoke",
            target_type="qa_thread",
            target_id=thread.id,
            details={"reason": "patient_archived"},
        )
    return len(threads)


# --- Doctor inbox + reply/dismiss (staff) ---------------------------------------------------------


def _patient_visits(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> list[dict[str, Any]]:
    """The patient's visits (id · title · date), oldest first — interleaved as markers in the thread."""
    rows = db.execute(
        select(Session.id, Session.title, func.coalesce(Session.captured_at, Session.updated_at, Session.created_at))
        .where(Session.tenant_id == tenant_id, Session.patient_id == patient_id)
        .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at))
    ).all()
    return [{"sessionId": str(sid), "title": title or "Visit", "date": _iso(date)} for sid, title, date in rows]


def _thread_inbox_item(db: DbSession, thread: QaThread, patient: Patient) -> dict[str, Any]:
    """Build one thread-centric inbox entry: the whole conversation + the pending question (if any)."""
    messages = _staff_messages(db, thread)
    pending = next((m for m in messages if m["role"] == ROLE_PATIENT and m["status"] == Q_PENDING), None)
    assigned_name = _doctor_name(db, thread.assigned_doctor_user_id)
    last_activity = messages[-1]["createdAt"] if messages else _iso(thread.updated_at)
    # Re-route is only meaningful for a multi-provider patient (≥2 treating doctors to choose between);
    # the UI hides the control otherwise so a single-doctor clinic isn't shown a no-op.
    treating_doctor_count = len(treating_doctors(db, tenant_id=thread.tenant_id, patient_id=patient.id))
    return {
        "threadId": str(thread.id),
        "patientId": str(patient.id),
        "patientName": patient.display_name,
        "assignedDoctor": (
            {"userId": str(thread.assigned_doctor_user_id), "name": assigned_name or "Doctor"}
            if thread.assigned_doctor_user_id
            else None
        ),
        "routingSource": thread.routing_source,
        "treatingDoctorCount": treating_doctor_count,
        "needsApproval": pending is not None,
        "pendingQuestion": (
            {
                "messageId": pending["id"],
                "question": pending["body"],
                "askedAt": pending["createdAt"],
                "suggestedReply": pending["draft"],
                "draftStatus": pending["draftStatus"],
                "draftSource": pending["draftSource"],
                "draftProvenance": pending["draftProvenance"],
            }
            if pending
            else None
        ),
        "messages": messages,
        "visits": _patient_visits(db, tenant_id=thread.tenant_id, patient_id=patient.id),
        "lastActivityAt": last_activity,
    }


def qa_inbox(db: DbSession, principal: CurrentPrincipal, *, scope: str = "mine") -> dict[str, Any]:
    """The doctor Q&A inbox — **thread-centric**: one patient conversation per entry (AES-402).

    Threads that need the doctor's approval (a pending question) sort first; the rest follow by most
    recent activity, so it reads like a triaged message list, not a flat all-patients chat. Each entry
    carries the whole conversation (the UI interleaves visit markers) + the pending question's
    AI-suggested reply. ``scope="mine"`` (default) = threads routed to me plus unrouted (nothing falls
    through); ``scope="all"`` = the whole clinic (foundation §7). Self-heals a missing/failed draft on
    read (silent, never a needs-input item). ``total`` counts threads awaiting approval (the badge).
    """
    require_qa_capability(db, principal.tenant_id)
    normalized_scope = scope if scope in {"mine", "all"} else "mine"
    pairs = db.execute(
        select(QaThread, Patient)
        .join(Patient, Patient.id == QaThread.patient_id)
        .where(QaThread.tenant_id == principal.tenant_id, QaThread.status == THREAD_ACTIVE)
    ).all()

    # Pass 1: self-heal any pending question that never got (or lost) its draft. Dispatch commits.
    in_scope: list[tuple[QaThread, Patient]] = []
    for thread, patient in pairs:
        if normalized_scope == "mine" and thread.assigned_doctor_user_id is not None and thread.assigned_doctor_user_id != principal.user_id:
            continue
        in_scope.append((thread, patient))
        for question in db.execute(
            select(QaMessage).where(
                QaMessage.thread_id == thread.id, QaMessage.role == ROLE_PATIENT, QaMessage.status == Q_PENDING
            )
        ).scalars():
            _ensure_draft_job(db, thread=thread, question=question)

    # Pass 2: build entries (reflecting any just-dispatched draft state), drop empty channels.
    items = [_thread_inbox_item(db, thread, patient) for thread, patient in in_scope]
    items = [item for item in items if item["messages"]]
    # Most-recent first, then float the threads awaiting approval to the top (stable two-key sort).
    items.sort(key=lambda item: item["lastActivityAt"] or "", reverse=True)
    items.sort(key=lambda item: 0 if item["needsApproval"] else 1)
    return {
        "schemaVersion": QA_SCHEMA_VERSION,
        "scope": normalized_scope,
        "items": items,
        "total": sum(1 for item in items if item["needsApproval"]),
    }


def _get_question(db: DbSession, tenant_id: uuid.UUID, message_id: str) -> QaMessage:
    message = db.execute(
        select(QaMessage).where(
            QaMessage.id == parse_uuid(message_id, "message_id"),
            QaMessage.tenant_id == tenant_id,
            QaMessage.role == ROLE_PATIENT,
        )
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return message


def send_reply(db: DbSession, principal: CurrentPrincipal, message_id: str, reply_text: str | None) -> dict[str, Any]:
    """Approve and send a reply to a patient question (doctor-verified; AES-402).

    ``reply_text`` is what the doctor approved — the AI draft as-is, or their edit. Nothing sends
    without this call. The exchange is captured into patient memory; the public thread then shows
    the verified reply.
    """
    require_qa_capability(db, principal.tenant_id)
    question = _get_question(db, principal.tenant_id, message_id)
    if question.status != Q_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This question is no longer pending")
    text = (reply_text if reply_text is not None else (question.draft or "")).strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reply text is required")
    text = text[:MAX_REPLY_CHARS]
    thread = _get_thread(db, principal.tenant_id, str(question.thread_id))
    now = _utc_now()
    reply = QaMessage(
        tenant_id=principal.tenant_id,
        thread_id=thread.id,
        role=ROLE_DOCTOR,
        body=text,
        status=R_SENT,
        in_reply_to_id=question.id,
        created_by_user_id=principal.user_id,
    )
    db.add(reply)
    db.flush()  # assign reply.id so the auto-indexed exemplar can reference it (idempotency key).
    question.status = Q_ANSWERED
    thread.updated_at = now
    patient = db.get(Patient, thread.patient_id)
    if patient is not None:
        _capture_exchange_into_memory(patient, question_text=question.body, reply_text=text, now=now)
    # Auto-index this doctor-approved reply into the clinic's knowledge base (AES-410 · Q3): it becomes
    # a retrievable exemplar for future drafts, with a one-tap exclude in the Library. Best-effort — in a
    # SAVEPOINT so an indexing hiccup rolls back only the index, never the doctor's send.
    try:
        with db.begin_nested():
            qa_library.auto_index_sent_reply(
                db,
                tenant_id=principal.tenant_id,
                question_text=question.body,
                reply_text=text,
                source_message_id=reply.id,
                doctor_user_id=principal.user_id,
            )
    except Exception:  # noqa: BLE001 — indexing is an enhancement; the reply must still send.
        pass
    # HALF-2 harvest: if the doctor edited the AI draft before sending, that delta is an eval signal
    # (the model got it not-quite-right and a human fixed it). Only when there WAS an AI draft (a
    # from-scratch reply isn't a correction) and the text actually changed (guarded in the helper).
    if question.draft:
        _record_qa_reply_feedback(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            patient_id=thread.patient_id,
            kind="correction",
            before=question.draft,
            after=text,
            context={
                "source": "send-edit",
                "draftSource": question.draft_source,
                "provenance": question.draft_provenance,
            },
        )
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.reply.send",
        target_type="qa_thread",
        target_id=thread.id,
        details={"question_id": str(question.id), "edited": reply_text is not None and reply_text.strip() != (question.draft or "").strip()},
    )
    db.commit()
    db.refresh(thread)
    return staff_thread_payload(db, thread, include_messages=True)


def dismiss_question(db: DbSession, principal: CurrentPrincipal, message_id: str) -> dict[str, Any]:
    """Dismiss a patient question without replying (the question stays in the patient's thread,
    simply unanswered — no internal handling leaks to the patient surface)."""
    require_qa_capability(db, principal.tenant_id)
    question = _get_question(db, principal.tenant_id, message_id)
    thread = _get_thread(db, principal.tenant_id, str(question.thread_id))
    if question.status == Q_PENDING:
        question.status = Q_DISMISSED
        # HALF-2 harvest: dismissing a question that HAD a ready draft is a rejection signal — the AI
        # reply was not worth sending. (No draft → nothing for the eval set to learn from.)
        if question.draft and question.draft_status in {DRAFT_READY, DRAFT_FAILED_REVISE}:
            _record_qa_reply_feedback(
                db,
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                patient_id=thread.patient_id,
                kind="rejection",
                before=question.draft,
                after=None,
                context={"source": "dismiss", "draftSource": question.draft_source, "provenance": question.draft_provenance},
            )
        audit(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            action="qa.question.dismiss",
            target_type="qa_message",
            target_id=question.id,
            details={},
        )
        db.commit()
    return staff_thread_payload(db, thread, include_messages=True)


def _capture_exchange_into_memory(patient: Patient, *, question_text: str, reply_text: str, now: datetime) -> None:
    """Append a sent Q&A exchange to the patient's free-text memory (AES-402).

    The exchange becomes part of the patient's longitudinal record — it flows into the transcription
    context and the Pro cross-visit synthesis, and grounds future reply drafts. Append-only and
    bounded so it stays a compact memory line, not a transcript dump.
    """
    stamp = now.date().isoformat()
    q = " ".join(question_text.split())[:300]
    a = " ".join(reply_text.split())[:300]
    entry = f"[Q&A {stamp}] Patient asked: “{q}” · Clinic replied: “{a}”"
    existing = (patient.notes or "").rstrip()
    patient.notes = f"{existing}\n{entry}".strip() if existing else entry


# --- Failure-detection harvest (HALF-2): learn from what the doctor does to a draft ----------------


QA_REPLY_OUTPUT_TYPE = "qa_reply"


def _record_qa_reply_feedback(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    patient_id: uuid.UUID | None,
    kind: str,
    before: str | None,
    after: str | None,
    context: dict[str, Any] | None = None,
) -> None:
    """Stage an ``ai_feedback_events`` row for a doctor's action on a Q&A reply draft (HALF-2).

    Every meaningful doctor action on a suggested reply is a real eval signal: a manual edit before
    send, a voice revise/replace, or a dismiss without replying. The AI draft (``before``) and the
    doctor's outcome (``after``) are the qa golden-set target; retrieval provenance travels in
    ``context`` for triage. Staged in the caller's transaction like ``audit`` — a ``correction`` is
    only recorded when the text actually changed; harvesting never raises into the doctor's action.
    """
    from app.services import feedback

    if kind == "correction":
        if not after or (before or "").strip() == (after or "").strip():
            return  # no real edit → not a correction signal
    feedback.record_feedback_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        kind=kind,
        ai_output_type=QA_REPLY_OUTPUT_TYPE,
        before_value=before,
        after_value=after,
        patient_id=patient_id,
        context=context or {},
    )


# --- Public patient surface (no auth — the token is the capability) -------------------------------


def _thread_by_token(db: DbSession, token: str) -> QaThread:
    thread = db.execute(select(QaThread).where(QaThread.token == token)).scalar_one_or_none()
    if thread is None or thread.status != THREAD_ACTIVE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This link is not available")
    return thread


def _thread_language(tenant: Tenant | None, messages: list[QaMessage]) -> str:
    """The language the public Q&A page should localize its chrome to (Q-10).

    The clinic's configured report language when set; otherwise inferred from the thread content
    (Persian script → ``fa``), so a fa clinic's Q&A page never renders English chrome over fa content.
    """
    if tenant is not None and tenant.report_language:
        return tenant.report_language
    blob = " ".join(m.body for m in messages if isinstance(m.body, str))
    if any("؀" <= ch <= "ۿ" for ch in blob):
        return "fa"
    return "en"


def _public_thread_projection(
    *,
    clinic_name: str | None,
    patient_name: str | None,
    language: str,
    messages: list[QaMessage],
    doctor_names: dict[uuid.UUID, str | None],
) -> dict[str, Any]:
    """Project a thread into the patient-facing payload — questions + verified replies ONLY (AES-403).

    Pure function (no DB): the withholding contract lives here. Drafts, routing, dismissed-reasons,
    internal status, and other patients are never included; a question maps to ``answered`` (with the
    sent reply), ``awaiting`` (still pending), or ``closed`` (dismissed, shown with no reply).
    """
    replies_by_question: dict[uuid.UUID, QaMessage] = {}
    for message in messages:
        if message.role == ROLE_DOCTOR and message.status == R_SENT and message.in_reply_to_id is not None:
            replies_by_question[message.in_reply_to_id] = message
    exchanges: list[dict[str, Any]] = []
    for message in messages:
        if message.role != ROLE_PATIENT:
            continue
        reply = replies_by_question.get(message.id)
        if reply is not None:
            public_status = "answered"
            reply_block = {
                "text": reply.body,
                "repliedAt": _iso(reply.created_at),
                "byline": (doctor_names.get(reply.created_by_user_id) if reply.created_by_user_id else None) or CARE_TEAM_BYLINE,
                "verified": True,
            }
        else:
            public_status = "closed" if message.status == Q_DISMISSED else "awaiting"
            reply_block = None
        exchanges.append(
            {
                "id": str(message.id),
                "question": message.body,
                "askedAt": _iso(message.created_at),
                "status": public_status,
                "reply": reply_block,
            }
        )
    return {
        "schemaVersion": QA_SCHEMA_VERSION,
        "payloadType": "post_session_qa",
        "status": THREAD_ACTIVE,
        "clinic": {"name": clinic_name},
        "patientName": patient_name,
        "language": language,
        "exchanges": exchanges,
    }


def public_thread_payload(db: DbSession, token: str) -> dict[str, Any]:
    """PUBLIC: the patient's own Q&A thread — their questions + doctor-verified replies (AES-401/403)."""
    thread = _thread_by_token(db, token)
    patient = db.get(Patient, thread.patient_id)
    tenant = db.get(Tenant, thread.tenant_id)
    messages = list(
        db.execute(
            select(QaMessage)
            .where(QaMessage.tenant_id == thread.tenant_id, QaMessage.thread_id == thread.id)
            .order_by(QaMessage.created_at)
        ).scalars()
    )
    doctor_ids = {m.created_by_user_id for m in messages if m.role == ROLE_DOCTOR and m.created_by_user_id}
    doctor_names = {uid: _doctor_name(db, uid) for uid in doctor_ids}
    return _public_thread_projection(
        clinic_name=tenant.name if tenant else None,
        patient_name=patient.display_name if patient else None,
        language=_thread_language(tenant, messages),
        messages=messages,
        doctor_names=doctor_names,
    )


def _enforce_ask_limits(db: DbSession, thread: QaThread) -> None:
    """Throttle the public ask endpoint (Q-8): a leaked token can't flood the inbox or LLM budget.

    Two thread-scoped caps (no shared state needed): a concurrent unanswered-question ceiling, and a
    rolling per-window rate. Both raise ``429`` so the public page can back off. Doctor sends/dismisses
    clear pending questions, so a legitimately active conversation is never blocked.
    """
    if _pending_question_count(db, thread.id) >= MAX_PENDING_QUESTIONS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="There are already several questions awaiting a reply. Please wait for the clinic to respond.",
        )
    window_start = _utc_now() - timedelta(seconds=ASK_RATE_WINDOW_SECONDS)
    recent = int(
        db.execute(
            select(func.count(QaMessage.id)).where(
                QaMessage.thread_id == thread.id,
                QaMessage.role == ROLE_PATIENT,
                QaMessage.created_at >= window_start,
            )
        ).scalar_one()
    )
    if recent >= ASK_RATE_MAX_IN_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many questions in a short time. Please wait a moment and try again.",
        )


def ask_question(db: DbSession, token: str, question_text: str) -> dict[str, Any]:
    """PUBLIC: the patient asks a question; routes a reply draft to the doctor's inbox (AES-402)."""
    thread = _thread_by_token(db, token)
    text = (question_text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A question is required")
    text = text[:MAX_QUESTION_CHARS]
    _enforce_ask_limits(db, thread)
    question = QaMessage(
        tenant_id=thread.tenant_id,
        thread_id=thread.id,
        role=ROLE_PATIENT,
        body=text,
        status=Q_PENDING,
        draft_status=DRAFT_NONE,
    )
    db.add(question)
    thread.updated_at = _utc_now()
    db.commit()
    db.refresh(question)
    # Draft the reply in the background; a dispatch failure is self-healed on the next inbox read.
    _dispatch_draft_for_question(db, thread=thread, question=question)
    db.refresh(question)
    return {
        "schemaVersion": QA_SCHEMA_VERSION,
        "id": str(question.id),
        "question": question.body,
        "askedAt": _iso(question.created_at),
        "status": "awaiting",
    }


# --- qa_draft AI job (creation, dispatch, worker payload, completion) ------------------------------


def _ensure_draft_job(db: DbSession, *, thread: QaThread, question: QaMessage) -> bool:
    """Create a draft job for a pending question that has none / a failed one. Returns True if it did.

    The self-healing driver: a draft that never started (broker was down) or failed is silently
    re-drafted. A draft already pending, ready, or being voice-edited (``revising``) is left alone —
    dispatching a fresh qa_draft mid voice-edit would race the revise and could clobber it (Q-2).
    Caller commits.
    """
    if question.status != Q_PENDING or question.draft_status in _DRAFT_INFLIGHT:
        return False
    _create_and_dispatch_draft_job(db, thread=thread, question=question)
    return True


def _dispatch_draft_for_question(db: DbSession, *, thread: QaThread, question: QaMessage) -> None:
    """Create + dispatch the reply-draft job for a newly-asked question (own commit)."""
    _create_and_dispatch_draft_job(db, thread=thread, question=question)
    db.commit()


def _enrichment_paused(db: DbSession, tenant_id: uuid.UUID) -> bool:
    """True when the clinic's metered AI spend has reached its budget (pause qa drafting; Q-8)."""
    try:
        from app.services.ai_usage import enrichment_paused

        return enrichment_paused(db, tenant_id)
    except Exception:  # noqa: BLE001 — a metering hiccup must never block drafting.
        return False


def _create_and_dispatch_draft_job(db: DbSession, *, thread: QaThread, question: QaMessage) -> None:
    """Create the patient-scoped ``qa_draft`` AiJob (target message in result_metadata) + dispatch it.

    Fair-use gate (Q-8): when the clinic is over its metered AI budget, do NOT buy an LLM draft — leave
    the question at ``draft_status = none`` (the doctor can still reply by hand) so the inbox self-heal
    re-attempts once the budget frees (new period / top-up / upgrade). qa drafts thus honour the same
    pause as background enrichment instead of being an uncapped side channel.
    """
    if _enrichment_paused(db, thread.tenant_id):
        question.draft_status = DRAFT_NONE
        return
    job = AiJob(
        tenant_id=thread.tenant_id,
        patient_id=thread.patient_id,
        job_type=AiJobType.qa_draft,
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        created_by_user_id=thread.assigned_doctor_user_id,
        result_metadata={"queue": "ai_jobs", "qa_thread_id": str(thread.id), "qa_message_id": str(question.id)},
    )
    db.add(job)
    question.draft_status = DRAFT_PENDING
    db.flush()
    question.draft_job_id = job.id
    db.flush()
    dispatch_qa_draft_job(db, job)


def dispatch_qa_draft_job(db: DbSession, job: AiJob) -> None:
    """Send a committed qa_draft job to Celery, marking broker failures (mirrors patient-memory)."""
    from app.celery_app import celery_app

    now = _utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {**(job.result_metadata or {}), "last_dispatched_at": now.isoformat(), "queue": "ai_jobs"}
    try:
        celery_app.send_task(QA_DRAFT_TASK_NAME, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        db.commit()
    except Exception as exc:  # noqa: BLE001 — broker down: persist a retryable state, recovery re-dispatches.
        schedule_retry(job, now=_utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {**(job.result_metadata or {}), "queue_error": str(exc)}
        db.commit()


# Bound the most-recent-visit aftercare prose fed to the draft (native script, the aftercare the
# patient was actually given). Enough to ground "never contradict the aftercare THIS patient was
# given" without dumping the whole report.
MAX_RECENT_AFTERCARE_CHARS = 800
# The thread's own prior exchange (bounded) so a follow-up question is drafted WITH the earlier Q→A of
# THIS conversation, not blind. Distinct from `priorAnswers`, which is doctor-wide (other patients).
THREAD_HISTORY_TURNS = 4


def _recent_visit_aftercare(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> str | None:
    """The aftercare prose from this patient's most recent visit report (G4 grounding).

    The synthesized report's `aftercare` section carries the effective aftercare the patient was given
    (dictated instructions + the applied protocol's guidance). Feed it so the draft can honour the
    prompt's "never contradict the aftercare THIS patient was given" rule instead of guessing. Bounded,
    native script, most-recent visit only.
    """
    rows = db.execute(
        select(Session.report_model)
        .where(Session.tenant_id == tenant_id, Session.patient_id == patient_id, Session.report_model.is_not(None))
        .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc())
        .limit(RECENT_VISIT_SUMMARIES)
    ).scalars()
    for report_model in rows:
        if not isinstance(report_model, dict):
            continue
        for section in report_model.get("sections") or []:
            if not isinstance(section, dict) or section.get("id") != "aftercare":
                continue
            texts = [
                block["text"].strip()
                for block in section.get("blocks") or []
                if isinstance(block, dict) and block.get("type") == "paragraph" and isinstance(block.get("text"), str) and block["text"].strip()
            ]
            if texts:
                return " ".join(texts)[:MAX_RECENT_AFTERCARE_CHARS]
    return None


def _thread_prior_turns(db: DbSession, *, thread: QaThread, exclude_message_id: uuid.UUID) -> list[dict[str, Any]]:
    """This thread's own prior sent Q→A exchanges (bounded), so a follow-up has conversational context.

    Only ANSWERED exchanges (a doctor-verified reply exists), oldest-first, excluding the question now
    being drafted. Thread-scoped (this patient) — unlike doctor-wide `priorAnswers`, this carries no
    cross-patient leak risk.
    """
    replies_by_question: dict[uuid.UUID, str] = {}
    messages = list(
        db.execute(
            select(QaMessage)
            .where(QaMessage.tenant_id == thread.tenant_id, QaMessage.thread_id == thread.id)
            .order_by(QaMessage.created_at)
        ).scalars()
    )
    for message in messages:
        if message.role == ROLE_DOCTOR and message.status == R_SENT and message.in_reply_to_id is not None:
            replies_by_question[message.in_reply_to_id] = message.body
    turns = [
        {"question": message.body, "answer": replies_by_question[message.id]}
        for message in messages
        if message.role == ROLE_PATIENT and message.id != exclude_message_id and message.id in replies_by_question
    ]
    return turns[-THREAD_HISTORY_TURNS:]


def _patient_qa_context(db: DbSession, patient: Patient | None, *, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Compact, withholding-safe patient context for grounding a reply draft."""
    if patient is None:
        return {}
    recent_summaries = [
        summary
        for summary in db.execute(
            select(Session.summary)
            .where(Session.tenant_id == tenant_id, Session.patient_id == patient.id, Session.summary.is_not(None))
            .order_by(func.coalesce(Session.captured_at, Session.updated_at, Session.created_at).desc())
            .limit(RECENT_VISIT_SUMMARIES)
        ).scalars()
        if isinstance(summary, str) and summary.strip()
    ]
    return {
        "displayName": patient.display_name,
        "memorySummary": persisted_summary(patient),
        "history": (patient.notes or "").strip() or None,
        "recentVisitSummaries": recent_summaries,
        # (G4) the aftercare THIS patient was actually given — grounds the prompt's never-contradict rule.
        "recentAftercare": _recent_visit_aftercare(db, tenant_id=tenant_id, patient_id=patient.id),
    }


# A leading greeting name in a prior answer is the most common cross-patient leak (Q-3): the draft is
# grounded on OTHER patients' replies, so "Hi Maryam," / "سلام سارا،" would splice a stranger's name
# into THIS patient's draft. Strip the name token right after a leading greeting before grounding.
_GREETING_NAME_RE = re.compile(
    r"^(\s*(?:hi|hello|hey|dear|سلام|درود|وقت بخیر)\b)[ \t]+([^\s,،.!؛:]+)",
    re.IGNORECASE,
)


def _strip_greeting_name(text: str | None) -> str | None:
    """Remove a stranger's name in a leading greeting from a prior-answer fragment (Q-3)."""
    if not isinstance(text, str) or not text.strip():
        return text
    return _GREETING_NAME_RE.sub(r"\1", text, count=1)


def _prior_doctor_answers(db: DbSession, *, tenant_id: uuid.UUID, doctor_user_id: uuid.UUID | None) -> list[dict[str, Any]]:
    """The doctor's prior sent Q&A answers (with their question) to ground the draft's voice.

    The answers come from OTHER patients (they teach the doctor's VOICE, not facts), so a leading
    greeting name is stripped server-side before it can leak into this patient's draft (Q-3).
    """
    question_alias = aliased(QaMessage)
    statement = (
        select(QaMessage.body, question_alias.body)
        .join(question_alias, question_alias.id == QaMessage.in_reply_to_id)
        .where(
            QaMessage.tenant_id == tenant_id,
            QaMessage.role == ROLE_DOCTOR,
            QaMessage.status == R_SENT,
        )
        .order_by(QaMessage.created_at.desc())
        .limit(PRIOR_ANSWERS_LIMIT)
    )
    if doctor_user_id is not None:
        statement = statement.where(QaMessage.created_by_user_id == doctor_user_id)
    return [
        {"question": _strip_greeting_name(question), "answer": _strip_greeting_name(answer)}
        for answer, question in db.execute(statement).all()
    ]


def _qa_draft_fallback(
    *,
    question: str,
    doctor_name: str,
    prior_answers: list[dict[str, Any]],
    patient_context: dict[str, Any],
    top_exemplar: dict[str, Any] | None = None,
) -> str:
    """Deterministic, clinically-cautious draft used when no AI gateway is configured (placeholder).

    Pure function (no DB / no LLM). When a retrieved exemplar is available (``top_exemplar``) the draft
    is grounded in the clinic's own standard guidance for this kind of question — so even gateway-less
    the reply is prepared "based on how this clinic answers". Otherwise it falls back to a generic,
    cautious reassurance grounded in the patient's recent visit. Either way it reassures, points to the
    aftercare given, and escalates to the clinic when warranted, and never invents clinical specifics. A
    real LLM processor replaces this in production (Pro always has a gateway); the contract (a plain-text
    reply string) is unchanged.
    """
    first_name = (patient_context.get("displayName") or "").split(" ")[0] if patient_context.get("displayName") else None
    greeting = f"Hi {first_name}," if first_name else "Hi,"
    closing = (
        "If it gets worse, doesn't settle in a few days, or you're worried at all, please reply here or call the clinic "
        "and we'll take a closer look."
    )
    if top_exemplar and isinstance(top_exemplar.get("answer"), str) and top_exemplar["answer"].strip():
        # Ground the reply in the clinic's own approved guidance for a similar question.
        guidance = " ".join(top_exemplar["answer"].split())[:600]
        return f"{greeting} thanks for reaching out. {guidance} {closing}\n\n— {doctor_name}"
    recent = patient_context.get("recentVisitSummaries") or []
    visit_line = (
        f"Looking at your most recent visit ({' '.join(str(recent[0]).split())[:160]}), "
        if recent
        else "Looking at your recent visit notes, "
    )
    grounding = (
        "this is a common question and what you describe is usually part of normal healing"
        if prior_answers
        else "what you describe is usually part of normal healing"
    )
    return (
        f"{greeting} thanks for reaching out. {visit_line}{grounding}. "
        f"Please keep following the aftercare we gave you. {closing}\n\n— {doctor_name}"
    )


def qa_draft_worker_payload(db: DbSession, job: AiJob, ai_models: dict[str, str]) -> dict[str, Any]:
    """Build the worker payload for a qa_draft job (question + grounding + deterministic fallback)."""
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    message_id = metadata.get("qa_message_id")
    question = (
        db.execute(
            select(QaMessage).where(QaMessage.id == parse_uuid(str(message_id), "qa_message_id"), QaMessage.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if message_id
        else None
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Q&A draft target question is missing")
    thread = db.get(QaThread, question.thread_id)
    patient = db.get(Patient, job.patient_id)
    doctor_user_id = thread.assigned_doctor_user_id if thread else None
    doctor_name = _doctor_name(db, doctor_user_id) or CARE_TEAM_BYLINE
    patient_context = _patient_qa_context(db, patient, tenant_id=job.tenant_id)
    prior_answers = _prior_doctor_answers(db, tenant_id=job.tenant_id, doctor_user_id=doctor_user_id)
    # Retrieve the clinic's most relevant exemplars (templates + auto-indexed sent replies) so the
    # draft is grounded in how THIS clinic answers this kind of question (AES-410). The worker stays
    # stateless — the backend builds `retrievedExemplars`; the top one drives the provenance chip.
    # Retrieval is an enhancement, never a hard dependency — a failure degrades to an ungrounded draft.
    try:
        exemplars = qa_retrieval.retrieve(db, tenant_id=job.tenant_id, query=question.body)
    except Exception:  # noqa: BLE001 — never let a retrieval hiccup break drafting.
        db.rollback()
        exemplars = []
    retrieved = [
        {"question": item.get("question"), "answer": item.get("answer"), "source": item.get("kind"), "score": item.get("score")}
        for item in exemplars
    ]
    provenance = qa_library.provenance_from_exemplars(exemplars)
    fallback_draft = _qa_draft_fallback(
        question=question.body,
        doctor_name=doctor_name,
        prior_answers=prior_answers,
        patient_context=patient_context,
        top_exemplar=exemplars[0] if exemplars else None,
    )
    # Stash the provenance on the job so completion can persist it onto the question (the worker never
    # sees or returns provenance — it is the backend's deterministic attribution of the top exemplar).
    job.result_metadata = {**(job.result_metadata or {}), "qa_provenance": provenance}
    db.commit()
    return {
        "job": ai_job_payload(job),
        "aiModels": ai_models,
        "qaDraft": {
            "patientQuestion": question.body,
            "patientContext": patient_context,
            "priorAnswers": prior_answers,
            "retrievedExemplars": retrieved,
            # (G4) THIS thread's own earlier Q→A exchanges (bounded), so a follow-up question is drafted
            # with the conversation's context — no cross-patient risk (thread == this patient).
            "threadHistory": _thread_prior_turns(db, thread=thread, exclude_message_id=question.id) if thread else [],
            "doctorName": doctor_name,
        },
        "deterministicFallback": {"draft": fallback_draft, "source": "mock-deterministic"},
    }


def complete_qa_draft_worker_job(db: DbSession, *, job: AiJob, output: dict[str, Any]) -> dict[str, Any]:
    """Persist a completed qa_draft job: write the suggested reply onto the pending question."""
    completed_at = _utc_now()
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    message_id = metadata.get("qa_message_id")
    question = (
        db.execute(
            select(QaMessage).where(QaMessage.id == parse_uuid(str(message_id), "qa_message_id"), QaMessage.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if message_id
        else None
    )
    draft_text = output.get("draft") or output.get("drafted_reply")
    if isinstance(draft_text, str):
        draft_text = draft_text.strip() or None
    else:
        draft_text = None
    # Retrieval provenance was stashed on the job when its payload was built (the top exemplar the
    # draft is grounded in); surface it as the doctor-only "based on: …" chip.
    provenance = metadata.get("qa_provenance") if isinstance(metadata.get("qa_provenance"), dict) else None
    # Optimistic lock (Q-2): only the job the question currently points at may write its draft. A stale
    # qa_draft that finishes after a newer qa_draft/qa_revise took over (``draft_job_id`` moved on) must
    # NOT clobber the fresher state — it completes quietly. If the question is gone or already handled
    # (answered/dismissed), the draft is likewise no longer needed.
    owns_draft = question is not None and question.status == Q_PENDING and question.draft_job_id == job.id
    if owns_draft and draft_text:
        question.draft = draft_text
        question.draft_status = DRAFT_READY
        question.draft_source = output.get("source")
        question.draft_provenance = provenance
    elif owns_draft and not draft_text:
        question.draft_status = DRAFT_FAILED
        question.draft_provenance = None
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.result_metadata = {**metadata, "completed_at": completed_at.isoformat(), "source": output.get("source")}
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="qa_message",
        target_id=question.id if question is not None else None,
        details={"job_id": str(job.id), "job_type": job.job_type.value},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}


# --- Voice edit of a reply draft (qa_revise; AES-402) ---------------------------------------------


def _voice_object_key(tenant_id: uuid.UUID, message_id: uuid.UUID, job_id: uuid.UUID) -> str:
    return f"tenants/{tenant_id}/qa/{message_id}/voice/{job_id}"


def request_voice_edit(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    object_store: ObjectStore,
    message_id: str,
    audio: bytes,
    content_type: str,
    current_draft: str | None,
) -> dict[str, Any]:
    """Store the doctor's voice note and dispatch a job to revise/replace the reply draft (AES-402).

    The current editable draft is sent as the base; the AI decides whether the voice note revises it
    or is an entirely new reply. The audio is transient (deleted once the job completes).
    """
    require_qa_capability(db, principal.tenant_id)
    if not audio:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The voice note is empty")
    question = _get_question(db, principal.tenant_id, message_id)
    if question.status != Q_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This question is no longer pending")
    thread = _get_thread(db, principal.tenant_id, str(question.thread_id))

    job = AiJob(
        tenant_id=principal.tenant_id,
        patient_id=thread.patient_id,
        job_type=AiJobType.qa_revise,
        status=AiJobStatus.queued,
        generated_by="ai-engine",
        created_by_user_id=principal.user_id,
        result_metadata={"queue": "ai_jobs", "qa_thread_id": str(thread.id), "qa_message_id": str(question.id)},
    )
    db.add(job)
    db.flush()
    object_key = _voice_object_key(principal.tenant_id, question.id, job.id)
    object_store.put_object(
        object_key=object_key,
        data=io.BytesIO(audio),
        length=len(audio),
        content_type=content_type or "application/octet-stream",
        metadata={"tenant-id": str(principal.tenant_id), "qa-message-id": str(question.id)},
    )
    job.result_metadata = {
        **(job.result_metadata or {}),
        "voice_object_key": object_key,
        "voice_content_type": content_type or "application/octet-stream",
        "current_draft": (current_draft or "")[:MAX_REPLY_CHARS],
    }
    question.draft_status = DRAFT_REVISING
    question.draft_job_id = job.id
    audit(
        db,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        action="qa.reply.voice_edit",
        target_type="qa_message",
        target_id=question.id,
        details={"job_id": str(job.id)},
    )
    db.commit()
    db.refresh(job)
    dispatch_qa_revise_job(db, job)
    return {"messageId": str(question.id), "draftStatus": DRAFT_REVISING, "jobId": str(job.id)}


def dispatch_qa_revise_job(db: DbSession, job: AiJob) -> None:
    """Send a committed qa_revise job to Celery, marking broker failures (mirrors qa_draft)."""
    from app.celery_app import celery_app

    now = _utc_now()
    job.last_dispatched_at = now
    job.result_metadata = {**(job.result_metadata or {}), "last_dispatched_at": now.isoformat(), "queue": "ai_jobs"}
    try:
        celery_app.send_task(QA_REVISE_TASK_NAME, args=[str(job.id)], task_id=str(job.id), queue="ai_jobs")
        db.commit()
    except Exception as exc:  # noqa: BLE001 — broker down: persist a retryable state, recovery re-dispatches.
        schedule_retry(job, now=_utc_now(), error_message=str(exc), retry_reason="broker_unavailable")
        job.result_metadata = {**(job.result_metadata or {}), "queue_error": str(exc)}
        db.commit()


def mark_qa_job_failed(db: DbSession, job: AiJob) -> None:
    """Mark a terminally-failed qa_draft/qa_revise's target question with a VISIBLE failed state (Q-7).

    Called from ``fail_worker_job`` when a qa job exhausts retries. Without this the question sits at
    ``pending``/``revising`` forever and the inbox shows "Drafting…" indefinitely (the self-heal skips
    an in-flight draft). A failed initial draft → ``failed``; a failed voice edit → ``failed_revise``
    (the current draft is unchanged, so the doctor is told the edit didn't land). Only writes when this
    job still owns the draft (optimistic lock). Does NOT commit — the caller's transaction does.
    """
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    message_id = metadata.get("qa_message_id")
    if not message_id:
        return
    question = db.execute(
        select(QaMessage).where(QaMessage.id == parse_uuid(str(message_id), "qa_message_id"), QaMessage.tenant_id == job.tenant_id)
    ).scalar_one_or_none()
    if question is None or question.status != Q_PENDING or question.draft_job_id != job.id:
        return
    question.draft_status = DRAFT_FAILED_REVISE if job.job_type == AiJobType.qa_revise else DRAFT_FAILED


def get_message_draft(db: DbSession, principal: CurrentPrincipal, message_id: str) -> dict[str, Any]:
    """Lightweight draft state for the inbox to poll while a voice edit (or initial draft) runs."""
    require_qa_capability(db, principal.tenant_id)
    question = _get_question(db, principal.tenant_id, message_id)
    return {
        "messageId": str(question.id),
        "status": question.status,
        "draft": question.draft,
        "draftStatus": question.draft_status,
        "draftSource": question.draft_source,
        "draftProvenance": question.draft_provenance,
        "draftMode": (question.draft_source or "").split(":")[-1] if (question.draft_source or "").startswith("ai-voice:") else None,
    }


def internal_qa_voice_bytes(db: DbSession, *, object_store: ObjectStore, job_id: str) -> dict[str, Any]:
    """INTERNAL: stream a qa_revise job's stored voice note to the trusted worker."""
    job = db.execute(select(AiJob).where(AiJob.id == parse_uuid(job_id, "job_id"))).scalar_one_or_none()
    if job is None or job.job_type != AiJobType.qa_revise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note not found")
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    object_key = metadata.get("voice_object_key")
    if not object_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note not found")
    return {
        "content": object_store.get_object_bytes(str(object_key)),
        "media_type": metadata.get("voice_content_type") or "application/octet-stream",
        "filename": f"qa-voice-{job_id}",
    }


def qa_revise_worker_payload(db: DbSession, job: AiJob, ai_models: dict[str, str]) -> dict[str, Any]:
    """Build the worker payload for a qa_revise job (current draft + question/grounding + audio path)."""
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    message_id = metadata.get("qa_message_id")
    question = (
        db.execute(
            select(QaMessage).where(QaMessage.id == parse_uuid(str(message_id), "qa_message_id"), QaMessage.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if message_id
        else None
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Q&A voice-edit target question is missing")
    thread = db.get(QaThread, question.thread_id)
    patient = db.get(Patient, job.patient_id)
    doctor_user_id = thread.assigned_doctor_user_id if thread else None
    doctor_name = _doctor_name(db, doctor_user_id) or CARE_TEAM_BYLINE
    patient_context = _patient_qa_context(db, patient, tenant_id=job.tenant_id)
    current_draft = metadata.get("current_draft") or question.draft or ""
    return {
        "job": ai_job_payload(job),
        "aiModels": ai_models,
        "qaRevise": {
            "currentDraft": current_draft,
            "patientQuestion": question.body,
            "patientContext": patient_context,
            # (G4) `priorAnswers` dropped: qa_revise applies the doctor's OWN spoken instruction to a
            # GIVEN draft; other-thread answers are noise here (tone already comes from the draft), and
            # they were a cross-patient leak surface. Removing them shrinks every voice-edit prompt.
            "doctorName": doctor_name,
            "voiceEndpoint": f"/internal/qa/voice/{job.id}",
        },
        # No gateway → keep the current draft unchanged (the doctor can still edit by hand).
        "deterministicFallback": {"mode": "revise", "reply": current_draft, "source": "mock-deterministic"},
    }


def complete_qa_revise_worker_job(db: DbSession, *, job: AiJob, output: dict[str, Any]) -> dict[str, Any]:
    """Persist a completed qa_revise job: write the revised/rewritten reply onto the pending question."""
    completed_at = _utc_now()
    metadata = job.result_metadata if isinstance(job.result_metadata, dict) else {}
    message_id = metadata.get("qa_message_id")
    question = (
        db.execute(
            select(QaMessage).where(QaMessage.id == parse_uuid(str(message_id), "qa_message_id"), QaMessage.tenant_id == job.tenant_id)
        ).scalar_one_or_none()
        if message_id
        else None
    )
    reply_text = output.get("reply") or output.get("draft")
    reply_text = reply_text.strip()[:MAX_REPLY_CHARS] if isinstance(reply_text, str) and reply_text.strip() else None
    mode = output.get("mode") if output.get("mode") in {"revise", "replace"} else "revise"
    # A usable voice edit ONLY when the model actually produced it (source ``ai:…``). The deterministic
    # fallback (no gateway / unusable output / audio fetch failed) echoes the current draft with a
    # ``mock-deterministic`` source — treating that as a success would falsely badge the reply "Revised"
    # while the doctor's spoken correction never landed (Q-1, INV-SILENT).
    source = output.get("source")
    applied_by_ai = isinstance(source, str) and source.startswith("ai:")
    before_draft = metadata.get("current_draft") or question.draft if question is not None else None
    # Optimistic lock (Q-2): only the job the question currently points at may write (a stale revise
    # that lost the race to a newer job completes quietly).
    owns_draft = question is not None and question.status == Q_PENDING and question.draft_job_id == job.id
    if owns_draft and applied_by_ai and reply_text:
        question.draft = reply_text
        question.draft_status = DRAFT_READY
        question.draft_source = f"ai-voice:{mode}"
        # A `replace` is a fresh dictation — it is no longer "based on" the retrieved exemplar; a
        # `revise` keeps grounding the same draft, so the provenance chip survives.
        if mode == "replace":
            question.draft_provenance = None
        # HALF-2 harvest: a voice edit IS a doctor correcting the AI reply — record the before/after so
        # the qa golden set learns from real edits (retrieval provenance kept for triage; Q3-scrubbed).
        _record_qa_reply_feedback(
            db,
            tenant_id=job.tenant_id,
            actor_user_id=job.created_by_user_id,
            patient_id=job.patient_id,
            kind="correction",
            before=before_draft,
            after=reply_text,
            context={"source": "voice-edit", "mode": mode, "draftSource": source, "provenance": question.draft_provenance},
        )
    elif owns_draft:
        # Couldn't apply the spoken edit: the draft is UNCHANGED. Surface a visible failure (never a
        # silent "Revised") — the doctor is told and can edit by hand or retry (Q-1).
        question.draft_status = DRAFT_FAILED_REVISE
    # The voice note was transient — delete it now that the edit is applied.
    object_key = metadata.get("voice_object_key")
    if object_key:
        try:
            from app.storage import get_object_store

            get_object_store().delete_object(str(object_key))
        except Exception:  # noqa: BLE001 — best-effort cleanup; a leftover object is harmless.
            pass
    job.status = AiJobStatus.succeeded
    job.completed_at = completed_at
    job.error_message = None
    job.result_metadata = {**metadata, "completed_at": completed_at.isoformat(), "mode": mode, "source": output.get("source")}
    audit(
        db,
        tenant_id=job.tenant_id,
        actor_user_id=job.created_by_user_id,
        action="ai_processing.complete",
        target_type="qa_message",
        target_id=question.id if question is not None else None,
        details={"job_id": str(job.id), "job_type": job.job_type.value, "mode": mode},
    )
    db.commit()
    db.refresh(job)
    return {"job": ai_job_payload(job)}
