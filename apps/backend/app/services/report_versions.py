"""Content-addressed report-version store (pipeline-versioning foundation).

Each synthesis output is snapshotted as an immutable, content-addressed ``SessionReportVersion`` keyed
by the **ordered in-context capture-set hash**. An undo/edit that returns a session to a previously-seen
capture set is then a deterministic **cache-hit restore** (no LLM, no "wrong entries"); a never-seen set
falls through to a recompute. The user-state overlay (safety-flag rejections / dose confirmations /
aftercare opt-outs) is NOT stored here — it stays in ``session.extracted_metadata`` and is applied on
top, so a restore never disturbs user decisions. See docs/architecture/pipeline-versioning.md.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, Session, SessionReportVersion

# AI-artifact keys restored from a version onto the session's extracted_metadata. The user-state
# overlay keys (below) are deliberately EXCLUDED so a restore never overrides a user decision.
_ARTIFACT_METADATA_KEYS = (
    "treatments",
    "safety_flags",
    "aftercare_selections",
    "uncertainties",
    "treatment_review",
    "source_capture_ids",
    "session_processing_output",
)
# User-state overlay — authoritative, never part of a version, never overwritten on restore.
OVERLAY_METADATA_KEYS = ("rejected_safety_flags", "confirmed_carried_forward", "dismissed_aftercare")

_FLOOR = datetime.min.replace(tzinfo=timezone.utc)


def _generated_text(value: Any) -> str:
    """Display/generated text from a capture metadata field ({text:…} or a bare string)."""
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"].strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def _capture_content(capture: Capture) -> str:
    """The processed content a capture contributes to synthesis (transcript / caption / note)."""
    md = capture.capture_metadata if isinstance(capture.capture_metadata, dict) else {}
    for key in ("transcript", "caption", "detail"):
        text = _generated_text(md.get(key))
        if text:
            return text
    return ""


def session_capture_set(db: DbSession, session: Session) -> tuple[str, list[dict[str, str]]]:
    """Deterministic content-address of the session's current non-deleted captures, ordered.

    Used IDENTICALLY at record + lookup time, so an undo that returns to a prior capture set produces
    the same hash by construction (a changed out-of-context/edit state just yields a different hash → a
    safe recompute, never a wrong restore). Returns (hash, [{captureId, contentHash}]).
    """
    captures = list(
        db.execute(
            select(Capture).where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalars()
    )
    captures.sort(key=lambda c: ((c.captured_at or c.created_at or _FLOOR), str(c.id)))
    items = [
        {"captureId": str(c.id), "contentHash": hashlib.sha256(_capture_content(c).encode("utf-8")).hexdigest()}
        for c in captures
    ]
    set_hash = hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return set_hash, items


def _artifacts(session: Session) -> dict[str, Any]:
    md = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    return {
        "summary": session.summary,
        "generated_summary": session.generated_summary,
        "generated_report": session.generated_report,
        "report_model": session.report_model,
        "report_template_key": session.report_template_key,
        **{key: md.get(key) for key in _ARTIFACT_METADATA_KEYS},
    }


def record_report_version(
    db: DbSession, session: Session, *, generated_by: str | None = None, generated_at: datetime | None = None
) -> SessionReportVersion:
    """Snapshot the session's current synthesized artifacts as a content-addressed report_version.

    Idempotent per (session, capture_set_hash): a session that re-synthesizes to the same capture set
    refreshes that version's artifacts in place rather than duplicating. Staged on the session; the
    caller commits.
    """
    set_hash, items = session_capture_set(db, session)
    existing = db.execute(
        select(SessionReportVersion).where(
            SessionReportVersion.tenant_id == session.tenant_id,
            SessionReportVersion.session_id == session.id,
            SessionReportVersion.capture_set_hash == set_hash,
        )
    ).scalar_one_or_none()
    artifacts = _artifacts(session)
    if existing is not None:
        existing.captured_capture_version_ids = items
        existing.artifacts = artifacts
        existing.generated_by = generated_by
        existing.generated_at = generated_at
        return existing
    version = SessionReportVersion(
        tenant_id=session.tenant_id,
        session_id=session.id,
        capture_set_hash=set_hash,
        captured_capture_version_ids=items,
        artifacts=artifacts,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    db.add(version)
    return version


def find_report_version_for_current_set(db: DbSession, session: Session) -> SessionReportVersion | None:
    """The stored version matching the session's CURRENT capture set, if any (the undo cache-hit)."""
    set_hash, _ = session_capture_set(db, session)
    return db.execute(
        select(SessionReportVersion)
        .where(
            SessionReportVersion.tenant_id == session.tenant_id,
            SessionReportVersion.session_id == session.id,
            SessionReportVersion.capture_set_hash == set_hash,
        )
        .order_by(SessionReportVersion.created_at.desc())
    ).scalars().first()


def restore_report_version(session: Session, version: SessionReportVersion) -> None:
    """Restore a session's synthesized report from a stored version (deterministic; no LLM).

    Sets the AI artifact fields; the user-state overlay keys in ``extracted_metadata`` are preserved
    untouched (ground-truth invariant). Staged on the session; the caller commits + re-derives patient
    projections. Clears the stale marker — a restored version is current for this capture set.
    """
    artifacts = version.artifacts if isinstance(version.artifacts, dict) else {}
    if "summary" in artifacts:
        session.summary = artifacts.get("summary")
    if "generated_summary" in artifacts:
        session.generated_summary = artifacts.get("generated_summary")
    if "generated_report" in artifacts:
        session.generated_report = artifacts.get("generated_report")
    if isinstance(artifacts.get("report_model"), dict):
        session.report_model = artifacts["report_model"]
    if isinstance(artifacts.get("report_template_key"), str):
        session.report_template_key = artifacts["report_template_key"]
    metadata = dict(session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {})
    for key in _ARTIFACT_METADATA_KEYS:
        if key in artifacts:
            metadata[key] = artifacts.get(key)
    now_iso = datetime.now(timezone.utc).isoformat()
    metadata["generated_output_stale"] = False
    metadata["restored_from_version_at"] = now_iso
    # Refresh the transient draft/stale markers the delete path (mark_session_draft_after_capture_delete)
    # left behind, so the restored report reads as COMPLETE/current rather than queued/partial — the
    # restored report_model is the source of truth for the Pro synthesized report.
    metadata["processing_status"] = {
        "state": "complete",
        "label": "Complete",
        "stage": "complete",
        "source": "restore",
        "updated_at": now_iso,
    }
    for transient in ("progressive_report", "summaries", "stale_reason", "stale_at"):
        metadata.pop(transient, None)
    session.extracted_metadata = metadata  # overlay keys untouched (never in _ARTIFACT_METADATA_KEYS)
