"""Mock patient-memory intelligence: a tier-aware patient *summary* (card) + *history* (detail).

This is a PLACEHOLDER for a future AI job — no real AI runs here. The flow it imitates:

1. A content change (a new/removed capture, an assignment) calls :func:`mark_patient_memory_updating`,
   which flips the patient's stored memory to ``updating`` and arms a ``ready_at`` a few seconds out
   (``MOCK_MEMORY_DELAY_SECONDS``) to imitate job latency. Prior finalized content stays visible.
2. The next read after ``ready_at`` calls :func:`finalize_patient_memory_if_due`, which writes the
   deterministic, tier-aware canned content and flips status back to ``ready``.

Tier shapes the *content*, never the tone:

* **Pro** reads as a synthesized, assistant-voiced brief (Snapshot / Story so far / Worth remembering
  / Right now). Source ``mock-ai``. The card summary is a warm one-liner.
* **Basic** reads as a faithful *structural* recap (visit counts, dates, capture types) — never a
  topic guessed from audio, because Basic has no summarization. Source ``mock-deterministic``.

The card ``summary`` is persisted (it powers the list + its updating lifecycle). The richer
``history`` is generated on read in the detail endpoint (one patient at a time), so it is never
stored. The frontend keeps showing prior content under an "Organizing memory" cue until status flips.

Language note: content is English for now. A future ``tenants.assistant_language`` axis (separate
from transcription/report language) will localize this; wiring that is deferred.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import AiJob, AiJobStatus, AiJobType, Patient, Session, Tenant

# Imitated AI-job latency. Short enough that the "updating → ready" transition is quick but visible,
# and lands within the frontend's processing-refresh poll ladder.
MOCK_MEMORY_DELAY_SECONDS = 4

MOCK_AI_SOURCE = "mock-ai"
MOCK_DETERMINISTIC_SOURCE = "mock-deterministic"

_TYPE_PHRASE = {
    "audio": "an audio note",
    "photo": "a photo",
    "note": "a written note",
}


# --------------------------------------------------------------------------- helpers


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _memory(patient: Patient) -> dict[str, Any] | None:
    return patient.memory if isinstance(patient.memory, dict) else None


def _session_sort_date(session: Session) -> datetime | None:
    return session.captured_at or session.updated_at or session.created_at


def _capture_count(session: Session) -> int:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    value = metadata.get("capture_count")
    return value if isinstance(value, int) and value >= 0 else 0


def _latest_type_phrase(session: Session) -> str:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    latest = metadata.get("latest_capture_type")
    return _TYPE_PHRASE.get(latest if isinstance(latest, str) else "", "a capture")


def _has_audio(session: Session) -> bool:
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    return metadata.get("latest_capture_type") == "audio"


def _fmt_date(value: datetime | None) -> str:
    if value is None:
        return "recently"
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return f"{value:%b} {value.day}"


def _fmt_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return f"{value:%H:%M}"


def _ordered(sessions: list[Session]) -> list[Session]:
    """Newest-first, by visit time."""
    return sorted(sessions, key=lambda s: _session_sort_date(s) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


# --------------------------------------------------------------------------- read helpers


def tenant_tier(db: DbSession, tenant_id: uuid.UUID) -> str:
    """Return the tenant's intelligence tier ('basic'|'pro'); memory artifacts are AI on Pro only."""
    tier = db.execute(select(Tenant.tier).where(Tenant.id == tenant_id)).scalar_one_or_none()
    return tier if tier in {"basic", "pro"} else "pro"


def memory_status(patient: Patient) -> str:
    mem = _memory(patient)
    return "updating" if mem and mem.get("status") == "updating" else "ready"


def persisted_summary(patient: Patient) -> str | None:
    mem = _memory(patient)
    if mem and isinstance(mem.get("summary"), str) and mem["summary"].strip():
        return mem["summary"].strip()
    return None


def memory_source(patient: Patient) -> str | None:
    mem = _memory(patient)
    return mem.get("source") if mem and isinstance(mem.get("source"), str) else None


def stored_history(patient: Patient) -> dict[str, Any] | None:
    """Return the patient's persisted history brief, if one has been generated."""
    mem = _memory(patient)
    if mem and isinstance(mem.get("history"), dict):
        return mem["history"]
    return None


def patient_has_active_memory_job(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Whether a patient_memory AI job is already queued/running for this patient (dedup guard)."""
    row = db.execute(
        select(AiJob.id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.patient_id == patient_id,
            AiJob.job_type == AiJobType.patient_memory,
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def patient_has_pending_capture_jobs(db: DbSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> bool:
    """Whether any of the patient's sessions still has a capture job in flight (report not settled)."""
    session_ids = [row[0] for row in db.execute(
        select(Session.id).where(Session.tenant_id == tenant_id, Session.patient_id == patient_id)
    ).all()]
    if not session_ids:
        return False
    row = db.execute(
        select(AiJob.id)
        .where(
            AiJob.tenant_id == tenant_id,
            AiJob.session_id.in_(session_ids),
            AiJob.capture_id.isnot(None),
            AiJob.status.in_([AiJobStatus.queued, AiJobStatus.running]),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def can_finalize_on_read(db: DbSession, *, tenant_id: uuid.UUID, patient: Patient, tier: str) -> bool:
    """Whether a read may deterministically finalize an `updating` memory.

    Basic always may (memory is deterministic). Pro normally waits for its AI job, so a read finalizes
    only when nothing is in flight (no memory job and no capture jobs) — a safety net so Pro memory is
    never permanently stuck in `updating` if a job failed terminally or was never dispatched.
    """
    if tier != "pro":
        return True
    return not patient_has_active_memory_job(db, tenant_id=tenant_id, patient_id=patient.id) and not patient_has_pending_capture_jobs(
        db, tenant_id=tenant_id, patient_id=patient.id
    )


def memory_updated_at(patient: Patient) -> str | None:
    mem = _memory(patient)
    return mem.get("updated_at") if mem and isinstance(mem.get("updated_at"), str) else None


# --------------------------------------------------------------------------- content generators


def generate_patient_memory(
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the deterministic, tier-aware canned memory for a patient.

    Returns ``{mode, summary, source, history}`` where ``history`` is
    ``{mode, snapshot, sections, visits, source}`` (Pro fills ``sections``; Basic fills ``visits``).
    """
    is_pro = tier == "pro"
    ordered = _ordered(sessions)
    count = len(ordered)
    latest = ordered[0] if ordered else None
    first = ordered[-1] if ordered else None
    # The patient's name is shown next to the card/avatar, so the copy never repeats it (redundant).
    visits_word = f"{count} visit" if count == 1 else f"{count} visits"

    if is_pro:
        content = _pro_content(count, visits_word, latest, first)
        source = MOCK_AI_SOURCE
    else:
        content = _basic_content(count, visits_word, latest, first, ordered)
        source = MOCK_DETERMINISTIC_SOURCE

    return {
        "mode": tier if is_pro else "basic",
        "summary": content["summary"],
        "source": source,
        "history": {
            "mode": "pro" if is_pro else "basic",
            "snapshot": content["snapshot"],
            "sections": content.get("sections", []),
            "visits": content.get("visits", []),
            "source": source,
        },
    }


def _pro_content(
    count: int,
    visits_word: str,
    latest: Session | None,
    first: Session | None,
) -> dict[str, Any]:
    if latest is None or first is None:
        return {
            "summary": "No visits have been captured yet.",
            "snapshot": "No visits captured yet.",
            "sections": [
                {"label": "Story so far", "body": "No visit has been captured yet."},
                {"label": "Worth remembering", "body": "Captures from the first visit will start building this history."},
                {"label": "Right now", "body": "Start a visit to begin building this memory."},
            ],
        }
    latest_date = _fmt_date(_session_sort_date(latest))
    first_date = _fmt_date(_session_sort_date(first))
    latest_phrase = _latest_type_phrase(latest)
    span = f"since {first_date}" if count > 1 else f"on {first_date}"
    summary = (
        f"{visits_word.capitalize()} on record, most recently {latest_phrase} on {latest_date} — "
        "all captured and organized."
    )
    if count > 1:
        story = (
            f"Memory spans {visits_word} {span}, each visit captured and folded in. The most recent, "
            f"on {latest_date}, came in as {latest_phrase} and has been saved."
        )
        remember = (
            "Visits have been regular, so continuity matters here — each builds on the last. "
            "I'll keep surfacing anything that needs your attention."
        )
    else:
        story = f"This memory starts with the visit on {first_date}, captured as {latest_phrase} and saved."
        remember = "This is an early record — the picture will fill in as more visits are captured."
    now_line = f"Everything from the {latest_date} visit is captured and organized for your review."
    return {
        "summary": summary,
        "snapshot": f"{visits_word.capitalize()} on record, most recently on {latest_date}.",
        "sections": [
            {"label": "Story so far", "body": story},
            {"label": "Worth remembering", "body": remember},
            {"label": "Right now", "body": now_line},
        ],
    }


def _basic_content(
    count: int,
    visits_word: str,
    latest: Session | None,
    first: Session | None,
    ordered: list[Session],
) -> dict[str, Any]:
    if latest is None or first is None:
        return {
            "summary": "No visits on record yet.",
            "snapshot": "No visits on record yet.",
            "visits": [],
        }
    latest_date = _fmt_date(_session_sort_date(latest))
    first_date = _fmt_date(_session_sort_date(first))
    latest_count = _capture_count(latest)
    latest_phrase = _latest_type_phrase(latest)
    if latest_count:
        capture_word = "capture" if latest_count == 1 else "captures"
        summary = (
            f"{visits_word.capitalize()} on record since {first_date}. Most recent on {latest_date}: "
            f"{latest_count} {capture_word} saved ({latest_phrase} most recent)."
        )
    else:
        summary = f"{visits_word.capitalize()} on record since {first_date}. Last seen {latest_date}."
    snapshot = f"{visits_word.capitalize()} on record, since {first_date}. Last seen {latest_date}."
    visits: list[str] = []
    for session in ordered[:6]:
        date_text = _fmt_date(_session_sort_date(session))
        time_text = _fmt_time(_session_sort_date(session))
        when = f"{date_text} · {time_text}" if time_text else date_text
        n = _capture_count(session)
        phrase = _latest_type_phrase(session)
        if n:
            capture_word = "capture" if n == 1 else "captures"
            line = f"{when} — {n} {capture_word} saved ({phrase} most recent)."
        else:
            line = f"{when} — visit saved."
        if _has_audio(session):
            line += " Transcript saved — open the visit to read it."
        visits.append(line)
    return {"summary": summary, "snapshot": snapshot, "visits": visits}


# --------------------------------------------------------------------------- lifecycle


def mark_patient_memory_updating(
    db: DbSession,
    patient_id: uuid.UUID | None,
    *,
    now: datetime | None = None,
) -> None:
    """Flag a patient's memory as refreshing after a content change.

    Keeps any prior finalized content visible; only flips status + arms ``ready_at``. Cheap and
    idempotent. The caller is responsible for committing.
    """
    if patient_id is None:
        return
    patient = db.get(Patient, patient_id)
    if patient is None:
        return
    moment = now or _now()
    mem = _memory(patient) or {}
    patient.memory = {
        **mem,
        "status": "updating",
        "updating_since": _iso(moment),
        "ready_at": _iso(moment + timedelta(seconds=MOCK_MEMORY_DELAY_SECONDS)),
    }


def finalize_patient_memory_if_due(
    db: DbSession,
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    now: datetime | None = None,
) -> bool:
    """If memory is ``updating`` and past its imitated latency, write canned content and flip to
    ``ready``. Returns True when it changed (caller should ensure the unit of work commits)."""
    mem = _memory(patient)
    if not mem or mem.get("status") != "updating":
        return False
    moment = now or _now()
    ready_at = _parse_iso(mem.get("ready_at"))
    if ready_at is not None and moment < ready_at:
        return False
    content = generate_patient_memory(patient, sessions, tier, now=moment)
    patient.memory = {
        "status": "ready",
        "mode": content["mode"],
        "summary": content["summary"],
        "history": content["history"],
        "source": content["source"],
        "updated_at": _iso(moment),
    }
    return True


# --------------------------------------------------------------------------- real AI job (Pro)


def _session_brief(session: Session) -> dict[str, Any]:
    """A compact, distilled per-visit brief fed to the patient-memory model (not raw transcripts)."""
    metadata = session.extracted_metadata if isinstance(session.extracted_metadata, dict) else {}
    summaries = metadata.get("summaries") if isinstance(metadata.get("summaries"), dict) else {}
    summary = session.generated_summary or session.summary or summaries.get("short")
    return {
        "date": _iso(_session_sort_date(session)),
        "captureCount": _capture_count(session),
        "latestType": metadata.get("latest_capture_type") if isinstance(metadata.get("latest_capture_type"), str) else None,
        "summary": summary.strip() if isinstance(summary, str) and summary.strip() else None,
    }


def build_patient_memory_job_input(
    patient: Patient,
    sessions: list[Session],
    tier: str,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """Build the worker payload for the combined patient-memory job.

    Incremental by design: the model gets the **prior** memory plus compact per-visit briefs (the
    session stage already distilled these), not raw transcripts — so cost stays ~flat as visits
    grow. A `deterministicFallback` is included so a gateway-less worker still returns valid content.
    """
    ordered = _ordered(sessions)
    prior = _memory(patient)
    prior_brief = None
    if prior and (prior.get("summary") or prior.get("history")):
        prior_brief = {"summary": prior.get("summary"), "history": prior.get("history")}
    fallback = generate_patient_memory(patient, sessions, tier)
    return {
        "tier": tier,
        "language": language,
        "patient": {
            "displayName": patient.display_name,
            "visitCount": len(ordered),
            "firstSeen": _iso(_session_sort_date(ordered[-1])) if ordered else None,
            "priorMemory": prior_brief,
            "sessions": [_session_brief(session) for session in ordered[:8]],
        },
        "deterministicFallback": {
            "summary": fallback["summary"],
            "history": fallback["history"],
            "source": fallback["source"],
        },
    }


def _coerce_history(history: Any, tier: str) -> dict[str, Any]:
    """Normalize a (possibly model-authored) history object into the stable stored shape."""
    history = history if isinstance(history, dict) else {}
    sections = [
        {"label": str(section.get("label", "")), "body": str(section.get("body", ""))}
        for section in (history.get("sections") if isinstance(history.get("sections"), list) else [])
        if isinstance(section, dict) and section.get("body")
    ]
    visits = [str(visit) for visit in (history.get("visits") if isinstance(history.get("visits"), list) else []) if isinstance(visit, str)]
    return {
        "mode": "pro" if tier == "pro" else "basic",
        "snapshot": str(history.get("snapshot", "")),
        "sections": sections,
        "visits": visits,
        "source": str(history.get("source", "")) or (MOCK_AI_SOURCE if tier == "pro" else MOCK_DETERMINISTIC_SOURCE),
    }


def apply_patient_memory_output(
    patient: Patient,
    output: dict[str, Any],
    tier: str,
    *,
    now: datetime | None = None,
) -> None:
    """Write a completed patient-memory job's output onto the patient (status → ready)."""
    moment = now or _now()
    summary = output.get("summary")
    history = output.get("history")
    source = output.get("source") if isinstance(output.get("source"), str) and output.get("source") else None
    if not isinstance(summary, str) or not summary.strip() or not isinstance(history, dict):
        # Defensive: the worker is expected to fall back to deterministic content, but guard anyway.
        fallback = generate_patient_memory(patient, [], tier, now=moment)
        summary, history, source = fallback["summary"], fallback["history"], fallback["source"]
    patient.memory = {
        "status": "ready",
        "mode": "pro" if tier == "pro" else "basic",
        "summary": summary.strip(),
        "history": _coerce_history(history, tier),
        "source": source or (MOCK_AI_SOURCE if tier == "pro" else MOCK_DETERMINISTIC_SOURCE),
        "updated_at": _iso(moment),
    }
