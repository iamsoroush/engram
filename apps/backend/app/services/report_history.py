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
from app.models import Capture, Session, SessionReportVersion
from app.services.capture_storage import get_session_for_tenant
from app.services.report_versions import (
    _ARTIFACT_METADATA_KEYS,
    current_capture_index,
    derive_version_trigger,
    find_report_version_for_current_set,
    get_session_report_version,
    in_context_capture_count,
    removal_target_for_version,
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
            )
            .order_by(SessionReportVersion.created_at.asc())
        ).scalars()
    )
    type_by_id = _capture_type_by_id(db, session)
    current_by_id, current_ooc = current_capture_index(db, session)
    current_version = find_report_version_for_current_set(db, session)
    current_id = str(current_version.id) if current_version is not None else None

    rows: list[dict[str, Any]] = []
    prev_items: list[dict[str, Any]] | None = None
    for version in versions:  # ascending → prev_items is the chronologically earlier version
        items = version.captured_capture_version_ids if isinstance(version.captured_capture_version_ids, list) else []
        removal = removal_target_for_version(current_by_id, current_ooc, version)
        rows.append(
            {
                **_version_meta(
                    version,
                    is_current=(str(version.id) == current_id),
                    restorable=bool(removal),  # reachable AND non-empty (an empty removal = already current)
                ),
                "trigger": derive_version_trigger(prev_items, items, type_by_id),
            }
        )
        prev_items = items
    rows.reverse()  # newest-first for display
    return {"versions": rows}


def get_session_report_version_detail(
    db: DbSession, principal: CurrentPrincipal, session_id: str, version_id: str
) -> dict[str, Any]:
    """One version's artifacts, session-shaped for a read-only preview.

    Returns the same fields ``restore_report_version`` copies onto a session (report prose/model + the
    artifact-class metadata). The user-state overlay is NOT included — it is applied client-side from the
    *live* session so user decisions are never time-traveled away (pipeline-versioning D2).
    """
    session = get_session_for_tenant(db, principal.tenant_id, parse_uuid(session_id, "session_id"))
    version = get_session_report_version(db, session, version_id)
    artifacts = version.artifacts if isinstance(version.artifacts, dict) else {}
    current_by_id, current_ooc = current_capture_index(db, session)
    removal = removal_target_for_version(current_by_id, current_ooc, version)
    current_version = find_report_version_for_current_set(db, session)
    return {
        "version": _version_meta(
            version,
            is_current=(current_version is not None and str(version.id) == str(current_version.id)),
            restorable=bool(removal),
        ),
        "report": {
            "summary": artifacts.get("summary"),
            "generatedSummary": artifacts.get("generated_summary"),
            "generatedReport": artifacts.get("generated_report"),
            "reportModel": artifacts.get("report_model"),
            "reportTemplateKey": artifacts.get("report_template_key"),
            "extractedMetadata": {key: artifacts.get(key) for key in _ARTIFACT_METADATA_KEYS if key in artifacts},
        },
    }
