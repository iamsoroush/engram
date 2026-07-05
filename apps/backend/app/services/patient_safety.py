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


def session_rejected_safety_flag_records(session: Session) -> list[dict[str, Any]]:
    """Rich rejection records ``[{key, kind, sourceCaptureIds, text}]`` maintained by the reject endpoint.

    Distinct from the plain ``rejected_safety_flags`` key list (which the frontend recomputes): these carry
    the rejected flag's kind + source captures so a rejection can follow the flag across a re-synthesis
    that rewords its text (S-F7) — a key alone can't, since the reworded text mints a new key.
    """
    raw = _session_metadata(session).get("rejected_safety_flag_records")
    return [record for record in raw if isinstance(record, dict) and isinstance(record.get("key"), str)] if isinstance(raw, list) else []


def carried_rejected_safety_flag_keys(session: Session) -> set[str]:
    """Rejected keys, augmented with reworded re-detections (S-F7).

    A rejection keyed on ``kind|normalized-text`` no longer matches after a re-synthesis reworded the
    flag, so the rejected wrong flag would reappear and re-sync onto the patient. For each rejection
    record whose exact key is no longer detected, a currently-detected flag of the SAME kind sharing a
    source capture is treated as the same (reworded) flag and its new key is added to the rejected set.
    """
    rejected = set(session_rejected_safety_flag_keys(session))
    detected = session_detected_safety_flags(session)
    detected_keys = {flag["key"] for flag in detected}
    for record in session_rejected_safety_flag_records(session):
        if record["key"] in detected_keys:
            continue  # exact key still detected — nothing to carry
        kind = record.get("kind")
        sources = {value for value in (record.get("sourceCaptureIds") or []) if isinstance(value, str)}
        if not sources:
            continue
        for flag in detected:
            if flag["key"] in rejected:
                continue
            if flag["kind"] == kind and sources & set(flag.get("sourceCaptureIds") or []):
                rejected.add(flag["key"])
    return rejected


def session_kept_safety_flags(session: Session) -> list[dict[str, Any]]:
    """Detected flags minus the rejected ones — what is shown and persisted to the patient.

    Rejections are matched tolerant of rewording (S-F7): a flag whose exact key was rejected OR that a
    prior rejection record re-identifies (same kind + shared source capture) is dropped.
    """
    rejected = carried_rejected_safety_flag_keys(session)
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

    Two safety guards are applied against the raw decisions here — the deterministic layer, resilient to
    a stale or cross-patient decision set (S-F6):

    * **Resolve every decision against THIS patient's actually-present flags.** The reconcile decisions
      were computed against the *then-assigned* patient's flags but can be re-applied later (cache-hit
      restore, completion after a mid-job reassignment) to a different patient. A duplicate/superseded
      whose ``ofKey`` is not a visible flag on this patient is downgraded to plain keep — never hide a
      flag whose twin isn't even here.
    * **Break duplicate cycles/chains.** ``{A: dup-of-B, B: dup-of-A}`` (or any mutual-duplicate group)
      would otherwise hide EVERY member and lose a distinct allergy. Each connected duplicate component
      keeps exactly one canonical flag visible (earliest-added, id-tiebroken); the rest collapse onto it.
      This preserves the "never lose a distinct flag" floor.
    """
    if not isinstance(decisions, dict):
        return
    raw = patient.safety_flags if isinstance(getattr(patient, "safety_flags", None), list) else []
    flags = [dict(flag) for flag in raw if isinstance(flag, dict)]
    # Deterministic canonical ordering per flag (earliest addedAt, then key).
    order = {flag.get("key"): (str(flag.get("addedAt") or ""), str(flag.get("key") or "")) for flag in flags}
    present = {key for key in order if key}

    # Union-find over duplicate edges among flags present on THIS patient; superseded stays directional.
    parent: dict[str, str] = {key: key for key in present}

    def _find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def _union(left: str, right: str) -> None:
        parent[_find(left)] = _find(right)

    superseded: dict[str, str | None] = {}
    for key in present:
        decision = decisions.get(key)
        if not isinstance(decision, dict):
            continue
        status = decision.get("status")
        of_key = decision.get("ofKey")
        resolves = of_key in present and of_key != key
        if status == "duplicate":
            # A duplicate HIDES its flag, so its ofKey must resolve to another visible flag on THIS
            # patient — else keep (never lose a distinct flag whose twin isn't here).
            if resolves:
                _union(key, of_key)
        elif status == "superseded":
            # A superseded flag stays VISIBLE and merely annotated, so it is safe to annotate even when
            # the ofKey doesn't resolve on this patient (a superseded ofKey may legitimately be None).
            superseded[key] = of_key if resolves else None

    # Canonical (kept-visible) flag per duplicate component = earliest-added, id-tiebroken.
    canonical: dict[str, str] = {}
    for key in present:
        root = _find(key)
        current = canonical.get(root)
        if current is None or order[key] < order[current]:
            canonical[root] = key

    updated: list[dict[str, Any]] = []
    for flag in flags:
        key = flag.get("key")
        root = _find(key) if key in parent else None
        canon = canonical.get(root) if root is not None else None
        if canon is not None and key != canon:
            flag["reconcileStatus"] = "duplicate"  # a real twin of the component's canonical (hidden)
            flag["reconcileOfKey"] = canon
        elif key in superseded:
            flag["reconcileStatus"] = "superseded"  # stays visible, annotated
            flag["reconcileOfKey"] = superseded[key]
        else:
            flag.pop("reconcileStatus", None)
            flag.pop("reconcileOfKey", None)
        updated.append(flag)
    patient.safety_flags = updated
