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
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Capture, CaptureStatus, Session, SessionReportVersion
from app.services.session_processing import capture_is_out_of_context

# AI-artifact keys restored from a version onto the session's extracted_metadata. The user-state
# overlay keys (below) are deliberately EXCLUDED so a restore never overrides a user decision.
_ARTIFACT_METADATA_KEYS = (
    "treatments",
    "safety_flags",
    "aftercare_selections",
    "uncertainties",
    # v2 companions of `uncertainties` / `safety_flags`: without these a restore desyncs the coded
    # uncertainty reasons, the cross-visit reconcile decisions, and the report-language stamp from the
    # artifacts they annotate (S-F14). The reconcile decisions are re-validated against the restored
    # patient's flags at apply time, so restoring them is safe even after a reassignment.
    "uncertainty_reasons",
    "safety_reconciliation",
    # (G6) the candidate-flag-set key the reconcile decisions were computed over — restored alongside
    # `safety_reconciliation` so the reconcile memo stays consistent across a cache-restore.
    "safety_reconciliation_keys",
    "lang",
    "treatment_review",
    "source_capture_ids",
    "session_processing_output",
)
# User-state overlay — authoritative, never part of a version, never overwritten on restore. The
# `treatment_overlay` (AES-1101) is the fourth class: human field edits on treatment rows, folded at
# render/projection (services/treatment_overlay.py) and excluded from restore for free — it is not in
# _ARTIFACT_METADATA_KEYS, so restore_report_version (which copies ONLY those) never touches it.
OVERLAY_METADATA_KEYS = (
    "rejected_safety_flags",
    "confirmed_carried_forward",
    "dismissed_aftercare",
    "treatment_overlay",
)

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


def session_capture_set(db: DbSession, session: Session) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic content-address of the session's current non-deleted captures, ordered.

    Used IDENTICALLY at record + lookup time, so an undo that returns to a prior capture set produces
    the same hash by construction (a changed out-of-context/edit state just yields a different hash → a
    safe recompute, never a wrong restore). Out-of-context membership is part of the key (D1): a
    "Mark relevant" / mark-out-of-context toggle changes the synthesized input, so it must change the
    hash — otherwise a cache-hit-before-dispatch would restore a report over the wrong capture set.
    Returns (hash, [{captureId, contentHash, outOfContext}]).
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
        {
            "captureId": str(c.id),
            "contentHash": hashlib.sha256(_capture_content(c).encode("utf-8")).hexdigest(),
            "outOfContext": capture_is_out_of_context(c),
        }
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
        # The patient this version was synthesized FOR. The capture-set hash is patient-blind (it hashes
        # capture content only), so two patients with the same captures collide; scoping the cache-hit to
        # the recorded patient stops a stale cross-patient version restoring on a reassigned session
        # (S-F2/S-F6). Kept out of _ARTIFACT_METADATA_KEYS so it never leaks into the restored metadata.
        "patientId": str(session.patient_id) if session.patient_id else None,
        **{key: md.get(key) for key in _ARTIFACT_METADATA_KEYS},
    }


def record_report_version(
    db: DbSession,
    session: Session,
    *,
    generated_by: str | None = None,
    generated_at: datetime | None = None,
    capture_set: tuple[str, list[dict[str, Any]]] | None = None,
) -> SessionReportVersion:
    """Snapshot the session's current synthesized artifacts as a content-addressed report_version.

    Idempotent per (session, capture_set_hash): a session that re-synthesizes to the same capture set
    refreshes that version's artifacts in place rather than duplicating. Staged on the session; the
    caller commits.

    ``capture_set`` overrides the (hash, items) the version is keyed by — pass the job-START snapshot so a
    mid-job capture EDIT can't key pre-edit artifacts under the post-edit content hash (S-F5). Defaults to
    the session's current capture set.
    """
    set_hash, items = capture_set if capture_set is not None else session_capture_set(db, session)
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
    """The stored version matching the session's CURRENT capture set AND patient, if any (undo cache-hit).

    Patient-scoped: the capture-set hash is patient-blind, so a version recorded while the session was
    assigned to a different patient must NOT cache-restore onto the reassigned session (it carries that
    patient's carry-forward doses + safety-reconcile decisions — S-F2/S-F6). A version whose recorded
    ``patientId`` differs from the session's current patient is skipped, forcing a fresh re-synthesis.
    """
    set_hash, _ = session_capture_set(db, session)
    current_patient = str(session.patient_id) if session.patient_id else None
    versions = db.execute(
        select(SessionReportVersion)
        .where(
            SessionReportVersion.tenant_id == session.tenant_id,
            SessionReportVersion.session_id == session.id,
            SessionReportVersion.capture_set_hash == set_hash,
        )
        .order_by(SessionReportVersion.created_at.desc())
    ).scalars()
    for version in versions:
        artifacts = version.artifacts if isinstance(version.artifacts, dict) else {}
        version_patient = artifacts.get("patientId")
        version_patient = str(version_patient) if version_patient else None
        if version_patient == current_patient:
            return version
    return None


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


# --- Report-version history (E14 / AES-14xx) ---------------------------------------------------------
# The read + revert-restore surface over this store. Trigger derivation and reachability are pure
# functions of the stored capture-set snapshots; the HTTP-facing reads live in services/report_history.py
# and the destructive revert-restore lives with the capture de-effect family in services/captures.py.

_ADDED_TRIGGER_BY_TYPE = {"photo": "photo_added", "audio": "audio_added", "note": "note_added"}
_EDITED_TRIGGER_BY_TYPE = {"photo": "caption_edited", "audio": "transcript_edited", "note": "note_edited"}


def _items_by_id(items: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("captureId"):
            result[str(item["captureId"])] = item
    return result


def in_context_capture_count(version: SessionReportVersion) -> int:
    """How many in-context captures the version was synthesized over (out-of-context excluded)."""
    return sum(
        1
        for item in (version.captured_capture_version_ids or [])
        if isinstance(item, dict) and not item.get("outOfContext")
    )


def derive_version_trigger(
    prev_items: list[dict[str, Any]] | None,
    curr_items: list[dict[str, Any]] | None,
    capture_type_by_id: dict[str, str],
) -> dict[str, Any]:
    """Structured descriptor for how a version differs from the chronologically prior one.

    Keys-only (``kind`` + optional ``count``); the frontend localizes the label (chrome is bilingual, so
    the server must never author the display string). Derived deterministically from the capture-set delta.
    """
    if prev_items is None:
        return {"kind": "first_report"}
    prev = _items_by_id(prev_items)
    curr = _items_by_id(curr_items)
    added = [cid for cid in curr if cid not in prev]
    removed = [cid for cid in prev if cid not in curr]
    if added and not removed:
        if len(added) == 1:
            return {"kind": _ADDED_TRIGGER_BY_TYPE.get(capture_type_by_id.get(added[0], ""), "capture_added")}
        return {"kind": "captures_added", "count": len(added)}
    if removed and not added:
        return {"kind": "capture_removed"} if len(removed) == 1 else {"kind": "captures_removed", "count": len(removed)}
    if added and removed:
        return {"kind": "report_updated"}
    # Same id set → an edit and/or an out-of-context toggle on existing captures.
    edited = [cid for cid in curr if prev[cid].get("contentHash") != curr[cid].get("contentHash")]
    toggled = [cid for cid in curr if bool(prev[cid].get("outOfContext")) != bool(curr[cid].get("outOfContext"))]
    if toggled and not edited:
        became_out = bool(curr[toggled[0]].get("outOfContext"))
        return {"kind": "marked_out_of_context" if became_out else "marked_relevant"}
    if edited:
        if len(edited) == 1:
            return {"kind": _EDITED_TRIGGER_BY_TYPE.get(capture_type_by_id.get(edited[0], ""), "capture_edited")}
        return {"kind": "captures_edited", "count": len(edited)}
    return {"kind": "report_updated"}


def current_capture_index(db: DbSession, session: Session) -> tuple[dict[str, Capture], dict[str, bool]]:
    """(id → Capture, id → out-of-context) over the session's CURRENT non-deleted captures."""
    captures = list(
        db.execute(
            select(Capture).where(
                Capture.tenant_id == session.tenant_id,
                Capture.session_id == session.id,
                Capture.status != CaptureStatus.deleted,
            )
        ).scalars()
    )
    by_id = {str(c.id): c for c in captures}
    ooc = {cid: capture_is_out_of_context(capture) for cid, capture in by_id.items()}
    return by_id, ooc


def removal_target_for_version(
    current_by_id: dict[str, Capture],
    current_ooc: dict[str, bool],
    version: SessionReportVersion,
) -> list[Capture] | None:
    """Current captures to soft-delete to return the session to ``version``'s capture set — or ``None`` if
    the version is NOT reachable by removal alone (→ preview-only). An **empty** list means the version
    already equals the current set.

    Reachable ⟺ every capture the version knew still exists AND its out-of-context membership is unchanged:
    a pure removal can neither un-delete a capture nor toggle context back, so anything else can't be
    reproduced by removal (those non-linear cases are honestly preview-only in v1).
    """
    v_by_id = _items_by_id(version.captured_capture_version_ids)
    if not set(v_by_id).issubset(current_by_id):
        return None
    for cid, item in v_by_id.items():
        if current_ooc.get(cid) != bool(item.get("outOfContext")):
            return None
    return [capture for cid, capture in current_by_id.items() if cid not in v_by_id]


def version_removal_target(db: DbSession, session: Session, version: SessionReportVersion) -> list[Capture] | None:
    """DB-backed :func:`removal_target_for_version` for the single-target restore action."""
    by_id, ooc = current_capture_index(db, session)
    return removal_target_for_version(by_id, ooc, version)


def get_session_report_version(db: DbSession, session: Session, version_id: str) -> SessionReportVersion:
    """Fetch one stored version scoped to the session/tenant (400 on a bad id, 404 when absent)."""
    try:
        vid = uuid.UUID(str(version_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid version id") from exc
    version = db.execute(
        select(SessionReportVersion).where(
            SessionReportVersion.id == vid,
            SessionReportVersion.tenant_id == session.tenant_id,
            SessionReportVersion.session_id == session.id,
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report version not found")
    return version
