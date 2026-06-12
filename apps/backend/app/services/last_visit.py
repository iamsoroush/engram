"""Last-visit fetch (aesthetics-Basic, AES-106 / AES-203).

How Basic answers "what did we use last time" — by **retrieval**, not a structured form. Returns the
patient's prior visit's free-text note(s) and that visit's photos (before/after media; Basic does
*not* tag them — the eye pairs). Powers the returning-patient capture strip's "same as last time"
note pre-fill (AES-106) and the glanceable visit history (AES-203). Zero AI.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Capture, CaptureStatus, CaptureType, Session
from app.services.patients import get_patient
from app.services.sessions import parse_uuid

LAST_VISIT_SCHEMA_VERSION = "2026-06-12.last-visit.v1"


def _sort_date(session: Session) -> datetime:
    return session.captured_at or session.updated_at or session.created_at or datetime.min


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _note_text(capture: Capture) -> str | None:
    """Return the free-text typed note carried by a note capture (instant, from metadata)."""
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    for key in ("detail", "text", "note", "body"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _caption(capture: Capture) -> str | None:
    metadata = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    caption = metadata.get("caption")
    if isinstance(caption, dict) and isinstance(caption.get("text"), str) and caption["text"].strip():
        return caption["text"].strip()
    return None


def _visit_label(visit_at: datetime | None) -> str:
    if visit_at is None:
        return "from last visit"
    return f"from last visit · {visit_at.astimezone().date().isoformat()}"


def get_last_visit(
    db: DbSession,
    principal: CurrentPrincipal,
    patient_id: str,
    *,
    exclude_session_id: str | None = None,
) -> dict[str, Any]:
    """Return the patient's prior visit (note + before/after media) for retrieval (AES-106/203).

    Args:
        db: Active database session.
        principal: Authenticated staff principal (tenant scope).
        patient_id: The patient whose prior visit to fetch.
        exclude_session_id: The current in-progress visit to skip, so a returning patient gets the
            visit *before* the one being captured now.

    Returns:
        ``{"schemaVersion", "patientId", "hasPriorVisit", "visit", "sameAsLastTime"}``. ``visit``
        carries ``sessionId``, ``title``, ``capturedAt``, ``note`` (concatenated typed note(s)),
        ``captureCount``, and ``media`` (the visit's photos as ``{captureId, type, fileEndpoint,
        contentEndpoint, capturedAt, caption}``). ``sameAsLastTime`` is the deterministic pre-fill
        payload (``{note, fromSessionId, fromVisitAt, label}``) or ``None`` when the prior visit has
        no typed note.
    """
    get_patient(db, principal.tenant_id, patient_id)  # 404s on a bad/foreign patient
    patient_uuid = parse_uuid(patient_id, "patient_id")
    exclude_uuid = parse_uuid(exclude_session_id, "exclude_session_id") if exclude_session_id else None

    statement = select(Session).where(
        Session.tenant_id == principal.tenant_id,
        Session.patient_id == patient_uuid,
    )
    if exclude_uuid is not None:
        statement = statement.where(Session.id != exclude_uuid)
    sessions = db.execute(statement).scalars().all()
    sessions.sort(key=_sort_date, reverse=True)

    empty = {
        "schemaVersion": LAST_VISIT_SCHEMA_VERSION,
        "patientId": str(patient_uuid),
        "hasPriorVisit": False,
        "visit": None,
        "sameAsLastTime": None,
    }
    # Skip empty shells (no non-deleted captures) so "last visit" is a real prior visit.
    for session in sessions:
        captures = db.execute(
            select(Capture)
            .where(
                Capture.tenant_id == principal.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
            .order_by(Capture.captured_at, Capture.created_at)
        ).scalars().all()
        if not captures:
            continue

        note_texts = [text for capture in captures if (text := _note_text(capture)) and capture.capture_type == CaptureType.note]
        note = "\n\n".join(note_texts) if note_texts else None
        media = [
            {
                "captureId": str(capture.id),
                "type": capture.capture_type.value,
                "fileEndpoint": f"/api/v1/captures/{capture.id}/file" if capture.source_artifact_id else None,
                "contentEndpoint": f"/api/v1/captures/{capture.id}/file-content" if capture.source_artifact_id else None,
                "capturedAt": _iso(capture.captured_at),
                "caption": _caption(capture),
            }
            for capture in captures
            if capture.capture_type == CaptureType.photo and capture.source_artifact_id
        ]
        visit_at = _sort_date(session)
        return {
            "schemaVersion": LAST_VISIT_SCHEMA_VERSION,
            "patientId": str(patient_uuid),
            "hasPriorVisit": True,
            "visit": {
                "sessionId": str(session.id),
                "title": session.title,
                "status": session.status.value,
                "capturedAt": _iso(session.captured_at),
                "updatedAt": _iso(session.updated_at),
                "captureCount": len(captures),
                "note": note,
                "noteSource": "captures" if note else None,
                "media": media,
            },
            "sameAsLastTime": (
                {
                    "note": note,
                    "fromSessionId": str(session.id),
                    "fromVisitAt": _iso(visit_at) if visit_at != datetime.min else None,
                    "label": _visit_label(session.captured_at or session.updated_at),
                }
                if note
                else None
            ),
        }
    return empty
