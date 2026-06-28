"""Session-level safety flags → cross-visit patient safety store.

The Pro session synthesis detects clinical SAFETY FLAGS (allergy / contraindication / consent) from
a visit's captures and rides them into ``session.extracted_metadata["safety_flags"]`` (see
``ai_engine`` synthesis). They are **opt-out**: every detected flag is auto-kept and the clinician
only acts to reject a wrong one (``extracted_metadata["rejected_safety_flags"]`` holds the rejected
keys). The non-rejected flags are persisted onto the **patient** (``Patient.safety_flags``) so they
surface at every future visit's point of care.

This module is the single source of truth for:

* the **stable key** of a flag (``safety_flag_key``) — recomputed identically on the frontend, so a
  rejection round-trips without a server-assigned id;
* the visit's **kept** flags (detected minus rejected);
* the **sync** that re-projects one session's kept flags onto the patient store (used by both the
  rejection endpoint and the synthesis worker, so the two never drift), idempotent per session.

Clinical ``text`` is in the report language and is NEVER translated — only the surrounding chrome is.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import Patient, Session

SAFETY_FLAG_KINDS: frozenset[str] = frozenset({"allergy", "contraindication", "consent"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    """Whitespace/case-fold a flag's text for keying. Mirrors the frontend ``safetyFlagKey``."""
    return " ".join(text.strip().lower().split())


def safety_flag_key(kind: str, text: str) -> str:
    """Stable key for a flag: ``"<kind>|<normalized text>"``. Identical to the frontend derivation."""
    return f"{kind}|{_normalize_text(text)}"


def _session_metadata(session: Session) -> dict[str, Any]:
    return session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}


def session_detected_safety_flags(session: Session) -> list[dict[str, Any]]:
    """The synthesis's raw safety flags for this visit (validated), each with its stable ``key``."""
    raw = _session_metadata(session).get("safety_flags")
    flags: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        text = item.get("text")
        if kind not in SAFETY_FLAG_KINDS or not (isinstance(text, str) and text.strip()):
            continue
        source_ids = item.get("sourceCaptureIds")
        flags.append(
            {
                "key": safety_flag_key(kind, text),
                "kind": kind,
                "text": text.strip(),
                "sourceCaptureIds": [str(value) for value in source_ids if isinstance(value, str)]
                if isinstance(source_ids, list)
                else [],
            }
        )
    return flags


def session_rejected_safety_flag_keys(session: Session) -> list[str]:
    """The keys of safety flags the clinician rejected on this visit (user state, opt-out)."""
    raw = _session_metadata(session).get("rejected_safety_flags")
    return [str(value) for value in raw if isinstance(value, str)] if isinstance(raw, list) else []


def session_kept_safety_flags(session: Session) -> list[dict[str, Any]]:
    """Detected flags minus the rejected ones — what is shown and persisted to the patient."""
    rejected = set(session_rejected_safety_flag_keys(session))
    return [flag for flag in session_detected_safety_flags(session) if flag["key"] not in rejected]


def patient_safety_flags(patient: Patient) -> list[dict[str, Any]]:
    """Coerce the patient's stored safety flags (None/garbage → [])."""
    raw = getattr(patient, "safety_flags", None)
    flags: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("kind") in SAFETY_FLAG_KINDS and isinstance(item.get("text"), str):
            flags.append(item)
    return flags


def sync_patient_safety_flags(patient: Patient, session: Session) -> None:
    """Re-project ONE session's kept safety flags onto the patient store (idempotent per session).

    Each stored entry records its ``sourceSessionId`` so re-running this for a session replaces only
    that session's contribution (a re-synthesis or a rejection updates the visit's set; other visits'
    flags are untouched). The patient mutation is staged on the ORM object; the caller commits.
    """
    session_id = str(session.id)
    others = [flag for flag in patient_safety_flags(patient) if flag.get("sourceSessionId") != session_id]
    added_at = _now_iso()
    current = [
        {
            "key": flag["key"],
            "kind": flag["kind"],
            "text": flag["text"],
            "sourceSessionId": session_id,
            "sourceCaptureIds": flag["sourceCaptureIds"],
            "addedAt": added_at,
        }
        for flag in session_kept_safety_flags(session)
    ]
    patient.safety_flags = others + current


def drop_session_safety_flags(patient: Patient, session_id: Any) -> None:
    """Remove one session's contribution from the patient store (on reassignment/unassignment).

    The patient mutation is staged on the ORM object; the caller commits.
    """
    session_id = str(session_id)
    patient.safety_flags = [flag for flag in patient_safety_flags(patient) if flag.get("sourceSessionId") != session_id]


def patient_safety_flags_payload(patient: Patient, *, exclude_session_id: Any = None) -> list[dict[str, Any]]:
    """Deduped, glanceable patient safety flags for the session-context card + timeline.

    Deduped by stable key (the first occurrence wins, keeping its provenance); clinical ``text`` is
    returned verbatim in the report language. Shape: ``[{key, kind, text}]``.

    ``exclude_session_id`` drops flags contributed by that session — passed for the active session's
    context card so a flag detected THIS visit (already shown in the opt-out "this visit" panel) is not
    also repeated here as cross-visit history; the card then carries only PRIOR visits' flags.
    """
    exclude = str(exclude_session_id) if exclude_session_id is not None else None
    seen: set[str] = set()
    payload: list[dict[str, Any]] = []
    for flag in patient_safety_flags(patient):
        if exclude is not None and flag.get("sourceSessionId") == exclude:
            continue
        # Apply the cross-visit reconcile (D7): a meaning-duplicate is collapsed (hidden — its canonical
        # twin is kept); a superseded flag is annotated, never dropped (safety errs to inclusion).
        if flag.get("reconcileStatus") == "duplicate":
            continue
        key = flag.get("key") or safety_flag_key(str(flag.get("kind")), str(flag.get("text")))
        if key in seen:
            continue
        seen.add(key)
        entry = {"key": key, "kind": flag["kind"], "text": flag["text"]}
        if flag.get("reconcileStatus") == "superseded":
            entry["superseded"] = True
        payload.append(entry)
    return payload


def apply_safety_reconciliation(patient: Patient, decisions: Any) -> None:
    """Annotate the patient's safety flags with the reconcile job's decisions (status + ofKey).

    ``decisions`` is ``{key: {status, ofKey}}`` from the selection-only reconcile. Idempotent: a flag
    not marked duplicate/superseded is reset to plain keep. Never removes a flag (the union is the
    deterministic floor); the payload merely hides meaning-duplicates + annotates supersedes. Staged on
    the patient; the caller commits.
    """
    if not isinstance(decisions, dict):
        return
    raw = patient.safety_flags if isinstance(getattr(patient, "safety_flags", None), list) else []
    updated: list[dict[str, Any]] = []
    for flag in raw:
        if not isinstance(flag, dict):
            continue
        flag = dict(flag)
        decision = decisions.get(flag.get("key"))
        status = decision.get("status") if isinstance(decision, dict) else None
        if status in {"duplicate", "superseded"}:
            flag["reconcileStatus"] = status
            flag["reconcileOfKey"] = decision.get("ofKey")
        else:
            flag.pop("reconcileStatus", None)
            flag.pop("reconcileOfKey", None)
        updated.append(flag)
    patient.safety_flags = updated
