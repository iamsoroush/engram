"""Correction-triggered synthesis escalation (escalation-tier decision — see docs/technical-decisions.md; deferred from Wave 2).

A **user correction is proof the cheap model tier failed on this input**, so the next re-synthesis of
that session should run on the strongest configured tier. The three correction signals — an explicit
assignment correction, a fix-at-source transcript/caption edit, and a treatment-overlay field edit —
set a pending marker on the session; the next ``session_organize`` dispatch pops it and stamps
``escalate: true`` on the job (``worker_job_payload`` → payload), which the worker already resolves
(``core.structured.escalation_requested``).

Decoupling "which correction" from "when synthesis runs" via a marker is deliberate: some corrections
re-dispatch synthesis inline (fix-at-source, force), others only mark the session stale and rely on the
background sweep, and a treatment-overlay edit runs no synthesis at all (it is instant/deterministic) —
so its escalation must wait for the NEXT capture-triggered synthesis. A single pending flag serves all
three uniformly. The marker is a transient control field (not user-state overlay, not an AI artifact),
cleared on consumption.
"""
from __future__ import annotations

from typing import Any

from app.models import Session

SYNTHESIS_ESCALATE_KEY = "synthesis_escalate_pending"


def _metadata(session: Session) -> dict[str, Any]:
    current = getattr(session, "extracted_metadata", None)
    return dict(current) if isinstance(current, dict) else {}


def mark_synthesis_escalation(session: Session) -> None:
    """Flag that the session's NEXT synthesis should escalate (a user correction proved a miss).

    Idempotent; staged on the ORM object (the caller commits). Safe to call on any session — the flag
    only matters if/when a synthesis dispatches.
    """
    metadata = _metadata(session)
    metadata[SYNTHESIS_ESCALATE_KEY] = True
    session.extracted_metadata = metadata


def pop_synthesis_escalation(session: Session) -> bool:
    """Read AND clear the pending-escalation flag; return whether it was set (consumed at dispatch)."""
    metadata = _metadata(session)
    pending = metadata.pop(SYNTHESIS_ESCALATE_KEY, None) is True
    if pending:
        session.extracted_metadata = metadata
    return pending
