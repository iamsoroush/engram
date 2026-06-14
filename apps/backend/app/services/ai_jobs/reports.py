"""Deterministic session report model + synchronous regeneration and contribution tracking."""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import (
    AiJob,
    AiJobStatus,
    AiJobType,
    Capture,
    CaptureStatus,
    CaptureType,
    OrganizationSource,
    Session,
    SessionStatus,
)
from app.services.capabilities import LIVE_REPORT_SYNTHESIS, tenant_has_capability
from app.services.caseload import tenant_vertical
from app.services.reporting import empty_report_model, render_report_body_markdown
from app.services.session_processing import capture_is_out_of_context

from app.services.ai_jobs.base import utc_now
from app.services.ai_jobs.context import generated_capture_text
from app.services.ai_jobs.orchestration import _session_capture_jobs

__all__ = [
    "report_contribution_effect",
    "mark_session_report_contributions",
    "has_append_intent",
    "session_has_pending_capture_jobs",
    "session_has_active_report_job",
    "session_has_reportable_capture",
    "session_has_uncontributed_capture",
    "build_session_report_model",
    "regenerate_session_report",
    "regenerate_session_report_if_idle",
]


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
    captures = sorted(
        _reportable_captures(db, tenant_id=session.tenant_id, session_id=session.id),
        key=lambda capture: (capture.captured_at or capture.created_at or utc_now()),
    )
    generated_at = utc_now()
    # Therapy branch: narrative-first, two-plane synthesis (DAP/SOAP/BIRP + private plane +
    # "Session so far") instead of the aesthetics by-type grouping. Kept fully isolated here so the
    # aesthetics path below is untouched. See app/services/therapy_reporting.py.
    if tenant_vertical(db, session.tenant_id) == "therapy":
        from app.services.therapy_reporting import apply_therapy_synthesis

        apply_therapy_synthesis(session, captures, db=db, generated_at=generated_at.isoformat())
        session.updated_at = generated_at
        return
    synthesized = tenant_has_capability(db, session.tenant_id, LIVE_REPORT_SYNTHESIS)
    model = build_session_report_model(session, captures, grouped=synthesized)
    session.report_model = model
    session.generated_report = render_report_body_markdown(model, db=db, session=session)
    session.organization_source = OrganizationSource.ai_engine
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    metadata = {**metadata, "generated_output_stale": False, "generated_at": generated_at.isoformat()}
    if synthesized:
        # The "Added to report" chip + meta strip ride on live-report synthesis; Basic is a plain chronological render.
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
