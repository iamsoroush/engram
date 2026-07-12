"""Report version-history read surface (E14 / AES-14xx).

The HTTP-facing reads over the content-addressed ``session_report_versions`` store: the version timeline
(list) and one version's artifacts (read-only preview). The pure store + reachability/trigger helpers live
in ``services/report_versions.py``; the destructive revert-restore lives with the capture de-effect family
in ``services/captures.py`` (``restore_session_report_version``) so it reuses the exact undo machinery. See
docs/architecture/pipeline-versioning.md and docs/work/ux-epic-report-history.md.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import CurrentPrincipal
from app.models import Capture, Patient, Session, SessionReportVersion
from app.services.capture_storage import get_session_for_tenant
from app.services.patient_safety import (
    safety_loss_diff,
    session_kept_safety_flags,
    session_rejected_safety_flag_keys,
    validate_safety_flags,
)
from app.services.report_versions import (
    _ARTIFACT_METADATA_KEYS,
    derive_version_trigger,
    find_report_version_for_current_set,
    full_capture_index,
    get_session_report_version,
    in_context_capture_count,
    session_version_transition,
    version_transition,
)
from app.services.sessions import parse_uuid


def _capture_type_by_id(db: DbSession, session: Session) -> dict[str, str]:
    """id → capture_type over ALL of the session's captures (including soft-deleted ones, so a removed
    capture's type is still known when labelling a `capture removed` trigger)."""
    rows = db.execute(
        select(Capture.id, Capture.capture_type).where(
            Capture.tenant_id == session.tenant_id,
            Capture.session_id == session.id,
        )
    ).all()
    return {str(cid): getattr(ctype, "value", str(ctype)) for cid, ctype in rows}


def _version_capture_ids(version: SessionReportVersion) -> list[str]:
    return [
        str(item["captureId"])
        for item in (version.captured_capture_version_ids or [])
        if isinstance(item, dict) and item.get("captureId")
    ]


def _version_meta(version: SessionReportVersion, *, is_current: bool, restorable: bool) -> dict[str, Any]:
    """Timeline-row metadata for one version (provenance demoted; no artifacts — those load on preview)."""
    return {
        "id": str(version.id),
        "captureSetHash": version.capture_set_hash,
        "captureCount": in_context_capture_count(version),
        # The capture ids this version knew — the client diffs them against the live session to name how
        # many captures a restore would remove (the destructive-action confirmation).
        "captureIds": _version_capture_ids(version),
        "generatedAt": version.generated_at.isoformat() if version.generated_at else None,
        "createdAt": version.created_at.isoformat() if version.created_at else None,
        "generatedBy": version.generated_by,
        "isCurrent": is_current,
        "restorable": restorable,
    }


def list_session_report_versions(db: DbSession, principal: CurrentPrincipal, session_id: str) -> dict[str, Any]:
    """The session's report-version timeline, newest-first.

    ``restorable`` = reachable by a pure removal (a proper past set); the owner-only gate is enforced on the
    restore action, not here (reading the timeline is staff/admin). ``isCurrent`` marks the version being
    rendered now (the patient-scoped cache-hit for the current capture set).
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    versions = list(
        db.execute(
            select(SessionReportVersion)
            .where(
                SessionReportVersion.tenant_id == session.tenant_id,
                SessionReportVersion.session_id == session.id,
                # E17: a forward-branch prune leaves the DB row but hides it from the timeline.
                SessionReportVersion.pruned_at.is_(None),
            )
            .order_by(SessionReportVersion.created_at.asc())
        ).scalars()
    )
    type_by_id = _capture_type_by_id(db, session)
    # Index over ALL captures (incl. soft-deleted) so a FORWARD (redo) version — one that re-effects a
    # de-effected capture — reads as restorable, not preview-only.
    all_by_id, all_ooc, live_ids = full_capture_index(db, session)
    current_version = find_report_version_for_current_set(db, session)
    current_id = str(current_version.id) if current_version is not None else None

    rows: list[dict[str, Any]] = []
    prev_items: list[dict[str, Any]] | None = None
    for version in versions:  # ascending → prev_items is the chronologically earlier version
        items = version.captured_capture_version_ids if isinstance(version.captured_capture_version_ids, list) else []
        transition = version_transition(all_by_id, all_ooc, live_ids, version)
        rows.append(
            {
                **_version_meta(
                    version,
                    is_current=(str(version.id) == current_id),
                    # Reachable (transition is not None) AND not already the current set (non-empty).
                    restorable=bool(transition is not None and not transition.is_noop),
                ),
                "trigger": derive_version_trigger(prev_items, items, type_by_id),
            }
        )
        prev_items = items
    rows.reverse()  # newest-first for display
    return {"versions": rows}


def restore_impact(db: DbSession, session: Session, version: SessionReportVersion) -> dict[str, Any]:
    """What restoring the session to ``version`` would do — captures moved + safety flags lost.

    Deterministic (no LLM): the transition gives the removed/restored capture counts; the safety-loss diff
    compares the visit's currently-kept flags against the target version's kept flags (detected − the
    live rejections), and marks each disappearing flag with whether it also leaves the PATIENT file (no
    other visit records it). Powers the restore confirm's safety-loss guard (E17 finding 1).
    """
    transition = session_version_transition(db, session, version)
    if transition is None:
        return {
            "reachable": False,
            "restorable": False,
            "removedCaptureCount": 0,
            "restoredCaptureCount": 0,
            "safetyLoss": [],
        }
    current_kept = session_kept_safety_flags(session)
    rejected = set(session_rejected_safety_flag_keys(session))
    target_detected = validate_safety_flags((version.artifacts or {}).get("safety_flags"))
    surviving_keys = {flag["key"] for flag in target_detected if flag["key"] not in rejected}
    patient = db.get(Patient, session.patient_id) if session.patient_id else None
    return {
        "reachable": True,
        "restorable": bool(transition.to_delete or transition.to_restore),
        "removedCaptureCount": len(transition.to_delete),
        "restoredCaptureCount": len(transition.to_restore),
        "safetyLoss": safety_loss_diff(patient, session.id, current_kept, surviving_keys),
    }


def get_session_report_version_detail(
    db: DbSession, principal: CurrentPrincipal, session_id: str, version_id: str
) -> dict[str, Any]:
    """One version's artifacts, session-shaped for a read-only preview.

    Returns the same fields ``restore_report_version`` copies onto a session (report prose/model + the
    artifact-class metadata). The user-state overlay is NOT included — it is applied client-side from the
    *live* session so user decisions are never time-traveled away (pipeline-versioning D2). Also carries
    ``restoreImpact`` (captures moved + safety loss) so the restore confirm can name what disappears.
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    version = get_session_report_version(db, session, version_id)
    artifacts = version.artifacts if isinstance(version.artifacts, dict) else {}
    impact = restore_impact(db, session, version)
    current_version = find_report_version_for_current_set(db, session)
    return {
        "version": _version_meta(
            version,
            is_current=(current_version is not None and str(version.id) == str(current_version.id)),
            restorable=impact["restorable"],
        ),
        "report": {
            "summary": artifacts.get("summary"),
            "generatedSummary": artifacts.get("generated_summary"),
            "generatedReport": artifacts.get("generated_report"),
            "reportModel": artifacts.get("report_model"),
            "reportTemplateKey": artifacts.get("report_template_key"),
            "extractedMetadata": {key: artifacts.get(key) for key in _ARTIFACT_METADATA_KEYS if key in artifacts},
        },
        "restoreImpact": impact,
    }
