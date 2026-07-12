"""Unified attention roll-up (Close-the-day / AES-1001).

One severity-tiered feed that aggregates every "needs you" signal that already lives in the
codebase — it invents no new clinical logic, it is a **roll-up** over existing sources:

* the needs-input assignment decisions (verify / choose-patient / resolve-conflict / assign-patient),
* unconfirmed carried-forward **doses** and ambiguous treatment corrections,
* the Batch-1 candidate suggestions (name correction, unassign, reassignment, inert-assignment
  conflict, "couldn't apply" notice) and per-capture ``patient_recheck``,
* detected clinical **safety** flags (shown first, but never counted as a to-do), and
* pending patient **Q&A** (deep-linked to the inbox thread; the reply flow is never reimplemented).

Every item maps to exactly one **severity tier** (the reusable language the sweep renders as
sections and the indicator renders as a coloured count):

* ``S1`` safety — shown, opt-out, **not counted** (never a blocker; counting it would pressure a
  clinician to "clear" safety, inverting the safe default);
* ``S2`` confirm — the true "N to confirm" (doses + the assignment decisions + conflicts);
* ``S3`` suggested — optional one-tap suggestions (a separate "optional" count);
* ``qa`` messages — pending patient questions (a separate async "messages" count).

The ``S4`` note tier (low-confidence extraction, missing lot) is deliberately **excluded** from the
roll-up: those are calm gray fix-at-source footnotes on the session, never a cross-session to-do.

Clinical ``reason``/``patientName`` text is returned verbatim in the report language (never
translated); the surrounding chrome (tier labels, section heads) is localized on the frontend from
the stable ``kind``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Capture, CaptureStatus, Patient, Session, SessionStatus
from app.services.capabilities import POST_SESSION_QA, tenant_capabilities
from app.services.patient_safety import session_kept_safety_flags
from app.services.treatment_overlay import overlay_satisfied_carry_forward_keys

ATTENTION_SCHEMA_VERSION = "2026-07-06.attention.v1"

# Tier → semantic group used by the counts + the indicator colour. `S4` (note) never rolls up.
TIER_SAFETY = "S1"
TIER_CONFIRM = "S2"
TIER_SUGGESTED = "S3"
TIER_MESSAGES = "qa"

# Kind → tier. The `kind` is the stable identity the frontend maps to a localized chrome label; the
# tier drives colour, section, and whether it counts toward the aggregate.
_KIND_TIER: dict[str, str] = {
    # S2 — confirm (the true "N to confirm")
    "dose": TIER_CONFIRM,
    "review-treatment": TIER_CONFIRM,
    "verify": TIER_CONFIRM,
    "choose-patient": TIER_CONFIRM,
    "resolve-conflict": TIER_CONFIRM,
    "assign-patient": TIER_CONFIRM,
    "inert-assignment": TIER_CONFIRM,
    "assignment-no-effect": TIER_CONFIRM,
    # S3 — suggested (optional one-tap)
    "suggested-reassignment": TIER_SUGGESTED,
    "suggested-name-correction": TIER_SUGGESTED,
    "suggested-unassign": TIER_SUGGESTED,
    "patient-recheck": TIER_SUGGESTED,
    # S1 — safety (shown, not counted)
    "safety-flag": TIER_SAFETY,
    # Q&A — messages
    "qa-pending": TIER_MESSAGES,
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _sort_time(session: Session) -> datetime | None:
    return session.captured_at or session.updated_at or session.created_at


def _metadata(session: Session) -> dict[str, Any]:
    return session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}


def _confirmed_carry_keys(session: Session, metadata: dict[str, Any]) -> set[str]:
    """Keys of carried-forward doses already confirmed (explicit list OR an overlay dose edit).

    Mirrors ``session_is_complete`` so the sweep's "N to confirm" never diverges from the report's
    own Complete gate.
    """
    explicit = set(metadata.get("confirmed_carried_forward") or [])
    return explicit | overlay_satisfied_carry_forward_keys(session)


def _assignment_decision(session: Session, metadata: dict[str, Any]) -> tuple[str, str] | None:
    """The single assignment decision a session needs, as ``(kind, reason)`` — or None.

    Priority mirrors ``patient_memory._session_needs_input_item`` exactly (the shared source of
    truth for the needs-input badge): verify → choose/resolve → assign. Review-treatments is handled
    separately, per-item, so it is not collapsed here.
    """
    action = metadata.get("ai_patient_action")
    if isinstance(action, dict) and action.get("needsVerification") is True:
        return (
            "verify",
            "An AI-created patient is awaiting your verification before it enters memory.",
        )
    match = metadata.get("patient_match")
    match_status = match.get("status") if isinstance(match, dict) else None
    if session.patient_id is None and match_status == "possible_match":
        risks = match.get("risks") if isinstance(match.get("risks"), list) else []
        has_conflict = any(
            "conflict" in str(risk).lower() or "national id" in str(risk).lower() for risk in risks
        )
        reason = match.get("reason") if isinstance(match.get("reason"), str) else None
        return (
            "resolve-conflict" if has_conflict else "choose-patient",
            reason or "Confirm which patient this visit belongs to before I update memory.",
        )
    if session.patient_id is None and session.status == SessionStatus.unassigned:
        return ("assign-patient", "This visit is saved, but I do not know which patient it belongs to.")
    return None


def _candidate_item(metadata: dict[str, Any]) -> tuple[str, str] | None:
    """The Batch-1 patient-match-candidate suggestion, as ``(kind, reason)`` — or None.

    An inert assignment (an appended-but-not-active reassignment, A-F7) is a **conflict** → S2;
    every other suggestion is an optional one-tap → S3.
    """
    candidate = metadata.get("patient_match_candidate")
    if not isinstance(candidate, dict):
        return None
    status = candidate.get("status") or candidate.get("decision")
    reason = candidate.get("reason") if isinstance(candidate.get("reason"), str) else None
    if status == "suggested_reassignment":
        if candidate.get("inertAssignment") is True:
            return ("inert-assignment", reason or "A recovered earlier capture named a different patient — review.")
        return ("suggested-reassignment", reason or "A capture suggests reassigning this visit.")
    if status == "assignment_no_effect":
        return ("assignment-no-effect", reason or "Heard a patient instruction but couldn't apply it — assign manually.")
    if status == "suggested_name_correction":
        return ("suggested-name-correction", reason or "The spoken name differs from this patient's stored name.")
    if status == "suggested_unassign":
        return ("suggested-unassign", reason or "A capture said this visit is not this patient — confirm to unassign.")
    return None


def session_attention_items(
    session: Session,
    *,
    patient_name: str | None,
    has_patient_recheck: bool,
) -> list[dict[str, Any]]:
    """Enumerate every attention item a single session contributes (pure — no DB).

    Returns raw item dicts without ``dayGroup``/aggregate context; the caller stamps those. The
    order within a session is stable (assignment decision, dose, review, candidate, recheck, safety).
    """
    metadata = _metadata(session)
    session_id = str(session.id)
    sort_dt = _sort_time(session)
    base = {
        "sessionId": session_id,
        "patientId": str(session.patient_id) if session.patient_id else None,
        "patientName": patient_name,
        "clinicianId": str(session.created_by_user_id) if session.created_by_user_id else None,
        "sortTime": _iso(sort_dt),
    }
    items: list[dict[str, Any]] = []

    def add(kind: str, reason: str | None, *, key: str | None = None) -> None:
        items.append({**base, "kind": kind, "tier": _KIND_TIER[kind], "reason": reason, "key": key})

    # Assignment decision (mutually exclusive — verify/choose/resolve/assign).
    decision = _assignment_decision(session, metadata)
    if decision is not None:
        add(decision[0], decision[1])

    # Unconfirmed carried-forward doses + ambiguous corrections (S2). Low-confidence / missing-lot
    # (S4 notes) are intentionally NOT rolled up — they stay as calm fix-at-source footnotes.
    review = metadata.get("treatment_review")
    if isinstance(review, list):
        confirmed = _confirmed_carry_keys(session, metadata)
        for item in review:
            if not isinstance(item, dict):
                continue
            category = item.get("category")
            reason = item.get("reason") if isinstance(item.get("reason"), str) else None
            if category == "carried_forward" and item.get("key") not in confirmed:
                add("dose", reason or "Confirm the carried-forward dose.", key=item.get("key"))
            elif category == "ambiguous":
                add("review-treatment", reason or "Confirm this treatment correction.")

    # Batch-1 candidate suggestion (S3, or S2 for an inert conflict).
    candidate = _candidate_item(metadata)
    if candidate is not None:
        add(candidate[0], candidate[1])

    # Per-capture transcript-edit recheck (S3).
    if has_patient_recheck:
        add("patient-recheck", "A capture that drives this visit's assignment was edited — recheck.")

    # Detected safety flags (S1 — shown, opt-out, never counted). Verbatim clinical text.
    for flag in session_kept_safety_flags(session):
        add("safety-flag", flag.get("text"))

    return items


def _day_group(sort_time_iso: str | None, *, local_today: Any) -> str:
    """`today` if the item's local calendar day is today, else `earlier` (carry-over)."""
    if not sort_time_iso:
        return "earlier"
    try:
        parsed = datetime.fromisoformat(sort_time_iso)
    except ValueError:
        return "earlier"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local_date = (parsed + local_today.offset).date()
    return "today" if local_date >= local_today.date else "earlier"


class _LocalToday:
    """The user's calendar 'today', shifted by their client tz offset (default UTC)."""

    def __init__(self, now: datetime, tz_offset_minutes: int) -> None:
        self.offset = timedelta(minutes=tz_offset_minutes)
        self.date = (now + self.offset).date()


def build_attention_feed(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    scope: str = "mine",
    tz_offset_minutes: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the unified attention roll-up for the Close-the-day sweep + the indicator.

    ``scope="mine"`` limits clinical items to the caller's own visits (a doctor's doses/safety) and
    the Q&A inbox to their routed threads; ``scope="clinic"`` spans the whole tenant (reception's
    assignment/intake coordination). Q&A is Pro-gated — Basic tenants simply contribute no messages.
    """
    normalized_scope = "clinic" if scope == "clinic" else "mine"
    tenant_id = principal.tenant_id
    now = now or datetime.now(timezone.utc)
    local_today = _LocalToday(now, tz_offset_minutes)

    session_stmt = select(Session).where(
        Session.tenant_id == tenant_id,
        Session.status != SessionStatus.failed,
    )
    if normalized_scope == "mine":
        session_stmt = session_stmt.where(Session.created_by_user_id == principal.user_id)
    sessions = db.execute(session_stmt).scalars().all()

    # Patient display-name map for the assigned sessions (content, verbatim).
    patient_ids = {session.patient_id for session in sessions if session.patient_id is not None}
    names: dict[uuid.UUID, str] = {}
    if patient_ids:
        for patient in db.execute(
            select(Patient).where(Patient.tenant_id == tenant_id, Patient.id.in_(patient_ids))
        ).scalars():
            names[patient.id] = patient.display_name

    # Sessions carrying a per-capture `patient_recheck` (transcript-edit re-check).
    recheck_sessions = _sessions_with_patient_recheck(db, tenant_id, principal, normalized_scope)

    items: list[dict[str, Any]] = []
    for session in sessions:
        session_items = session_attention_items(
            session,
            patient_name=names.get(session.patient_id) if session.patient_id else None,
            has_patient_recheck=session.id in recheck_sessions,
        )
        for item in session_items:
            item["dayGroup"] = _day_group(item["sortTime"], local_today=local_today)
            item["id"] = f"{item['sessionId']}:{item['kind']}:{item.get('key') or ''}"
            items.append(item)

    # Pending patient Q&A (Pro-gated; deep-links to the inbox thread — never a reply surface here).
    if POST_SESSION_QA in tenant_capabilities(db, tenant_id):
        from app.services.qa import qa_inbox

        inbox = qa_inbox(db, principal, scope="mine" if normalized_scope == "mine" else "all")
        for thread in inbox.get("items", []):
            if not thread.get("needsApproval"):
                continue
            pending = thread.get("pendingQuestion") or {}
            asked_at = pending.get("askedAt")
            items.append(
                {
                    "id": f"qa:{thread.get('threadId')}",
                    "kind": "qa-pending",
                    "tier": TIER_MESSAGES,
                    # Escalation (AES-1901): a red-flagged patient question escalates the bell above the
                    # normal messages tier — it's the most time-critical signal in the app.
                    "urgent": bool(thread.get("urgent")),
                    "sessionId": None,
                    "patientId": thread.get("patientId"),
                    "patientName": thread.get("patientName"),
                    "clinicianId": None,
                    "threadId": thread.get("threadId"),
                    "reason": pending.get("question"),
                    "key": None,
                    "sortTime": asked_at,
                    "dayGroup": _day_group(asked_at, local_today=local_today),
                }
            )

    aggregate = aggregate_attention_items(items)
    return {
        "schemaVersion": ATTENTION_SCHEMA_VERSION,
        "scope": normalized_scope,
        **aggregate,
    }


def aggregate_attention_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts + indicator colour + severity sort over a raw item list (pure)."""
    counts = {
        "confirm": sum(1 for item in items if item["tier"] == TIER_CONFIRM),
        "suggested": sum(1 for item in items if item["tier"] == TIER_SUGGESTED),
        "messages": sum(1 for item in items if item["tier"] == TIER_MESSAGES),
        "safety": sum(1 for item in items if item["tier"] == TIER_SAFETY),
        # Urgent red-flagged patient questions (AES-1901) — a subset of `messages`, surfaced separately
        # so the indicator can escalate above the normal violet messages tone.
        "urgent": sum(1 for item in items if item["tier"] == TIER_MESSAGES and item.get("urgent")),
    }
    # The aggregate "to-do" total excludes safety (opt-out awareness, never a to-do).
    counts["total"] = counts["confirm"] + counts["suggested"] + counts["messages"]

    # Indicator colour: an urgent patient red flag tops everything (the most time-critical signal),
    # then safety (never loses salience), then confirm, messages, suggested. None when everything is
    # clear (an empty feed means the checks ran and passed).
    highest = None
    if counts["urgent"]:
        highest = "urgent"
    elif counts["safety"]:
        highest = "safety"
    elif counts["confirm"]:
        highest = "confirm"
    elif counts["messages"]:
        highest = "messages"
    elif counts["suggested"]:
        highest = "suggested"

    # Newest-open first; the frontend buckets into severity sections + the Earlier carry-over group.
    ordered = sorted(items, key=lambda item: item.get("sortTime") or "", reverse=True)
    return {"counts": counts, "highestTier": highest, "items": ordered}


def _sessions_with_patient_recheck(
    db: DbSession, tenant_id: uuid.UUID, principal: CurrentPrincipal, scope: str
) -> set[uuid.UUID]:
    """Session ids with a live per-capture ``patient_recheck`` marker (transcript-edit re-check)."""
    stmt = (
        select(Capture.session_id)
        .join(Session, Session.id == Capture.session_id)
        .where(
            Capture.tenant_id == tenant_id,
            Capture.status != CaptureStatus.deleted,
            Capture.capture_metadata["needs_review"]["kind"].astext == "patient_recheck",
        )
    )
    if scope == "mine":
        stmt = stmt.where(Session.created_by_user_id == principal.user_id)
    return {row[0] for row in db.execute(stmt).all() if row[0] is not None}
