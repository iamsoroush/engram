"""AI-quality feedback harvesting — the eval golden-set harvester (``docs/ai_engine/eval-epic.md`` §1b).

Every staff correction of an AI output (transcript / caption / treatment / patient-match) and every
report/brief thumbs rating is written to ``ai_feedback_events`` as a candidate eval case. Two entry
points:

- ``record_feedback_event`` / the ``record_*`` helpers — called from the service layer *inside the
  existing correction transaction* (like ``audit``): cheap, append-only, and wrapped so a logging bug
  can never break the user's edit. This is the non-bypassable harvester.
- ``create_feedback`` / ``list_feedback`` — back the thin ``POST/GET /feedback`` endpoint (the report
  thumbs rating + any client-supplied signal).

PII posture: the before/after AI-output *text* is stored verbatim because it IS the eval target (a
transcript's confusable name is the case). Structured patient PII (names, national id, phone, DOB,
address, raw match evidence) never enters ``context`` — ``scrub_context`` redacts it.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import AiFeedbackEvent

logger = logging.getLogger(__name__)

ALLOWED_KINDS = frozenset({"correction", "confirmation", "rating", "rejection"})
ALLOWED_OUTPUT_TYPES = frozenset(
    {"transcript", "caption", "treatment", "patient_match", "report", "brief", "safety_flag", "qa_reply"}
)

# Keys whose values may carry patient PII; redacted before anything is persisted to `context`.
_SENSITIVE_KEYS = frozenset(
    {
        "name",
        "names",
        "displayname",
        "display_name",
        "fullname",
        "full_name",
        "legalfirstname",
        "legal_first_name",
        "legallastname",
        "legal_last_name",
        "firstname",
        "lastname",
        "patientname",
        "phone",
        "email",
        "nationalid",
        "national_id",
        "dateofbirth",
        "date_of_birth",
        "dob",
        "address",
        "evidence",
        "identifiervalue",
        "identifier_value",
        "normalizedvalue",
        "normalized_value",
        "reason",  # an AI match reason can quote the spoken patient name
    }
)
_REDACTED = "[redacted]"
_MAX_TEXT = 8000


def _is_sensitive_key(key: str) -> bool:
    return key.lower() in _SENSITIVE_KEYS


def scrub_context(value: Any) -> Any:
    """Recursively redact values under PII-bearing keys, preserving structure for eval triage."""
    if isinstance(value, dict):
        return {key: (_REDACTED if _is_sensitive_key(str(key)) else scrub_context(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_context(item) for item in value]
    return value


def _clip(text: str | None) -> str | None:
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT]


def text_of(value: Any) -> str | None:
    """Pull the editable text out of a caption/transcript metadata value (dict ``{text}`` or str)."""
    if isinstance(value, dict):
        inner = value.get("text")
        return inner if isinstance(inner, str) else None
    if isinstance(value, str):
        return value
    return None


def record_feedback_event(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    kind: str,
    ai_output_type: str,
    before_value: str | None = None,
    after_value: str | None = None,
    rating: int | None = None,
    comment: str | None = None,
    context: dict[str, Any] | None = None,
    session_id: uuid.UUID | None = None,
    capture_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
) -> None:
    """Stage one feedback row in the current transaction (no commit). Never raises into the caller.

    Mirrors ``auth.service.audit``: a plain ``db.add`` so the harvest commits atomically with the
    correction it records. Guarded end-to-end — a malformed value or unexpected error logs a warning
    and drops the signal rather than poisoning the user's edit.
    """
    try:
        if kind not in ALLOWED_KINDS or ai_output_type not in ALLOWED_OUTPUT_TYPES:
            logger.warning("feedback: dropping event with kind=%s output=%s", kind, ai_output_type)
            return
        db.add(
            AiFeedbackEvent(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                kind=kind,
                ai_output_type=ai_output_type,
                before_value=_clip(before_value),
                after_value=_clip(after_value),
                rating=rating,
                comment=_clip(comment),
                context=scrub_context(context or {}),
                session_id=session_id,
                capture_id=capture_id,
                patient_id=patient_id,
            )
        )
    except Exception:  # noqa: BLE001 — feedback harvesting must never break a correction
        logger.exception("feedback: failed to stage event (kind=%s output=%s)", kind, ai_output_type)


def record_text_correction(
    db: DbSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    ai_output_type: str,
    before: str | None,
    after: str | None,
    session_id: uuid.UUID | None = None,
    capture_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    """Record a caption/transcript correction, but only when the staff text actually changed."""
    if not after or (before or "").strip() == (after or "").strip():
        return
    record_feedback_event(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        kind="correction",
        ai_output_type=ai_output_type,
        before_value=before,
        after_value=after,
        session_id=session_id,
        capture_id=capture_id,
        patient_id=patient_id,
        context=context,
    )


def record_capture_text_correction(
    db: DbSession,
    principal: CurrentPrincipal,
    capture: Any,
    previous_metadata: dict[str, Any],
    incoming_metadata: dict[str, Any],
) -> None:
    """Harvest a transcript/caption edit from a ``PATCH /captures`` staff edit.

    ``before`` is the preserved AI original (``ai_caption``/``ai_transcript``) when present, else the
    value being replaced; ``after`` is the incoming staff text. The AI text is the eval target — stored
    verbatim — so this is what feeds the transcription/caption golden sets.
    """
    for field, output_type in (("caption", "caption"), ("transcript", "transcript")):
        incoming = incoming_metadata.get(field)
        if not isinstance(incoming, dict) or incoming.get("source") != "staff_edit":
            continue
        after = text_of(incoming)
        ai_original = previous_metadata.get(f"ai_{field}")
        before_source = ai_original if isinstance(ai_original, dict) else previous_metadata.get(field)
        before = text_of(before_source)
        before_origin = before_source.get("source") if isinstance(before_source, dict) else None
        record_text_correction(
            db,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            ai_output_type=output_type,
            before=before,
            after=after,
            session_id=capture.session_id,
            capture_id=capture.id,
            patient_id=capture.patient_id,
            context={"source": "capture-edit", "ai_source": before_origin},
        )


def create_feedback(db: DbSession, principal: CurrentPrincipal, request: Any) -> dict[str, Any]:
    """Persist a client-supplied feedback signal (the report/brief thumbs rating) and return it."""
    kind = (request.kind or "rating").strip()
    output_type = (request.ai_output_type or "report").strip()
    if kind not in ALLOWED_KINDS:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback kind")
    if output_type not in ALLOWED_OUTPUT_TYPES:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid feedback output type")

    def _opt_uuid(value: str | None, name: str) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {name}") from exc

    event = AiFeedbackEvent(
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        kind=kind,
        ai_output_type=output_type,
        before_value=_clip(request.before),
        after_value=_clip(request.after),
        rating=request.rating,
        comment=_clip(request.comment),
        context=scrub_context(request.context or {}),
        session_id=_opt_uuid(request.session_id, "sessionId"),
        capture_id=_opt_uuid(request.capture_id, "captureId"),
        patient_id=_opt_uuid(request.patient_id, "patientId"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return feedback_payload(event)


def list_feedback(
    db: DbSession,
    principal: CurrentPrincipal,
    *,
    limit: int = 50,
    kind: str | None = None,
    ai_output_type: str | None = None,
) -> list[dict[str, Any]]:
    """List recent feedback for the tenant (the harvester / QA read). Tenant-scoped, newest first."""
    statement = select(AiFeedbackEvent).where(AiFeedbackEvent.tenant_id == principal.tenant_id)
    if kind:
        statement = statement.where(AiFeedbackEvent.kind == kind)
    if ai_output_type:
        statement = statement.where(AiFeedbackEvent.ai_output_type == ai_output_type)
    rows = db.execute(statement.order_by(AiFeedbackEvent.created_at.desc()).limit(min(limit, 200))).scalars()
    return [feedback_payload(row) for row in rows]


def feedback_payload(event: AiFeedbackEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "kind": event.kind,
        "aiOutputType": event.ai_output_type,
        "before": event.before_value,
        "after": event.after_value,
        "rating": event.rating,
        "comment": event.comment,
        "context": event.context,
        "sessionId": str(event.session_id) if event.session_id else None,
        "captureId": str(event.capture_id) if event.capture_id else None,
        "patientId": str(event.patient_id) if event.patient_id else None,
        "actorUserId": str(event.actor_user_id) if event.actor_user_id else None,
        "createdAt": event.created_at.isoformat() if event.created_at else None,
    }
